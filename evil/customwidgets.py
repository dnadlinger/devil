from PyQt5 import QtWidgets as QtW

class TTLExpansionSpinBox(QtW.QSpinBox):
    def textFromValue(self, value):
        dt = 1000 * 2048. / 96000000 # since we use a 11bit gated clock and want ms as unit
        return "%.2f" % (dt*value)
