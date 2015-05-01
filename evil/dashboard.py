from PyQt4 import QtCore as QtC
from PyQt4 import QtGui as QtG
from math import sqrt
import pyqtgraph as pg


class Dashboard(QtG.QMainWindow):
    closed = QtC.pyqtSignal()

    def __init__(self):
        QtG.QWidget.__init__(self)

        self.setWindowTitle('EVIL Dashboard')
        self._view = pg.GraphicsLayoutWidget()
        self.setCentralWidget(self._view)

        self._channels = []
        self._channel_curve_map = {}

    def add_channel(self, channel):
        self._channels.append(channel)
        channel.shutting_down.connect(self._remove_sending_channel)
        self._relayout()

        channel.main_stream_packet_received.connect(self._got_stream_packet)

    def resizeEvent(self, event):
        self._relayout()

    def closeEvent(self, event):
        self.closed.emit()

    def _remove_sending_channel(self):
        self._channels.remove(self.sender())
        self._relayout()

    def _relayout(self):
        self._channels.sort(key=lambda a: a.resource.display_name)

        self._view.clear()
        self._channel_curve_map.clear()

        if not self._channels:
            return

        window_aspect = self.width() / self.height()
        target_aspect = 1

        cols = round(sqrt(len(self._channels) * window_aspect / target_aspect))

        last_row = len(self._channels) % cols
        if last_row == 0:
            last_row += cols

        channel_iter = iter(self._channels + [None] * (cols - last_row))
        for row in zip(*([channel_iter] * cols)):
            for channel in row:
                if not channel:
                    break

                plot = self._view.addPlot(
                    title=channel.resource.display_name)
                plot.setMouseEnabled(False, False)
                plot.hideButtons()
                plot.hideAxis('left')
                plot.hideAxis('bottom')
                plot.setRange(yRange=(-513, 513), padding=0)

                # TODO: Update plot.titleLabel background based on state.

                curve = pg.PlotCurveItem(antialias=True)
                plot.addItem(curve)
                self._channel_curve_map[channel] = curve

            self._view.nextRow()

        col_width = self.width() / cols
        for i in range(cols):
            self._view.ci.layout.setColumnMaximumWidth(i, col_width)

    def _got_stream_packet(self, packet):
        curve = self._channel_curve_map[self.sender()]
        curve.setData(packet.samples)
