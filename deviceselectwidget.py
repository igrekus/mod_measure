from PyQt5.QtCore import pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QWidget, QComboBox, QFormLayout, QDoubleSpinBox, QCheckBox


class DeviceSelectWidget(QWidget):

    selectedChanged = pyqtSignal(int)
    secondaryChanged = pyqtSignal()

    def __init__(self, parent=None, params=None):
        super().__init__(parent=parent)

        self._layout = QFormLayout()
        self._combo = QComboBox()

        for i, label in enumerate(params.keys()):
            self._combo.addItem(label)

        self._layout.addRow('Прибор', self._combo)

        self.setLayout(self._layout)

        self._combo.setCurrentIndex(0)
        self._combo.currentIndexChanged.connect(self.on_indexChanged)

        self._enabled = True
        self._secondaryParamWidgets = {}
        self._secondaryParams = {}

    @property
    def selected(self):
        return self._combo.currentText()

    @pyqtSlot(int)
    def on_indexChanged(self, text):
        print(text)
        self.selectedChanged.emit(text)

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        self._combo.setEnabled(value)

    def addParam(self, label, widget):
        self._layout.addRow(label, widget)

    def createWidgets(self, params: dict):
        makers = {
            'spin': _make_double_spinbox,
            'check': _make_checkbox,
        }
        for key, settings in params.items():
            make, label, args = settings
            widget = makers[make](**args)
            if make == 'check':
                widget.value = widget.isChecked
                widget.valueChanged = widget.toggled
                widget.setValue = widget.setChecked

            self._secondaryParamWidgets[key] = widget
            self._layout.addRow(label, widget)

            widget.valueChanged.connect(self.on_params_changed)

    def on_params_changed(self, value):
        self.secondaryChanged.emit()

    def updateWidgets(self, params):
        for key, value in params.items():
            self._secondaryParamWidgets[key].setValue(value)

    @property
    def params(self):
        return {k: w.value() for k, w in self._secondaryParamWidgets.items()}


def _make_double_spinbox(parent, start=0.0, end=1.0, step=0.1, decimals=2, value=0.1, suffix=''):
    spinbox = QDoubleSpinBox(parent=parent)
    spinbox.setRange(start, end)
    spinbox.setSingleStep(step)
    spinbox.setDecimals(decimals)
    spinbox.setValue(value)
    spinbox.setSuffix(suffix)
    return spinbox


def _make_checkbox(parent, is_checked):
    checkbox = QCheckBox(parent=parent)
    checkbox.setChecked(is_checked)
    return checkbox
