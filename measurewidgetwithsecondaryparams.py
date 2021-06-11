from PyQt5.QtCore import pyqtSignal, QTimer

from mytools.measurewidget import MeasureWidget, MeasureTask, CancelToken
from util.file import remove_if_exists


class MeasureWidgetWithSecondaryParameters(MeasureWidget):
    secondaryChanged = pyqtSignal(dict)

    def __init__(self, parent=None, controller=None):
        super().__init__(parent=parent, controller=controller)

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
                'Fmod': [
                    'spin',
                    'Fмод=',
                    {'parent': self, 'start': 0.0, 'end': 40.0, 'step': 1.0, 'decimals': 3, 'value': 1.0, 'suffix': ' МГЦ'}
                ],
                'Umod': [
                    'spin',
                    'Uмод=',
                    {'parent': self, 'start': 0.0, 'end': 100.0, 'step': 1.0, 'decimals': 2, 'value': 30.0, 'suffix': ' %'}
                ],
                'Uoffs': [
                    'spin',
                    'Uсм=',
                    {'parent': self, 'start': -10.0, 'end': 10.0, 'step': 0.1, 'decimals': 2, 'value': 0.5, 'suffix': ' В'}
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
                'sa_span': [
                    'spin',
                    'Span=',
                    {'parent': self, 'start': 0.0, 'end': 1000.0, 'step': 1.0, 'value': 10.0, 'suffix': ' МГц'}
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
