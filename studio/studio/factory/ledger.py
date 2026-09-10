"""Indexed segment integrals; template detail is never expanded per garment."""
from bisect import bisect_right
from collections import Counter, defaultdict
from itertools import groupby
import numpy as np
from .template import COL, COLUMNS, TemplateIndex

MODEL = {'version':'factory-resources/1', 'is_estimate':True,
         'common_load':'union_of_working_intervals', 'overhead_allocation':'active_garment_count',
         'transport':'fixed_batch_service_including_return', 'cart_power_kw':0, 'cart_eur_h':0,
         'labour':'direct_work_only', 'co2_scope':'process_electricity_only',
         'units':{'time':'s','energy':'kWh','emissions':'gCO2e','cost':'EUR','geometry':'mm'}}


def row_value(row, template, rates, t):
    duration = row['end_s']-row['start_s']
    f = min(1., max(0., (t-row['start_s'])/duration))
    if row['kind'] == 'template':
        local = template.local_at(row,t)
        return template.at(local)-template.at(row['template_start_s'])
    result = np.zeros(len(COLUMNS)); elapsed = duration*f
    if row['kind'] == 'transport':
        result[COL['labour_s']] = elapsed
    else:
        result[COL['zund_kwh']] = rates['zund_idle_kw']*elapsed/3600
        result[COL['equipment_eur']] = rates['zund_eur_h']*elapsed/3600
        if template.vacuum_at_boundary(row['template_start_s']):
            result[COL['vacuum_kwh']] = rates['vacuum_kw']*elapsed/3600
    return result


def prefix_rows(ids, rows, values, weight=1.):
    ids = sorted(ids, key=lambda i:(rows[i]['end_s'],i))
    matrix = np.asarray([values[i]*weight for i in ids]) if ids else np.zeros((0,len(COLUMNS)))
    return {'ids':ids, 'ends':[rows[i]['end_s'] for i in ids],
            'prefix':np.vstack((np.zeros(len(COLUMNS)),np.cumsum(matrix,axis=0))).tolist()}


def curve(spans):
    merged = []
    for start, end, rate in spans:
        if merged and merged[-1][1] == start and merged[-1][2] == rate: merged[-1][1] = end
        else: merged.append([start,end,rate])
    prefix = [0.]
    for start,end,rate in merged: prefix.append(prefix[-1]+(end-start)*rate)
    return {'starts':[x[0] for x in merged], 'ends':[x[1] for x in merged],
            'rates':[x[2] for x in merged], 'prefix':prefix}


def curve_at(index, t):
    i = bisect_right(index['starts'],t)-1
    if i < 0: return 0.
    return index['prefix'][i]+(min(t,index['ends'][i])-index['starts'][i])*index['rates'][i]


def overhead(rows, garments, kw):
    edges = defaultdict(lambda:[[],[]])
    for row in rows:
        if row['kind'] == 'wait': continue
        edges[row['start_s']][1].extend(row['garments'])
        edges[row['end_s']][0].extend(row['garments'])
    active, previous = set(), 0.
    global_spans, garment_spans, order_spans = [], defaultdict(list), defaultdict(list)
    for timestamp, (ends,starts) in sorted(edges.items()):
        if active and timestamp > previous:
            rate = kw/3600/len(active)
            global_spans.append([previous,timestamp,kw/3600])
            for gi in sorted(active): garment_spans[str(gi)].append([previous,timestamp,rate])
            for oi,count in sorted(Counter(garments[gi]['order_index'] for gi in active).items()):
                order_spans[str(oi)].append([previous,timestamp,rate*count])
        for gi in ends:
            if gi not in active: raise ValueError('unmatched working interval end')
            active.remove(gi)
        for gi in starts:
            if gi in active: raise ValueError('garment simultaneously assigned to two operations')
            active.add(gi)
        previous = timestamp
    if active: raise ValueError('unclosed working intervals')
    return {'global':curve(global_spans), 'garments':{k:curve(v) for k,v in garment_spans.items()},
            'orders':{k:curve(v) for k,v in order_spans.items()}}


