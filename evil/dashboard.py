from PyQt4 import QtCore as QtC
from PyQt4 import QtGui as QtG
from math import sqrt
from evil.channel import Channel
import pyqtgraph as pg

# Currently, we always display the stream with index 0 on the dashboard. This
# could be made user-configurable in the future.
STREAM_IDX_TO_DISPLAY = 0


class Dashboard(QtG.QMainWindow):
    closed = QtC.pyqtSignal()
    hide_channel = QtC.pyqtSignal(object)

    def __init__(self):
        QtG.QWidget.__init__(self)

        settings = QtC.QSettings()

        saved_geometry = settings.value("dashboard/geometry")
        if saved_geometry:
            self.restoreGeometry(saved_geometry)

        stored_window_state = settings.value("dashboard/windowState")
        if stored_window_state:
            self.restoreState(stored_window_state)

        self.setWindowTitle('EVIL Dashboard')
        self._view = pg.GraphicsLayoutWidget()
        self.setCentralWidget(self._view)

        self._channels = []
        self._channel_curve_map = {}
        self._channel_condition_text_map = {}
        self._channel_plot_map = {}
        self._channel_name_label_map = {}

    def add_channel(self, channel):
        self.add_channels([channel])

    def add_channels(self, channels):
        for c in channels:
            c.shutting_down.connect(self._channel_shutting_down)
            c.error_conditions_changed.connect(
                self._channel_conditions_changed)
            c.status_changed.connect(self._channel_status_changed)
            c.stream_packet_received.connect(self._got_stream_packet)

            c.add_stream_subscription(STREAM_IDX_TO_DISPLAY)
            self._channels.append(c)

        self._relayout()

    def remove_channel(self, channel):
        channel.shutting_down.disconnect(self._channel_shutting_down)
        channel.error_conditions_changed.disconnect(
            self._channel_conditions_changed)
        channel.status_changed.disconnect(self._channel_status_changed)
        channel.stream_packet_received.disconnect(self._got_stream_packet)
        channel.remove_stream_subscription(STREAM_IDX_TO_DISPLAY)

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
        settings = QtC.QSettings()
        settings.setValue("dashboard/geometry", self.saveGeometry())
        settings.setValue("dashboard/windowState", self.saveState())

        self.closed.emit()
        QtG.QMainWindow.closeEvent(self, event)

    def _relayout(self):
        self._channels.sort(key=lambda a: a.resource.display_name)

        self._view.clear()
        self._channel_curve_map.clear()
        self._channel_condition_text_map.clear()
        self._channel_plot_map.clear()
        self._channel_name_label_map.clear()

        if not self._channels:
            return

        layout = self._view.ci.layout
        layout.setHorizontalSpacing(20)

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
                self._add_plot_for_channel(channel)
            self._view.nextRow()

            for channel in row:
                if not channel:
                    break
                self._add_name_for_channel(channel)
                self._update_status_colors(channel, channel.current_status())
            self._view.nextRow()

        col_width = self.width() / cols - layout.horizontalSpacing()
        for i in range(cols):
            layout.setColumnFixedWidth(i, col_width)

        # Set maximum width so that overly long names do not break the grid
        # layout, even if they obviously still look ugly.
        for l in self._channel_name_label_map.values():
            l.setMaximumWidth(col_width)

    def _add_plot_for_channel(self, channel):
        plot = self._view.addPlot()
        self._channel_plot_map[channel] = plot
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

        curve = pg.PlotCurveItem(antialias=True)
        plot.addItem(curve)
        self._channel_curve_map[channel] = curve

        text = pg.TextItem(html='')
        plot.addItem(text)
        text.setPos(0, 513)
        self._channel_condition_text_map[channel] = text
        self._update_condition_text(channel, channel.current_error_conditions())

    def _add_name_for_channel(self, channel):
        label = LabelItemWithBg(text=channel.resource.display_name, bold=True)
        self._channel_name_label_map[channel] = label
        self._view.addItem(label)

    def _got_stream_packet(self, packet):
        if packet.stream_idx != STREAM_IDX_TO_DISPLAY:
            return

        curve = self._channel_curve_map[self.sender()]
        curve.setData(packet.samples)

        plot = self._channel_plot_map[self.sender()]
        plot.setXRange(0, len(packet.samples), padding=0)

    def _channel_conditions_changed(self, conditions):
        channel = self.sender()
        self._update_condition_text(channel, conditions)

    def _update_condition_text(self, channel, error_conditions):
        text = '&nbsp;&nbsp;'.join(map(lambda e: e.short_name,
                                       error_conditions))
        self._channel_condition_text_map[channel].setHtml(
            '<span style="color: red; font-weight: bold">' + text + '</span>')

    def _channel_status_changed(self, status):
        self._update_status_colors(self.sender(), status)

    def _update_status_colors(self, channel, status):
        curve = self._channel_curve_map[channel]
        label = self._channel_name_label_map[channel]

        if status == Channel.Status.idle:
            curve.setPen(pg.mkPen((128, 128, 128)))
            label.setText(channel.resource.display_name, color=QtG.QColor(
                128, 128, 128))
            label.setBgColor(QtG.QColor(0, 0, 0))
            return

        curve.setPen(pg.mkPen((255, 255, 255)))
        label.setText(channel.resource.display_name, color=QtG.QColor(
            255, 255, 255))
        if status == Channel.Status.configuring:
            label.setBgColor(QtG.QColor(0, 128, 0))
            return
        if status == Channel.Status.running:
            label.setBgColor(QtG.QColor(0, 0, 128))
            return

    def _channel_shutting_down(self):
        self.remove_channel(self.sender())


class LabelItemWithBg(pg.LabelItem):
    def __init__(self, text=' ', parent=None, angle=0, **kwargs):
        pg.LabelItem.__init__(self, text, parent, angle, **kwargs)

        self._bg_color = QtG.QColor(0, 0, 0)

    def setBgColor(self, color):
        self._bg_color = color
        self.update()

    def paint(self, p, *args):
        p.setPen(QtC.Qt.NoPen)
        p.setBrush(QtG.QBrush(self._bg_color))
        p.drawRect(self.rect())
