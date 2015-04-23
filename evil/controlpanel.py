from PyQt5 import QtCore as QtC
from PyQt5 import QtGui as QtG
from PyQt5.uic import loadUi
import numpy as np
from evil.streamingview import StreamingView

# Bits indicating system error conditions in the control register.
COND_ADC_OVERFLOW = 1 << 0

GUI_VERSION = 2.0


class ControlPanel(QtG.QWidget):
    stream_active_channels_changed = QtC.pyqtSignal(list)
    stream_acquisition_config_changed = QtC.pyqtSignal(float, int)

    def __init__(self, stream_names, register_area):
        QtG.QWidget.__init__(self)

        self._stream_names = stream_names

        loadUi('ui/controlpanel.ui', self)

        self.stream_save_file = None
        self.current_stream_data = None

        self.loadButton.clicked.connect(self.load_data)
        self.saveButton.clicked.connect(self.save_data)
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

        self.registerAreaLayout.addWidget(register_area)
        register_area.extra_plot_items_changed.connect(self._set_extra_plot_items)

    def _set_extra_plot_items(self, items):
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

        view.channel_changed.connect(self._update_active_streaming_channels)
        view.removed.connect(self._remove_streaming_view)

        view.set_extra_plot_items(self._extra_plot_items)

        self._update_streaming_view_buttons()
        self._update_active_streaming_channels()

    def _remove_streaming_view(self):
        """Removes the sending streaming channel from the list."""

        assert len(self._streaming_views) > 1, 'Attempted to delete last streaming view'
        c = self.sender()
        self._streaming_views.remove(c)
        self.streamingViewsLayout.removeWidget(c)
        c.deleteLater()

        self._update_streaming_view_buttons()
        self._update_active_streaming_channels()

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

    def _update_active_streaming_channels(self):
        active_channels = [v.channel for v in self._streaming_views]
        self.stream_active_channels_changed.emit(active_channels)

    def _update_stream_acquisition_config(self):
        time_span_seconds = self.acquireTimeSpinBox.value()
        points = self.acquirePointsSpinBox.value()
        self.stream_acquisition_config_changed.emit(time_span_seconds, points)

    def got_stream_data(self, reg_id, data):
        data_l = len(data)
        dt = 1e-3 / self.settings['hardwareSampleDelaySpinBox'].widget.sample_rate()
        xdata = np.linspace(0, dt * data_l, data_l)

        data_with_axis = np.vstack((xdata, 4 * data))
        for v in self._streaming_views:
            v.update_stream_data(reg_id, data_with_axis)

    def update_cond_display(self, data):
        def update_overflow_state(widget, overflow):
            if overflow:
                widget.setText('over-/underflow')
                widget.setStyleSheet('QLabel {color: red}')
            else:
                widget.setText('in range')
                widget.setStyleSheet('QLabel {color: black}')

        update_overflow_state(self.adcOverflowText, data & COND_ADC_OVERFLOW)

    def load_data(self):
        filename = QtG.QFileDialog.getOpenFileName(self, filter="EVIL file (*.evf);;All files(*)")
        with open(filename, 'r') as f:
            if not f.readline().startswith('EVILfile'):
                raise Exception('<b>Invalid file format</b>')
            for line in f:
                name, val = line.split("\t")
                self.settings[name].value(int(val))
                self.communication.write(self.settings[name])

    def save_data(self):
        filename = QtG.QFileDialog.getSaveFileName(self, directory="unnamed.evf",
                                                   filter="EVIL file (*.evf);;All files(*)")
        with open(filename, 'w') as f:
            f.write("EVILfile\t%s\n" % GUI_VERSION)
            for name, setting in self.settings.items():
                line = name + "\t" + str(setting.value()) + "\n"
                f.write(line)

    # noinspection PyUnusedLocal
    def closeEvent(self, event):
        if self.stream_save_file is not None:
            self.stream_save_file.close()
