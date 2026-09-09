import {wt,unit} from './workflow-i18n.js';
const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
export function resourceView(root,current,planned,size,lang,preset){
  const opened=[...root.querySelectorAll('details')].map(d=>d.open);
  const focus=[...root.querySelectorAll('summary')].indexOf(document.activeElement);
  root.replaceChildren();root.classList.add('resource-card');
  root.append(el('h2',wt(lang,'resources')),el('p',`${wt(lang,'size')}: ${size?.label||wt(lang,'unknown')}`));
  const table=el('table');table.className='resource-table';const head=el('tr');
  for(const s of ['',wt(lang,'current'),wt(lang,'planned')]){const cell=el('th',s);cell.scope='col';head.append(cell);}const thead=el('thead');thead.append(head);table.append(thead);
  const body=el('tbody');const format=(v,u)=>Number.isFinite(v)?`${new Intl.NumberFormat(lang,{maximumFractionDigits:u==='kWh'?5: u==='EUR'?4:2}).format(v)} ${u}`:wt(lang,'unknown');
  for(const [key,u] of [['flow_time_s','s'],['energy_kwh','kWh'],['co2e_g','gCO₂e'],['cost_eur','EUR'],['labour_time_s','s'],['thread_used_m','m']]){
    const row=el('tr');const name=el('th',wt(lang,key));name.scope='row';row.append(name,el('td',format(current?.[key],u)),el('td',format(planned?.[key],u)));body.append(row);
  }table.append(body);root.append(table);
  const details=el('details');details.append(el('summary',wt(lang,'costs')));const dl=el('dl');dl.className='resource-breakdown';
  for(const key of ['fabric','thread','labour','electricity','equipment'])dl.append(el('dt',wt(lang,key)),el('dd',`${format(current?.cost_breakdown_eur?.[key],'EUR')} / ${format(planned?.cost_breakdown_eur?.[key],'EUR')}`));details.append(dl);root.append(details);
  if(preset){const more=el('details');more.append(el('summary',wt(lang,'assumptions')));const list=el('dl');list.className='resource-breakdown';for(const [key,value] of Object.entries(preset))list.append(el('dt',wt(lang,key)),el('dd',`${value} ${key==='currency'?'':unit(key)}`));more.append(list);root.append(more);}
  for(const key of ['estimateNote','labourNote']){const note=el('p',wt(lang,key));note.className='muted note';root.append(note);}
  root.querySelectorAll('details').forEach((d,i)=>{d.open=!!opened[i];});
  if(focus>=0)root.querySelectorAll('summary')[focus]?.focus({preventScroll:true});
}
