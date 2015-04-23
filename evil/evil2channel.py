from PyQt5 import QtCore as QtC
from PyQt5 import QtWidgets as QtW
from PyQt5 import uic
from evil.channel import Channel, Register
from evil.controlpanel import ControlPanel

RELOCK_THRESHOLD_REG_IDX = 10

PID_RST_N = 1 << 0
RAMP_RST_N = 1 << 1
OUTPUT_SEL = 1 << 2
PID_POLARITY = 1 << 3
LD_ON = 1 << 4
SWEEPING_MASK = PID_RST_N | RAMP_RST_N | OUTPUT_SEL
SWEEPING_STATE = RAMP_RST_N | OUTPUT_SEL


class Evil2Channel(Channel):
    STREAM_NAMES = [
        'ADC (error signal)',
        'PID/ramp output',
        'Relocking slow lowpass filter',
        'Relocking filter difference (relocking)'
    ]

    def __init__(self, zmq_ctx, host_addr, resource):
        Channel.__init__(self, zmq_ctx, host_addr, resource)

        self._system_control_reg = Register(0)

        self._widget_name_to_reg = {
            'centerSpinBox': Register(1, True),
            'rangeSpinBox': Register(2),
            'frequencySpinBox': Register(3),
            'inputOffsetSpinBox': Register(4, True),
            'outputOffsetSpinBox': Register(5, True),
            'pGainSpinBox': Register(6),
            'iGainSpinBox': Register(7),
            'dGainSpinBox': Register(8),
            'filterResponseSpinBox': Register(9, True),
            'thresholdSpinBox': Register(RELOCK_THRESHOLD_REG_IDX),
            'ttlExpSpinBox': Register(11)
        }

    def _registers(self):
        regs = list(self._widget_name_to_reg.values())
        regs.append(self._system_control_reg)
        return regs

    def _create_control_panel(self):
        reg_area = Evil2RegisterArea(self._system_control_reg, self._widget_name_to_reg)
        c = ControlPanel(self.STREAM_NAMES, reg_area)
        return c


class Evil2RegisterArea(QtW.QWidget):
    extra_plot_items_changed = QtC.pyqtSignal(dict)

    def __init__(self, system_control_reg, register_name_map):
        QtW.QWidget.__init__(self)

        uic.loadUi('ui/evil2registerarea.ui', self)

        self._system_control_reg = system_control_reg
        self._set_control_flags(system_control_reg.sval)
        system_control_reg.changed_remotely.connect(self._set_control_flags)

        for widget_name, register in register_name_map.items():
            widget = getattr(self, widget_name)
            register.changed_remotely.connect(widget.setValue)
            widget.setValue(register.sval)
            widget.valueChanged.connect(register.set_from_local_change)

        self.sweepButton.clicked.connect(self.toggle_sweep)
        self.flipPolarityButton.clicked.connect(self.toggle_polarity)
        self.resetPidButton.clicked.connect(self.pid_reset)
        self.relockingEnabledCheckBox.clicked.connect(self.toggle_relocking)
        self.thresholdSpinBox.valueChanged.connect(self.emit_extra_plot_items_changed)

    def _set_control_flags(self, flags):
        self._control_flags = flags
        self.relockingEnabledCheckBox.setChecked(flags & LD_ON)

        if flags & PID_POLARITY:
            self.flipPolarityButton.setStyleSheet('QPushButton {color: blue}')
        else:
            self.flipPolarityButton.setStyleSheet('QPushButton {color: green}')

        if (flags & SWEEPING_MASK) == SWEEPING_STATE:
            self.sweepButton.setText('Sweeping')
            self.sweepButton.setStyleSheet('QPushButton {color: green}')
        else:
            self.sweepButton.setText('Controlling')
            self.sweepButton.setStyleSheet('QPushButton {color: blue}')

    def emit_extra_plot_items_changed(self, value):
        value = {RELOCK_THRESHOLD_REG_IDX: {'threshold': value}}
        self.extra_plot_items_changed.emit(value)

    def pid_reset(self):
        self.pid_off()
        self.pid_on()

    def toggle_relocking(self):
        self._control_flags ^= LD_ON
        self._system_control_reg.set_from_local_change(self._control_flags)

    def toggle_polarity(self):
        pid_was_on = self.pid_off()

        self._control_flags ^= PID_POLARITY
        self._system_control_reg.set_from_local_change(self._control_flags)

        if pid_was_on:
            self.pid_on()

    def toggle_sweep(self):
        # Only read one bit here but write all to be resilient against invalid
        # states (e.g. when somebody loads an old parameter save file).
        sweeping = self._control_flags & OUTPUT_SEL
        self._control_flags &= ~SWEEPING_MASK

        if sweeping:
            self._control_flags |= ((~SWEEPING_STATE) & SWEEPING_MASK)
        else:
            self._control_flags |= (SWEEPING_STATE & SWEEPING_MASK)

        self._system_control_reg.set_from_local_change(self._control_flags)

    def pid_off(self):
        if not (self._control_flags & PID_RST_N):
            return False

        self._control_flags &= ~PID_RST_N
        self._system_control_reg.set_from_local_change(self._control_flags)
        return True

    def pid_on(self):
        self._control_flags |= PID_RST_N
        self._system_control_reg.set_from_local_change(self._control_flags)
