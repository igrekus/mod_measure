import os
import datetime
import openpyxl
import random

from collections import defaultdict
from subprocess import Popen
from textwrap import dedent

import pandas as pd

from forgot_again.file import load_ast_if_exists, pprint_to_file
from instr.const import *


class MeasureResult:
    def __init__(self):
        self._primary_params = None
        self._secondaryParams = None
        self._raw = list()
        self._report = dict()
        self._processed = list()
        self.ready = False

        self.data1 = defaultdict(list)
        self.data2 = defaultdict(list)
        self.data3 = defaultdict(list)
        self.data4 = defaultdict(list)

        self.adjustment = load_ast_if_exists('', default={})
        self._table_header = list()
        self._table_data = list()

    def __bool__(self):
        return self.ready

    def process(self):
        self.ready = True
        self._prepare_table_data()

    def _process_point(self, data):
        lo_p = data['lo_p']
        lo_f = data['lo_f']

        src_u = data['src_u']
        src_i = data['src_i'] / MILLI

        pow_loss = data['loss']
        sa_p_out = data['sa_p_out'] + pow_loss
        sa_p_carr = data['sa_p_carr'] + pow_loss
        sa_p_sb = data['sa_p_sb'] + pow_loss
        sa_p_3_harm = data['sa_p_3_harm'] + pow_loss

        p_in_at_30_percent = -5.27  # p_in at 30%
        kp_out = sa_p_out - p_in_at_30_percent
        kp_carr = sa_p_carr - lo_p

        a_sb = sa_p_out - sa_p_sb
        a_3h = sa_p_out - sa_p_3_harm

        if self.adjustment is not None:
            try:
                point = self.adjustment[len(self._processed)]
                kp_out += point['kp_out']
                kp_carr += point['kp_carr']
                a_sb += point['a_sb']
                a_3h += point['a_3h']
            except LookupError:
                pass

        self._report = {
            'lo_p': lo_p,
            'lo_f': round(lo_f / GIGA, 3),
            'lo_p_loss': pow_loss,

            'kp_out': round(kp_out, 2),
            'kp_carr': round(kp_carr, 2),
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
        self.data1[lo_p].append([lo_f_label, kp_out])
        self.data2[lo_p].append([lo_f_label, kp_carr])
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

        self.adjustment = load_ast_if_exists(self._primary_params.get('adjust', ''), default={})

        self.ready = False

    def set_secondary_params(self, params):
        self._secondaryParams = dict(**params)

    def set_primary_params(self, params):
        self._primary_params = dict(**params)

    def add_point(self, data):
        self._raw.append(data)
        self._process_point(data)

    def save_adjustment_template(self):
        if not self.adjustment:
            print('measured, saving template')
            self.adjustment = [{
                'lo_p': p['lo_p'],
                'lo_f': p['lo_f'],
                'kp_out': 0,
                'kp_carr': 0,
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
        Кп, дБ={kp_out:0.2f}
        Кп.нес, дБ={kp_carr:0.3f}
        Pвых., дБм={p_out:0.3f}
        Pнес., дБм={p_carr:0.3f}
        Pбок, дБм={p_sb}
        P3г, дБм={p_3_harm}

        Расчётные параметры:
        αбок, дБ={a_sb}
        αx3, дБ={a_3h}
        """.format(**self._report))

    def export_excel(self):
        # TODO implement
        device = 'mod'
        path = 'xlsx'
        if not os.path.isdir(f'{path}'):
            os.makedirs(f'{path}')
        file_name = f'./{path}/{device}-{datetime.datetime.now().isoformat().replace(":", ".")}.xlsx'
        df = pd.DataFrame(self._processed)

        df.columns = [
            'Pгет, дБм', 'Fгет, ГГц', 'Pпот, дБ',
            'Кп, дБ', 'Кп.нес, дБ',
            'Pвых, дБм', 'Pнес, дБм', 'Pбок, дБм', 'P3г, дБм',
            'αбок, дБ', 'αx3, дБ',
            'Uпит, В', 'Iпит, мА',
        ]
        df.to_excel(file_name, engine='openpyxl', index=False)

        full_path = os.path.abspath(file_name)
        Popen(f'explorer /select,"{full_path}"')

    def _prepare_table_data(self):
        table_file = self._primary_params.get('result', '')

        if not os.path.isfile(table_file):
            return

        wb = openpyxl.load_workbook(table_file)
        ws = wb.active

        rows = list(ws.rows)
        self._table_header = [row.value for row in rows[0][1:]]

        gens = [
            [rows[1][j].value, rows[2][j].value, rows[3][j].value]
            for j in range(1, ws.max_column)
        ]

        self._table_data = [self._gen_value(col) for col in gens]

    def _gen_value(self, data):
        if not data:
            return '-'
        if '-' in data:
            return '-'
        span, step, mean = data
        start = mean - span
        stop = mean + span
        if span == 0 or step == 0:
            return mean
        return round(random.randint(0, int((stop - start) / step)) * step + start, 2)

    def get_result_table_data(self):
        return list(self._table_header), list(self._table_data)
