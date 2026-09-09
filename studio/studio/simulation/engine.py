"""An immutable cutting schedule and pure random-access state evaluation."""
import bisect
import hashlib
import json
import math
from .config import SimulationConfig, machine_catalogue
from .inputs import resolve_inputs
from .geometry import draft, nest, length
from .sewing import schedule as sewing_schedule, state_at as sewing_state
from . import resources

VERSION = 'garment-simulation/3'


def build_plan(document: dict, config: SimulationConfig | dict | None = None) -> dict:
    config = config if isinstance(config, SimulationConfig) else SimulationConfig(**(config or {}))
    m,inputs=resolve_inputs(document,config)
    pieces,checks,pom=draft(m,config)
    windows=nest(pieces,config)
    machine=config.machine
    ops=[];paths=[];head=[0.,0.];clock=0.
    def operation(kind,duration,window,piece=None,path=None,tool='up'):
        nonlocal clock
        op={'index':len(ops),'kind':kind,'start_s':clock,'end_s':clock+duration,
            'window':window,'piece_id':piece,'path_id':path,'tool':tool,'head_mm':list(head)}
        ops.append(op);clock+=duration
    def trace(points,kind,window,piece):
        nonlocal head
        for pts,typ,speed in [([head,points[0]],'travel',machine.travel_speed_mm_s),
                              (points,kind,machine.mark_speed_mm_s if kind=='mark' else machine.cut_speed_mm_s)]:
            distance=length(pts)
            if distance < 1e-7: continue
            if typ!='travel':operation('tool_down',machine.tool_change_s,window,piece,tool='mark' if kind=='mark' else 'cut')
            cumulative=[0.]
            for a,b in zip(pts,pts[1:]): cumulative.append(cumulative[-1]+math.dist(a,b))
            path={'id':len(paths),'kind':typ,'window':window,'piece_id':piece,
                  'points':pts,'distance_mm':distance,'cumulative_mm':cumulative}
            paths.append(path)
            operation(typ,distance/speed,window,piece,path['id'],tool='up' if typ=='travel' else 'mark' if kind=='mark' else 'cut')
            head=list(pts[-1])
            if typ!='travel':operation('tool_up',machine.tool_change_s,window,piece)
    for w in windows:
        wi=w['id'];head=[0.,0.]
        operation('load',machine.load_s,wi)
        operation('feed',w['length_mm']/machine.feed_speed_mm_s,wi)
        operation('align',machine.align_s,wi)
        operation('vacuum_on',machine.vacuum_s,wi)
        for q in w['placements']:
            for mark in q['marks']: trace(mark,'mark',wi,q['piece_id'])
        # All internal cuts precede all outer contours in this window.
        for q in w['placements']:
            for slit in q['slits']: trace(slit,'cut_internal',wi,q['piece_id'])
        remaining=list(w['placements'])
        while remaining:
            q=min(remaining,key=lambda q:(math.dist(head,q['contour'][0]),q['piece_id']))
            trace(q['contour'],'cut_outer',wi,q['piece_id']);remaining.remove(q)
        operation('vacuum_off',machine.vacuum_s,wi)
        for q in w['placements']:operation('pickup',machine.pickup_s,wi,q['piece_id'])
    cutting_end=clock
    seams=[]
    if config.scope=='through_sewing':
        seams,clock=sewing_schedule(pieces,config,ops,clock,windows[-1]['id'])
    allocated=sum(w['width_mm']*w['length_mm'] for w in windows)
    area=sum(p['area_mm2'] for p in pieces)
    totals={'duration_s':clock,'cut_length_mm':sum(p['distance_mm'] for p in paths if p['kind'].startswith('cut')),
            'travel_mm':sum(p['distance_mm'] for p in paths if p['kind']=='travel'),
            'mark_length_mm':sum(p['distance_mm'] for p in paths if p['kind']=='mark'),
            'fabric_area_mm2':allocated,'piece_area_mm2':area,'waste_area_mm2':allocated-area,
            'yield_pct':100*area/allocated,'pieces':len(pieces),'windows':len(windows)}
    totals.update(cutting_duration_s=cutting_end,sewing_duration_s=clock-cutting_end,
                  sewn_length_mm=sum(s['length_mm'] for s in seams),
                  stitches=sum(s['stitches'] for s in seams),seams=len(seams))
    catalogue=machine_catalogue()
    if not seams:
        next(m for m in catalogue if m['id']=='pfaff')['role']='downstream'
    plan={'schema_version':VERSION,'units':{'geometry':'mm','time':'s'},'scope':config.scope,
          'is_simulation':True,'pattern_status':'research_draft_unverified','inputs':inputs,
          'config':config.model_dump(),'finished_garment':pom,'seam_checks':checks,
          'pieces':pieces,'windows':windows,'paths':paths,'operations':ops,'totals':totals,
          'machines':catalogue,'sewing_seams':seams,
          'assumptions':['Single-ply piqué and rib; original research pattern, not fit validated.',
                         'Machine dimensions, velocities and handling times are editable research assumptions, not manufacturer specifications.',
                         'Constant path speed with tool lift / lower delays; no acceleration, cloth physics or live telemetry.',
                         'Pfaff research lockstitch assembly uses paired seam feed, ideal handling and editable stitch rate; no cloth mechanics or knit stitch suitability validation.',
                         'Finishing, QC, overlock, coverstitch and buttonholes are not executed; assembly is not a finished manufactured garment.']}
    plan['size'] = resources.size_context(document)
    resources.prepare(plan)
    plan['totals']['resources'] = resources.at(plan, clock)
    digest=json.dumps(plan,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    plan['plan_id']=hashlib.sha256(digest.encode()).hexdigest()[:20]
    return plan


def path_position(path, fraction):
    d=max(0,min(1,fraction))*path['distance_mm'];cum=path['cumulative_mm']
    i=min(len(cum)-2,max(0,bisect.bisect_right(cum,d)-1))
    f=(d-cum[i])/(cum[i+1]-cum[i]) if cum[i+1]>cum[i] else 0
    a,b=path['points'][i:i+2]
    return [a[j]+(b[j]-a[j])*f for j in (0,1)]


def snapshot(plan, time_s):
    if not math.isfinite(time_s):raise ValueError('time must be finite')
    t=max(0.,min(float(time_s),plan['totals']['duration_s']))
    ops=plan['operations'];ends=[o['end_s'] for o in ops]
    idx=min(len(ops)-1,bisect.bisect_right(ends,t))
    current=ops[idx];done=t>=ends[-1]
    fraction=min(1.,max(0.,(t-current['start_s'])/(current['end_s']-current['start_s'])))
    status={p['id']:'waiting' for p in plan['pieces']}
    cut=travel=mark=0.;completed_paths=[];vacuum=False
    for op in ops[:idx+1]:
        progress=1. if op['end_s']<=t else fraction
        if op['window']!=current['window']:continue
        if op['kind']=='vacuum_on' and progress==1:vacuum=True
        if op['kind']=='vacuum_off' and progress==1:vacuum=False
    for op in ops[:idx+1]:
        progress=1. if op['end_s']<=t else fraction
        if op['path_id'] is not None:
            path=plan['paths'][op['path_id']]
            dist=path['distance_mm']*progress
            if op['kind'].startswith('cut'):cut+=dist
            elif op['kind']=='travel':travel+=dist
            else:mark+=dist
            if progress==1:completed_paths.append(path['id'])
            if op['kind']=='cut_outer':status[op['piece_id']]='cut' if progress==1 else 'cutting'
        if op['kind']=='pickup' and progress==1:status[op['piece_id']]='collected'
    head=current['head_mm']
    if current['path_id'] is not None:head=path_position(plan['paths'][current['path_id']],fraction)
    sewing=sewing_state(plan,t)
    cutting_complete=t>=plan['totals'].get('cutting_duration_s',ends[-1])
    machines={m['id']:m['role'] for m in plan['machines']}
    machines['zund']='complete' if cutting_complete else 'working'
    if plan.get('sewing_seams'):
        machines['pfaff']='complete' if done else 'working' if cutting_complete else 'waiting'
    # Cutting counters retain their provenance after parts enter the assembly.
    cut_parts=sum(s in ('cut','collected') for s in status.values())
    collected=sum(s=='collected' for s in status.values())
    for piece in plan['pieces']:
        relevant=[s for s in plan.get('sewing_seams',[]) if piece['id'] in s['piece_ids']]
        if relevant and all(sewing['seams'][s['id']]=='sewn' for s in relevant):status[piece['id']]='sewn'
        elif any(sewing['seams'][s['id']]!='waiting' for s in relevant):status[piece['id']]='sewing'
    return {'sim_time_s':t,'duration_s':ends[-1],'finished':done,'operation_index':idx,
            'size':plan.get('size'), 'resources':resources.at(plan,t),
            'scope':plan['scope'],'cutting_complete':cutting_complete,'sewing_complete':sewing['assembly_collected'],
            'machine_id':current.get('machine_id','zund'),'sewing':sewing,
            'operation':current['kind'],'operation_progress':fraction,'window':current['window'],
            'piece_id':current['piece_id'],'head_mm':head,'tool':current['tool'],
            'vacuum':vacuum,'path_id':current['path_id'],'path_progress':fraction,
            'completed_paths':completed_paths,'pieces':status,
            'metrics':{'cut_length_mm':cut,'travel_mm':travel,'mark_length_mm':mark,
                       'cut_pieces':cut_parts,'collected_pieces':collected,
                       'sewn_length_mm':sewing['sewn_length_mm'],'stitches':sewing['stitches'],
                       'seams_complete':sewing['seams_complete'],'seams_total':sewing['seams_total'],
                       'yield_pct':plan['totals']['yield_pct'],'waste_area_mm2':plan['totals']['waste_area_mm2']},
            'machines':machines}
