"""One-style factory run: geometry once, SimPy schedule, indexed accounting."""
from datetime import datetime, timezone
import uuid
from ..simulation import build_plan, SimulationConfig
from .config import Scenario
from .template import compile_template
from .scheduler import schedule
from .ledger import MODEL, build_index, build_result
from .replay import checkpoints
from .storage import VERSION, content_hash


def simulate(scenario, *, release_order=None):
    scenario = scenario if isinstance(scenario,Scenario) else Scenario.model_validate(scenario)
    normalized = scenario.normalized()
    template = build_plan(scenario.document(),SimulationConfig(**normalized['config']))
    template_index = compile_template(template)
    scheduled = schedule(normalized,template,template_index,release_order=release_order)
    garments = scheduled['garments']
    bounds = {}
    for oi in range(len(normalized['orders'])):
        members = [g for g in garments if g['order_index'] == oi]
        bounds[str(oi)] = {'start_s':min(g['start_s'] for g in members), 'end_s':max(g['end_s'] for g in members)}
    run = {'schema_version':VERSION,'run_id':uuid.uuid4().hex,
           'created_at':datetime.now(timezone.utc).isoformat(),'is_simulation':True,
           'scope':'through_sewing','finished_garment':False,'resource_model':dict(MODEL),
           'scenario':normalized,'template':template,'template_index':template_index,
           **scheduled,'start_s':min(g['start_s'] for g in garments),'order_bounds':bounds,
           'assumptions':['One research polo template and size per run; no cross-garment nesting.',
                          'Separate cutting, sewing and transport worker pools; no preemption.',
                          'Unbounded cutting output queue; sewing buffer includes transit reservations.',
                          'Batch service includes loading, delivery, unloading and return; all arrive at service end.',
                          'Idle unoccupied equipment is off; occupied cutter waits use standby power and retained vacuum.',
                          'Common electricity applies once to the union of actual working intervals.',
                          'No shifts, failures, QC, finishing, shipping or actual manufactured-product claim.']}
    run['index'] = build_index(run)
    run['checkpoints'] = checkpoints(run['events'],len(garments))
    run['result'] = build_result(run)
    run['content_hash'] = content_hash(run)
    return run
