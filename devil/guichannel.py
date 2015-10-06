class GuiChannel:
    def __init__(self, channel, create_control_panel_fn):
        self.channel = channel
        self._create_control_panel_fn = create_control_panel_fn
        self._control_panel = None

    def show_control_panel(self):
        if self._control_panel:
            self._control_panel.activateWindow()
            self._control_panel.raise_()
        else:
            self._control_panel = self._create_control_panel_fn(self.channel)
            self._control_panel.closed.connect(self._destroy_control_panel)

            # Channel -> Control Panel connections
            self.channel.stream_packet_received.connect(
                self._control_panel.got_stream_packet)
            self.channel.stream_acquisition_config_changed.connect(
                self._control_panel.set_stream_acquisition_config)
            self.channel.shutting_down.connect(self._control_panel.disconnected)

            self.channel.status_changed.connect(
                lambda s: self._set_trigger_from_status(s))
            self._set_trigger_from_status(self.channel.current_status())

            # Control Panel -> channel connections
            self._control_panel.set_stream_acquisition_config(
                *self.channel.stream_acquisition_config())
            self._control_panel.stream_acquisition_config_changed.connect(
                self.channel.set_stream_acquisition_config)
            self._control_panel.stream_subscription_added.connect(
                self.channel.add_stream_subscription)
            for c in self._control_panel.active_stream_channels():
                self.channel.add_stream_subscription(c)
            self._control_panel.stream_subscription_removed.connect(
                self.channel.remove_stream_subscription)

            self._control_panel.show()

    def _destroy_control_panel(self):
        self._control_panel.deleteLater()
        self._control_panel = None

    def _set_trigger_from_status(self, status):
        if self._control_panel:
            self._control_panel.set_can_trigger_streams(
                status == self.channel.Status.configuring)
