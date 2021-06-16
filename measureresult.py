import os
import datetime

from collections import defaultdict
from subprocess import Popen
from textwrap import dedent

import pandas as pd

from util.file import load_ast_if_exists, pprint_to_file
from util.const import *


class MeasureResult:
    def __init__(self):
        self._secondaryParams = None
        self._raw = list()
        self._report = dict()
        self._processed = list()
        self.ready = False

        self.data1 = defaultdict(list)
        self.data2 = defaultdict(list)
        self.data3 = defaultdict(list)
        self.data4 = defaultdict(list)

        self.adjustment = load_ast_if_exists('adjust.ini', default=None)

    def __bool__(self):
        return self.ready

    def _process(self):
        self.ready = True

    def _process_point(self, data):
        lo_p = data['lo_p']
        lo_f = data['lo_f']

        src_u = data['src_u']
        src_i = data['src_i']

        pow_loss = data['loss']
        sa_p_out = data['sa_p_out'] + pow_loss
        sa_p_carr = data['sa_p_carr'] + pow_loss
        sa_p_sb = data['sa_p_sb'] + pow_loss
        sa_p_3_harm = data['sa_p_3_harm'] + pow_loss

        a_sb = sa_p_out - sa_p_sb
        a_3h = sa_p_out - sa_p_3_harm

        if self.adjustment is not None:
            point = self.adjustment[len(self._processed)]
            sa_p_out += point['p_out']
            sa_p_carr += point['p_carr']
            a_sb += point['a_sb']
            a_3h += point['a_3h']

        self._report = {
            'lo_p': lo_p,
            'lo_f': round(lo_f / GIGA, 3),
            'lo_p_loss': pow_loss,

            'p_out': round(sa_p_out, 2),
            'p_carr': round(sa_p_carr, 2),
            'p_sb': round(sa_p_sb, 2),
            'p_3_harm': round(sa_p_3_harm, 2),

            'a_sb': round(a_sb, 2),
            'a_3h': round(a_3h, 2),

            'src_u': src_u,
            'src_i': round(src_i, 2),
        }

        lo_f_label = lo_f / GIGA
        self.data1[lo_p].append([lo_f_label, sa_p_out])
        self.data2[lo_p].append([lo_f_label, sa_p_carr])
        self.data3[lo_p].append([lo_f_label, a_sb])
        self.data4[lo_p].append([lo_f_label, a_3h])
        self._processed.append({**self._report})

    def clear(self):
        self._secondaryParams.clear()
        self._raw.clear()
        self._report.clear()
        self._processed.clear()

        self.data1.clear()
        self.data2.clear()
        self.data3.clear()
        self.data4.clear()

        self.ready = False

    def set_secondary_params(self, params):
        self._secondaryParams = dict(**params)

    def add_point(self, data):
        self._raw.append(data)
        self._process_point(data)

    def save_adjustment_template(self):
        if self.adjustment is None:
            print('measured, saving template')
            self.adjustment = [{
                'lo_p': p['lo_p'],
                'lo_f': p['lo_f'],
                'p_out': 0,
                'p_carr': 0,
                'a_sb': 0,
                'a_3h': 0,

            } for p in self._processed]
            pprint_to_file('adjust.ini', self.adjustment)

    @property
    def report(self):
        return dedent("""        Генератор:
        Pгет, дБм={lo_p}
        Fгет, ГГц={lo_f:0.2f}
        Pпот, дБ={lo_p_loss:0.2f}
        
        Источник питания:
        U, В={src_u}
        I, мА={src_i}

        Анализатор:
        Pвых, дБм={p_out:0.3f}
        Pнес, дБм={p_carr:0.3f}
        Pбок, дБм={p_sb}
        P3г, дБм={p_3_harm}
        
        Расчётные параметры:
        αбок, дБ={a_sb}
        αx3, дБ={a_3h}
        """.format(**self._report))

    def export_excel(self):
        # TODO implement
        device = 'demod'
        path = 'xlsx'
        if not os.path.isdir(f'{path}'):
            os.makedirs(f'{path}')
        file_name = f'./{path}/{device}-{datetime.datetime.now().isoformat().replace(":", ".")}.xlsx'
        df = pd.DataFrame(self._processed)

        df.columns = [
            'Pгет, дБм', 'Fгет, ГГц',
            'Pвх, дБм', 'Fвх, ГГц',
            'Uпит, В', 'Iпит, мА',
            'UI, мВ', 'UQ, мВ',
            'Δφ, º', 'Fосц, ГГц',
            'Fпч, МГц', 'αош, мВ',
            'Pпч, дБм', 'Кп, дБм',
            'αош, раз', 'αош, дБ',
            'φош, º', 'αзк, дБ',
            'Потери, дБ',
        ]
        df.to_excel(file_name, engine='openpyxl', index=False)

        full_path = os.path.abspath(file_name)
        Popen(f'explorer /select,"{full_path}"')
