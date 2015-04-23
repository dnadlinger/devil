import qtzmq
import msgpack
import zmq

from PyQt5 import QtCore as QtC

MSGPACKRPC_REQUEST = 0
MSGPACKRPC_RESPONSE = 1
MSGPACKRPC_NOTIFICATION = 2


class Register(QtC.QObject):
    changed_locally = QtC.pyqtSignal(int, int)
    changed_remotely = QtC.pyqtSignal(int)
    desynchronized = QtC.pyqtSignal()

    def __init__(self, idx, is_signed = False):
        QtC.QObject.__init__(self)

        self.idx = idx
        self._is_signed = is_signed
        self._remote_updates_to_ignore = []
        self._uval = 0
        self._synchronized = False

    @property
    def sval(self):
        return self._from_unsigned(self._uval)

    def set_from_local_change(self, new_sval):
        new_uval = self._to_unsigned(new_sval)

        if not self._synchronized:
            return

        if self._uval == new_uval:
            return

        old_uval = self._uval
        self._uval = new_uval
        self._remote_updates_to_ignore.append(new_uval)
        self.changed_locally.emit(old_uval, new_uval)

    def set_from_remote_notification(self, new_uval):
        if not self._synchronized:
            return
        try:
            i = self._remote_updates_to_ignore.index(new_uval)
            self._remote_updates_to_ignore = self._remote_updates_to_ignore[i + 1:]
        except ValueError:
            self._remote_updates_to_ignore.clear()
            if new_uval != self._uval:
                self._uval = new_uval
                self.changed_remotely.emit(self.sval)

    def set_from_remote_query(self, new_uval):
        self._uval = new_uval
        self._synchronized = True
        self.changed_remotely.emit(self.sval)

    def mark_as_desynchronized(self):
        self._synchronized = False
        self.desynchronized.emit()

    def _from_unsigned(self, uval):
        if self._is_signed and uval >= 2**15:
            return uval - 2 ** 16
        return uval

    def _to_unsigned(self, sval):
        if self._is_signed and sval < 0:
            return sval + 2 ** 16
        return sval


class Channel(QtC.QObject):
    connection_ready = QtC.pyqtSignal()
    shutting_down = QtC.pyqtSignal()
    streaming_params_changed = QtC.pyqtSignal()  # FIXME: Parameter type

    def __init__(self, zmq_ctx, host_addr, resource):
        QtC.QObject.__init__(self)

        self.resource = resource

        self._zmq_ctx = zmq_ctx
        self._host_addr = host_addr
        self._pending_rpc_request = None
        self._rpc_request_queue = []
        self._active_streaming_sockets = []

        self._reg_idx_to_object = {}
        self._control_panel = None

        self._rpc_socket = qtzmq.Socket(zmq_ctx, zmq.REQ)
        self._rpc_socket.received_msg.connect(
            lambda m: QtC.qCritical('Unhandled message on RPC socket: {}'.format(m)))
        self._rpc_socket.error.connect(self._socket_error)
        self._rpc_socket.connect(self._remote_endpoint(resource.port))

        self._invoke_rpc('notificationPort', [], self._got_notification_port)

    def show_control_panel(self):
        if self._control_panel:
            self._control_panel.activateWindow()
        else:
            self._control_panel = self._create_control_panel()
            self._control_panel.show()

    def _set_stream_acquisition_config(self, time_span_seconds, points):
        self._invoke_rpc('setStreamAcquisitionConfig', [time_span_seconds, points])

    def _modify_register(self, reg_idx, old_val, new_val):
        self._invoke_rpc('modifyRegister', [reg_idx, old_val, new_val],
                         lambda succeeded: succeeded or self._register_conflict(reg_idx))

    def _registers(self):
        return []

    def _create_control_panel(self):
        raise NotImplementedError('Need to implement control panel for specific EVIL version')

    def _register_conflict(self, reg_idx):
        self._reg_idx_to_object[reg_idx].mark_as_desynchronized()
        self._read_registers([reg_idx])

    def _got_notification_port(self, port):
        self._notification_socket = qtzmq.Socket(self._zmq_ctx, zmq.SUB)
        self._notification_socket.error.connect(self._socket_error)
        self._notification_socket.connect(self._remote_endpoint(port))
        self._notification_socket.received_msg.connect(self._handle_notification)

        self._invoke_rpc('streamPorts', [], self._got_stream_ports)

    def _got_stream_ports(self, ports):
        self._streaming_ports = ports

        # Initialize registers.
        regs = self._registers()
        for r in regs:
            self._reg_idx_to_object[r.idx] = r
            r.changed_locally.connect(lambda old_val, new_val, idx=r.idx:
                                      self._modify_register(idx, old_val, new_val))

        self._read_registers([r.idx for r in regs], self.connection_ready.emit)

    def _read_registers(self, registers, completion_handler=None):
        if not registers:
            if completion_handler:
                completion_handler()
            return

        idx = registers.pop(0)

        def handle(val):
            self._reg_idx_to_object[idx].set_from_remote_query(val)
            self._read_registers(registers, completion_handler)

        self._invoke_rpc('readRegister', [idx], handle)

    def _handle_notification(self, msg):
        try:
            msg_type, method, params = msgpack.unpackb(msg, encoding='utf-8')
            if msg_type != MSGPACKRPC_NOTIFICATION:
                self._rpc_error('Expected msgpack-rpc notification, but got: ' + type)
                return

            if method == 'registerChanged':
                idx, value = params
                self._reg_idx_to_object[idx].set_from_remote_notification(value)
                return

            if method == 'shutdown':
                self._rpc_socket.close()
                self._notification_socket.close()
                for s in self._active_streaming_sockets:
                    s.close()
                self.shutting_down.emit()
                return

            QtC.qWarning('Received unknown notification type: {}{}'.format(method, params))

        except Exception as e:
            self._socket_error(e)

    def _invoke_rpc(self, method, args, response_handler = None):
        # We do not use the sequence id, just pass zero.
        request = msgpack.packb((MSGPACKRPC_REQUEST, 0, method, args))

        self._rpc_request_queue.append((request, response_handler))
        if not self._pending_rpc_request:
            self._send_next_rpc_request()

    def _rpc_response_handler(self, response):
        try:
            msg_type, seq_id, err, ret_val = msgpack.unpackb(response, encoding='utf-8')
            if msg_type != MSGPACKRPC_RESPONSE:
                self._rpc_error('Unexpected msgpack-rpc message type: {}'.format(msg_type))
            elif err:
                self._rpc_error(err)
            else:
                _, response_handler = self._pending_rpc_request
                if response_handler:
                    response_handler(ret_val)

            self._pending_rpc_request = None
            if self._rpc_request_queue:
                self._send_next_rpc_request()
        except Exception as e:
            self._rpc_error(e)

    def _send_next_rpc_request(self):
        self._pending_rpc_request = self._rpc_request_queue.pop(0)
        self._rpc_socket.request(self._pending_rpc_request[0],
                                 self._rpc_response_handler)

    def _socket_error(self, err):
        # TODO: Close and unregister device.
        QtC.qWarning('Socket error: {}'.format(err))

    def _rpc_error(self, err):
        # TODO: Close and unregister device.
        QtC.qWarning('RPC error: {}'.format(err))

    def _remote_endpoint(self, port):
        return 'tcp://{}:{}'.format(self._host_addr.toString(), port)