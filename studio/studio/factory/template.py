"""One geometric template; indexed sub-operation quantities and completion times."""
from bisect import bisect_right
from itertools import groupby
import math
import numpy as np
from ..simulation.resources import ATTENDED
from ..simulation.engine import path_position

COLUMNS = ('zund_kwh', 'pfaff_kwh', 'vacuum_kwh', 'veit_kwh', 'qc_kwh', 'labour_s', 'equipment_eur',
           'thread_m', 'body_m2', 'rib_m2', 'fabric_eur', 'cut_length_mm',
           'travel_mm', 'mark_length_mm', 'sewn_length_mm', 'stitches',
           'collected_pieces', 'seams_complete', 'pressed', 'inspected')
COL = {name: i for i, name in enumerate(COLUMNS)}
METRICS = COLUMNS[COL['cut_length_mm']:]
COUNTS = ('stitches', 'collected_pieces', 'seams_complete', 'pressed', 'inspected')


def local_time(row, t):
    if t >= row['end_s']: return row['template_end_s']
    if t <= row['start_s']: return row['template_start_s']
    if row['kind'] == 'template':
        # Translation preserves operation boundaries for the no-wait template.
        return min(row['template_end_s'],t+(row['template_start_s']-row['start_s']))
    f = (t-row['start_s'])/(row['end_s']-row['start_s'])
    return row['template_start_s']+(row['template_end_s']-row['template_start_s'])*f


def compile_template(plan):
    def key(op):
        station = 'transport' if op['kind'] == 'transfer_to_sewing' else op.get('machine_id', 'zund')
        return station, op['window'], op['kind'] in ATTENDED
    segments = []
    for (station, window, attended), group in groupby(plan['operations'], key):
        ops = list(group)
        segments.append({'id': len(segments), 'station': station, 'window': window,
                         'attended': attended, 'start_s': ops[0]['start_s'],
                         'end_s': ops[-1]['end_s'], 'first_op': ops[0]['index'],
                         'last_op': ops[-1]['index']})
    linear, jumps, prefix = [], [], [np.zeros(len(COLUMNS))]
    vacuum, vacuum_end, pieces, seams, path_ends = False, [], {}, {}, []
    seam_by_id = {s['id']: s for s in plan['sewing_seams']}
    for op, row in zip(plan['operations'], plan['resource_ledger']):
        a, b = np.zeros(len(COLUMNS)), np.zeros(len(COLUMNS))
        kind, end = op['kind'], op['end_s']
        if kind != 'transfer_to_sewing':
            for name, value in ((row['machine']+'_kwh', row['machine_kwh']),
                                ('vacuum_kwh', row['vacuum_kwh']), ('labour_s', row['labour_s']),
                                ('equipment_eur', row['equipment_eur']), ('thread_m', row['thread_m'])):
                a[COL[name]] = value
            b[COL['thread_m']] = row['tail_m_at_end']
            b[COL[row['material']+'_m2']] = row['area_m2_at_end']
            b[COL['fabric_eur']] = row['fabric_eur_at_end']
        if op['path_id'] is not None:
            name = 'cut_length_mm' if kind.startswith('cut') else 'travel_mm' if kind == 'travel' else 'mark_length_mm'
            a[COL[name]] = plan['paths'][op['path_id']]['distance_mm']
            path_ends.append([end, op['path_id']])
        if kind == 'cut_outer':
            pieces.setdefault(op['piece_id'], {}).update(cut_start=op['start_s'], cut_end=end)
        if kind == 'pickup':
            pieces.setdefault(op['piece_id'], {})['pickup'] = end
            b[COL['collected_pieces']] = 1
        if kind == 'stitch':
            seam = seam_by_id[op['seam_id']]
            a[COL['sewn_length_mm']] = seam['length_mm']
            a[COL['stitches']] = seam['stitches']
            seams.setdefault(seam['id'], {}).update(start=op['start_s'], end=end)
        if kind == 'thread_trim':
            seams.setdefault(op['seam_id'], {})['trim'] = end
            b[COL['seams_complete']] = 1
        if kind == 'vacuum_on': vacuum = True
        if kind == 'vacuum_off': vacuum = False
        vacuum_end.append(vacuum)
        linear.append(a.tolist()); jumps.append(b.tolist()); prefix.append(prefix[-1]+a+b)
    return {'segments': segments, 'ends': [o['end_s'] for o in plan['operations']],
            'prefix': [v.tolist() for v in prefix], 'linear': linear, 'jumps': jumps,
            'vacuum_end': vacuum_end, 'piece_times': pieces, 'seam_times': seams,
            'path_ends': [x[0] for x in path_ends], 'path_ids': [x[1] for x in path_ends]}


