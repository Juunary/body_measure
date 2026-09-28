import {DesktopViewer} from './polo-viewer.js';
import {uiCopy,machineNames,fieldNames,stepNames} from './desktop-copy.js';
import {ResponseGate,chaptersFor,duration} from './desktop-state.js';

const $=id=>document.getElementById(id);
const stages=['cutting','sewing','buttons','qc','ready_for_qr'];
const machines=['zund','pfaff','overlock','button','qc'];
const text={
 ko:{title:'3D 폴로 생산 시뮬레이터',openMeasurement:'측정 JSON 열기',example:'연구 예제',openProject:'프로젝트 열기',saveProject:'저장',source:'입력',noSource:'측정 결과 또는 예제를 여세요',generate:'계획 생성·재생',overview:'전체 공정',cutter:'재단기',top:'원단 위',autoFollow:'공정 자동 추적',empty:'측정 결과를 열거나 연구 예제로 시작하세요.',webglError:'3D 가속을 시작하지 못했습니다. WebView2와 그래픽 드라이버를 확인하세요.',currentStage:'현재 공정',time:'시간',energy:'전력',cost:'비용',sewn:'봉제 길이',buttons:'단추',equipment:'설비',ready:'QC 정상 · QR 발급 준비 완료',notIssued:'QR은 아직 발급되지 않았습니다.',play:'재생',pause:'일시정지',restart:'처음부터',timeline:'공정 타임라인',speed:'배속',terminal:'터미널',settings:'패턴·장비·공정 설정',settingsNote:'모든 수치는 연구용 가정입니다. 측정에서 쓸 수 없는 값만 수동 보완하고 사유를 기록하세요.',pattern:'패턴',process:'봉제·단추·QC',manual:'측정값 수동 보완',disclaimer:'연구 시뮬레이션입니다. 실제 제품·설비·품질을 검증하지 않습니다.',cutting:'재단',sewing:'봉제',buttonsStage:'단추 작업',finishing:'스팀 마감',qc:'품질검사',ready_for_qr:'QR 발급 준비',working:'작업 중',complete:'완료',waiting:'대기',paused:'일시정지',playing:'재생 중',completed:'완료'},
 en:{title:'3D Polo Manufacturing Simulator',openMeasurement:'Open measurement JSON',example:'Research example',openProject:'Open project',saveProject:'Save',source:'Input',noSource:'Open a measurement result or example',generate:'Generate & play',overview:'Full line',cutter:'Cutter',top:'Fabric top',autoFollow:'Follow process',empty:'Open a measurement result or start with the research example.',webglError:'3D acceleration failed. Check WebView2 and the graphics driver.',currentStage:'Current stage',time:'Time',energy:'Energy',cost:'Cost',sewn:'Sewn length',buttons:'Buttons',equipment:'Equipment',ready:'QC pass · Ready for QR',notIssued:'No QR has been issued.',play:'Play',pause:'Pause',restart:'Restart',timeline:'Process timeline',speed:'Speed',terminal:'Terminal',settings:'Pattern, machine & process settings',settingsNote:'All values are research assumptions. Supplement only unusable measurements and record a reason.',pattern:'Pattern',process:'Sewing, buttons & QC',manual:'Manual measurement supplements',disclaimer:'Research simulation. It does not validate a real product, machine or quality result.',cutting:'Cutting',sewing:'Sewing',buttonsStage:'Buttons',finishing:'Steam finishing',qc:'Quality control',ready_for_qr:'Ready for QR',working:'Working',complete:'Complete',waiting:'Waiting',paused:'Paused',playing:'Playing',completed:'Complete'},
 de:{title:'3D-Polo-Produktionssimulation',openMeasurement:'Mess-JSON öffnen',example:'Forschungsbeispiel',openProject:'Projekt öffnen',saveProject:'Speichern',source:'Eingabe',noSource:'Messergebnis oder Beispiel öffnen',generate:'Plan erstellen & abspielen',overview:'Gesamtprozess',cutter:'Cutter',top:'Stoffansicht',autoFollow:'Prozess folgen',empty:'Öffnen Sie ein Messergebnis oder das Forschungsbeispiel.',webglError:'3D-Beschleunigung fehlgeschlagen. WebView2 und Grafiktreiber prüfen.',currentStage:'Aktueller Prozess',time:'Zeit',energy:'Energie',cost:'Kosten',sewn:'Nahtlänge',buttons:'Knöpfe',equipment:'Maschinen',ready:'QC bestanden · Bereit für QR',notIssued:'Es wurde noch kein QR erzeugt.',play:'Abspielen',pause:'Pause',restart:'Neustart',timeline:'Prozesszeitleiste',speed:'Tempo',terminal:'Terminal',settings:'Schnitt-, Maschinen- und Prozesseinstellungen',settingsNote:'Alle Werte sind Forschungsannahmen. Nur ungeeignete Messwerte manuell mit Begründung ergänzen.',pattern:'Schnitt',process:'Nähen, Knöpfe & QC',manual:'Manuelle Messwert-Ergänzungen',disclaimer:'Forschungssimulation. Keine Validierung realer Produkte, Maschinen oder Qualität.',cutting:'Zuschnitt',sewing:'Nähen',buttonsStage:'Knöpfe',finishing:'Dampffinish',qc:'Qualitätsprüfung',ready_for_qr:'Bereit für QR',working:'In Arbeit',complete:'Fertig',waiting:'Wartet',paused:'Pause',playing:'Läuft',completed:'Fertig'}
};
for(const language of Object.keys(text))Object.assign(text[language],uiCopy[language]);
const operations={load:'원단 적재',feed:'원단 이송',align:'정렬',mark:'마킹',cut_internal:'내부 절단',cut_outer:'외곽 절단',pickup:'재단물 회수',sewing_setup:'재봉기 준비',seam_align:'봉합선 정렬',presser_down:'노루발 하강',stitch:'봉제 진행',thread_trim:'실 절단',presser_up:'노루발 상승',assembly_pickup:'조립물 회수',button_setup:'단추 장비 준비',buttonhole_align:'단춧구멍 정렬',buttonhole_stitch:'단춧구멍 봉제',buttonhole_cut:'단춧구멍 절개',button_attach_align:'단추 정렬',button_attach_stitch:'단추 부착',hand_work:'수작업',qc_load:'검사대 투입',qc_scan:'카메라 검사',qc_release:'검사 완료·배출',ready_for_qr:'QR 발급 전 대기'};
const labels={zund:'Zünd S3',pfaff:'Pfaff 본봉',overlock:'오버로크',button:'단춧구멍·단추',qc:'Camera QC'};
let lang=localStorage.getItem('polo.lang')||'ko',config=null,plan=null,polling=false;
if(!text[lang])lang='ko';
let viewer=null;
function createViewer(){try{viewer=new DesktopViewer($('desktop-canvas'),()=>{$('webgl-error').hidden=false});viewer.onManualCamera=()=>{$('auto-follow').checked=false};$('webgl-error').hidden=true}catch(e){$('webgl-error').hidden=false;viewer=null;console.error(e)}}
createViewer();
function tr(k){return text[lang][k]||k}
function localize(){document.documentElement.lang=lang;document.querySelectorAll('[data-i18n]').forEach(x=>x.textContent=tr(x.dataset.i18n));document.querySelectorAll('[data-title]').forEach(x=>x.title=tr(x.dataset.title));renderStageTrack();renderMachines();renderCosts();if(lastState)renderState(lastState);}
function error(message=''){$('error').textContent=message}
async function api(method,...args){const result=await window.pywebview.api[method](...args);if(!result.ok)throw new Error(result.error);return result.data}
function get(obj,path){return path.split('.').reduce((v,k)=>v?.[k],obj)}
function set(obj,path,value){const bits=path.split('.');let node=obj;for(const key of bits.slice(0,-1))node=node[key];node[bits.at(-1)]=value}
const fields=[
 ['design.chest_ease_mm','Chest ease','mm'],['design.length_mm','Garment length','mm'],['design.sleeve_length_mm','Sleeve length','mm'],['design.seam_mm','Seam allowance','mm'],['design.shrink_pct','Shrinkage','%'],['design.placket_length_mm','Placket length','mm'],['design.placket_width_mm','Placket width','mm']
];
const processFields=[
 ['process.transfer_s','Station transfer','s'],['process.lockstitch.active_kw','Lockstitch power','kW'],['process.overlock.active_kw','Overlock power','kW'],
 ['process.buttons.count','Button count',''],['process.buttons.top_offset_mm','Button top offset','mm'],['process.buttons.spacing_mm','Button spacing','mm'],['process.buttons.diameter_mm','Button diameter','mm'],['process.buttons.hole_length_mm','Buttonhole length','mm'],['process.buttons.hole_stitches','Buttonhole stitches','st'],['process.buttons.attach_stitches','Button attach stitches','st'],
 ['process.qc.load_s','QC load','s'],['process.qc.scan_s','QC scan','s'],['process.qc.release_s','QC release','s'],['process.qc.active_kw','QC power','kW']
];
const manualKeys=['chest_circumference','waist_circumference','neck_circumference','across_back_shoulder_width','back_length','upper_arm_girth','hip_girth','sleeve_opening_girth','armhole_depth','shoulder_slope','front_back_width'];

