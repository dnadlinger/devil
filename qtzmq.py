import zmq

from PyQt5 import QtCore as QtC


class Socket(QtC.QObject):
    received_msg = QtC.pyqtSignal(bytes)
    error = QtC.pyqtSignal(zmq.ZMQError)

    def __init__(self, ctx, sock_type):
        QtC.QObject.__init__(self)

        self._socket = ctx.socket(sock_type)

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

    def _might_have_data(self):
        try:
            # TODO: Do we need to try and receive multiple messages here to
            # make sure wo do not miss any (if QSocketNotifier is strictly
            # edge-triggered w.r.t. some internal buffer in the event loop)?
            # On the other hand, for some 0MQ socket types like REQ/REP this
            # breaks the protocol if we have not sent another message in the
            # response handler.
            msg = self._socket.recv(flags=zmq.NOBLOCK)
            if self._response_handler:
                handler = self._response_handler
                self._response_handler = None
                handler(msg)
            else:
                self.received_msg.emit(msg)
        except zmq.ZMQError as e:
            if e.errno != zmq.EAGAIN:
                self._response_handler = None
                self.error.emit(e)
