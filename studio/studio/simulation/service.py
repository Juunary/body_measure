"""Studio adapter: persist the plan, publish small clock snapshots via SSE."""
import json
from dataclasses import asdict
from pathlib import Path
from ..paths import RUNS
from .config import SimulationConfig
from .engine import build_plan
from .inputs import inspect_inputs
from .playback import Playback, terminal_lines


def document_for(job):
    if job.simulation_document is not None:
        return {**job.simulation_document, 'sizing': dict(job.size_view or {})}
    return {'units':'mm','pathway':'measured_clothed' if job.params.get('clothed') else 'estimated',
            'measurements':{k:asdict(v) for k,v in job.measurements.items()},
            'sizing':dict(job.size_view or {}),
            'meta':{'garment_prototypes':{k:v.to_dict() for k,v in job.prototypes.items()}}}


def input_view(job):
    return inspect_inputs(document_for(job), SimulationConfig())


def write_json(path, data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    temp.replace(path)


def start(job, config):
    plan=build_plan(document_for(job),config)
    if job.simulation: job.simulation.close()
    folder=RUNS/job.id/'simulation'
    last_saved=[None]
    def publish(state):
        # Publish under the playback lock; an old callback cannot overtake a seek.
        job.state=('sewing_complete' if state['sewing_complete'] else 'cutting_complete') if state['finished'] else 'simulating'
        job.replay={'is_simulation':True,'scope':plan['scope'],'status':state['status'],
                    'run_id':state['run_id'],'plan_id':plan['plan_id'],
                    'totals':plan['totals'] if state['finished'] else state['metrics'],
                    'cutting_complete':state['cutting_complete'],'sewing_complete':state['sewing_complete'],'finished_garment':False}
        job.emit('simulation_state','simulation',**state)
        marker=(state['revision'],state['status'],state['speed'],state['finished'])
        if marker!=last_saved[0]:
            write_json(folder/'result.json',{'schema_version':plan['schema_version'],**job.replay,'state':state})
            last_saved[0]=marker
    def on_error(exc):
        job.state='error'
        job.emit('error','simulation',stage='simulation',message=str(exc))
    player=Playback(plan,publish,on_error=on_error)
    job.simulation=player
    job.params['simulation']=config.model_dump()
    job.passport={}
    write_json(folder/'plan.json',plan)
    job.emit('simulation_ready','simulation',run_id=player.run_id,plan_id=plan['plan_id'])
    try:
        player.start()
    except Exception:
        player.close()
        job.simulation=None
        job.replay={}
        raise
    return player
