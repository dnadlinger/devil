import zmq

from PyQt4 import QtCore as QtC


class Socket(QtC.QObject):
    received_msg = QtC.pyqtSignal(bytes)
    error = QtC.pyqtSignal(zmq.ZMQError)

    def __init__(self, ctx, sock_type):
        QtC.QObject.__init__(self)

        self._socket = ctx.socket(sock_type)

        if sock_type == zmq.SUB:
            # By default, subscribe to everything.
            self._socket.setsockopt(zmq.SUBSCRIBE, b'')

        fd = self._socket.getsockopt(zmq.FD)
        self._notifier = QtC.QSocketNotifier(fd, QtC.QSocketNotifier.Read, self)
        self._notifier.activated.connect(self._might_have_data)

        self._response_handler = None

    def connect(self, addrspec):
        self._socket.connect(addrspec)

    def send(self, msg):
        return self._socket.send(msg)

    def request(self, msg, response_handler):
        self._response_handler = response_handler
        return self.send(msg)

    def close(self):
        self._notifier.setEnabled(False)
        self._socket.close()

    def _might_have_data(self):
        try:
            # At least for SUB sockets, we need to try to receive more messages
            # even if there aren't any for the socket notifier to work
            # correctly.
            while True:
                msg = self._socket.recv(flags=zmq.NOBLOCK)
                if self._response_handler:
                    handler = self._response_handler
                    self._response_handler = None
                    handler(msg)
                else:
                    self.received_msg.emit(msg)
        except zmq.ZMQError as e:
            # EAGAIN == would have blocked
            # EFSM == can't send/receive due to the protocol state machine
            if e.errno not in (zmq.EAGAIN, zmq.EFSM):
                self._response_handler = None
                self.error.emit(e)
