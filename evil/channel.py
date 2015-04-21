import qtzmq
import msgpack
import zmq

from PyQt5 import QtCore as QtC

MSGPACKRPC_REQUEST = 0
MSGPACKRPC_RESPONSE = 1
MSGPACKRPC_NOTIFICATION = 2

class Channel(QtC.QObject):
    connection_ready = QtC.pyqtSignal()
    shutting_down = QtC.pyqtSignal()

    def __init__(self, zmq_ctx, host_addr, resource):
        QtC.QObject.__init__(self)

        self.resource = resource

        self._zmq_ctx = zmq_ctx
        self._host_addr = host_addr

        QtC.qDebug("Connecting to {}".format(resource))

        self._rpc_socket = qtzmq.Socket(zmq_ctx, zmq.REQ)
        self._rpc_socket.received_msg.connect(lambda m: print(m))
        self._rpc_socket.error.connect(self.socket_error)
        self._rpc_socket.connect(self._remote_endpoint(resource.port))

        self._send_rpc_request("notificationPort", [], self._got_notification_port)

        self._active_streaming_sockets = []

        self._control_panel = None

    def show_control_panel(self):
        if self._control_panel:
            self._control_panel.activateWindow()
        else:
            # self._control_panel = ControlPanel()
            QtC.qDebug('Creating Control Panel')

    def _got_notification_port(self, port):
        QtC.qDebug('Notification port: {}'.format(port))
        self._notification_socket = qtzmq.Socket(self._zmq_ctx, zmq.SUB)
        self._notification_socket.error.connect(self.socket_error)
        self._notification_socket.connect(self._remote_endpoint(port))
        self._notification_socket.received_msg.connect(self._handle_notification)

        self._send_rpc_request('streamingPorts', [], self._got_streaming_ports)

    def _got_streaming_ports(self, ports):
        QtC.qDebug('Streaming ports: {}'.format(ports))
        self._streaming_ports = ports
        self.connection_ready.emit()

    def _handle_notification(self, msg):
        try:
            msg_type, method, params = msgpack.unpackb(msg, encoding='utf-8')
            if msg_type != MSGPACKRPC_NOTIFICATION:
                self._rpc_error('Expected msgpack-rpc notification, but got: ' + type)
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
            self._rpc_socket(e)

    def _send_rpc_request(self, method, args, response_handler):
        # We do not use the sequence id, just pass zero.
        request = msgpack.packb((MSGPACKRPC_REQUEST, 0, method, args))
        def handler(response):
            try:
                msg_type, seq_id, err, ret_val = msgpack.unpackb(response, encoding='utf-8')
                if msg_type != MSGPACKRPC_RESPONSE:
                    self._rpc_error('Unexpected msgpack-rpc message type: {}'.format(type))
                    return
                if err:
                    self._rpc_error(err)
                    return
                response_handler(ret_val)
            except Exception as e:
                self._rpc_error(e)
        self._rpc_socket.request(request, handler)

    def socket_error(self, err):
        # TODO: Close and unregister device.
        QtC.qWarning('Socket error: {}'.format(err))

    def _rpc_error(self, err):
        # TODO: Close and unregister device.
        QtC.qWarning('RPC error: {}'.format(err))

    def _remote_endpoint(self, port):
        return 'tcp://{}:{}'.format(self._host_addr.toString(), port)
