from PyQt4 import QtCore as QtC
from PyQt4 import QtGui as QtG
from PyQt4.uic import loadUi
from evil.dashboard import Dashboard

HEADER_SETTING = 'device_list_header'
IN_DASHBOARD_SETTINGS = 'show_in_dashboard/'


class DeviceList(QtG.QWidget):
    closed = QtC.pyqtSignal()
    force_rescan = QtC.pyqtSignal()

    def __init__(self):
        QtG.QWidget.__init__(self)
        loadUi('ui/devicelist.ui', self)

        s = QtC.QSettings()
        if s.contains(HEADER_SETTING):
            self.deviceTableWidget.horizontalHeader().restoreState(
                s.value(HEADER_SETTING))

        self.forceRescanButton.clicked.connect(self.force_rescan)
        self.openDashboardButton.clicked.connect(self._open_dashboard)

        self.channels = []

        self._channel_in_dashboard_boxes = {}

        self._dashboard = None

    def register(self, channel):
        # We need to keep a reference to the object around as connecting to a
        # signal only creates a weak references.
        self.channels.append(channel)
        self.channels.sort(key=lambda a: a.resource.display_name)
        channel.connection_ready.connect(lambda: self._display_channel(channel))
        channel.shutting_down.connect(lambda: self._remove_channel(channel))

    def closeEvent(self, event):
        state = self.deviceTableWidget.horizontalHeader().saveState()
        QtC.QSettings().setValue(HEADER_SETTING, state)

        self.closed.emit()

    def _display_channel(self, channel):
        tw = self.deviceTableWidget
        row = tw.rowCount()
        tw.insertRow(row)

        tw.setItem(row, 0, QtG.QTableWidgetItem(channel.resource.display_name))

        dev_id = channel.resource.dev_id
        tw.setItem(row, 1, QtG.QTableWidgetItem(dev_id))

        tw.setItem(row, 2, QtG.QTableWidgetItem(str(channel.resource.version)))

        show_in_dashboard = QtG.QCheckBox()
        show_in_dashboard.setChecked(self._load_show_in_dashboard(dev_id))
        show_in_dashboard.stateChanged.connect(
            lambda val: self._show_in_dashboard_changed(channel, val))
        self._channel_in_dashboard_boxes[channel] = show_in_dashboard
        tw.setCellWidget(row, 3, show_in_dashboard)

        open_button = QtG.QPushButton('Control Panel')
        open_button.clicked.connect(channel.show_control_panel)
        tw.setCellWidget(row, 4, open_button)

        tw.sortItems(0)

        if self._dashboard:
            self._dashboard.add_channel(channel)

    def _remove_channel(self, channel):
        idx = self.channels.index(channel)
        self.deviceTableWidget.removeRow(idx)
        self.channels.remove(channel)
        del self._channel_in_dashboard_boxes[channel]

    def _show_in_dashboard_changed(self, channel, new_val):
        s = QtC.QSettings()
        s.setValue(IN_DASHBOARD_SETTINGS + channel.resource.dev_id, new_val)

        if self._dashboard:
            if new_val == 2:
                self._dashboard.add_channel(channel)
            elif new_val == 0:
                self._dashboard.remove_channel(channel)

    def _load_show_in_dashboard(self, dev_id):
        s = QtC.QSettings()
        return int(s.value(IN_DASHBOARD_SETTINGS + dev_id, 0))

    def _open_dashboard(self):
        if not self._dashboard:
            self._dashboard = Dashboard()
            for c in self.channels:
                if self._load_show_in_dashboard(c.resource.dev_id):
                    self._dashboard.add_channel(c)
            self._dashboard.closed.connect(self._dashboard_closed)
            self._dashboard.hide_channel.connect(self._hide_from_dashboard)
            self._dashboard.show()

    def _hide_from_dashboard(self, channel):
        checkbox = self._channel_in_dashboard_boxes.get(channel, None)
        if checkbox:
            checkbox.setChecked(0)

    def _dashboard_closed(self):
        self._dashboard = None