class TemplateIndex:
    def __init__(self, plan, index):
        self.plan, self.index = plan, index
        self.ends = index['ends']
        self.prefix, self.linear = np.asarray(index['prefix']), np.asarray(index['linear'])

    def local_at(self,row,t):
        local = local_time(row,t)
        if row['kind'] != 'template' or row['start_s'] == row['template_start_s']:
            return local
        # A shifted segment can lose a few ULPs when translated back. Resolve
        # boundaries against their forward-mapped factory time, so a completed
        # pickup/trim is neither delayed nor charged before that time.
        i = bisect_right(self.ends,local)
        tolerance = 4*max(math.ulp(t),math.ulp(row['start_s']),math.ulp(local))
        for j in (i-1,i):
            if not 0 <= j < len(self.ends): continue
            boundary = self.ends[j]
            if not row['template_start_s'] < boundary < row['template_end_s']: continue
            if abs(local-boundary)>tolerance: continue
            world_boundary = row['start_s']+(boundary-row['template_start_s'])
            if t == world_boundary: return boundary
            if t < world_boundary and local >= boundary: return math.nextafter(boundary,-math.inf)
            if t > world_boundary and local < boundary: return math.nextafter(boundary,math.inf)
        return local

    def at(self, t):
        i = bisect_right(self.ends, t)
        result = self.prefix[i].copy()
        if i < len(self.ends):
            op = self.plan['operations'][i]
            f = max(0., (t-op['start_s'])/(op['end_s']-op['start_s']))
            delta = self.linear[i]*f
            delta[COL['stitches']] = math.floor(delta[COL['stitches']]+1e-8)
            result += delta
        return result

    def vacuum_at_boundary(self, t):
        i = bisect_right(self.ends, t)
        return bool(i and self.index['vacuum_end'][i-1])

    def detail(self, t):
        t = max(0., min(t, self.ends[-1]))
        i = min(len(self.ends)-1, bisect_right(self.ends, t))
        op = self.plan['operations'][i]
        f = min(1., max(0., (t-op['start_s'])/(op['end_s']-op['start_s'])))
        piece_states = {}
        seam_states = {k: 'sewn' if t >= v['trim'] else 'stitched' if t >= v['end'] else
                       'sewing' if t >= v['start'] else 'waiting' for k,v in self.index['seam_times'].items()}
        for piece in self.plan['pieces']:
            v = self.index['piece_times'][piece['id']]
            state = ('collected' if t >= v['pickup'] else 'cut' if t >= v['cut_end'] else
                     'cutting' if t >= v['cut_start'] else 'waiting')
            relevant = [s['id'] for s in self.plan['sewing_seams'] if piece['id'] in s['piece_ids']]
            if relevant and all(seam_states[k] == 'sewn' for k in relevant): state = 'sewn'
            elif any(seam_states[k] != 'waiting' for k in relevant): state = 'sewing'
            piece_states[piece['id']] = state
        return {'template_time_s': t, 'operation_index': i, 'operation': op['kind'],
                'operation_progress': f, 'window': op['window'], 'tool': op['tool'],
                'head_mm': path_position(self.plan['paths'][op['path_id']], f) if op['path_id'] is not None else op['head_mm'],
                'path_id': op['path_id'], 'path_progress': f,
                'completed_paths': self.index['path_ids'][:bisect_right(self.index['path_ends'],t)],
                'vacuum': self.vacuum_at_boundary(t), 'pieces': piece_states, 'seams': seam_states}
