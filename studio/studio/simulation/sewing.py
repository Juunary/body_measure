"""Paired seam paths and deterministic lockstitch research assembly.

This models feed kinematics, not cloth mechanics or industrial knit finishing.
Coordinates are in each un-nested pattern piece's local millimetres.
"""
import math
from shapely.geometry import LineString
from shapely.ops import substring
from .geometry import length


def schedule(pieces, config, operations, start_s, window):
    by_id = {p['id']: p for p in pieces}
    seams = []
    m = config.machine
    clock = start_s

    def edge(piece, name):
        return by_id[piece]['seams'][name]

    def add(key, a, points_a, b=None, points_b=None, ratio=1):
        distance = length(points_a)
        if points_b is not None and abs(length(points_b)-distance*ratio) > .5:
            raise ValueError(f'{key}: sewing seam mismatch; check paired pattern edges')
        stitches = math.ceil(distance/m.stitch_length_mm)
        seams.append({'id': key, 'piece_ids': [a]+([b] if b and b != a else []),
                      'sides': [{'piece_id': a, 'points': points_a}]+
                               ([{'piece_id': b, 'points': points_b}] if b else []),
                      'length_mm': distance, 'feed_ratio': ratio, 'stitches': stitches,
                      'actual_stitch_mm': distance/stitches})

    for side in ('left', 'right'):
        add('placket_'+side, 'front', edge('front','placket'), 'placket_'+side, edge('placket_'+side,'long_edge'))
    for side in ('left', 'right'):
        add('shoulder_'+side, 'front', edge('front','shoulder_'+side), 'back', edge('back','shoulder_'+side))
    neckline_total = sum(length(edge(p,'neckline')) for p in ('front','back'))
    collar = LineString(edge('collar','attach'))
    offset = 0.
    for p in ('front','back'):
        end = offset+length(edge(p,'neckline'))/neckline_total
        section = [list(p) for p in substring(collar,offset,min(1.,end),normalized=True).coords]
        add('collar_'+p, p, edge(p,'neckline'), 'collar', section, config.design.rib_ratio)
        offset = end
    for side in ('left','right'):
        sleeve = 'sleeve_'+side
        for body in ('front','back'):
            add('armhole_'+side+'_'+body,body,edge(body,'armhole_'+side),sleeve,edge(sleeve,'cap_'+body))
        add('side_'+side,'front',edge('front','side_'+side),'back',edge('back','side_'+side))
        add('underarm_'+side,sleeve,edge(sleeve,'underarm_front'),sleeve,edge(sleeve,'underarm_back'))
        add('cuff_'+side,sleeve,edge(sleeve,'opening'),'cuff_'+side,edge('cuff_'+side,'attach'),config.design.rib_ratio)
    for body in ('front','back'):
        add('hem_'+body,body,edge(body,'hem'))

    def op(kind, duration, seam=None, tool='up'):
        nonlocal clock
        operations.append({'index':len(operations),'kind':kind,'start_s':clock,'end_s':clock+duration,
                           'window':window,'piece_id':seam['piece_ids'][0] if seam else None,
                           'path_id':None,'tool':tool,'head_mm':[0.,0.],
                           'machine_id':'pfaff','seam_id':seam['id'] if seam else None})
        clock += duration

    op('transfer_to_sewing',m.transfer_s)
    op('sewing_setup',m.sewing_setup_s)
    for seam in seams:
        op('seam_align',m.seam_align_s,seam)
        op('presser_down',m.presser_s,seam)
        op('stitch',seam['stitches']*60/m.stitches_per_min,seam,'needle')
        op('thread_trim',m.thread_trim_s,seam)
        op('presser_up',m.presser_s,seam)
    op('assembly_pickup',m.pickup_s)
    return seams, clock


def state_at(plan, t):
    seams = plan.get('sewing_seams',[])
    by_id = {s['id']:s for s in seams}
    states = {s['id']:'waiting' for s in seams}
    sewn = 0.
    stitches = 0
    active = None
    progress = 0.
    presser = False
    for op in plan['operations']:
        if op['start_s'] > t: break
        if op.get('machine_id') != 'pfaff': continue
        f = min(1.,(t-op['start_s'])/(op['end_s']-op['start_s']))
        key = op.get('seam_id')
        if op['start_s'] <= t < op['end_s']:
            active = key
            progress = f if op['kind']=='stitch' else (1. if op['kind'] in ('thread_trim','presser_up') else 0.)
        if op['kind']=='presser_down' and f==1: presser=True
        if op['kind']=='presser_up' and f==1: presser=False
        if op['kind']=='stitch':
            seam=by_id[key]
            sewn += seam['length_mm']*f
            stitches += math.floor(seam['stitches']*f+1e-8)
            states[key] = 'stitched' if f==1 else 'sewing'
        if op['kind']=='thread_trim' and f==1: states[key]='sewn'
    complete = bool(seams) and t>=plan['totals']['duration_s']
    return {'seams':states,'seam_id':active,'seam_progress':progress,'presser_down':presser,
            'sewn_length_mm':sewn,'stitches':stitches,'seams_complete':sum(v=='sewn' for v in states.values()),
            'seams_total':len(seams),'assembly_collected':complete}
