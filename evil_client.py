#!/usr/bin/env python

from evil.evil2channel import Evil2Channel
from evil.devicelist import DeviceList
import fliquer
import zmq

from PyQt5 import QtCore as QtC
from PyQt5 import QtWidgets as QtW

if __name__ == '__main__':
    import sys

    QtC.QCoreApplication.setApplicationName("EVIL")
    QtC.QCoreApplication.setOrganizationName("TIQI")
    QtC.QCoreApplication.setOrganizationDomain("tiqi.ethz.ch")

    zmq_ctx = zmq.Context()
    app = QtW.QApplication(sys.argv)
    node = fliquer.Node()

    device_list = DeviceList()

    def new_resource(host, resource):
        if resource.dev_type == 'tiqi.evil.channel':
            if resource.version.major == 2:
                device_list.register(Evil2Channel(zmq_ctx, host, resource))
            else:
                QtC.qWarning('Cannot handle EVIL version {}, ignoring'.format(
                             resource.version))

    node.new_remote_resource.connect(new_resource)

    device_list.show()
    sys.exit(app.exec_())
