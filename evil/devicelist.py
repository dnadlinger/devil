from PyQt5 import QtCore as QtC
from PyQt5 import QtWidgets as QtW
from PyQt5.uic import loadUi


class DeviceList(QtW.QWidget):
    def __init__(self):
        QtW.QWidget.__init__(self)
        loadUi('ui/devicelist.ui', self)

        self._channels = []

    def register(self, channel):
        # We need to keep a reference to the object around as connecting to a
        # signal only creates a weak references.
        self._channels.append(channel)
        channel.connection_ready.connect(lambda: self._display_channel(channel))
        channel.shutting_down.connect(lambda: self._remove_channel(channel))

    def _display_channel(self, channel):
        tw = self.deviceTableWidget
        row = tw.rowCount()
        tw.insertRow(row)

        name = QtW.QTableWidgetItem(channel.resource.display_name)
        tw.setItem(row, 0, name)

        dev_id = QtW.QTableWidgetItem(channel.resource.dev_id)
        tw.setItem(row, 1, dev_id)

        version = QtW.QTableWidgetItem(str(channel.resource.version))
        tw.setItem(row, 2, version)

        show_in_overview_box = QtW.QCheckBox()
        tw.setCellWidget(row, 3, show_in_overview_box)

        open_button = QtW.QPushButton("Control Panel")
        open_button.clicked.connect(channel.show_control_panel)
        tw.setCellWidget(row, 4, open_button)

    def _remove_channel(self, channel):
        idx = self._channels.index(channel)
        self.deviceTableWidget.removeRow(idx)
        self._channels.remove(channel)
