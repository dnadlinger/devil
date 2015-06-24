from PyQt4 import QtCore as QtC
from PyQt4 import QtGui as QtG
from math import sqrt
from devil.channel import Channel
import pyqtgraph as pg

# Currently, we always display the stream with index 0 on the dashboard. This
# could be made user-configurable in the future.
STREAM_IDX_TO_DISPLAY = 0

COLOR_BG = (0, 43, 54)
COLOR_VERSION_LINE = (0, 29, 36)
COLOR_TRACE_ACTIVE = (238, 232, 213)
COLOR_TRACE_INACTIVE = (101, 123, 131)
COLOR_LABEL_BG_ACTIVE = (7, 54, 66)
COLOR_LABEL_BG_INACTIVE = (0, 43, 54)
COLOR_LABEL_CONFIGURING = (133, 153, 0)
COLOR_LABEL_RUNNING = (38, 139, 210)
CSS_COLOR_ERROR = '#dc322f'


class Dashboard(QtG.QMainWindow):
    closed = QtC.pyqtSignal()
    hide_channel = QtC.pyqtSignal(object)

    def __init__(self, version_string):
        QtG.QWidget.__init__(self)

        self._version_string = version_string

        settings = QtC.QSettings()

        saved_geometry = settings.value('dashboard/geometry')
        if saved_geometry:
            self.restoreGeometry(saved_geometry)

        stored_window_state = settings.value('dashboard/windowState')
        if stored_window_state:
            self.restoreState(stored_window_state)

        self.setWindowTitle('Dashboard – DEVIL ' + self._version_string)
        self._view = pg.GraphicsLayoutWidget()
        self._view.setBackground(COLOR_BG)
        self.setCentralWidget(self._view)

        self._guichannels = []
        self._channel_curve_map = {}
        self._channel_condition_text_map = {}
        self._channel_plot_map = {}
        self._channel_name_label_map = {}

    def add_channel(self, channel):
        self.add_channels([channel])

    def add_channels(self, guichannels):
        for c in guichannels:
            c.channel.shutting_down.connect(self._channel_shutting_down)
            c.channel.add_stream_subscription(STREAM_IDX_TO_DISPLAY)
            self._guichannels.append(c)

        self._relayout()

        for c in guichannels:
            c.channel.error_conditions_changed.connect(
                self._channel_conditions_changed)
            c.channel.status_changed.connect(self._channel_status_changed)
            c.channel.stream_packet_received.connect(self._got_stream_packet)

    def remove_channel(self, guichannel):
        c = guichannel.channel
        c.shutting_down.disconnect(self._channel_shutting_down)
        c.error_conditions_changed.disconnect(
            self._channel_conditions_changed)
        c.status_changed.disconnect(self._channel_status_changed)
        c.stream_packet_received.disconnect(self._got_stream_packet)
        c.remove_stream_subscription(STREAM_IDX_TO_DISPLAY)

        self._guichannels.remove(guichannel)
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
        settings.setValue('dashboard/geometry', self.saveGeometry())
        settings.setValue('dashboard/windowState', self.saveState())

        for gc in self._guichannels:
            gc.channel.remove_stream_subscription(STREAM_IDX_TO_DISPLAY)

        self.closed.emit()
        QtG.QMainWindow.closeEvent(self, event)

    def _relayout(self):
        self._view.clear()
        self._channel_curve_map.clear()
        self._channel_condition_text_map.clear()
        self._channel_plot_map.clear()
        self._channel_name_label_map.clear()

        if not self._guichannels:
            return

        layout = self._view.ci.layout
        layout.setHorizontalSpacing(20)

        # TODO: Set larger spacing below label. Somehow, layout.setRowSpacing
        # only ever seems to add space before the very first row, though.
        layout.setVerticalSpacing(10)

        window_aspect = self.width() / self.height()
        target_aspect = 1

        cols = round(sqrt(len(self._guichannels) * window_aspect / target_aspect))
        cols = min(cols, len(self._guichannels))

        last_row = len(self._guichannels) % cols
        if last_row == 0:
            last_row += cols

        self._guichannels.sort(key=lambda a: a.channel.resource.display_name)
        channel_iter = iter(self._guichannels + [None] * (cols - last_row))
        for row in zip(*([channel_iter] * cols)):
            for guichannel in row:
                if not guichannel:
                    break
                self._add_plot_for_channel(guichannel)
            self._view.nextRow()

            for guichannel in row:
                if not guichannel:
                    break
                self._add_name_for_channel(guichannel)
                c = guichannel.channel
                self._update_status_colors(c, c.current_status())
            self._view.nextRow()

        col_width = self.width() / cols - layout.horizontalSpacing()
        for i in range(cols):
            layout.setColumnFixedWidth(i, col_width)

        # Set maximum width so that overly long names do not break the grid
        # layout, even if they obviously still look ugly.
        for l in self._channel_name_label_map.values():
            l.setMaximumWidth(col_width)

        # FIXME: For some weird reason, this causes the channel traces to
        # disappear (but not the name labels, etc.). Seems to be a pyqtgraph
        # bug.
        #
        # self._view.nextRow()
        # self._version_label = pg.LabelItem(justify='left')
        # self._version_label.setText('DEVIL client v' + self._version_string,
        #                             bold=True,
        #                             color=QtG.QColor(*COLOR_VERSION_LINE))
        # self._view.addItem(self._version_label, colspan=cols)

    def _add_plot_for_channel(self, guichannel):
        channel = guichannel.channel

        plot = self._view.addPlot()
        self._channel_plot_map[channel] = plot
        plot.setMouseEnabled(False, False)
        plot.hideButtons()
        plot.hideAxis('left')
        plot.hideAxis('bottom')
        plot.setRange(yRange=(-514, 514), padding=0)

        # Disable the default pyqtgraph context menu entries, except for
        # the export option. Note: It is not clear whether these are
        # supposed to be public APIs, so this might stop working when
        # pyqtgraph is updated.
        plot.setMenuEnabled(False, None)
        plot.vb.menu.clear()

        panel_action = plot.vb.menu.addAction('Open Control Panel...')
        panel_action.triggered.connect(guichannel.show_control_panel)

        unlock_action = plot.vb.menu.addAction('Unlock')
        unlock_action.triggered.connect(channel.unlock)

        hide_action = plot.vb.menu.addAction('Hide from Dashboard')
        hide_action.triggered.connect(lambda *args, gc=guichannel:
                                      self.hide_channel.emit(gc))

        curve = pg.PlotCurveItem(antialias=True)
        plot.addItem(curve)
        self._channel_curve_map[channel] = curve

        text = pg.TextItem(html='')
        plot.addItem(text)
        text.setPos(0, 513)
        self._channel_condition_text_map[channel] = text
        self._update_condition_text(channel, channel.current_error_conditions())

    def _add_name_for_channel(self, guichannel):
        label = LabelItemWithBg(text=guichannel.channel.resource.display_name, bold=True)
        self._channel_name_label_map[guichannel.channel] = label
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
        html = '<span style="color: {}; font-weight: bold">{}</span>'.format(
            CSS_COLOR_ERROR, text)
        self._channel_condition_text_map[channel].setHtml(html)

    def _channel_status_changed(self, status):
        self._update_status_colors(self.sender(), status)

    def _update_status_colors(self, channel, status):
        curve = self._channel_curve_map[channel]
        label = self._channel_name_label_map[channel]

        if status == Channel.Status.idle:
            curve.setPen(pg.mkPen(COLOR_TRACE_INACTIVE))
            label.setText(channel.resource.display_name, color=QtG.QColor(
                *COLOR_TRACE_INACTIVE))
            label.setBgColor(QtG.QColor(*COLOR_LABEL_BG_INACTIVE))
            return

        curve.setPen(pg.mkPen(COLOR_TRACE_ACTIVE))
        label.setBgColor(QtG.QColor(*COLOR_LABEL_BG_ACTIVE))

        if status == Channel.Status.configuring:
            text_color = COLOR_LABEL_CONFIGURING
        if status == Channel.Status.running:
            text_color = COLOR_LABEL_RUNNING
        label.setText(channel.resource.display_name, color=QtG.QColor(
            *text_color))

    def _channel_shutting_down(self):
        channel = self.sender()
        for gc in self._guichannels:
            if gc.channel == channel:
                self.remove_channel(gc)
                return


class LabelItemWithBg(pg.LabelItem):
    def __init__(self, text=' ', parent=None, angle=0, **kwargs):
        pg.LabelItem.__init__(self, text, parent, angle, **kwargs)

        self._bg_color = QtG.QColor(*COLOR_BG)

    def setBgColor(self, color):
        self._bg_color = color
        self.update()

    def paint(self, p, *args):
        p.setPen(QtC.Qt.NoPen)
        p.setBrush(QtG.QBrush(self._bg_color))
        p.drawRect(self.rect())
