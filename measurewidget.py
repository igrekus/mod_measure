from PyQt5 import uic
from PyQt5.QtCore import pyqtSlot, pyqtSignal, QRunnable, QThreadPool, QTimer
from PyQt5.QtWidgets import QWidget

from mytools.deviceselectwidget import DeviceSelectWidget
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

        self._paramInputWidget = DeviceSelectWidget(parent=self, params=self._controller.deviceParams)
        self._ui.layParams.insertWidget(0, self._paramInputWidget)
        self._paramInputWidget.selectedChanged.connect(self.on_selectedChanged)

        self._selectedDevice = self._paramInputWidget.selected

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
        self._paramInputWidget.enabled = True

    def _modePreCheck(self):
        self._ui.btnCheck.setEnabled(True)
        self._ui.btnMeasure.setEnabled(False)
        self._ui.btnCancel.setEnabled(False)
        self._ui.btnCalibrateLO.setEnabled(False)
        self._ui.btnCalibrateRF.setEnabled(False)
        self._paramInputWidget.enabled = True

    def _modeDuringCheck(self):
        self._ui.btnCheck.setEnabled(False)
        self._ui.btnMeasure.setEnabled(False)
        self._ui.btnCancel.setEnabled(False)
        self._ui.btnCalibrateLO.setEnabled(False)
        self._ui.btnCalibrateRF.setEnabled(False)
        self._paramInputWidget.enabled = False

    def _modePreMeasure(self):
        self._ui.btnCheck.setEnabled(False)
        self._ui.btnMeasure.setEnabled(True)
        self._ui.btnCancel.setEnabled(False)
        self._ui.btnCalibrateLO.setEnabled(True)
        self._ui.btnCalibrateRF.setEnabled(True)
        self._paramInputWidget.enabled = False

    def _modeDuringMeasure(self):
        self._ui.btnCheck.setEnabled(False)
        self._ui.btnMeasure.setEnabled(False)
        self._ui.btnCancel.setEnabled(True)
        self._ui.btnCalibrateLO.setEnabled(False)
        self._ui.btnCalibrateRF.setEnabled(False)
        self._paramInputWidget.enabled = False

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

        self._paramInputWidget.createWidgets(
            params={
                'Plo_min': [
                    'spin',
                    'Pгет мин=',
                    {'parent': self, 'start': -30.0, 'end': 30.0, 'step': 1.0, 'value': -10.0, 'suffix': ' дБм'}
                ],
                'Plo_max': [
                    'spin',
                    'Pгет макс=',
                    {'parent': self, 'start': -30.0, 'end': 30.0, 'step': 1.0, 'value': 0.0, 'suffix': ' дБм'}
                ],
                'Plo_delta': [
                    'spin',
                    'ΔPгет=',
                    {'parent': self, 'start': 0.0, 'end': 30.0, 'step': 1.0, 'value': 5.0, 'suffix': ' дБм'}
                ],
                'Flo_min': [
                    'spin',
                    'Fгет.мин=',
                    {'parent': self, 'start': 0.0, 'end': 40.0, 'step': 1.0, 'decimals': 3, 'value': 0.005, 'suffix': ' ГГЦ'}
                ],
                'Flo_max': [
                    'spin',
                    'Fгет.макс=',
                    {'parent': self, 'start': 0.0, 'end': 40.0, 'step': 1.0, 'decimals': 3, 'value': 6.005, 'suffix': ' ГГЦ'}
                ],
                'Flo_delta': [
                    'spin',
                    'ΔFгет=',
                    {'parent': self, 'start': 0.0, 'end': 40.0, 'step': 0.1, 'decimals': 3, 'value': 0.1, 'suffix': ' ГГЦ'}
                ],
                'is_Flo_div2': [
                    'check',
                    '1/2 Fгет.',
                    {'parent': self, 'is_checked': False}
                ],
                'Usrc': [
                    'spin',
                    'Uпит.=',
                    {'parent': self, 'start': 4.75, 'end': 5.25, 'step': 0.25, 'value': 5.0, 'suffix': ' В'}
                ],
                'sa_rlev': [
                    'spin',
                    'Rlev=',
                    {'parent': self, 'start': -30.0, 'end': 30.0, 'step': 1.0, 'value': 10.0, 'suffix': ' дБ'}
                ],
                'sa_scale_y': [
                    'spin',
                    'Scale y=',
                    {'parent': self, 'start': 0.0, 'end': 30.0, 'step': 1.0, 'value': 5.0, 'suffix': ' дБ'}
                ],
            }
        )

    def _connectSignals(self):
        self._paramInputWidget.secondaryChanged.connect(self.on_params_changed)

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

    def on_params_changed(self):
        self.secondaryChanged.emit(self._paramInputWidget.params)

    def updateWidgets(self, params):
        self._paramInputWidget.updateWidgets(params)
        self._connectSignals()

    def on_debounced_gui(self):
        # remove_if_exists('cal_lo.ini')
        # remove_if_exists('cal_rf.ini')
        remove_if_exists('adjust.ini')