def build_index(run):
    rows, garments = run['rows'], run['garments']
    template = TemplateIndex(run['template'],run['template_index'])
    rates = run['scenario']['config']['resources']
    values = [row_value(row,template,rates,row['end_s']) for row in rows]
    lanes, instance_rows, garment_rows, order_rows = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for row in rows:
        lanes[row['machine'] or row['cart']].append(row['id'])
        for rid in (row['machine'],row['worker'],row['cart']):
            if rid: instance_rows[rid].append(row['id'])
        for gi in row['garments']: garment_rows[str(gi)].append(row['id'])
        order_rows[str(garments[row['garments'][0]]['order_index'])].append(row['id'])
    def intervals(ids):
        ids = sorted(ids,key=lambda i:(rows[i]['start_s'],i))
        for a,b in zip(ids,ids[1:]):
            if rows[a]['end_s'] > rows[b]['start_s']+1e-8:
                raise ValueError(f'overlapping instance allocation: {a}, {b}')
        return {'ids':ids,'starts':[rows[i]['start_s'] for i in ids]}
    # Transport labour is shared by the members; other rows belong to one garment.
    per_garment_values = [v/len(row['garments']) for v,row in zip(values,rows)]
    return {'global':prefix_rows(range(len(rows)),rows,values),
            'lanes':{k:intervals(v) for k,v in lanes.items()},
            'instances':{k:intervals(v) for k,v in instance_rows.items()},
            'garments':{k:{**prefix_rows(v,rows,per_garment_values), **{'timeline':intervals(v)}} for k,v in garment_rows.items()},
            'orders':{k:prefix_rows(v,rows,values) for k,v in order_rows.items()},
            'overhead':overhead(rows,garments,rates['overhead_kw'])}


def quantities(vector, overhead_kwh, rates, flow_s):
    v = dict(zip(COLUMNS,vector))
    energy = {'zund':v['zund_kwh'],'pfaff':v['pfaff_kwh'],'vacuum':v['vacuum_kwh'],'overhead':overhead_kwh}
    kwh = sum(energy.values())
    cost = {'fabric':v['fabric_eur'], 'thread':v['thread_m']*rates['thread_eur_m'],
            'labour':v['labour_s']/3600*rates['labour_eur_h'],
            'electricity':kwh*rates['electricity_eur_kwh'],'equipment':v['equipment_eur']}
    return {'flow_time_s':flow_s, 'energy_kwh':float(kwh), 'co2e_g':float(kwh*rates['grid_gco2e_kwh']),
            'cost_eur':float(sum(cost.values())), 'energy_breakdown_kwh':{k:float(x) for k,x in energy.items()},
            'cost_breakdown_eur':{k:float(x) for k,x in cost.items()}, 'labour_time_s':float(v['labour_s']),
            'thread_used_m':float(v['thread_m']), 'fabric_used_m2':{'body':float(v['body_m2']),'rib':float(v['rib_m2'])},
            'metrics':{k:int(round(v[k])) if k in ('stitches','collected_pieces','seams_complete') else float(v[k])
                       for k in COLUMNS[9:]}}


class Ledger:
    def __init__(self, run):
        self.run, self.index = run, run['index']
        self.rows, self.rates = run['rows'], run['scenario']['config']['resources']
        self.template = TemplateIndex(run['template'],run['template_index'])
        self.prefixes = {'global':np.asarray(self.index['global']['prefix'])}
        for group in ('garments','orders'):
            for key,value in self.index[group].items(): self.prefixes[group+key] = np.asarray(value['prefix'])

    def active(self,t):
        for lane in self.index['lanes'].values():
            i = bisect_right(lane['starts'],t)-1
            if i >= 0:
                row = self.rows[lane['ids'][i]]
                if t < row['end_s']: yield row

    def at(self, t, garment=None, order=None):
        t = max(0.,min(t,self.run['duration_s']))
        if garment is not None:
            key, group = str(garment),'garments'
            data = self.index[group][key]
            prefix = self.prefixes[group+key]
            g = self.run['garments'][garment]
            flow = max(0.,min(t,g['end_s'])-g['start_s'])
            oh = self.index['overhead'][group][key]
        elif order is not None:
            key, group = str(order),'orders'; data = self.index[group][key]
            prefix = self.prefixes[group+key]
            bounds = self.run['order_bounds'][key]
            flow = max(0.,min(t,bounds['end_s'])-bounds['start_s'])
            oh = self.index['overhead'][group][key]
        else:
            data = self.index['global']; prefix = self.prefixes['global']
            flow = max(0., t-self.run['start_s']); oh = self.index['overhead']['global']
        value = prefix[bisect_right(data['ends'],t)].copy()
        for row in self.active(t):
            if garment is not None and garment not in row['garments']: continue
            if order is not None and self.run['garments'][row['garments'][0]]['order_index'] != order: continue
            delta = row_value(row,self.template,self.rates,t)
            value += delta/len(row['garments']) if garment is not None else delta
        return quantities(value,curve_at(oh,t),self.rates,flow)


