import numpy as np
from PyQt5 import QtCore as QtC
from PyQt5 import QtGui as QtG
from PyQt5.uic import loadUi
from pyqtgraph.graphicsItems.InfiniteLine import InfiniteLine

class StreamingView(QtG.QWidget):
    """A streaming plot view and associated controls."""

    channel_changed = QtC.pyqtSignal()
    removed = QtC.pyqtSignal()

    def __init__(self, channel_names, initial_channel=0):
        QtG.QWidget.__init__(self)
        loadUi('ui/streamingchannel.ui', self)

        self.streamingChannelComboBox.clear()
        for name in channel_names:
            self.streamingChannelComboBox.addItem(name)
        self.streamingChannelComboBox.setCurrentIndex(initial_channel)

        self.streamingChannelComboBox.currentIndexChanged.connect(self.channel_changed)
        self.streamingChannelComboBox.currentIndexChanged.connect(self._add_extra_items_from_dict)

        self.removeViewButton.setIcon(QtG.QIcon('ui/images/list-remove.png'))
        self.removeViewButton.clicked.connect(self.removed)

        pi = self.plotWidget.getPlotItem()
        pi.setRange(xRange=(0, 1), yRange=(-512, 512), padding = 0)
        pi.setLabel('bottom', 'time', 's')
        self._plot_curve = pi.plot()

        self._extra_plot_items = {}
        self._displayed_extra_items = []

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
        pi.setRange(xRange=(0, len(samples) * interval), padding = 0)

        use_trigger = self.rampTriggerCheckBox.isChecked()
        if use_trigger:
            samples = samples[packet.trigger_offset:]

        self._plot_curve.setData(np.arange(0, len(samples) * interval, interval),
                                 samples)

    def set_extra_plot_items(self, extra_plot_items):
        self._extra_plot_items = extra_plot_items
        self._add_extra_items_from_dict()

    def _add_extra_items_from_dict(self):
        for item in self._displayed_extra_items:
            self.plotWidget.getPlotItem().removeItem(item)
        self._displayed_extra_items = []

        if self.channel in self._extra_plot_items:
            items = self._extra_plot_items[self.channel]

            threshold = items.get('threshold')
            if threshold is not None:
                self._displayed_extra_items.append(InfiniteLine(threshold, angle=0))

        for item in self._displayed_extra_items:
            self.plotWidget.getPlotItem().addItem(item)
