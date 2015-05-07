#!/usr/bin/env python

from evil.evil2channel import Evil2Channel
from evil.devicelist import DeviceList
import fliquer
import zmq

from PyQt4 import QtCore as QtC
from PyQt4 import QtGui as QtG

if __name__ == '__main__':
    import sys

    QtC.QCoreApplication.setApplicationName('EVIL')
    QtC.QCoreApplication.setOrganizationName('TIQI')
    QtC.QCoreApplication.setOrganizationDomain('tiqi.ethz.ch')

    app = QtG.QApplication(sys.argv)

    shared_mem = QtC.QSharedMemory('tiqi.evil.client.isStarted')
    if not shared_mem.create(1) and\
            shared_mem.error() == QtC.QSharedMemory.AlreadyExists:
        error_msg = QtG.QMessageBox(QtG.QMessageBox.Warning,
                                    'EVIL Client already running',
                                    'Another instance of the EVIL client '
                                    'software is already running on your '
                                    'system. On Windows, this might cause '
                                    'network devices not to be discovered '
                                    'properly. Do you want to continue?',
                                    QtG.QMessageBox.Yes |
                                    QtG.QMessageBox.No)
        error_msg.setDefaultButton(QtG.QMessageBox.No)
        if error_msg.exec_() == QtG.QMessageBox.No:
            sys.exit(1)

    zmq_ctx = zmq.Context()

    device_list = DeviceList()
    device_list.closed.connect(app.quit)

    def new_resource(host, resource):
        if resource.dev_type != 'tiqi.evil.channel':
            return

        if resource.dev_id in [c.resource.dev_id for c in
                               device_list.channels]:
            # Resource already exists, ignore.
            return

        if resource.version.major == 2:
            device_list.register(Evil2Channel(zmq_ctx, host, resource))
        else:
            QtC.qWarning('Cannot handle EVIL version {}, ignoring'.format(
                resource.version))

    node = fliquer.Node()
    node.new_remote_resource.connect(new_resource)
    device_list.force_rescan.connect(node.broadcast_enumeration_request)

    device_list.show()
    sys.exit(app.exec_())