def build_result(run):
    ledger, duration = Ledger(run), run['duration_s']
    horizon = duration-run['start_s']
    instances = {}
    for pool, members in run['inventory'].items():
        for rid in members:
            ids = run['index']['instances'].get(rid,{}).get('ids',[])
            work = sum(run['rows'][i]['end_s']-run['rows'][i]['start_s'] for i in ids if run['rows'][i]['kind'] != 'wait')
            wait = sum(run['rows'][i]['end_s']-run['rows'][i]['start_s'] for i in ids if run['rows'][i]['kind'] == 'wait')
            instances[rid] = {'pool':pool,'working_s':work,'held_wait_s':wait,'occupied_s':work+wait,
                              'idle_s':max(0.,horizon-work-wait),'utilization_pct':100*work/horizon}
    garment_results = []
    for gi,g in enumerate(run['garments']):
        ids = run['index']['garments'][str(gi)]['ids']
        waits = {'before_cutting_s':g['start_s']-g['release_s'],
                 'cutting_worker_s':sum(run['rows'][i]['end_s']-run['rows'][i]['start_s'] for i in ids if run['rows'][i]['kind']=='wait'),
                 'before_transport_s':g['transport_start_s']-g['cut_end_s'],
                 'before_sewing_s':g['sewing_start_s']-g['transport_end_s']}
        garment_results.append({'id':g['id'],'order_id':run['scenario']['orders'][g['order_index']]['id'],
                                'lead_time_s':g['end_s']-g['release_s'], 'waits':waits,
                                'resources':ledger.at(duration,garment=gi)})
    orders = []
    for oi,order in enumerate(run['scenario']['orders']):
        bounds = run['order_bounds'][str(oi)]
        orders.append({'id':order['id'],'quantity':order['quantity'],**bounds,
                       'lead_time_s':bounds['end_s']-order['release_s'],
                       'resources':ledger.at(duration,order=oi)})
    counts = Counter(); statuses = ['not_released']*len(run['garments'])
    area, peak, last = defaultdict(float), Counter(), 0.
    slots = 0
    for timestamp, group in groupby(run['events'],key=lambda e:e['time_s']):
        dt = timestamp-last
        for name,count in counts.items(): area[name] += count*dt
        area['buffer_reserved_or_occupied'] += slots*dt
        for event in group:
            for gi,status in event['garments']:
                if statuses[gi] != 'not_released': counts[statuses[gi]] -= 1
                statuses[gi] = status; counts[status] += 1
            slots = event['buffer_used']
        last = timestamp
        for name,count in counts.items(): peak[name] = max(peak[name],count)
        peak['buffer_reserved_or_occupied'] = max(peak['buffer_reserved_or_occupied'],slots)
    queues = {name:{'peak':peak[name],'time_average':area[name]/horizon}
              for name in ('cut_queue','cut_worker_wait','cut_output','buffer','buffer_reserved_or_occupied')}
    return {'completed_garments':len(run['garments']), 'finished_garment':False,
            'makespan_s':horizon, 'completion_time_s':duration,
            'throughput_per_hour':len(run['garments'])*3600/horizon,
            'resources':ledger.at(duration), 'orders':orders, 'garments':garment_results,
            'instances':instances,'queues':queues}
