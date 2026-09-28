export class ResponseGate {
  constructor(){this.reset()}
  reset(state=null){this.run=state?.run_id??null;this.plan=state?.plan_id??null;this.seq=-1;this.revision=-1}
  accept(state){
    if(!state||!this.run||state.run_id!==this.run||state.plan_id!==this.plan||
       state.seq<=this.seq||state.revision<this.revision)return false;
    this.seq=state.seq;this.revision=state.revision;return true;
  }
}
export function chaptersFor(plan){
  if(plan.timeline)return plan.timeline;
  const keys=['cutting','lockstitch','overlock','coverstitch','buttons','finishing','qc','ready_for_qr'];
  const machines=['zund','pfaff','overlock','coverstitch','button','veit','qc','qc'];
  const starts=machines.map((id,i)=>i===0?0:i===7?plan.boundaries.qc_end_s:
    plan.operations.find(op=>op.kind==='transfer_to_'+id).start_s);
  return keys.map((id,i)=>({id,machine_id:machines[i],start_s:starts[i],
    end_s:starts[i+1]??plan.totals.duration_s,duration_s:(starts[i+1]??plan.totals.duration_s)-starts[i]}));
}
export function duration(seconds){
  const total=Math.max(0,Math.floor(seconds+1e-7));
  const minutes=Math.floor(total/60),secs=String(total%60).padStart(2,'0');
  return minutes+':'+secs;
}
