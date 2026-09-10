"""Checkpointed, idempotent replay, independent of SimPy and wall-clock time."""
from bisect import bisect_right
from copy import deepcopy
import math
from .ledger import Ledger
from .stages import readouts

CHECKPOINT_INTERVAL = 256


def initial_state(count):
    return {'seq':0,'garments':['not_released']*count,'counts':{'not_released':count},
            'resources':{},'buffer_used':0}


def apply_event(state, event):
    if event['seq'] <= state['seq']: return False
    if event['seq'] != state['seq']+1: raise ValueError('event sequence gap')
    for gi,status in event['garments']:
        old = state['garments'][gi]
        state['counts'][old] -= 1
        state['counts'][status] = state['counts'].get(status,0)+1
        state['garments'][gi] = status
    for rid,value in event['resources'].items():
        if value is None: state['resources'].pop(rid,None)
        else: state['resources'][rid] = value
    state['seq'],state['buffer_used'] = event['seq'],event['buffer_used']
    return True


def checkpoints(events,count):
    state = initial_state(count)
    result = [{'event_count':0,'state':deepcopy(state)}]
    for event in events:
        apply_event(state,event)
        if state['seq'] % CHECKPOINT_INTERVAL == 0:
            result.append({'event_count':state['seq'],'state':deepcopy(state)})
    return result


class Replay:
    def __init__(self, run):
        self.run, self.ledger = run, Ledger(run)
        self.times = [e['time_s'] for e in run['events']]
        self.state = initial_state(len(run['garments']))
        self.by_id = {g['id']:i for i,g in enumerate(run['garments'])}
        self.applied_last = 0

    def snapshot(self,time_s,garment_id=None):
        if isinstance(time_s,bool) or not math.isfinite(time_s) or not 0 <= time_s <= self.run['duration_s']:
            raise ValueError('time must be finite and within the saved run')
        if garment_id is not None and garment_id not in self.by_id: raise ValueError('unknown garment ID')
        target = bisect_right(self.times,time_s)
        if not self.state['seq'] <= target <= self.state['seq']+255:
            self.state = deepcopy(self.run['checkpoints'][target//CHECKPOINT_INTERVAL]['state'])
        self.applied_last = target-self.state['seq']
        for i in range(self.state['seq'],target): apply_event(self.state,self.run['events'][i])
        result = {'run_id':self.run['run_id'],'content_hash':self.run['content_hash'],'seq':target,
                  'time_s':time_s,'duration_s':self.run['duration_s'],'size':self.run['scenario']['size'],
                  'scope':self.run['scope'],'is_simulation':True,'finished_garment':False,
                  'counts':{k:v for k,v in self.state['counts'].items() if v},
                  'buffer_used':self.state['buffer_used'],
                  'active_resources':deepcopy(self.state['resources']),
                  'resources':self.ledger.at(time_s),'selected_garment':None}
        if garment_id is not None:
            gi = self.by_id[garment_id]
            timeline = self.run['index']['garments'][str(gi)]['timeline']
            i = bisect_right(timeline['starts'],time_s)-1
            local, stage = 0., None
            if i >= 0:
                row = self.run['rows'][timeline['ids'][i]]
                local = self.ledger.template.local_at(row,time_s)
                if row['kind'] == 'stage' and time_s < row['end_s']:
                    f = (time_s-row['start_s'])/(row['end_s']-row['start_s'])
                    stage = {'stage':row['stage'],'step':row['step'],'attended':row['attended'],
                             'step_progress':f,'machine':row['machine'],
                             'readouts':readouts(row['station'],row['step'],f)}
                elif row['kind'] == 'wait' and row['station'] != 'zund' and time_s < row['end_s']:
                    stage = {'stage':'finishing' if row['station'] == 'veit' else 'qc','step':'worker_wait',
                             'attended':False,'step_progress':0.,'machine':row['machine'],'readouts':{}}
            detail = self.ledger.template.detail(local)
            if stage:
                # Sewing detail is complete here; the stage step is the live operation.
                detail.update(operation=stage['step'],operation_progress=stage['step_progress'],
                              window=None,tool=None,head_mm=None,path_id=None,path_progress=0.)
            result['selected_garment'] = {'id':garment_id,'status':self.state['garments'][gi],
                                           **detail,'stage':stage,
                                           'resources':self.ledger.at(time_s,garment=gi)}
        return result
