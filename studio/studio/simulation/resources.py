"""Pure integration of operation resources. Wall time never enters the ledger."""
VERSION = 'research-resources/1'
ATTENDED = frozenset(('load', 'align', 'vacuum_on', 'vacuum_off', 'pickup',
                     'transfer_to_sewing', 'sewing_setup', 'seam_align', 'presser_down',
                     'stitch', 'thread_trim', 'presser_up', 'assembly_pickup'))
ZUND_ACTIVE = frozenset(('feed', 'mark', 'cut_internal', 'cut_outer', 'travel', 'tool_up', 'tool_down'))


def size_context(document):
    size = document.get('sizing') or document.get('meta', {}).get('size') or {}
    if not isinstance(size, dict): size = {}
    override = size.get('override') or {}
    label = override.get('size') or size.get('qr_option') or size.get('size')
    if not isinstance(label, str): label = None
    return {'label': label.upper() if label else None,
            'source': 'manual_override' if override else size.get('size_source', '3d_scan' if label else 'unknown'),
            'chart': size.get('chart')}


def prepare(plan):
    """Annotate one immutable ledger row per operation, including timed purchases."""
    r = plan['config']['resources']
    windows = {w['id']: w for w in plan['windows']}
    seams = {s['id']: s for s in plan['sewing_seams']}
    vacuum = False
    rows = []
    for op in plan['operations']:
        kind = op['kind']
        sewing = op.get('machine_id') == 'pfaff'
        if kind == 'vacuum_on': vacuum = True
        kw = (r['pfaff_active_kw'] if kind == 'stitch' else r['pfaff_idle_kw']) if sewing else (
            r['zund_active_kw'] if kind in ZUND_ACTIVE else r['zund_idle_kw'])
        vacuum_kw = r['vacuum_kw'] if vacuum and not sewing else 0
        duration = op['end_s'] - op['start_s']
        thread_m = seams[op['seam_id']]['length_mm'] / 1000 * r['thread_ratio'] if kind == 'stitch' else 0
        window = windows[op['window']]
        area = window['width_mm'] * window['length_mm'] / 1e6 if kind == 'load' else 0
        # The nesting engine separates body fabric and rib by material.
        material = 'rib' if window['material'] == 'rib' else 'body'
        rows.append({'start_s': op['start_s'], 'end_s': op['end_s'],
                     'machine': 'pfaff' if sewing else 'zund',
                     'machine_kwh': kw * duration / 3600,
                     'vacuum_kwh': vacuum_kw * duration / 3600,
                     'overhead_kwh': r['overhead_kw'] * duration / 3600,
                     'labour_s': duration if kind in ATTENDED else 0,
                     'equipment_eur': duration / 3600 * r['pfaff_eur_h' if sewing else 'zund_eur_h'],
                     'thread_m': thread_m,
                     'tail_m_at_end': r['thread_tail_m'] if kind == 'thread_trim' else 0,
                     'material': material, 'area_m2_at_end': area,
                     'fabric_eur_at_end': area * r[material + '_eur_m2']})
        if kind == 'vacuum_off': vacuum = False
    plan['resource_model'] = {'version': VERSION, 'is_estimate': True,
                              'scope': 'cutting_sewing_operations', 'co2_scope': 'process_electricity_only',
                              'labour_model': 'attended_operations', 'attended_operations': sorted(ATTENDED),
                              'units': {'energy': 'kWh', 'emissions': 'gCO2e', 'cost': 'EUR',
                                        'time': 's', 'fabric': 'm2', 'thread': 'm', 'power': 'kW',
                                        'electricity_rate': 'EUR/kWh', 'grid_factor': 'gCO2e/kWh',
                                        'hourly_rate': 'EUR/h', 'fabric_rate': 'EUR/m2', 'thread_rate': 'EUR/m'}}
    plan['resource_ledger'] = rows


def at(plan, time_s):
    """Unknown historical assumptions stay unknown instead of using new defaults."""
    if 'resource_ledger' not in plan: return None
    r = plan['config']['resources']
    energy = dict(zund=0., pfaff=0., vacuum=0., overhead=0.)
    cost = dict(fabric=0., thread=0., labour=0., electricity=0., equipment=0.)
    area = dict(body=0., rib=0.)
    thread = labour = 0.
    for row in plan['resource_ledger']:
        if time_s <= row['start_s']: break
        f = min(1., (time_s-row['start_s']) / (row['end_s']-row['start_s']))
        energy[row['machine']] += row['machine_kwh'] * f
        energy['vacuum'] += row['vacuum_kwh'] * f
        energy['overhead'] += row['overhead_kwh'] * f
        labour += row['labour_s'] * f
        cost['equipment'] += row['equipment_eur'] * f
        thread += row['thread_m'] * f
        if f == 1:
            thread += row['tail_m_at_end']
            area[row['material']] += row['area_m2_at_end']
            cost['fabric'] += row['fabric_eur_at_end']
    kwh = sum(energy.values())
    cost.update(thread=thread*r['thread_eur_m'], labour=labour/3600*r['labour_eur_h'],
                electricity=kwh*r['electricity_eur_kwh'])
    return {'flow_time_s': max(0., min(time_s, plan['totals']['duration_s'])),
            'energy_kwh': kwh, 'co2e_g': kwh*r['grid_gco2e_kwh'], 'cost_eur': sum(cost.values()),
            'cost_breakdown_eur': cost, 'energy_breakdown_kwh': energy,
            'labour_time_s': labour, 'fabric_used_m2': area, 'thread_used_m': thread}
