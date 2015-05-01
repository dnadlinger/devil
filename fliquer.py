import msgpack
import socket

from PyQt4 import QtCore as QtC
from PyQt4 import QtNetwork as QtN

MSGPACKRPC_NOTIFICATION = 2


class SemVer:
    def __init__(self, major, minor, patch, pre_release, build_metadata):
        self.major = major
        self.minor = minor
        self.patch = patch
        self.pre_release = pre_release
        self.build_metadata = build_metadata

    def __str__(self):
        res = '{}.{}.{}'.format(self.major, self.minor, self.patch)

        if self.pre_release:
            res += '-'
            res += self.pre_release

        if self.build_metadata:
            res += '+'
            res += self.build_metadata

        return res


class Resource:
    def __init__(self, dev_type, dev_id, display_name, version, port):
        self.dev_type = dev_type
        self.dev_id = dev_id
        self.display_name = display_name
        self.version = version
        self.port = port

    def __str__(self):
        return '{} {} {} "{}", port {}'.format(self.dev_type, self.version, self.dev_id,
                                               self.display_name, self.port)


def resource_from_tuple(dev_type, dev_id, display_name, version, port,
                        *ignore_reserved):
    return Resource(dev_type, dev_id, display_name, SemVer(*version), port)


class Node(QtC.QObject):
    """
    Fliquer resource discovery protocol node

    Client-only for now.
    """

    new_remote_resource = QtC.pyqtSignal(QtN.QHostAddress, Resource)

    def __init__(self, port=8474):
        QtC.QObject.__init__(self)

        self.port = port

        # We create a low-level socket ourselves because setting SO_REUSEADDR
        # via the QUdpSocket bind options does not seem to work on PyQt 5.4.1.
        native_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        native_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        native_sock.bind(('0.0.0.0', port))

        self._socket = QtN.QUdpSocket()
        self._socket.setSocketDescriptor(native_sock.detach(), QtN.QUdpSocket.BoundState)
        self._socket.readyRead.connect(self._read_packet)

        self.broadcast_enumeration_request()

    def broadcast_enumeration_request(self):
        msg = msgpack.packb((MSGPACKRPC_NOTIFICATION, 'enumerate', ()))

        for interface in QtN.QNetworkInterface.allInterfaces():
            if not interface.flags() & QtN.QNetworkInterface.CanBroadcast:
                continue
            for address_entry in interface.addressEntries():
                broadcast = address_entry.broadcast()
                if not broadcast.isNull():
                    self._socket.writeDatagram(msg, broadcast, self.port)

    def _read_packet(self):
        while self._socket.hasPendingDatagrams():
            size = self._socket.pendingDatagramSize()
            data, host, port = self._socket.readDatagram(size)

            try:
                msg = msgpack.unpackb(data, encoding='utf-8')
                dev_type, method, args = msg

                if dev_type != MSGPACKRPC_NOTIFICATION:
                    self._debug('Invalid message dev_type')
                    continue

                if method == 'enumerate':
                    # For now, we are client-only, ignore.
                    continue

                if method == 'resources':
                    for resource in args:
                        self.new_remote_resource.emit(host, resource_from_tuple(*resource))
                    continue

                self._debug('Unknown method in message: {}', method)
            except Exception as e:
                self._debug('Received invalid UDP packet from {}:{}: {}', host, port, e)
                continue

    def _debug(self, fmt, *args):
        QtC.qDebug('[fliquer.Node] ' + fmt.format(*args))


if __name__ == '__main__':
    import sys
    app = QtC.QCoreApplication(sys.argv)
    node = Node()
    node.new_remote_resource.connect(lambda h, r: print(r))
    sys.exit(app.exec_())
