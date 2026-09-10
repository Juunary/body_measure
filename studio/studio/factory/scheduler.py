"""SimPy clocks coarse segments; one dispatcher arbitrates complete timestamp groups.

Timeout callbacks only enqueue facts. Completions and releases at a timestamp
are drained before ordered, atomic resource allocation. No process can win an
idle machine merely by being constructed first.
"""
import bisect
import simpy


class SchedulingError(ValueError):
    pass


def schedule(scenario, template, index, release_order=None):
    factory = scenario['factory']
    env, agenda, pending = simpy.Environment(), [], []
    rows, events, garments, output = [], [], [], [[] for _ in scenario['orders']]
    order_garments, cut_counts = [], [0]*len(scenario['orders'])
    inventory = {name: [f'{name}-{i+1:03d}' for i in range(factory[name])]
                 for name in ('zund','pfaff','cutting_workers','sewing_workers','transport_workers','carts')}
    free = {k: set(v) for k,v in inventory.items()}
    buffer_used = 0
    segments = index['segments']
    cutting = [s for s in segments if s['station'] == 'zund']
    transport = next(s for s in segments if s['station'] == 'transport')
    sewing = [s for s in segments if s['station'] == 'pfaff']
    if len(sewing) != 1:
        raise SchedulingError('phase 1 expects one continuously attended sewing stage')
    for oi, order in enumerate(scenario['orders']):
        members = []
        for number in range(1, order['quantity']+1):
            gi = len(garments); members.append(gi)
            garments.append({'id': f"{order['id']}:{number:04d}", 'order_index': oi, 'number': number,
                             'release_s': order['release_s'], 'start_s': None, 'cut_end_s': None,
                             'transport_start_s': None, 'transport_end_s': None,
                             'sewing_start_s': None, 'end_s': None, 'cut_machine': None})
        order_garments.append(members)

    def later(delay, kind, payload):
        env.timeout(delay).callbacks.append(lambda event: agenda.append((kind, payload)))

    def enqueue(kind, members, segment=None):
        g = garments[members[0]]
        request = {'kind': kind, 'members': members, 'segment': segment, 'ready_s': env.now}
        key = (env.now, g['order_index'], g['number'], kind)
        bisect.insort(pending, (key, request), key=lambda item:item[0])

    def emit(kind, updates=(), resources=None):
        events.append({'seq': len(events)+1, 'time_s': env.now, 'kind': kind,
                       'garments': list(updates), 'resources': resources or {}, 'buffer_used': buffer_used})

    def take(pool):
        value = min(free[pool]); free[pool].remove(value); return value

    def give(pool, value):
        if value in free[pool]: raise SchedulingError(f'double release: {value}')
        free[pool].add(value)

    def finish_row(row_id):
        nonlocal buffer_used
        row = rows[row_id]; members = row['garments']; gi = members[0]; g = garments[gi]
        changes = {}
        if row['kind'] == 'transport':
            give('transport_workers', row['worker']); give('carts', row['cart'])
            changes.update({row['worker']: None, row['cart']: None})
            for member in members:
                garments[member]['transport_end_s'] = env.now
                enqueue('sew', [member])
            emit('transport_complete', [(member,'buffer') for member in members], changes)
        elif row['station'] == 'zund':
            if row['worker']:
                give('cutting_workers', row['worker']); changes[row['worker']] = None
            next_index = row['cut_index']+1
            if next_index == len(cutting):
                g['cut_end_s'] = env.now
                give('zund', row['machine']); changes[row['machine']] = None
                cut_counts[g['order_index']] += 1
                output[g['order_index']].append(gi)
                emit('cutting_complete', [(gi,'cut_output')], changes)
            else:
                changes[row['machine']] = {'mode':'waiting', 'garments':[gi], 'row_id':None}
                enqueue('cut', [gi], next_index)
                emit('cut_segment_complete', [(gi,'cut_worker_wait')], changes)
        else:
            g['end_s'] = env.now
            give('pfaff', row['machine']); give('sewing_workers', row['worker'])
            emit('sewing_complete', [(gi,'complete')], {row['machine']:None, row['worker']:None})

    def make_batches():
        for oi, queue in enumerate(output):
            queue.sort(key=lambda gi:(garments[gi]['cut_end_s'], garments[gi]['number']))
            batch = factory['batch_size']
            while len(queue) >= batch or (queue and cut_counts[oi] == len(order_garments[oi])):
                members = queue[:batch]; del queue[:batch]
                enqueue('transfer', members)

    def dispatch():
        nonlocal buffer_used
        remaining = []
        for key, request in pending:
            kind, members = request['kind'], request['members']
            gi = members[0]; g = garments[gi]
            worker = machine = cart = None
            if kind == 'cut':
                seg = cutting[request['segment']]
                if (g['cut_machine'] is None and not free['zund']) or (seg['attended'] and not free['cutting_workers']):
                    remaining.append((key,request)); continue
                if g['cut_machine'] is None:
                    g['cut_machine'] = take('zund'); g['start_s'] = env.now
                machine = g['cut_machine']
                if seg['attended']: worker = take('cutting_workers')
                if request['segment'] and env.now > request['ready_s']:
                    rows.append({'id':len(rows), 'kind':'wait', 'station':'zund',
                                 'start_s':request['ready_s'], 'end_s':env.now, 'garments':[gi],
                                 'machine':machine, 'worker':None, 'cart':None,
                                 'template_start_s':seg['start_s'], 'template_end_s':seg['start_s']})
                status = 'cutting'
                duration = seg['end_s']-seg['start_s']
            elif kind == 'sew':
                if not free['pfaff'] or not free['sewing_workers']:
                    remaining.append((key,request)); continue
                machine, worker = take('pfaff'), take('sewing_workers')
                buffer_used -= 1
                g['sewing_start_s'] = env.now
                seg, status = sewing[0], 'sewing'
                duration = seg['end_s']-seg['start_s']
            else:
                if (buffer_used+len(members) > factory['buffer_capacity'] or
                        not free['transport_workers'] or not free['carts']):
                    remaining.append((key,request)); continue
                worker, cart = take('transport_workers'), take('carts')
                buffer_used += len(members)
                for member in members: garments[member]['transport_start_s'] = env.now
                seg, status = transport, 'transporting'
                duration = factory['transport_s']
            row = {'id':len(rows), 'kind':'transport' if kind == 'transfer' else 'template',
                   'station':seg['station'], 'start_s':env.now, 'end_s':env.now+duration,
                   'garments':members, 'machine':machine, 'worker':worker, 'cart':cart,
                   'template_start_s':seg['start_s'], 'template_end_s':seg['end_s'],
                   'segment_id':seg['id'], 'cut_index':request['segment']}
            rows.append(row)
            assigned = {rid:{'mode':'working', 'garments':members, 'row_id':row['id']}
                        for rid in (machine,worker,cart) if rid}
            emit(kind+'_start', [(member,status) for member in members], assigned)
            later(duration, 'finish', row['id'])
        pending[:] = remaining

    release_order = list(range(len(order_garments))) if release_order is None else list(release_order)
    if sorted(release_order) != list(range(len(order_garments))):
        raise ValueError('release_order must be a permutation of order indices')
    for oi in release_order: later(scenario['orders'][oi]['release_s'], 'release', oi)
    while env.peek() != float('inf'):
        timestamp = env.peek()
        # Drain every SimPy event at this physical timestamp before allocating.
        while env.peek() == timestamp: env.step()
        for kind, payload in sorted(agenda, key=lambda a:(0 if a[0]=='finish' else 1,a[1])):
            if kind == 'finish': finish_row(payload)
            else:
                for gi in order_garments[payload]: enqueue('cut', [gi], 0)
                emit('order_released', [(gi,'cut_queue') for gi in order_garments[payload]])
        agenda.clear(); make_batches(); dispatch()
        # A later eligible sewing request can free buffer for an earlier transfer.
        while pending:
            before = len(pending); dispatch()
            if len(pending) == before: break
    unfinished = [g['id'] for g in garments if g['end_s'] is None]
    if unfinished:
        raise SchedulingError(f'event queue exhausted with unfinished garments {unfinished[:10]}; '
                              f'pending={[(r[1]["kind"],r[1]["members"]) for r in pending[:10]]}; '
                              f'buffer={buffer_used}/{factory["buffer_capacity"]}')
    if buffer_used or any(free[k] != set(v) for k,v in inventory.items()):
        raise SchedulingError('run ended with retained resources or buffer reservations')
    return {'garments':garments, 'rows':rows, 'events':events, 'inventory':inventory, 'duration_s':env.now}
