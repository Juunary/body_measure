import {context,initialJob,rememberJob,getJSON,navigation,subscribe,wt,processPhase} from './workflow.js';
import {renderGarment,saveSettings} from './settings.js';
import {resourceView} from './resource-view.js';
const $=id=>document.getElementById(id),node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
let ctx,job,data,simulation,source,error='',generating=false,requestVersion=0,recordRevision=0,restoredConfig=false;
function mismatch(){const size=data?.size?.override?.size||data?.size?.qr_option;return simulation?.plan?.schema_version==='garment-simulation/3'&&simulation.plan.size?.label!==size?.toUpperCase();}
function renderNavigation(){navigation({job,lang:ctx.lang,size:data?.size,busy:data?.busy_stage,error:!job?error:null,phase:processPhase(ctx.lang,simulation?.state)});}
function render(){
  document.documentElement.lang=ctx.lang;document.title=wt(ctx.lang,'qr')+' · Maß-DPP';$('subtitle').textContent=wt(ctx.lang,'qr');
  renderNavigation();
  document.querySelectorAll('#langs button').forEach(b=>b.classList.toggle('on',b.dataset.lang===ctx.lang));
  $('qr-config-title').textContent=wt(ctx.lang,'garment');$('qr-title').textContent=wt(ctx.lang,'qr');$('qr-generate').textContent=wt(ctx.lang,'qr');
  const size=data?.size?.override?.size||data?.size?.qr_option;
  $('qr-generate').disabled=!job||!size||generating||!!data?.busy_stage||mismatch();
  $('qr-message').textContent=error||(mismatch()?wt(ctx.lang,'mismatch'):job&&!size?wt(ctx.lang,'noSize'):'');
  renderGarment({...ctx,page:'qr',job,size:data?.size,onChange:()=>saveSettings(ctx.settings)});
  const p=data?.passport?.code?data.passport:null,summary=p?.public_summary,process=summary?.process;
  $('qr-capture-note').textContent=p?`${wt(ctx.lang,'generated')}${summary?.generated_at?' · '+new Intl.DateTimeFormat(ctx.lang,{dateStyle:'medium',timeStyle:'short'}).format(new Date(summary.generated_at)):''}. ${wt(ctx.lang,'frozenNote')}`:wt(ctx.lang,'livePreview');
  resourceView($('qr-resource-card'),p?process?.resources:simulation?.state?.resources,p?process?.planned_resources:simulation?.plan?.totals.resources,p?process?.run_size:simulation?.plan?.size,ctx.lang,p?process?.estimation?.preset:simulation?.plan?.config.resources);
  const card=$('qr-card');const wasOpen=card.querySelector('details')?.open;card.replaceChildren();if(!p)return;
  const img=node('img');img.alt='QR';img.src=`/api/qr/${p.code}.png?base_url=${encodeURIComponent(location.origin)}&scale=8`;img.width=260;img.height=260;card.append(img,node('p',p.code));
  const url=node('p',p.url);url.className='url';card.append(url);const actions=node('div');actions.className='qr-actions';
  const link=node('a',wt(ctx.lang,'openPassport'));link.href=`/view/${p.code}`;link.target='_blank';link.rel='noopener';actions.append(link);
  const download=node('a',wt(ctx.lang,'saveQr'));download.href=img.src;download.download=`mass-dpp-${p.code}.png`;actions.append(download);card.append(actions);
  const details=node('details');details.open=!!wasOpen;details.append(node('summary',wt(ctx.lang,'passportJson')),node('pre',JSON.stringify(p.passport,null,2)));card.append(details);
}
async function refresh(){
  if(!job)return;const id=job,version=++requestVersion,revision=recordRevision;
  const [record,sim]=await Promise.all([getJSON(`/api/jobs/${id}/result`),getJSON(`/api/jobs/${id}/simulation`)]);
  if(version!==requestVersion||job!==id)return;
  // A size/passport event can arrive while this older HTTP snapshot is in flight.
  // Read after that event before replacing the UI's newer assignment.
  if(revision!==recordRevision)return refresh();
  if(simulation?.state?.run_id===sim.state?.run_id&&simulation.state.seq>sim.state.seq)sim.state=simulation.state;
  if(!restoredConfig&&record.passport?.config){ctx.settings.garment=structuredClone(record.passport.config);saveSettings(ctx.settings);}
  restoredConfig=true;
  data=record;simulation=sim;render();return record;
}
function fail(e){error=e.status===404?wt(ctx.lang,'expired'):e.message;if(e.status===404){source?.close();job=null;data=null;simulation=null;rememberJob(null);}render();}
async function boot(){
  ctx=await context();render();
  let languageVersion=0;
  document.querySelectorAll('#langs button').forEach(b=>b.onclick=async()=>{const version=++languageVersion;ctx.lang=b.dataset.lang;ctx.settings.lang=ctx.lang;saveSettings(ctx.settings);const schema=await getJSON(`/api/schema/active?lang=${ctx.lang}`);if(version===languageVersion){ctx.schema=schema;render();}});
  $('qr-generate').onclick=async()=>{if(generating)return;generating=true;error='';render();try{saveSettings(ctx.settings);data.passport=await getJSON(`/api/jobs/${job}/passport`,{config:ctx.settings.garment,base_url:location.origin});}catch(e){error=e.message;}finally{generating=false;render();}};
  job=initialJob();if(!job)return;rememberJob(job);
  try{
    await refresh();if(!job)return;
    source=subscribe(job,data.last_event_id,{
      any:kind=>{if(['size','passport','stage','end','simulation_ready','simulation_reset'].includes(kind))recordRevision++;},
      simulation_state:s=>{if(simulation?.state&&s.run_id===simulation.state.run_id&&s.seq>simulation.state.seq){simulation.state=s;renderNavigation();if(!data?.passport?.code)resourceView($('qr-resource-card'),s.resources,simulation.plan.totals.resources,s.size,ctx.lang,simulation.plan.config.resources);}},
      passport:p=>{data.passport=p;data.busy_stage=null;render();},size:s=>{data.size=s;render();},
      simulation_ready:()=>refresh().catch(fail),simulation_reset:()=>refresh().catch(fail),end:()=>refresh().catch(fail),
      stage:e=>{if(e.status==='start'&&['load','measure','size'].includes(e.phase)){data.busy_stage=e.phase;render();}},
    },()=>{error='';refresh().catch(fail);},()=>{error=wt(ctx.lang,'connection');render();});
  }catch(e){fail(e);}
}
boot().catch(e=>$('workflow-message').textContent=e.message);
