import {context,initialJob,rememberJob,getJSON,navigation,subscribe,wt} from './workflow.js';
import {saveSettings} from './settings.js';
import {SimulationPanel} from './simulation-panel.js';
let ctx,job,data,source,panel,connectionError,sizeCursor=0;
function chrome(){
  document.documentElement.lang=ctx.lang;document.title=wt(ctx.lang,'simulation')+' · Maß-DPP';
  document.getElementById('subtitle').textContent=wt(ctx.lang,'simulation');
  const state=panel?.state;
  navigation({job,lang:ctx.lang,size:data?.size,busy:data?.busy_stage,error:connectionError,phase:state?panel.t(state.finished?(state.sewing_complete?'sewingComplete':'cuttingComplete'):state.status):null});
  document.querySelectorAll('#langs button').forEach(b=>b.classList.toggle('on',b.dataset.lang===ctx.lang));
  if(panel){const assigned=data?.size?.override?.size||data?.size?.qr_option;const captured=panel.plan?.size?.label;
    if(panel.plan?.schema_version==='garment-simulation/3'&&captured!==(assigned?.toUpperCase()||null))document.getElementById('workflow-message').textContent=wt(ctx.lang,'mismatch');
    document.getElementById('sim-start').disabled=!job||!!data?.busy_stage;
  }
}
async function metadata(){if(!job)return;const id=job;const result=await getJSON(`/api/jobs/${id}/result`);if(job===id){if(result.last_event_id<sizeCursor)result.size=data?.size;data=result;chrome();}}
async function attach(id){
  source?.close();job=id;sizeCursor=0;rememberJob(id);connectionError=null;
  data=await getJSON(`/api/jobs/${id}/result`);await panel.setJob(id);chrome();
  source=subscribe(id,data.last_event_id,{
    simulation_state:s=>panel.receive(s),simulation_ready:()=>{panel.restore();metadata().catch(fail);},
    simulation_reset:()=>{panel.setJob(id);metadata().catch(fail);},
    size:s=>{data.size=s;sizeCursor=s.id;chrome();},stage:e=>{if(e.status==='start'&&['load','measure','size'].includes(e.phase)){data.busy_stage=e.phase;chrome();}},
    end:()=>metadata().catch(fail),error:e=>panel.error(e.message),
  },()=>{connectionError=null;metadata().catch(fail);panel.restore();},()=>{connectionError=wt(ctx.lang,'connection');chrome();});
}
function fail(e){if(e.status===404){source?.close();job=null;data=null;rememberJob(null);panel.setJob(null);connectionError=wt(ctx.lang,'expired');}else connectionError=e.message;chrome();}
async function boot(){
  ctx=await context();
  panel=new SimulationPanel({lang:()=>ctx.lang,onExample:attach,onState:()=>chrome()});await panel.ready;
  document.querySelectorAll('#langs button').forEach(b=>b.onclick=()=>{ctx.lang=b.dataset.lang;ctx.settings.lang=ctx.lang;saveSettings(ctx.settings);chrome();panel.localize();});
  chrome();const id=initialJob();if(id)await attach(id).catch(fail);
}
boot().catch(e=>document.getElementById('workflow-message').textContent=e.message);
