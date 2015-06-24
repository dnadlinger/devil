#!/usr/bin/env python

from devil.evil2channel import Evil2Channel, create_evil2_control_panel
from devil.devicelist import DeviceList
import fliquer
import zmq

from PyQt4 import QtCore as QtC
from PyQt4 import QtGui as QtG

VERSION_STRING = '1.0.1'

if __name__ == '__main__':
    import sys

    QtC.QCoreApplication.setApplicationName('DEVIL')
    QtC.QCoreApplication.setOrganizationName('TIQI')
    QtC.QCoreApplication.setOrganizationDomain('tiqi.ethz.ch')

    app = QtG.QApplication(sys.argv)

    shared_mem = QtC.QSharedMemory('tiqi.devil.client.isStarted')
    if not shared_mem.create(1) and\
            shared_mem.error() == QtC.QSharedMemory.AlreadyExists:
        error_msg = QtG.QMessageBox(QtG.QMessageBox.Warning,
                                    'DEVIL already running',
                                    'Another instance of the DEVIL client '
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

    device_list = DeviceList(VERSION_STRING)
    device_list.closed.connect(app.quit)

    def new_resource(host, resource):
        if resource.dev_type != 'tiqi.devil.channel':
            return

        if resource.dev_id in [c.channel.resource.dev_id for c in
                               device_list.guichannels]:
            # Resource already exists, ignore.
            return

        if resource.version.major == 2:
            device_list.register(Evil2Channel(zmq_ctx, host, resource),
                lambda *args: create_evil2_control_panel(VERSION_STRING, *args))
        else:
            QtC.qWarning('Cannot handle EVIL version {}, ignoring'.format(
                resource.version))

    node = fliquer.Node()
    node.new_remote_resource.connect(new_resource)
    device_list.force_rescan.connect(node.broadcast_enumeration_request)

    device_list.show()
    sys.exit(app.exec_())
