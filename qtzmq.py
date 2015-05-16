import zmq

from PyQt4 import QtCore as QtC


class Socket(QtC.QObject):
    received_msg = QtC.pyqtSignal(bytes)
    error = QtC.pyqtSignal(zmq.ZMQError)

    def __init__(self, ctx, sock_type):
        QtC.QObject.__init__(self)

        self._socket = ctx.socket(sock_type)

        # Do not try to reconnect. In our application, we expect services to
        # suddenly disappear if the physical device is unplugged. Reconnection
        # is handled via rediscovery on the application layer.
        self._socket.setsockopt(zmq.RECONNECT_IVL, -1)

        if sock_type == zmq.SUB:
            # By default, subscribe to everything.
            self._socket.setsockopt(zmq.SUBSCRIBE, b'')

        fd = self._socket.getsockopt(zmq.FD)
        self._notifier = QtC.QSocketNotifier(fd, QtC.QSocketNotifier.Read, self)
        self._notifier.activated.connect(self._might_have_data)

        self._response_handler = None
        self._closed = False

    def connect(self, addrspec):
        self._socket.connect(addrspec)

    def send(self, msg):
        assert not self._closed
        return self._socket.send(msg)

    def request(self, msg, response_handler):
        assert not self._closed

        self._response_handler = response_handler
        return self.send(msg)

    def close(self):
        assert not self._closed
        self._closed = True

        self._notifier.setEnabled(False)
        self._socket.close()

    def _might_have_data(self):
        try:
            # At least for SUB sockets, we need to try to receive more messages
            # even if there aren't any for the socket notifier to work
            # correctly. Do not continue to try to read if the socket has been
            # closed in the response handler to not signal spurious errors.
            while not self._closed:
                msg = self._socket.recv(flags=zmq.NOBLOCK)
                if self._response_handler:
                    handler = self._response_handler
                    self._response_handler = None
                    handler(msg)
                else:
                    self.received_msg.emit(msg)
        except zmq.ZMQError as e:
            # EAGAIN == would have blocked
            # EFSM == can't send/receive right now due to the protocol ordering
            # constraints
            if e.errno not in (zmq.EAGAIN, zmq.EFSM):
                self._response_handler = None
                self.error.emit(e)
