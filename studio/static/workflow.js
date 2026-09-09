// Shared connection and navigation. Navigation never sends a run/control request.
import {loadSettings,saveSettings} from './settings.js';
import {wt} from './workflow-i18n.js';
export {wt};
export function processPhase(lang,state){return state?wt(lang,state.finished?(state.sewing_complete?'sewingComplete':'cuttingComplete'):state.status):null;}
export function initialJob(){const id=new URLSearchParams(location.search).get('job');if(id)return id;try{return sessionStorage.getItem('studio.currentJob');}catch{return null;}}
export function rememberJob(id){
  try{if(id)sessionStorage.setItem('studio.currentJob',id);else sessionStorage.removeItem('studio.currentJob');}catch{}
  const url=new URL(location.href);if(id)url.searchParams.set('job',id);else url.searchParams.delete('job');history.replaceState(null,'',url);
}
export async function getJSON(url,body){
  const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await r.json();if(!r.ok){const e=new Error(typeof data.detail==='string'?data.detail:data.detail?.message||JSON.stringify(data.detail));e.status=r.status;throw e;}return data;
}
export async function context(){
  const options=await getJSON('/api/settings/options');
  const settings=loadSettings({lang:options.default_lang||'en',chart:options.default_chart,replay:options.replay,garment:options.default_config});
  const requested=new URLSearchParams(location.search).get('lang');if(['en','de','ko'].includes(requested))settings.lang=requested;
  const lang=['en','de','ko'].includes(settings.lang)?settings.lang:'en';settings.lang=lang;
  saveSettings(settings);
  return {options,settings,lang,schema:await getJSON(`/api/schema/active?lang=${lang}`)};
}
export function navigation({job,lang,size,busy,phase,error}){
  const nav=document.getElementById('workflow-nav');const signature=JSON.stringify([job,lang,location.pathname]);
  if(nav.dataset.signature!==signature){
    nav.dataset.signature=signature;nav.replaceChildren();
    for(const page of ['measure','simulation','qr']){
      const a=document.createElement('a');a.href=`/${page}${job?'?job='+encodeURIComponent(job):''}`;a.dataset.page=page;a.textContent=wt(lang,page);
      if(location.pathname===`/${page}`)a.setAttribute('aria-current','page');nav.append(a);
    }
  }
  const label=size?.override?.size||size?.qr_option||size?.label||size?.size;
  document.getElementById('workflow-status').textContent=`${wt(lang,'job')}: ${job||'—'} · ${wt(lang,'size')}: ${label?.toUpperCase()||wt(lang,'unknown')} · ${busy||phase||wt(lang,'ready')}`;
  document.getElementById('workflow-message').textContent=error||(!job?wt(lang,'noJob'):'');
  for(const a of document.querySelectorAll('[data-next]')){a.href=`/${a.dataset.next}${job?'?job='+encodeURIComponent(job):''}`;a.textContent=`${wt(lang,'next')} → ${wt(lang,a.dataset.next)}`;}
}
const events=['stage','line','frame','error','mesh_ready','pose','measurements','prototypes','landmarks','curves','size','report','totals','passport','end','simulation_ready','simulation_state','simulation_reset'];
export function subscribe(job,cursor,handlers,onOpen,onLost){
  let last=cursor||0;
  const source=new EventSource(`/api/jobs/${encodeURIComponent(job)}/events?after=${last}`);
  for(const kind of events)source.addEventListener(kind,e=>{
    if(typeof e.data!=='string')return;
    const data=JSON.parse(e.data),id=Number(e.lastEventId||data.id);
    if(id<=last)return;last=id;handlers[kind]?.(data);handlers.any?.(kind,data);
  });
  source.onopen=()=>onOpen?.();source.onerror=()=>onLost?.();
  window.addEventListener('pagehide',()=>source.close(),{once:true});return source;
}
// A history-cache restore must reconnect to the server's current job state.
window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
