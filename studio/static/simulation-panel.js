import { CuttingViewer } from './simulation-viewer.js';
import { st } from './simulation-i18n.js';
import {wt,unit} from './workflow-i18n.js';
import {resourceView} from './resource-view.js';

const $=id=>document.getElementById(id);
export class SimulationPanel {
  constructor({lang,onExample,onState}) {
    this.lang=lang;this.onExample=onExample;this.onState=onState;this.job=null;this.run=null;this.state=null;this.seq=-1;this.config=null;this.inputRows=[];
    this.root=$('simulation-panel');this.mode='both';this.generation=0;this.restoreRequest=0;
    try {this.viewer=new CuttingViewer($('cutting-canvas'),()=>this.webglError());}catch(e){this.webglError();}
    this.root.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>this.setMode(b.dataset.view));
    this.root.querySelectorAll('[data-camera]').forEach(b=>b.onclick=()=>{
      this.viewer?.cameraMode(b.dataset.camera);this.root.querySelectorAll('[data-camera]').forEach(x=>x.classList.toggle('selected',x===b));
    });
    this.root.querySelectorAll('[data-control]').forEach(b=>b.onclick=()=>this.control(b.dataset.control));
    $('sim-start').onclick=()=>this.start();
    $('sim-example').onclick=()=>this.example();
    $('sim-scope').onchange=()=>{this.config.scope=$('sim-scope').value;this.renderMachines();};
    $('sim-speed').onchange=()=>this.state?this.control('speed',+$('sim-speed').value):null;
    $('sim-seek').onchange=()=>this.control('seek',+$('sim-seek').value);
    $('sim-seek').oninput=()=>{$('sim-time').textContent=`${(+$('sim-seek').value).toFixed(1)} s`;};
    $('sim-download').onclick=()=>{if(this.job)window.location.href=`/api/jobs/${this.job}/simulation/download`;};
    this.ready=this.init();
  }
  t(key){return st(this.lang(),key);}
  async init(){
    try {
      const r=await fetch('/api/simulation/options');if(!r.ok)throw new Error(await r.text());this.options=await r.json();
      this.config=structuredClone(this.options.defaults);
      try {const saved=JSON.parse(localStorage.getItem('studio.cutting.profile')||'null');if(saved){for(const key of ['design','machine','resources'])this.config[key]={...this.config[key],...saved[key]};}}catch(e){}
      this.viewer?.makeMachines(this.options.machines);this.renderInputs();this.localize();
    }catch(e){this.error(e.message);}
  }
  webglError(){this.viewer=null;this.root.classList.add('no-webgl');this.setMode('terminal');this.error(this.t('noWebGL'));}
  error(message){$('sim-error').textContent=message||'';}
  localize(){
    $('resource-input-title').textContent=wt(this.lang(),'assumptions');
    $('resource-input-note').textContent=wt(this.lang(),'estimateNote')+' '+wt(this.lang(),'newRun');
    this.root.querySelectorAll('[data-st]').forEach(el=>el.textContent=this.t(el.dataset.st));
    this.root.querySelectorAll('[data-st-aria]').forEach(el=>el.setAttribute('aria-label',this.t(el.dataset.stAria)));
    this.renderMachines();this.renderInputs();if(this.state)this.renderState(this.state);
    $('sim-example-note').textContent=this.exampleJob?this.t('synthetic'):'';
  }
  setMode(mode){if(!this.viewer&&mode!=='terminal')mode='terminal';this.mode=mode;this.root.dataset.mode=mode;
    this.root.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('selected',b.dataset.view===mode);b.setAttribute('aria-pressed',String(b.dataset.view===mode));});this.viewer?.resize();}
  async setJob(job){
    await this.ready;this.job=job;this.generation++;this.run=null;this.state=null;this.seq=-1;this.inputRows=[];
    this.config.manual={};$('sim-terminal').textContent='';$('sim-empty').hidden=false;this.error('');
    this.plan=null;this.viewer?.clear();$('sim-example-note').textContent='';$('sim-part-list').replaceChildren();
    for(const id of ['sim-cut','sim-travel'])$(id).textContent='0.00 m';$('sim-yield').textContent='—';$('sim-parts-count').textContent='0 / 9';
    $('sim-status').textContent=this.t('waiting');$('sim-operation').textContent=this.t('plan');$('sim-time').textContent='0.0 s';
    $('sim-cli').textContent=job?`python -m studio.simulate --attach ${job} --server ${location.origin}`:'';
    this.root.querySelectorAll('[data-control],#sim-download,#sim-seek,#sim-speed').forEach(x=>x.disabled=true);
    $('sim-start').disabled=!job;
    $('sim-sewn').textContent='0.00 m';$('sim-stitches').textContent='0';
    if(job)await this.restore();
    else resourceView($('sim-resource-card'),null,null,null,this.lang());
  }
  async restore(){
    if(!this.job)return;const job=this.job,generation=this.generation,request=++this.restoreRequest;
    try {
      const r=await fetch(`/api/jobs/${job}/simulation`);if(!r.ok)throw new Error((await r.json()).detail);
      const data=await r.json();if(this.job!==job||this.generation!==generation||this.restoreRequest!==request)return;
    this.inputRows=data.inputs;this.exampleJob=!!data.example;
    $('sim-example-note').textContent=this.exampleJob?this.t('synthetic'):'';
      if(data.plan&&data.state){
        if(this.run!==data.state.run_id){this.run=data.state.run_id;this.seq=-1;this.config={resources:structuredClone(this.options.defaults.resources),...structuredClone(data.plan.config)};this.viewer?.setPlan(data.plan);this.plan=data.plan;}
        this.receive(data.state);
      }
      this.renderInputs();
    }catch(e){this.error(String(e.message));}
  }
  receive(s){
    if(s.run_id!==this.run){this.restore();return;}
    if(s.seq<=this.seq)return;this.seq=s.seq;this.state=s;
    $('sim-empty').hidden=true;
    this.viewer?.apply(s);this.renderState(s);this.onState?.(s);
  }
  renderState(s){
    resourceView($('sim-resource-card'),s.resources,this.plan?.totals.resources,s.size,this.lang(),this.plan?.config.resources);
    this.root.querySelectorAll('[data-control],#sim-download,#sim-seek,#sim-speed').forEach(x=>x.disabled=false);
    $('sim-status').textContent=this.t(s.status);$('sim-operation').textContent=this.t(s.operation);
    $('sim-active-part').textContent=s.machine_id==='pfaff'?`Pfaff · ${this.t(s.sewing?.seam_id||s.operation)}`:s.piece_id?this.t(s.piece_id):`Zünd S3 · ${s.window+1}/${this.plan?.windows.length||'—'}`;
    $('sim-time').textContent=`${s.sim_time_s.toFixed(1)} / ${s.duration_s.toFixed(1)} s`;
    $('sim-seek').max=s.duration_s;if(document.activeElement!==$('sim-seek'))$('sim-seek').value=s.sim_time_s;
    $('sim-speed').value=s.speed;
    $('sim-cut').textContent=`${(s.metrics.cut_length_mm/1000).toFixed(2)} m`;
    $('sim-travel').textContent=`${(s.metrics.travel_mm/1000).toFixed(2)} m`;
    $('sim-sewn').textContent=`${((s.metrics.sewn_length_mm||0)/1000).toFixed(2)} m`;
    $('sim-stitches').textContent=`${s.metrics.stitches||0} · ${s.metrics.seams_complete||0}/${s.metrics.seams_total||0}`;
    if(s.finished)$('sim-status').textContent=this.t(s.sewing_complete?'sewingComplete':'cuttingComplete');
    this.root.querySelectorAll('[data-machine-status]').forEach(el=>el.textContent=this.t(s.machines[el.dataset.machineStatus]));
    $('sim-yield').textContent=`${s.metrics.yield_pct.toFixed(1)}%`;
    $('sim-parts-count').textContent=`${s.metrics.collected_pieces} / ${Object.keys(s.pieces).length}`;
    $('sim-terminal').textContent=(s.terminal_lines||this.terminalLines(s)).join('\n');
    $('sim-part-list').replaceChildren(...Object.entries(s.pieces).map(([id,status])=>{
      const item=document.createElement('div');item.className=`sim-part ${status}`;
      const name=document.createElement('span');name.textContent=this.t(id);
      const badge=document.createElement('b');badge.textContent=this.t(status==='cut'?'cut_done':status);item.append(name,badge);return item;
    }));
    const play=this.root.querySelector('[data-control="play"]');play.disabled=s.status==='playing';
    this.root.querySelector('[data-control="pause"]').disabled=s.status!=='playing';
  }
  terminalLines(s){
    // A reconnect immediately obtains the server's terminal renderer too.
    return [`${s.status} · ${s.sim_time_s.toFixed(2)} s · ${s.operation}`,
      `X ${s.head_mm[0].toFixed(2)} Y ${s.head_mm[1].toFixed(2)} mm · ${s.tool}`];
  }
  async control(action,value){
    if(!this.job||!this.state)return;
    try {const r=await fetch(`/api/jobs/${this.job}/simulation/control`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:this.run,action,value})});
      const data=await r.json();if(!r.ok)throw new Error(this.detail(data));this.receive(data);this.error('');
    }catch(e){this.error(e.message);}
  }
  detail(data){const d=data.detail;return typeof d==='string'?d:d?.message||JSON.stringify(d);}
  async start(){
    if(!this.job){this.error(this.t('empty'));return;}
    $('sim-start').disabled=true;this.error('');
    try {
      // Native constraints catch missing source reasons before sending a plan.
      if(!$('sim-input-form').checkValidity()){$('sim-inputs').open=true;$('sim-input-form').reportValidity();return;}
      const config=structuredClone(this.config);config.speed=+$('sim-speed').value||10;
      const r=await fetch(`/api/jobs/${this.job}/run/simulate`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});
      const data=await r.json();if(!r.ok)throw new Error(this.detail(data));
      localStorage.setItem('studio.cutting.profile',JSON.stringify({design:config.design,machine:config.machine,resources:config.resources}));
      await this.restore();
    }catch(e){this.error(e.message);$('sim-inputs').open=true;}
    finally {$('sim-start').disabled=!this.job;}
  }
  async example(){
    try {const r=await fetch('/api/simulation/example',{method:'POST'});if(!r.ok)throw new Error(await r.text());const data=await r.json();
      await this.onExample(data.job_id);this.config={...structuredClone(this.options.defaults),...data.config};
      this.renderInputs();$('sim-example-note').textContent=this.t('synthetic');await this.start();
    }catch(e){this.error(e.message);}
  }
  renderMachines(){
    if(!this.options)return;
    $('sim-machine-list').replaceChildren(...this.options.machines.map(m=>{
      const b=document.createElement('button');b.type='button';b.className=`sim-machine ${m.role}`;
      const name=document.createElement('strong');name.textContent=m.name;
      const status=document.createElement('span');status.dataset.machineStatus=m.id;status.textContent=this.t(m.id==='pfaff'&&this.config?.scope==='through_cutting'?'downstream':m.role);b.append(name,status);
      b.onclick=()=>{this.viewer?.focus(m.id);$('sim-machine-detail').textContent=`${m.name} · ${this.t(m.source==='plan'?'planSource':'polo_addition')} · ${this.t(m.shape==='cutting'?'cuttingDetail':m.shape==='sewing'?'sewingDetail':m.shape)}`;};return b;
    }));
  }
  renderInputs(){
    if(!this.config||!this.options)return;
    $('sim-scope').value=this.config.scope||'through_cutting';
    for(const group of ['design','machine','resources']){
      const schema=this.options.schema.$defs[{design:'Design',machine:'Machine',resources:'Resources'}[group]].properties;
      $(`sim-${group}-inputs`).replaceChildren(...Object.entries(this.config[group]||{}).filter(([key])=>key!=='currency').map(([key,value])=>{
        const label=document.createElement('label');label.textContent=group==='resources'?wt(this.lang(),key):this.t(key);
        const wrap=document.createElement('span');wrap.className='sim-number';
        const input=document.createElement('input');input.type='number';input.value=value;input.step='any';input.required=true;
        input.min=schema[key].minimum;input.max=schema[key].maximum;input.setAttribute('aria-label',label.textContent);input.dataset.configKey=key;input.dataset.configGroup=group;
        input.oninput=()=>{this.config[group][key]=input.value===''?null:+input.value;};
        const suffix=document.createElement('small');suffix.textContent=group==='resources'?unit(key):key==='stitches_per_min'?'st/min':key.endsWith('_mm_s')?'mm/s':key.endsWith('_mm')?'mm':key.endsWith('_pct')?'%':key.endsWith('_s')?'s':'×';
        wrap.append(input,suffix);label.append(wrap);return label;
      }));
    }
    $('sim-body-inputs').replaceChildren(...Object.entries(this.options.required).map(([key,rule])=>{
      const row=this.inputRows.find(r=>r.key===key);const manual=this.config.manual[key];
      const wrap=document.createElement('div');wrap.className='sim-body-row';
      const label=document.createElement('label');label.textContent=this.t(key);
      const detail=document.createElement('small');detail.textContent=`${row?.value??'—'} ${rule.unit} · ${this.t(row?.source||'missing')}${row?.auto_basis?' · '+row.auto_basis:''}${row?.reason?' · '+row.reason:''}`;
      label.append(detail);const number=document.createElement('input');number.type='number';number.step='any';number.min=rule.min;number.max=rule.max;number.value=manual?.value??(row?.usable?row.value:'');
      number.placeholder=`${this.t('manual')} (${rule.unit})`;number.setAttribute('aria-label',`${this.t(key)} ${this.t('manual')}`);
      const reason=document.createElement('input');reason.type='text';reason.value=manual?.reason||'';reason.placeholder=this.t('reason');reason.setAttribute('aria-label',`${this.t(key)} ${this.t('reason')}`);reason.maxLength=500;reason.required=!!manual;
      const update=()=>{if(number.value===''){delete this.config.manual[key];reason.required=false;}else{this.config.manual[key]={value:+number.value,unit:rule.unit,reason:reason.value};reason.required=true;}};
      number.oninput=reason.oninput=update;wrap.append(label,number,reason);return wrap;
    }));
  }
}
