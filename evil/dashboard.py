from PyQt4 import QtCore as QtC
from PyQt4 import QtGui as QtG
from math import sqrt
import pyqtgraph as pg


class Dashboard(QtG.QMainWindow):
    closed = QtC.pyqtSignal()
    hide_channel = QtC.pyqtSignal(object)

    def __init__(self):
        QtG.QWidget.__init__(self)

        self.setWindowTitle('EVIL Dashboard')
        self._view = pg.GraphicsLayoutWidget()
        self.setCentralWidget(self._view)

        self._channels = []
        self._channel_curve_map = {}

    def add_channel(self, channel):
        self._channels.append(channel)
        channel.shutting_down.connect(lambda: self._remove_channel(
            self.sender()))
        self._relayout()

        channel.main_stream_packet_received.connect(self._got_stream_packet)

    def remove_channel(self, channel):
        channel.main_stream_packet_received.disconnect(self._got_stream_packet)
        self._channels.remove(channel)
        self._relayout()

    def resizeEvent(self, event):
        self._relayout()

    def changeEvent(self, event):
        if event.type() == QtC.QEvent.WindowStateChange:
            state = self.windowState()
            if state & QtC.Qt.WindowMaximized:
                self.setWindowState(state & ~QtC.Qt.WindowMaximized |
                                    QtC.Qt.WindowFullScreen)
        QtG.QMainWindow.changeEvent(self, event)

    def keyPressEvent(self, event):
        if event.key() & QtC.Qt.Key_Escape:
            state = self.windowState()
            if state & QtC.Qt.WindowFullScreen:
                self.setWindowState(state & ~QtC.Qt.WindowFullScreen)
                return
        QtG.QMainWindow.keyPressEvent(self, event)

    def closeEvent(self, event):
        self.closed.emit()

    def _relayout(self):
        self._channels.sort(key=lambda a: a.resource.display_name)

        self._view.clear()
        self._channel_curve_map.clear()

        if not self._channels:
            return

        window_aspect = self.width() / self.height()
        target_aspect = 1

        cols = round(sqrt(len(self._channels) * window_aspect / target_aspect))
        cols = min(cols, len(self._channels))

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

                # Disable the default pyqtgraph context menu entries, except for
                # the export option. Note: It is not clear whether these are
                # supposed to be public APIs, so this might stop working when
                # pyqtgraph is updated.
                plot.setMenuEnabled(False, None)
                plot.vb.menu.clear()

                panel_action = plot.vb.menu.addAction('Open Control Panel...')
                panel_action.triggered.connect(channel.show_control_panel)

                unlock_action = plot.vb.menu.addAction('Unlock')
                unlock_action.triggered.connect(channel.unlock)

                hide_action = plot.vb.menu.addAction('Hide from Dashboard')
                hide_action.triggered.connect(lambda *args, c=channel:
                                              self.hide_channel.emit(c))

                # TODO: Update plot.titleLabel background based on state.

                curve = pg.PlotCurveItem(antialias=True)
                plot.addItem(curve)
                self._channel_curve_map[channel] = curve

            self._view.nextRow()

        col_width = self.width() / cols
        for i in range(cols):
            self._view.ci.layout.setColumnPreferredWidth(i, col_width)

    def _got_stream_packet(self, packet):
        curve = self._channel_curve_map[self.sender()]
        curve.setData(packet.samples)
