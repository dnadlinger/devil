from evil.channel import Channel
import fliquer
import zmq

from PyQt5 import QtCore as QtC

if __name__ == '__main__':
    import sys

    zmq_ctx = zmq.Context()
    app = QtC.QCoreApplication(sys.argv)
    node = fliquer.Node()

    channels = []

    def new_resource(host, resource):
        if resource.dev_type == 'tiqi.evil.channel':
            if resource.version.major == 2:
                channels.append(Channel(zmq_ctx, host, resource))
            else:
                QtC.qWarning('Cannot handle EVIL version {}, ignoring'.format(
                             resource.version))

    node.new_remote_resource.connect(new_resource)
    sys.exit(app.exec_())