const gate=new ResponseGate();
let lastState=null,chapters=[],epoch=0,busy=false,hasDocument=false,scrubbing=false,loadedSource=null;
let controlQueue=Promise.resolve(),noticeTimer;
const machineButtons=new Map();
const fieldLabel=name=>fieldNames[name]?.[['ko','en','de'].indexOf(lang)]||name;
function notice(message){clearTimeout(noticeTimer);$('notice').textContent=message;noticeTimer=setTimeout(()=>$('notice').textContent='',3500)}
function numberField([path,label,unit],parent){
  const el=document.createElement('label');el.textContent=fieldLabel(label);
  const input=document.createElement('input');input.type='number';input.step='any';input.required=true;
  input.value=get(config,path);input.dataset.path=path;input.setAttribute('aria-label',fieldLabel(label));
  if(path.endsWith('.count')){input.step='1';input.min='1';input.max='4'}
  input.oninput=()=>{set(config,path,input.value===''?null:+input.value);$('dirty').hidden=false};
  const small=document.createElement('small');small.textContent=unit;el.append(input,small);parent.append(el);
}
function renderConfig(){
  if(!config)return;
  $('pattern-inputs').replaceChildren();$('process-inputs').replaceChildren();
  fields.forEach(f=>numberField(f,$('pattern-inputs')));
  processFields.forEach(f=>numberField(f,$('process-inputs')));
  $('manual-inputs').replaceChildren();
  manualKeys.forEach(key=>{
    const row=document.createElement('div');row.className='manual-row';
    const name=document.createElement('small');name.textContent=fieldLabel(key);name.title=key;
    const value=document.createElement('input');value.type='number';value.step='any';
    value.placeholder=key==='shoulder_slope'?'deg':'mm';value.value=config.manual[key]?.value??'';
    value.setAttribute('aria-label',fieldLabel(key));
    const reason=document.createElement('input');
    reason.placeholder={ko:'수동 보완 사유',en:'Reason',de:'Begründung'}[lang];
    reason.setAttribute('aria-label',fieldLabel(key)+' '+reason.placeholder);
    reason.value=config.manual[key]?.reason??'';reason.required=value.value!=='';
    const update=()=>{
      if(value.value==='')delete config.manual[key];
      else config.manual[key]={value:+value.value,unit:key==='shoulder_slope'?'deg':'mm',reason:reason.value};
      reason.required=value.value!=='';$('dirty').hidden=false;
    };
    value.oninput=reason.oninput=update;row.append(name,value,reason);$('manual-inputs').append(row);
  });
}
function chapterName(key){return tr(key==='buttons'?'buttonsStage':key)}
function machineName(id){const i=machines.indexOf(id);return i>=0?machineNames[lang][i]:tr(id)}
function renderStageTrack(){
  const rows=chapters.length?chapters:['cutting','sewing','buttons','qc','ready_for_qr'].map(id=>({id}));
  $('stage-track').replaceChildren(...rows.map((row,i)=>{
    const button=document.createElement('button');button.type='button';button.disabled=!plan;
    button.dataset.chapter=row.id;
    const number=document.createElement('small');number.textContent=String(i+1).padStart(2,'0');
    const label=document.createElement('b');label.textContent=chapterName(row.id);
    const time=document.createElement('span');time.className='chapter-time';time.textContent=plan?(row.id==='ready_for_qr'?tr('waiting'):duration(row.duration_s)):'—';
    const bar=document.createElement('i');button.append(number,label,time,bar);
    button.onclick=()=>control('seek',row.start_s);return button;
  }));
}
function renderMachines(){
  machineButtons.clear();
  $('machines').replaceChildren(...machines.map(id=>{
    const b=document.createElement('button'),name=document.createElement('b'),status=document.createElement('span');
    name.textContent=machineName(id);status.textContent=tr('waiting');b.append(name,status);
    b.disabled=!plan;b.onclick=()=>{$('auto-follow').checked=false;viewer?.setAutoFollow(false);viewer?.focus(id)};
    machineButtons.set(id,b);return b;
  }));
}
function renderCosts(){
  $('cost-breakdown').replaceChildren(...['fabric','thread','labour','electricity','equipment'].map(key=>{
    const row=document.createElement('div');row.className='cost-row';row.dataset.cost=key;
    const info=document.createElement('div'),name=document.createElement('span'),value=document.createElement('b');
    name.textContent=tr(key==='equipment'?'equipmentCost':key);value.textContent='€0.000';info.append(name,value);
    const track=document.createElement('i');track.append(document.createElement('i'));row.append(info,track);return row;
  }));
  const planned=document.createElement('p');planned.className='cost-total';planned.id='cost-planned';$('cost-breakdown').append(planned);
}
const opDE={load:'Stoff einlegen',feed:'Stofftransport',align:'Ausrichten',mark:'Markieren',travel:'Werkzeug verfahren',tool_up:'Werkzeug anheben',tool_down:'Werkzeug absenken',vacuum_on:'Vakuum einschalten',vacuum_off:'Vakuum ausschalten',cut_internal:'Innenschnitt',cut_outer:'Außenkontur schneiden',pickup:'Schnittteil aufnehmen',stitch:'Naht nähen',hand_work:'Handarbeit',button_setup:'Knopfstation vorbereiten',buttonhole_align:'Knopfloch ausrichten',buttonhole_stitch:'Knopfloch nähen',buttonhole_cut:'Knopfloch schneiden',button_attach_align:'Knopf ausrichten',button_attach_stitch:'Knopf annähen',qc_load:'Prüftisch beladen',qc_scan:'Kamera-Scan',qc_release:'Prüfung abschließen',ready_for_qr:'Bereit für QR'};
Object.assign(operations,{travel:'헤드 이동',tool_up:'절단 도구 상승',tool_down:'절단 도구 하강',vacuum_on:'원단 흡착',vacuum_off:'흡착 해제'});
function operationName(s){
  if(s.transport)return tr('transport')+' · '+machineName(s.transport.to);
  if(s.step)return String(s.step.no).padStart(2,'0')+' · '+(stepNames[s.step.no]?.[['ko','en','de'].indexOf(lang)]||s.step.name);
  return lang==='ko'?(operations[s.operation]||s.operation):lang==='de'?(opDE[s.operation]||s.operation):s.operation.replaceAll('_',' ');
}
function renderState(s){
  const chapterIndex=chapters.findIndex(c=>c.id===s.chapter);
  $('status').textContent=tr(s.ready_for_qr?'completed':s.status);$('operation').textContent=operationName(s);
  $('machine').textContent=machineName(s.focus_machine_id||s.machine_id);
  const help=s.transport?'transferHelp':s.stage==='cutting'?'cutHelp':s.stage==='sewing'?'sewHelp':s.stage==='buttons'?'buttonHelp':s.stage==='qc'?'qcHelp':'readyHelp';
  $('operation-help').textContent=tr(help);
  const progress=s.ready_for_qr?1:s.operation_progress;
  $('op-progress').value=progress;$('op-percent').textContent=Math.round(progress*100)+'%';
  $('metric-time').textContent=duration(s.sim_time_s);
  $('metric-energy').textContent=s.resources.energy_kwh.toFixed(4)+' kWh';
  $('metric-co2').textContent=s.resources.co2e_g.toFixed(1)+' g';
  $('metric-cost').textContent='€'+s.resources.cost_eur.toFixed(3);
  $('metric-sewn').textContent=(s.metrics.sewn_length_mm/1000).toFixed(2)+' m';
  $('metric-buttons').textContent=s.metrics.buttons_attached+' / '+s.metrics.buttons_total;
  $('clock').textContent=duration(s.sim_time_s)+' / '+duration(s.duration_s);
  $('seek').max=s.duration_s;if(!scrubbing)$('seek').value=s.sim_time_s;
  $('speed').value=String(s.speed);
  $('play-toggle').textContent=tr(s.status==='playing'?'pause':'play');
  $('terminal-output').textContent=s.terminal_lines.join('\n');
  $('remaining').textContent=s.ready_for_qr?tr('ready'):tr('remaining')+' · '+duration((s.duration_s-s.sim_time_s)/s.speed);
  $('timeline-label').textContent=Math.round(s.sim_time_s/s.duration_s*100)+'%';
  $('ready-card').hidden=!s.ready_for_qr;
  $('viewer-caption').hidden=false;$('scene-index').textContent=String(chapterIndex+1).padStart(2,'0')+' / '+String(chapters.length).padStart(2,'0');
  $('scene-title').textContent=chapterName(s.chapter);
  $('scene-subtitle').textContent=s.stage==='cutting'?tr('parts')+' '+s.metrics.collected_pieces+' / 9':
    s.stage==='sewing'?tr('steps')+' '+s.metrics.steps_complete+' / '+s.metrics.steps_total+' · '+tr('seams')+' '+s.metrics.seams_complete+' / '+s.metrics.seams_total+' · '+duration(s.metrics.sewing_work_s):tr('yield')+' '+s.metrics.yield_pct.toFixed(1)+'%';
  const seam=plan.sewing_seams.find(x=>x.id===s.sewing.seam_id);
  $('seam-detail').hidden=!seam;
  if(seam)$('seam-detail').textContent=seam.id.replaceAll('_',' ')+' · '+seam.length_mm.toFixed(0)+' mm · '+seam.stitches+' '+tr('stitches');
  const readoutKey=JSON.stringify(s.readouts);
  if($('readouts').dataset.key!==readoutKey+lang){
    $('readouts').dataset.key=readoutKey+lang;
    $('readouts').replaceChildren(...Object.entries(s.readouts||{}).map(([key,val])=>{
      const span=document.createElement('span'),unit={press_temp_c:' °C',steam_bar:' bar',humidity_pct:' %'}[key]||'';
      span.textContent=tr(key)+' '+(typeof val==='number'?(key==='frames'?val:val.toFixed(1))+unit:tr(val));return span;
    }));
  }
  [...$('stage-track').children].forEach((button,i)=>{
    button.classList.toggle('done',i<chapterIndex);button.classList.toggle('active',i===chapterIndex);
    button.setAttribute('aria-current',i===chapterIndex?'step':'false');
    button.querySelector('i').style.width=(i<chapterIndex?100:i===chapterIndex?s.chapter_progress*100:0)+'%';
  });
  for(const [id,button] of machineButtons){
    button.className=s.machines[id];button.lastChild.textContent=tr(s.machines[id]||'waiting');
  }
  $('cost-breakdown').querySelectorAll('[data-cost]').forEach(row=>{
    const amount=s.resources.cost_breakdown_eur[row.dataset.cost];
    row.querySelector('b').textContent='€'+amount.toFixed(3);
    row.querySelector('i i').style.width=(amount/Math.max(.001,s.resources.cost_eur)*100)+'%';
  });
  $('cost-planned').textContent=tr('planned')+' €'+plan.totals.resources.cost_eur.toFixed(3);
}
function applyState(s){
  if(!gate.accept(s))return;
  lastState=s;$('empty').hidden=true;viewer?.apply(s);renderState(s);
}
function controlsEnabled(){
  document.querySelectorAll('[data-control],#seek,#speed,#save-project').forEach(el=>el.disabled=!plan||busy);
  document.querySelectorAll('#example,#open-measure,#open-project,#empty-start').forEach(el=>el.disabled=busy);
  $('generate').disabled=!hasDocument||busy;
}
function setBusy(value){busy=value;document.body.classList.toggle('busy',value);controlsEnabled()}
function sourceName(data){
  loadedSource=data;
  const name=data.source?.kind==='synthetic_example'?tr('synthetic'):data.summary||data.source?.path||data.path||'Project';
  $('source-name').textContent=name.split(/[\\/]/).at(-1);$('source-name').title=name;
}
function loadRun(data){
  epoch++;plan=data.plan;chapters=chaptersFor(plan);config=data.config||plan.config;
  gate.reset(data.state);hasDocument=true;
  viewer?.setPlan(plan);renderConfig();renderStageTrack();renderMachines();renderCosts();
  applyState(data.state);sourceName(data);$('dirty').hidden=true;controlsEnabled();
}
function clearRun(){
  epoch++;gate.reset();plan=null;lastState=null;chapters=[];viewer?.clear();
  $('viewer-caption').hidden=true;$('empty').hidden=false;$('ready-card').hidden=true;
  for(const id of ['status','operation','machine','metric-time','metric-energy','metric-co2','metric-cost','metric-sewn','metric-buttons','clock','remaining'])$(id).textContent='—';
  $('operation-help').textContent='';$('readouts').replaceChildren();$('readouts').dataset.key='';
  $('seam-detail').hidden=true;$('terminal-output').textContent='';$('seek').value=0;
  $('op-progress').value=0;$('op-percent').textContent='0%';$('timeline-label').textContent='0%';
  renderStageTrack();renderMachines();renderCosts();controlsEnabled();
}
async function action(fn){
  if(busy)return;setBusy(true);error();
  try{await fn()}catch(e){error(e.message)}finally{setBusy(false)}
}
function control(action,value=null){
  const requestedEpoch=epoch;
  controlQueue=controlQueue.then(async()=>{
    if(!plan||requestedEpoch!==epoch)return;
    try{
      error();const name=action==='toggle'?(lastState.status==='playing'?'pause':'play'):action;
      const s=await api('control',name,value);
      if(requestedEpoch===epoch)applyState(s);
    }catch(e){error(e.message)}
  });
  return controlQueue;
}
document.querySelectorAll('[data-camera]').forEach(b=>b.onclick=()=>{
  $('auto-follow').checked=false;viewer?.setAutoFollow(false);viewer?.cameraMode(b.dataset.camera);
});
$('auto-follow').onchange=e=>{
  viewer?.setAutoFollow(e.target.checked);
  if(e.target.checked&&lastState)viewer?.focus(lastState.focus_machine_id);
};
$('show-labels').onchange=e=>viewer?.setLabels(e.target.checked);
$('language').value=lang;
$('language').onchange=e=>{
  lang=e.target.value;localStorage.setItem('polo.lang',lang);localize();renderConfig();
  if(loadedSource)sourceName(loadedSource);
};
$('example').onclick=()=>action(async()=>{
  const data=await api('load_example');clearRun();config=data.config;hasDocument=true;
  sourceName(data);renderConfig();notice(tr('generating'));loadRun(await api('generate',config));
});
$('empty-start').onclick=()=>$('example').click();
$('open-measure').onclick=()=>action(async()=>{
  const data=await api('choose_measurement');if(!data)return;
  clearRun();hasDocument=true;sourceName(data);$('settings-panel').open=true;
});
$('open-project').onclick=()=>action(async()=>{
  const data=await api('choose_project');if(data){loadRun(data);notice(tr('loaded'))}
});
$('save-project').onclick=()=>action(async()=>{
  const data=await api('save_project');if(data)notice(tr('saved'));
});
$('generate').onclick=()=>action(async()=>{
  if(!$('settings-form').reportValidity()){$('settings-panel').open=true;return}
  notice(tr('generating'));loadRun(await api('generate',config));
});
document.querySelectorAll('[data-control]').forEach(b=>b.onclick=()=>control(b.dataset.control));
$('seek').oninput=e=>{scrubbing=true;$('clock').textContent=duration(+e.target.value)+' / '+duration(lastState.duration_s)};
$('seek').onchange=async e=>{const position=+e.target.value;await control('seek',position);scrubbing=false};
$('seek').onblur=()=>{scrubbing=false};
$('speed').onchange=e=>control('speed',+e.target.value);
$('settings-toggle').onclick=()=>{$('settings-panel').open=!$('settings-panel').open;if($('settings-panel').open)$('settings-panel').scrollIntoView({behavior:'smooth',block:'start'})};
for(const tab of ['equipment','cost'])$('tab-'+tab).onclick=()=>{
  $('machines').hidden=tab!=='equipment';$('cost-breakdown').hidden=tab!=='cost';
  $('tab-equipment').setAttribute('aria-selected',String(tab==='equipment'));
  $('tab-cost').setAttribute('aria-selected',String(tab==='cost'));
};
document.addEventListener('keydown',e=>{
  if(!plan||busy||e.altKey||e.ctrlKey||e.metaKey||e.target.closest('input,select,textarea,button,summary,[contenteditable]'))return;
  if(e.code==='Space'){e.preventDefault();control('toggle')}
  else if(e.key==='ArrowLeft'||e.key==='ArrowRight'){
    e.preventDefault();control('seek',Math.max(0,Math.min(lastState.duration_s,lastState.sim_time_s+(e.key==='ArrowLeft'?-5:5))));
  }else if(e.key==='Home'){e.preventDefault();control('seek',0)}
});
$('retry-3d').onclick=()=>{
  if(viewer){viewer.renderer.setAnimationLoop(null);viewer.resizeObserver.disconnect();viewer.controls.dispose();viewer.clear();viewer.renderer.dispose()}
  createViewer();if(plan&&viewer){viewer.setPlan(plan);viewer.apply(lastState)}
};
async function poll(){
  if(!plan||polling||busy)return;
  const requestEpoch=epoch;polling=true;
  try{const s=await api('get_state');if(requestEpoch===epoch)applyState(s)}catch(e){error(e.message)}finally{polling=false}
}
let initialized=false;
async function ready(){
  if(initialized)return;initialized=true;
  try{
    const data=await api('get_options');config=data.defaults;hasDocument=data.has_document;
    renderConfig();localize();controlsEnabled();setInterval(poll,100);
  }catch(e){error(e.message);initialized=false}
}
localize();controlsEnabled();
if(window.pywebview)ready();else window.addEventListener('pywebviewready',ready);

export {viewer,lastState,plan};
