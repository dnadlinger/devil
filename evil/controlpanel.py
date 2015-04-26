from PyQt4 import QtCore as QtC
from PyQt4 import QtGui as QtG
from PyQt4.uic import loadUi
import numpy as np
from evil.streamingview import StreamingView

GUI_VERSION = 4.0


class ControlPanel(QtG.QWidget):
    closed = QtC.pyqtSignal()
    active_streams_changed = QtC.pyqtSignal()
    stream_acquisition_config_changed = QtC.pyqtSignal(float, int)

    def __init__(self, channel_name, stream_names, register_area):
        QtG.QWidget.__init__(self)

        self._stream_names = stream_names

        loadUi('ui/controlpanel.ui', self)
        self.setWindowTitle(channel_name + ' – EVIL')

        self.stream_save_file = None

        self.loadButton.clicked.connect(self._load_settings)
        self.saveButton.clicked.connect(self._save_settings)
        self.streamSnapshotFileButton.clicked.connect(self._choose_stream_snapshot_file)

        self.streamSnapshotButton.setIcon(QtG.QIcon('ui/images/shot.png'))
        self.streamSnapshotButton.clicked.connect(self._save_stream_snapshot)

        self.acquireTimeSpinBox.valueChanged.connect(self._update_stream_acquisition_config)
        self.acquirePointsSpinBox.valueChanged.connect(self._update_stream_acquisition_config)

        # these are things that are added to the plot of a particular streaming channel
        # e.g. the threshold line to the filtered difference streaming channel
        self._extra_plot_items = {}

        self._streaming_views = []
        self.add_streaming_view()

        self.addStreamingViewButton.setIcon(QtG.QIcon('ui/images/list-add.png'))
        self.addStreamingViewButton.clicked.connect(self.add_streaming_view)
        self._update_streaming_view_buttons()

        self._register_area = register_area
        self.registerAreaLayout.addWidget(register_area)

        self._extra_plot_items = {}
        register_area.extra_plot_items_changed.connect(self._set_extra_plot_items)

    def active_stream_channels(self):
        return [v.channel for v in self._streaming_views]

    def set_error_conditions(self, conds):
        l = self.errorConditionLabel
        if conds:
            l.setText(', '.join(c.long_name for c in conds))
            l.setStyleSheet('QLabel {color: red}')
        else:
            l.setText('(no hardware errors detected)')
            l.setStyleSheet('QLabel {color: gray}')

    def got_stream_packet(self, packet):
        for v in self._streaming_views:
            v.got_packet(packet)

    def disconnected(self):
        self.errorConditionLabel.setText('(connection lost)')

        self._set_layout_enabled(self.leftSideLayout, False)
        self._set_layout_enabled(self.streamingLayout, False)
        self.saveButton.setEnabled(True)

    def closeEvent(self, event):
        self.closed.emit()
        if self.stream_save_file is not None:
            self.stream_save_file.close()

        QtG.QWidget.closeEvent(self, event)

    def set_stream_acquisition_config(self, time_span_seconds, points):
        self.acquireTimeSpinBox.setValue(time_span_seconds * 1000)
        self.acquirePointsSpinBox.setValue(points)

    def _update_stream_acquisition_config(self):
        time_span_seconds = self.acquireTimeSpinBox.value() / 1000.0
        points = self.acquirePointsSpinBox.value()
        self.stream_acquisition_config_changed.emit(time_span_seconds, points)

    def _set_extra_plot_items(self, items):
        self._extra_plot_items = items
        for chan in self._streaming_views:
            chan.set_extra_plot_items(items)

    def _choose_stream_snapshot_file(self):
        filename = QtG.QFileDialog.getSaveFileName(self, directory='unnamed.evl',
                                                   filter='EVIL logfile (*.evl);;All files(*)')
        try:
            if self.stream_save_file is not None:
                self.stream_save_file.close()
            self.stream_save_file = open(filename, 'wb')
        except Exception as e:
            QtC.qCritical('Could not open streaming data file: {}'.format(e))

    def _save_stream_snapshot(self):
        stream_data = [v.current_stream_data for v in self._streaming_views]
        if len(self._streaming_views) == 1:
            # Save a one-dimensional array if only one streaming channel is
            # active for backwards compatibility.
            np.save(self.stream_save_file, stream_data[0])
        else:
            max_len = max([len(s) for s in stream_data])

            data = np.zeros((len(self._streaming_views), max_len))
            for i, d in enumerate(stream_data):
                data[i, :len(d)] = d
            np.save(self.stream_save_file, data)

    def add_streaming_view(self):
        """Adds a new streaming channel view."""

        # Icing on the cake: Choose a channel not already displayed.
        streamed_channels = [v.channel for v in self._streaming_views]
        unstreamed_channels = [i for i in range(len(self._stream_names)) if i not in streamed_channels]

        view = StreamingView(self._stream_names, unstreamed_channels.pop(0))
        self.streamingViewsLayout.addWidget(view)
        self._streaming_views.append(view)

        view.channel_changed.connect(self.active_streams_changed)
        view.removed.connect(self._remove_streaming_view)

        view.set_extra_plot_items(self._extra_plot_items)

        self._update_streaming_view_buttons()
        self.active_streams_changed.emit()

    def _remove_streaming_view(self):
        """Removes the sending streaming channel from the list."""

        assert len(self._streaming_views) > 1, 'Attempted to delete last streaming view'
        c = self.sender()
        self._streaming_views.remove(c)
        self.streamingViewsLayout.removeWidget(c)
        c.deleteLater()

        self._update_streaming_view_buttons()
        self.active_streams_changed.emit()

    def _update_streaming_view_buttons(self):
        """(De)activates streaming channel add/remove buttons.

        We always want to have at least one streaming channel, and having more
        streaming views than the number of hardware channels makes no sense.
        """

        n = len(self._streaming_views)
        self.addStreamingViewButton.setEnabled(
            n < len(self._stream_names))
        for v in self._streaming_views:
            v.enable_remove(n > 1)

    def _load_settings(self):
        filename = QtG.QFileDialog.getOpenFileName(self, filter="EVIL file (*.evf);;All files(*)")
        if not filename:
            return

        try:
            with open(filename, 'r') as f:
                header_line = f.readline()
                if not header_line.startswith('EVILfile'):
                    raise Exception('Invalid file format')

                dual_file = False
                if header_line.split('\t')[1].startswith('2.'):
                    dual_file = True
                    msg = 'This file has been created by an old client ' \
                          'software version. Select "Yes" to load the ' \
                          'settings stored for the fast channel, or "No" for ' \
                          'the slow channel.'
                    res = QtG.QMessageBox.question(self, 'EVIL – Load fast '
                                                         'channel?',
                                                   msg, QtG.QMessageBox.Yes |
                                                   QtG.QMessageBox.No,
                                                   QtG.QMessageBox.Yes)
                    load_fast = res == QtG.QMessageBox.Yes

                SLOW_PREFIX = 'slow_pid_'

                settings = {}
                for line in f:
                    key, value = line.split("\t")

                    if dual_file:
                        if load_fast and not key.startswith(SLOW_PREFIX):
                            settings[key] = int(value)
                        elif not load_fast and key.startswith(SLOW_PREFIX):
                            settings[key[len(SLOW_PREFIX):]] = int(value)
                    else:
                        settings[key] = int(value)

                self._register_area.load_settings(settings)

        except Exception as e:
            msg = 'An error occurred while trying to load settings from "{}": {}'.\
                format(filename, e)
            QtG.QMessageBox.warning(self, 'EVIL – Could not load settings', msg)

    def _save_settings(self):
        filename = QtG.QFileDialog.getSaveFileName(self, directory="unnamed.evf",
                                                   filter="EVIL file (*.evf);;All files(*)")
        if not filename:
            return

        try:
            with open(filename, 'w') as f:
                f.write("EVILfile\t%s\n" % GUI_VERSION)
                settings = self._register_area.save_settings()
                for key, value in settings.items():
                    line = key + "\t" + str(value) + "\n"
                    f.write(line)
        except Exception as e:
            msg = 'An error occurred while trying to save settings to "{}": {}'.format(filename, e)
            QtG.QMessageBox.warning(self, 'EVIL – Could not save settings', msg)

    def _set_layout_enabled(self, layout, enabled):
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget():
                item = item.widget()
            if item.layout():
                self._set_layout_enabled(item.layout(), enabled)
            elif getattr(item, 'setEnabled', None):
                item.setEnabled(enabled)
