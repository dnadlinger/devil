import numpy as np
import pyqtgraph as pg
from PyQt4 import QtCore as QtC
from PyQt4 import QtGui as QtG
from PyQt4.uic import loadUi


class StreamingView(QtG.QWidget):
    """A streaming plot view and associated controls."""

    channel_changed = QtC.pyqtSignal(int, int)
    removed = QtC.pyqtSignal()

    def __init__(self, channel_names, initial_channel=0):
        QtG.QWidget.__init__(self)
        loadUi('ui/streamingchannel.ui', self)

        self.streamingChannelComboBox.clear()
        for name in channel_names:
            self.streamingChannelComboBox.addItem(name)
        self.streamingChannelComboBox.setCurrentIndex(initial_channel)
        self._current_channel = initial_channel

        self.streamingChannelComboBox.currentIndexChanged.connect(
            self._change_channel)

        self.removeViewButton.setIcon(QtG.QIcon('ui/images/list-remove.png'))
        self.removeViewButton.clicked.connect(self.removed)

        pi = self.plotWidget.getPlotItem()
        self._last_x_range = 1.0
        pi.setRange(xRange=(0, self._last_x_range), yRange=(-513, 513),
                    padding=0)
        pi.setLabel('bottom', 'time', 's')
        self._plot_curve = pi.plot(antialias=True)

        self._extra_plot_items = {}
        self._displayed_extra_items = []
        self.rampTriggerCheckBox.stateChanged.connect(
            self._add_extra_items_from_dict)

    @property
    def channel(self):
        """The index of the selected streaming channel."""
        return int(self.streamingChannelComboBox.currentIndex())

    def enable_remove(self, can_remove):
        self.removeViewButton.setEnabled(can_remove)

    def got_packet(self, packet):
        if packet.stream_idx != self.channel:
            return

        samples = packet.samples
        interval = packet.sample_interval_seconds

        pi = self.plotWidget.getPlotItem()

        x_range = len(samples) * interval

        if x_range != self._last_x_range:
            self._last_x_range = x_range
            pi.setRange(xRange=(0, self._last_x_range), padding = 0)
            self._add_extra_items_from_dict()

        if self._use_trigger():
            samples = samples[packet.trigger_offset:]

        sample_times = np.linspace(0, (len(samples) - 1) * interval, len(samples))
        self._plot_curve.setData(sample_times, samples)

    def current_data(self):
        return self._plot_curve.getData()[1]

    def set_extra_plot_items(self, extra_plot_items):
        self._extra_plot_items = extra_plot_items
        self._add_extra_items_from_dict()

    def _use_trigger(self):
        return self.rampTriggerCheckBox.isChecked()

    def _change_channel(self, new_idx):
        old_idx = self._current_channel
        self._current_channel = new_idx
        self._add_extra_items_from_dict()
        self.channel_changed.emit(old_idx, new_idx)

    def _add_extra_items_from_dict(self):
        for item in self._displayed_extra_items:
            self.plotWidget.getPlotItem().removeItem(item)
        self._displayed_extra_items = []

        if self.channel not in self._extra_plot_items:
            return
        items = self._extra_plot_items[self.channel]

        threshold = items.get('threshold')
        if threshold is not None:
            self._displayed_extra_items.append(
                pg.InfiniteLine(threshold, angle=0))

        offset = items.get('offset')
        if offset is not None:
            self._displayed_extra_items.append(
                pg.InfiniteLine(-offset, angle=0))

        period = items.get('period')
        if period is not None and self._use_trigger():
            main_period, extra_divisions = period

            period_count = int(np.ceil(self._last_x_range / main_period))
            if period_count < 24:
                for i in range(period_count):
                    main_x = (i + 1) * main_period
                    self._displayed_extra_items.append(pg.InfiniteLine(
                        main_x, angle=90, pen=pg.mkPen((100, 100, 100),
                                                       style=QtC.Qt.DashLine)))

                    # When user increases the frequency so far that we'd
                    # end up with an unreasonable period count, start by
                    # hiding the extra divisions to give feedback as to
                    # what is going on.
                    if period_count > 8:
                        continue
                    for div in extra_divisions:
                        div_x = div + i * main_period
                        self._displayed_extra_items.append(pg.InfiniteLine(
                            div_x, angle=90, pen=pg.mkPen((100, 100, 100),
                                                          style=QtC.Qt.DotLine)))

        for item in self._displayed_extra_items:
            self.plotWidget.getPlotItem().addItem(item)
