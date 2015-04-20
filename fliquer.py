import msgpack
import sys
import socket

from PyQt5 import QtCore as QtC
from PyQt5 import QtNetwork as QtN

MSGPACKRPC_NOTIFICATION = 2


class SemVer:
    def __init__(self, major, minor, patch, pre_release, build_metadata):
        self.major = major
        self.minor = minor
        self.patch = patch
        self.pre_release = pre_release.decode('utf-8')
        self.build_metadata = build_metadata.decode('utf-8')

    def __str__(self):
        res = "{}.{}.{}".format(self.major, self.minor, self.patch)

        if self.pre_release:
            res += "-"
            res += self.pre_release

        if self.build_metadata:
            res += "+"
            res += self.build_metadata

        return res


class Resource:
    def __init__(self, type, id, display_name, version, port):
        self.type = type
        self.id = id
        self.display_name = display_name
        self.version = version
        self.port = port

    def __str__(self):
        return '{} {} {} "{}, port {}'.format(self.type, self.version, self.id,
                                              self.display_name, self.port)

    @staticmethod
    def from_msgpack(type, id, display_name, version, port):
        return Resource(type.decode('utf-8'), id.decode('utf-8'),
                        display_name.decode('utf-8'), SemVer(*version), port)


class Node(QtC.QObject):
    """
    Fliquer resource discovery protocol node

    Client-only for now.
    """

    new_remote_resource = QtC.pyqtSignal(QtN.QHostAddress, Resource)

    def __init__(self, port=8474):
        QtC.QObject.__init__(self)

        self.port = port

        # We directly create
        native_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        native_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        native_sock.bind(('0.0.0.0', port))

        self.socket = QtN.QUdpSocket()
        self.socket.setSocketDescriptor(native_sock.detach(), QtN.QUdpSocket.BoundState)
        self.socket.readyRead.connect(self.read_packet)

        self.broadcast_enumeration_request()

    def read_packet(self):
        while self.socket.hasPendingDatagrams():
            size = self.socket.pendingDatagramSize()
            data, host, port = self.socket.readDatagram(size)

            try:
                msg = msgpack.unpackb(data)
                type, method, args = msg

                if type != MSGPACKRPC_NOTIFICATION:
                    self._debug('Invalid message type')
                    continue

                if method == b'enumerate':
                    # For now, we are client-only, ignore.
                    continue

                if method == b'resources':
                    for resource in args:
                        r = Resource.from_msgpack(*resource)
                        r = Resource.from_msgpack(*resource)
                        self.new_remote_resource.emit(host, r)
                    continue

                self._debug('Unknown method in message: {}', method)
            except:
                self._debug('Received invalid UDP packet from {}:{}', host, port)
                continue

    def broadcast_enumeration_request(self):
        msg = msgpack.packb((MSGPACKRPC_NOTIFICATION, 'enumerate', ()))
        self.socket.writeDatagram(msg, QtN.QHostAddress.Broadcast, self.port)

    def _debug(self, fmt, *args):
        QtC.qDebug('[fliquer.Node] ' + fmt.format(*args))


if __name__ == '__main__':
    app = QtC.QCoreApplication(sys.argv)
    node = Node()
    node.new_remote_resource.connect(lambda h, r: print(r))
    sys.exit(app.exec_())
