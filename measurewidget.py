from PyQt5 import uic
from PyQt5.QtCore import pyqtSlot, pyqtSignal, QRunnable, QThreadPool, QTimer
from PyQt5.QtWidgets import QWidget, QDoubleSpinBox, QCheckBox

from deviceselectwidget import DeviceSelectWidget
from util.file import remove_if_exists


class MeasureTask(QRunnable):

    def __init__(self, fn, end, token, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.end = end
        self.token = token
        self.args = args
        self.kwargs = kwargs

    def run(self):
        self.fn(self.token, *self.args, **self.kwargs)
        self.end()


class CancelToken:
    def __init__(self):
        self.cancelled = False


class MeasureWidget(QWidget):

    selectedChanged = pyqtSignal(int)
    sampleFound = pyqtSignal()
    measureComplete = pyqtSignal()
    measureStarted = pyqtSignal()
    calibrateFinished = pyqtSignal()

    def __init__(self, parent=None, controller=None):
        super().__init__(parent=parent)

        self._ui = uic.loadUi('measurewidget.ui', self)
        self._controller = controller
        self._threads = QThreadPool()

        self._devices = DeviceSelectWidget(parent=self, params=self._controller.deviceParams)
        self._ui.layParams.insertWidget(0, self._devices)
        self._devices.selectedChanged.connect(self.on_selectedChanged)

        self._selectedDevice = self._devices.selected

    def check(self):
        print('checking...')
        self._modeDuringCheck()
        self._threads.start(MeasureTask(self._controller.check,
                                        self.checkTaskComplete,
                                        self._selectedDevice))

    def checkTaskComplete(self):
        if not self._controller.present:
            print('sample not found')
            # QMessageBox.information(self, 'Ошибка', 'Не удалось найти образец, проверьте подключение')
            self._modePreCheck()
            return False

        print('found sample')
        self._modePreMeasure()
        self.sampleFound.emit()
        return True

    def calibrate(self, what):
        raise NotImplementedError

    def calibrateTaskComplete(self):
        raise NotImplementedError

    def measure(self):
        print('measuring...')
        self._modeDuringMeasure()
        self._threads.start(MeasureTask(self._controller.measure,
                                        self.measureTaskComplete,
                                        self._selectedDevice))

    def cancel(self):
        pass

    def measureTaskComplete(self):
        if not self._controller.hasResult:
            print('error during measurement')
            return False

        self._modePreCheck()
        self.measureComplete.emit()
        return True

    @pyqtSlot()
    def on_instrumentsConnected(self):
        self._modePreCheck()

    @pyqtSlot()
    def on_btnCheck_clicked(self):
        print('checking sample presence')
        self.check()

    @pyqtSlot()
    def on_btnCalibrateLO_clicked(self):
        print('start LO calibration')
        self.calibrate('LO')

    @pyqtSlot()
    def on_btnCalibrateRF_clicked(self):
        print('start RF calibration')
        self.calibrate('RF')

    @pyqtSlot()
    def on_btnMeasure_clicked(self):
        print('start measure')
        self.measureStarted.emit()
        self.measure()

    @pyqtSlot()
    def on_btnCancel_clicked(self):
        print('cancel click')
        self.cancel()

    @pyqtSlot(int)
    def on_selectedChanged(self, value):
        self._selectedDevice = value
        self.selectedChanged.emit(value)

    @pyqtSlot(bool)
    def on_grpParams_toggled(self, state):
        self._ui.widgetContainer.setVisible(state)

    def _modePreConnect(self):
        self._ui.btnCheck.setEnabled(False)
        self._ui.btnMeasure.setEnabled(False)
        self._ui.btnCancel.setEnabled(False)
        self._ui.btnCalibrateLO.setEnabled(False)
        self._ui.btnCalibrateRf.setEnabled(False)
        self._devices.enabled = True

    def _modePreCheck(self):
        self._ui.btnCheck.setEnabled(True)
        self._ui.btnMeasure.setEnabled(False)
        self._ui.btnCancel.setEnabled(False)
        self._ui.btnCalibrateLO.setEnabled(False)
        self._ui.btnCalibrateRF.setEnabled(False)
        self._devices.enabled = True

    def _modeDuringCheck(self):
        self._ui.btnCheck.setEnabled(False)
        self._ui.btnMeasure.setEnabled(False)
        self._ui.btnCancel.setEnabled(False)
        self._ui.btnCalibrateLO.setEnabled(False)
        self._ui.btnCalibrateRF.setEnabled(False)
        self._devices.enabled = False

    def _modePreMeasure(self):
        self._ui.btnCheck.setEnabled(False)
        self._ui.btnMeasure.setEnabled(True)
        self._ui.btnCancel.setEnabled(False)
        self._ui.btnCalibrateLO.setEnabled(True)
        self._ui.btnCalibrateRF.setEnabled(True)
        self._devices.enabled = False

    def _modeDuringMeasure(self):
        self._ui.btnCheck.setEnabled(False)
        self._ui.btnMeasure.setEnabled(False)
        self._ui.btnCancel.setEnabled(True)
        self._ui.btnCalibrateLO.setEnabled(False)
        self._ui.btnCalibrateRF.setEnabled(False)
        self._devices.enabled = False

    def updateWidgets(self, params):
        raise NotImplementedError


class MeasureWidgetWithSecondaryParameters(MeasureWidget):
    secondaryChanged = pyqtSignal(dict)

    def __init__(self, parent=None, controller=None):
        super().__init__(parent=parent, controller=controller)

        self._token = CancelToken()

        self._uiDebouncer = QTimer()
        self._uiDebouncer.setSingleShot(True)
        self._uiDebouncer.timeout.connect(self.on_debounced_gui)

        self._params = 0

        # region LO params
        self._spinPloMin = QDoubleSpinBox(parent=self)
        self._spinPloMin.setRange(-30, 30)
        self._spinPloMin.setSingleStep(1)
        self._spinPloMin.setValue(-10)
        self._spinPloMin.setSuffix(' дБм')
        self._devices._layout.addRow('Pгет мин=', self._spinPloMin)

        self._spinPloMax = QDoubleSpinBox(parent=self)
        self._spinPloMax.setRange(-30, 30)
        self._spinPloMax.setSingleStep(1)
        self._spinPloMax.setValue(0)
        self._spinPloMax.setSuffix(' дБм')
        self._devices._layout.addRow('Pгет макс=', self._spinPloMax)

        self._spinPloDelta = QDoubleSpinBox(parent=self)
        self._spinPloDelta.setRange(0, 30)
        self._spinPloDelta.setSingleStep(1)
        self._spinPloDelta.setValue(5)
        self._spinPloDelta.setSuffix(' дБм')
        self._devices._layout.addRow('ΔPгет=', self._spinPloDelta)

        self._spinFloMin = QDoubleSpinBox(parent=self)
        self._spinFloMin.setRange(0, 40)
        self._spinFloMin.setSingleStep(1)
        self._spinFloMin.setDecimals(3)
        self._spinFloMin.setValue(0.005)
        self._spinFloMin.setSuffix(' ГГц')
        self._devices._layout.addRow('Fгет.мин=', self._spinFloMin)

        self._spinFloMax = QDoubleSpinBox(parent=self)
        self._spinFloMax.setRange(0, 40)
        self._spinFloMax.setSingleStep(1)
        self._spinFloMax.setDecimals(3)
        self._spinFloMax.setValue(6.005)
        self._spinFloMax.setSuffix(' ГГц')
        self._devices._layout.addRow('Fгет.макс=', self._spinFloMax)

        self._spinFloDelta = QDoubleSpinBox(parent=self)
        self._spinFloDelta.setRange(0, 40)
        self._spinFloDelta.setSingleStep(0.1)
        self._spinFloDelta.setDecimals(3)
        self._spinFloDelta.setValue(0.1)
        self._spinFloDelta.setSuffix(' ГГц')
        self._devices._layout.addRow('ΔFгет=', self._spinFloDelta)

        self._checkFreqLoDiv2 = QCheckBox(parent=self)
        self._checkFreqLoDiv2.setChecked(False)
        self._devices._layout.addRow('1/2 Fгет.', self._checkFreqLoDiv2)
        # endregion

        # region power source params
        self._spinUsrc = QDoubleSpinBox(parent=self)
        self._spinUsrc.setRange(4.75, 5.25)
        self._spinUsrc.setSingleStep(0.25)
        self._spinUsrc.setValue(5)
        self._spinUsrc.setSuffix(' В')
        self._devices._layout.addRow('Uпит.=', self._spinUsrc)
        # endregion

        # region SA params
        self._spinSaRefLevel = QDoubleSpinBox(parent=self)
        self._spinSaRefLevel.setRange(-30, 30)
        self._spinSaRefLevel.setSingleStep(0.1)
        self._spinSaRefLevel.setValue(10)
        self._spinSaRefLevel.setSuffix(' дБ')
        self._devices._layout.addRow('Rlev=', self._spinSaRefLevel)

        self._spinSaScaleY = QDoubleSpinBox(parent=self)
        self._spinSaScaleY.setRange(0, 30)
        self._spinSaScaleY.setSingleStep(0.1)
        self._spinSaScaleY.setValue(5)
        self._spinSaScaleY.setSuffix(' дБ')
        self._devices._layout.addRow('Scale y=', self._spinSaScaleY)
        # endregion

    def _connectSignals(self):
        self._spinPloMin.valueChanged.connect(self.on_params_changed)
        self._spinPloMax.valueChanged.connect(self.on_params_changed)
        self._spinPloDelta.valueChanged.connect(self.on_params_changed)
        self._spinFloMin.valueChanged.connect(self.on_params_changed)
        self._spinFloMax.valueChanged.connect(self.on_params_changed)
        self._spinFloDelta.valueChanged.connect(self.on_params_changed)
        self._checkFreqLoDiv2.toggled.connect(self.on_params_changed)

        self._spinUsrc.valueChanged.connect(self.on_params_changed)

        self._spinSaRefLevel.valueChanged.connect(self.on_params_changed)
        self._spinSaScaleY.valueChanged.connect(self.on_params_changed)

    def check(self):
        print('subclass checking...')
        self._modeDuringCheck()
        self._threads.start(
            MeasureTask(
                self._controller.check,
                self.checkTaskComplete,
                self._token,
                [self._selectedDevice, self._params]
            ))

    def checkTaskComplete(self):
        res = super(MeasureWidgetWithSecondaryParameters, self).checkTaskComplete()
        if not res:
            self._token = CancelToken()
        return res

    def calibrate(self, what):
        print(f'calibrating {what}...')
        self._modeDuringMeasure()
        self._threads.start(
            MeasureTask(
                self._controller._calibrateLO if what == 'LO' else self._controller._calibrateRF,
                self.calibrateTaskComplete,
                self._token,
                [self._selectedDevice, self._params]
            ))

    def calibrateTaskComplete(self):
        print('calibrate finished')
        self._modePreMeasure()
        self.calibrateFinished.emit()

    def measure(self):
        print('subclass measuring...')
        self._modeDuringMeasure()
        self._threads.start(
            MeasureTask(
                self._controller.measure,
                self.measureTaskComplete,
                self._token,
                [self._selectedDevice, self._params]
            ))

    def measureTaskComplete(self):
        res = super(MeasureWidgetWithSecondaryParameters, self).measureTaskComplete()
        if not res:
            self._token = CancelToken()
            self._modePreCheck()
        return res

    def cancel(self):
        if not self._token.cancelled:
            if self._threads.activeThreadCount() > 0:
                print('cancelling task')
            self._token.cancelled = True

    def on_params_changed(self, value):
        if value != 1:
            self._uiDebouncer.start(5000)

        params = {
            'Plo_min': self._spinPloMin.value(),
            'Plo_max': self._spinPloMax.value(),
            'Plo_delta': self._spinPloDelta.value(),
            'Flo_min': self._spinFloMin.value(),
            'Flo_max': self._spinFloMax.value(),
            'Flo_delta': self._spinFloDelta.value(),
            'is_Flo_div2': self._checkFreqLoDiv2.isChecked(),

            'Usrc': self._spinUsrc.value(),

            'sa_rlev': self._spinSaRefLevel.value(),
            'sa_scale_y': self._spinSaScaleY.value(),
        }
        self.secondaryChanged.emit(params)

    def updateWidgets(self, params):
        self._spinPloMin.setValue(params['Plo_min'])
        self._spinPloMax.setValue(params['Plo_max'])
        self._spinPloDelta.setValue(params['Plo_delta'])
        self._spinFloMin.setValue(params['Flo_min'])
        self._spinFloMax.setValue(params['Flo_max'])
        self._spinFloDelta.setValue(params['Flo_delta'])
        self._checkFreqLoDiv2.setChecked(params['is_Flo_div2'])
        self._spinUsrc.setValue(params['Usrc'])
        self._spinSaRefLevel.setValue(params['sa_rlev'])
        self._spinSaScaleY.setValue(params['sa_scale_y'])

        self._connectSignals()

    def on_debounced_gui(self):
        # remove_if_exists('cal_lo.ini')
        # remove_if_exists('cal_rf.ini')
        remove_if_exists('adjust.ini')
