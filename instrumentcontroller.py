import ast
import time

import numpy as np

from collections import defaultdict
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal

from instr.instrumentfactory import mock_enabled, GeneratorFactory, SourceFactory, MultimeterFactory, AnalyzerFactory
from measureresult import MeasureResult
from util.file import load_ast_if_exists, pprint_to_file


class InstrumentController(QObject):
    pointReady = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        addrs = load_ast_if_exists('instr.ini', default={
            'Анализатор': 'GPIB1::18::INSTR',
            'P LO': 'GPIB1::6::INSTR',
            'Источник': 'GPIB1::3::INSTR',
            'Мультиметр': 'GPIB1::22::INSTR',
        })

        self.requiredInstruments = {
            'Анализатор': AnalyzerFactory(addrs['Анализатор']),
            'P LO': GeneratorFactory(addrs['P LO']),
            'Источник': SourceFactory(addrs['Источник']),
            'Мультиметр': MultimeterFactory(addrs['Мультиметр']),
        }

        self.deviceParams = {
            'Модулятор': {
                'F': 1,
            },
        }

        self.secondaryParams = load_ast_if_exists('params.ini', default={
            'Plo_min': -10.0,
            'Plo_max': 0.0,
            'Plo_delta': 5.0,
            'Flo_min': 0.05,
            'Flo_max': 6.05,
            'Flo_delta': 0.1,
            'is_Flo_div2': False,
            'Fmod': 1.0,   # MHz
            'Umod': 30,   # %
            'Uoffs': 250,   # mV
            'Usrc': 5.0,
            'sa_rlev': 10.0,
            'sa_scale_y': 5.0,
            'sa_span': 10.0,   # MHz
        })

        self._calibrated_pows_lo = load_ast_if_exists('cal_lo.ini', default={})
        self._calibrated_pows_rf = load_ast_if_exists('cal_rf.ini', default={})

        self._instruments = dict()
        self.found = False
        self.present = False
        self.hasResult = False
        self.only_main_states = False

        self.result = MeasureResult()

    def __str__(self):
        return f'{self._instruments}'

    def connect(self, addrs):
        print(f'searching for {addrs}')
        for k, v in addrs.items():
            self.requiredInstruments[k].addr = v
        self.found = self._find()

    def _find(self):
        self._instruments = {
            k: v.find() for k, v in self.requiredInstruments.items()
        }
        return all(self._instruments.values())

    def check(self, token, params):
        print(f'call check with {token} {params}')
        device, secondary = params
        self.present = self._check(token, device, secondary)
        print('sample pass')

    def _check(self, token, device, secondary):
        print(f'launch check with {self.deviceParams[device]} {self.secondaryParams}')
        self._init()
        return True

    def calibrate(self, token, params):
        print(f'call calibrate with {token} {params}')
        return self._calibrate(token, self.secondaryParams)

    def _calibrateLO(self, token, secondary):
        print('run calibrate LO with', secondary)

        gen_lo = self._instruments['P LO']
        sa = self._instruments['Анализатор']

        secondary = self.secondaryParams

        pow_lo_start = secondary['Plo_min']
        pow_lo_end = secondary['Plo_max']
        pow_lo_step = secondary['Plo_delta']
        freq_lo_start = secondary['Flo_min']
        freq_lo_end = secondary['Flo_max']
        freq_lo_step = secondary['Flo_delta']
        freq_lo_div2 = secondary['is_Flo_div2']

        pow_lo_values = [round(x, 3) for x in np.arange(start=pow_lo_start, stop=pow_lo_end + 0.002, step=pow_lo_step)] \
            if pow_lo_start != pow_lo_end else [pow_lo_start]
        freq_lo_values = [round(x, 3) for x in
                          np.arange(start=freq_lo_start, stop=freq_lo_end + 0.0001, step=freq_lo_step)]

        sa.send(':CAL:AUTO OFF')
        sa.send(':SENS:FREQ:SPAN 1MHz')
        sa.send(f'DISP:WIND:TRAC:Y:RLEV 10')
        sa.send(f'DISP:WIND:TRAC:Y:PDIV 5')

        gen_lo.send(f':OUTP:MOD:STAT OFF')

        sa.send(':CALC:MARK1:MODE POS')

        result = defaultdict(dict)
        for pow_lo in pow_lo_values:
            gen_lo.send(f'SOUR:POW {pow_lo}dbm')

            for freq in freq_lo_values:

                if freq_lo_div2:
                    freq /= 2

                if token.cancelled:
                    gen_lo.send(f'OUTP:STAT OFF')
                    time.sleep(0.5)

                    gen_lo.send(f'SOUR:POW {pow_lo}dbm')

                    gen_lo.send(f'SOUR:FREQ {freq_lo_start}GHz')
                    raise RuntimeError('calibration cancelled')

                gen_lo.send(f'SOUR:FREQ {freq}GHz')
                gen_lo.send(f'OUTP:STAT ON')

                if not mock_enabled:
                    time.sleep(0.35)

                sa.send(f':SENSe:FREQuency:CENTer {freq}GHz')
                sa.send(f':CALCulate:MARKer1:X:CENTer {freq}GHz')

                if not mock_enabled:
                    time.sleep(0.35)

                pow_read = float(sa.query(':CALCulate:MARKer:Y?'))
                loss = abs(pow_lo - pow_read)
                if mock_enabled:
                    loss = 10

                print('loss: ', loss)
                result[pow_lo][freq] = loss

        result = {k: v for k, v in result.items()}
        pprint_to_file('cal_lo.ini', result)

        gen_lo.send(f'OUTP:STAT OFF')
        sa.send(':CAL:AUTO ON')
        self._calibrated_pows_lo = result
        return True

    def _calibrateRF(self, token, secondary):
        print('run empty calibrate RF')
        gen = self._instruments['P LO']

        result = dict()
        pprint_to_file('cal_rf.ini', result)

        self._calibrated_pows_rf = result
        return True

    def measure(self, token, params):
        print(f'call measure with {token} {params}')
        device, _ = params
        try:
            self.result.set_secondary_params(self.secondaryParams)
            self._measure(token, device)
            # self.hasResult = bool(self.result)
            self.hasResult = True  # HACK
        except RuntimeError as ex:
            print('runtime error:', ex)

    def _measure(self, token, device):
        param = self.deviceParams[device]
        secondary = self.secondaryParams
        print(f'launch measure with {token} {param} {secondary}')

        self._clear()
        self._measure_s_params(token, param, secondary)
        return True

    def _clear(self):
        self.result.clear()

    def _init(self):
        self._instruments['P LO'].send('*RST')
        self._instruments['Источник'].send('*RST')
        self._instruments['Мультиметр'].send('*RST')
        self._instruments['Анализатор'].send('*RST')

    def _measure_s_params(self, token, param, secondary):
        gen_lo = self._instruments['P LO']
        src = self._instruments['Источник']
        mult = self._instruments['Мультиметр']
        sa = self._instruments['Анализатор']

        lo_pow_start = secondary['Plo_min']
        lo_pow_end = secondary['Plo_max']
        lo_pow_step = secondary['Plo_delta']
        lo_f_start = secondary['Flo_min']
        lo_f_end = secondary['Flo_max']
        lo_f_step = secondary['Flo_delta']

        lo_f_is_div2 = secondary['is_Flo_div2']

        mod_f = secondary['Fmod']
        mod_u = secondary['Umod']
        mod_u_offs = secondary['Uoffs'] / 1_000

        src_u = secondary['Usrc']
        src_i_max = 200   # mA

        sa_rlev = secondary['sa_rlev']
        sa_scale_y = secondary['sa_scale_y']
        sa_span = secondary['sa_span']

        pow_lo_values = [
            round(x, 3)for x in
            np.arange(start=lo_pow_start, stop=lo_pow_end + 0.002, step=lo_pow_step)
        ] if lo_pow_start != lo_pow_end else [lo_pow_start]

        freq_lo_values = [
            round(x, 3) for x in
            np.arange(start=lo_f_start, stop=lo_f_end + 0.0001, step=lo_f_step)
        ]

        gen_lo.send(f':OUTP:MOD:STAT OFF')

        sa.send(':CAL:AUTO OFF')
        sa.send(':SENS:FREQ:SPAN 1MHz')
        sa.send(f'DISP:WIND:TRAC:Y:RLEV {sa_rlev}')
        sa.send(f'DISP:WIND:TRAC:Y:PDIV {sa_scale_y}')
        sa.send(':CALC:MARK1:MODE POS')

        src.send(f'APPLY p6v,{src_u}V,{src_i_max}mA')

        if mock_enabled:
            # with open('./mock_data/meas_1_-10-5db.txt', mode='rt', encoding='utf-8') as f:
            with open('./mock_data/meas_1_-10db.txt', mode='rt', encoding='utf-8') as f:
                index = 0
                mocked_raw_data = ast.literal_eval(''.join(f.readlines()))

        res = []
        for pow_lo in pow_lo_values:

            for freq_lo in freq_lo_values:

                if lo_f_is_div2:
                    freq_lo /= 2

                if token.cancelled:
                    gen_lo.send(f'OUTP:STAT OFF')
                    time.sleep(0.5)
                    src.send('OUTPut OFF')

                    gen_lo.send(f'SOUR:POW {lo_pow_start}dbm')
                    gen_lo.send(f'SOUR:FREQ {lo_f_start}GHz')
                    raise RuntimeError('measurement cancelled')

                gen_lo.send(f'SOUR:POW {round(pow_lo + self._calibrated_pows_lo.get(pow_lo, dict()).get(freq_lo, 0) * 2, 2)}dbm')
                gen_lo.send(f'SOUR:FREQ {freq_lo}GHz')

                # TODO hoist out of the loops
                src.send('OUTPut ON')

                gen_lo.send(f'OUTP:STAT ON')

                # time.sleep(0.5)
                if not mock_enabled:
                    time.sleep(2)

                lo_p_read = float(gen_lo.query('SOUR:POW?'))
                lo_f_read = float(gen_lo.query('SOUR:FREQ?'))

                src_u_read = src_u
                src_i_read = float(mult.query('MEAS:CURR:DC? 1A,DEF'))

                sa_p_out = 10   # @f_out = lo_f + mod_f
                sa_p_carr = 11   # @f_carr = lo_f
                sa_p_sb = 12   # @f_sb = lo_f - mod_f
                sa_p_mod_f_x3 = 13   # @f_x3 = lo_sb - 3*f_mod

                raw_point = {
                    'lo_p': lo_p_read,
                    'lo_f': lo_f_read,
                    'src_u': src_u_read,   # power source voltage as set in GUI
                    'src_i': src_i_read,
                    'sa_p_out': sa_p_out,
                    'sa_p_carr': sa_p_carr,
                    'sa_p_sb': sa_p_sb,
                    'sa_p_mod_f_x3': sa_p_mod_f_x3,
                }

                if mock_enabled:
                    raw_point = mocked_raw_data[index]
                    index += 1

                print(raw_point)
                self._add_measure_point(raw_point)

                res.append(raw_point)

        gen_lo.send(f'OUTP:STAT OFF')
        time.sleep(0.5)
        src.send('OUTPut OFF')

        gen_lo.send(f'SOUR:POW {lo_pow_start}dbm')
        gen_lo.send(f'SOUR:FREQ {lo_f_start}GHz')

        if not mock_enabled:
            with open('out.txt', mode='wt', encoding='utf-8') as f:
                f.write(str(res))

        return res

    def _add_measure_point(self, data):
        print('measured point:', data)
        self.result.add_point(data)
        self.pointReady.emit()

    def saveConfigs(self):
        pprint_to_file('params.ini', self.secondaryParams)

    @pyqtSlot(dict)
    def on_secondary_changed(self, params):
        self.secondaryParams = params

    @property
    def status(self):
        return [i.status for i in self._instruments.values()]
