import {resourceView} from './resource-view.js';
import {wt} from './workflow-i18n.js';
const words={
  skip:['Skip to product','Zum Produkt','제품 정보로 이동'],loading:['Loading product passport…','Produktpass wird geladen…','제품 패스포트를 불러오는 중…'],retry:['Try again','Erneut versuchen','다시 시도'],
  polo:['Polo shirt','Poloshirt','폴로 셔츠'],intro:['The product, its materials, and the story of its making.','Das Produkt, seine Materialien und sein Entstehungsprozess.','제품과 소재, 그리고 만들어지는 과정을 한눈에 확인하세요.'],
  configuration:['Your product configuration','Ihre Produktkonfiguration','제품 구성'],colour:['Colour','Farbe','색상'],size:['Size','Größe','사이즈'],fit:['Fit','Passform','핏'],
  illustration:['Representative polo illustration, not a photograph of a produced item. The selected colour is shown below.','Beispielabbildung eines Polos, kein Foto eines gefertigten Produkts. Die gewählte Farbe steht unten.','폴로 형태 예시이며 실제 생산품 사진이 아닙니다. 선택한 색상은 아래에 표시됩니다.'],
  imageUnavailable:['Product illustration unavailable.','Produktabbildung nicht verfügbar.','제품 예시 이미지를 불러올 수 없습니다.'],
  configurationSource:['Source: configuration encoded in this QR.','Quelle: in diesem QR codierte Konfiguration.','출처: 이 QR에 인코딩된 제품 구성.'],
  updated:['Passport updated','Pass aktualisiert','패스포트 갱신 시각'],notRecorded:['No saved snapshot','Kein gespeicherter Stand','저장 기록 없음'],recorded:['Saved passport','Gespeicherter Produktpass','저장된 패스포트'],configOnly:['Configuration only','Nur Konfiguration','구성 정보만 제공'],
  snapshot:['This is the state when the QR was last generated. Generate it again in Studio to update the results.','Stand der letzten QR-Erstellung. Für neue Ergebnisse den QR in Studio erneut erstellen.','마지막 QR 생성 시점의 기록입니다. 결과를 갱신하려면 Studio에서 QR을 다시 생성하세요.'],
  noRecord:['No linked process record. Only the encoded product configuration is available.','Kein verknüpfter Prozessdatensatz. Nur die codierte Produktkonfiguration ist verfügbar.','연결된 공정 기록이 없습니다. QR에 담긴 제품 구성만 확인할 수 있습니다.'],
  copy:['Copy link','Link kopieren','링크 복사'],download:['Download JSON','JSON herunterladen','JSON 다운로드'],print:['Print','Drucken','인쇄'],copied:['Link copied.','Link kopiert.','링크를 복사했습니다.'],copyFailed:['Copy the link from your browser address bar.','Bitte den Link aus der Adressleiste kopieren.','브라우저 주소창에서 링크를 복사해 주세요.'],saved:['Public summary downloaded.','Öffentliche Übersicht heruntergeladen.','공개 요약을 다운로드했습니다.'],
  material:['Material','Material','소재'],recycled:['Declared recycled content','Deklarierter Recyclinganteil','구성에 명시된 재생 원료 비율'],declared:['Composition is declared in the QR configuration; it is not a material test result.','Zusammensetzung laut QR-Konfiguration; kein Ergebnis einer Materialprüfung.','소재 구성은 QR에 입력된 정보이며 소재 시험 결과가 아닙니다.'],
  care:['Care & maintenance','Pflege & Erhalt','세탁·관리'],careSource:['Care setting from the QR configuration. Follow the finished product’s care label when available.','Pflegeangabe aus der QR-Konfiguration. Soweit vorhanden, das Pflegeetikett des fertigen Produkts beachten.','QR 구성의 세탁 설정입니다. 완제품의 관리 라벨이 제공되면 해당 안내를 따르세요.'],
  wash:['Machine wash','Maschinenwäsche','기계 세탁'],hand:['Hand wash','Handwäsche','손세탁'],handShort:['Hand','Hand','손세탁'],
  repair:['Repair, warranty & end of life','Reparatur, Garantie & Verwertung','수선·보증·사용 후 처리'],notProvided:['Verified product-specific instructions have not been provided.','Verifizierte produktspezifische Angaben liegen nicht vor.','이 제품에 대해 검증된 안내가 제공되지 않았습니다.'],
  process:['Making this polo','Entstehung dieses Polos','제품 공정 결과'],simulation:['RESEARCH SIMULATION','FORSCHUNGSSIMULATION','연구용 시뮬레이션'],
  simulationNote:['Cutting and sewing describe a research simulation, not verified manufacture of a finished garment.','Zuschnitt und Nähen beziehen sich auf eine Forschungssimulation, nicht auf eine verifizierte Fertigung.','재단·봉제 결과는 연구용 시뮬레이션이며 실제 완제품의 생산을 증명하지 않습니다.'],
  sizing:['Measurement & size assignment','Messung & Größenzuordnung','측정·사이즈 배정'],pattern:['Pattern generation','Schnittkonstruktion','패턴 생성'],cutting:['Zünd S3 · cutting','Zünd S3 · Zuschnitt','Zünd S3 · 재단'],sewing:['Pfaff · sewing','Pfaff · Nähen','Pfaff · 봉제'],
  complete:['Complete','Abgeschlossen','완료'],in_progress:['In progress','In Arbeit','진행 중'],not_started:['Not started','Nicht gestartet','미실행'],excluded:['Outside this run','Außerhalb dieses Laufs','범위 제외'],unknown:['No record','Kein Datensatz','기록 없음'],not_executed:['Not executed','Nicht ausgeführt','미실행'],
  finishing:['Finishing','Finish','마감'],qc:['Quality inspection','Qualitätsprüfung','품질 검사'],
  cut_length_mm:['Cut length','Schnittlänge','재단 길이'],yield_pct:['Planned fabric yield','Geplante Stoffausnutzung','계획 원단 이용률'],collected_pieces:['Collected parts','Entnommene Teile','회수 부품'],sewn_length_mm:['Sewn length','Nahtlänge','봉제 길이'],stitches:['Stitches','Stiche','스티치 수'],seams_complete:['Completed seams','Fertige Nähte','완료 봉합선'],process_time_s:['Elapsed process time','Verstrichene Prozesszeit','경과 공정 시간'],planned_time_s:['Planned total time','Geplante Gesamtzeit','계획 총 공정 시간'],
  timeNote:['Process times are calculated simulation times, not stopwatch measurements.','Prozesszeiten sind berechnete Simulationszeiten, keine gemessenen Fertigungszeiten.','공정 시간은 계산된 시뮬레이션 시간이며 실제 장비에서 측정한 시간이 아닙니다.'],
  measured:['A measurement record and size assignment were available at QR generation.','Bei QR-Erstellung lagen Messdatensatz und Größenzuordnung vor.','QR 생성 시 측정 기록과 사이즈 배정 결과가 있었습니다.'],
  sizeOnly:['Size was assigned without a linked measurement record.','Größe ohne verknüpften Messdatensatz zugeordnet.','연결된 측정 기록 없이 사이즈가 지정됐습니다.'],
  manualSize:['Size was manually selected.','Größe wurde manuell gewählt.','사이즈는 수동으로 선택됐습니다.'],
  playing:['Simulation was running at capture.','Simulation lief zum Speicherzeitpunkt.','기록 시점에 시뮬레이션이 진행 중이었습니다.'],paused:['Simulation was paused at capture.','Simulation war zum Speicherzeitpunkt pausiert.','기록 시점에 시뮬레이션이 일시정지 상태였습니다.'],error:['Simulation reported an error.','Simulation meldete einen Fehler.','시뮬레이션 오류가 기록됐습니다.'],
  cutting_complete:['Cutting completed in simulation. Sewing is outside this run.','Zuschnitt in der Simulation abgeschlossen. Nähen liegt außerhalb dieses Laufs.','시뮬레이션 재단이 완료됐습니다. 봉제는 이번 실행 범위에서 제외됐습니다.'],sewing_complete:['Cutting and research sewing assembly completed in simulation.','Zuschnitt und Forschungs-Nähmontage in der Simulation abgeschlossen.','시뮬레이션 재단과 연구용 봉제 조립이 완료됐습니다.'],
  identity:['Product identification','Produktidentifikation','제품 식별 정보'],code:['Configuration code','Konfigurationscode','구성 코드'],qrVersion:['QR schema','QR-Schema','QR 스키마'],recordType:['Record type','Datensatztyp','기록 유형'],configurationRecord:['Product configuration','Produktkonfiguration','제품 구성 단위'],sameCode:['The same configuration produces the same QR. This address shows its most recently generated saved record.','Dieselbe Konfiguration erzeugt denselben QR. Diese Adresse zeigt den zuletzt erzeugten gespeicherten Stand.','같은 구성은 같은 QR을 생성합니다. 이 주소에는 가장 최근에 생성한 저장 기록이 표시됩니다.'],
  footer:['A textile research passport. Product declarations and simulated process results are identified by source.','Ein textiler Forschungsproduktpass. Produktangaben und simulierte Prozessergebnisse sind nach Quelle gekennzeichnet.','텍스타일 연구용 패스포트입니다. 제품 구성 정보와 시뮬레이션 결과의 출처를 구분해 표시합니다.'],
  invalid:['This QR does not contain a supported product code.','Dieser QR enthält keinen unterstützten Produktcode.','이 QR에는 지원되는 제품 코드가 없습니다.'],loadError:['The passport could not be loaded. Check the connection and try again.','Der Produktpass konnte nicht geladen werden. Verbindung prüfen und erneut versuchen.','패스포트를 불러오지 못했습니다. 연결을 확인하고 다시 시도해 주세요.']
};
const $=id=>document.getElementById(id),supported=['en','de','ko'];
let lang='en',data=null,loadToken=0,errorKey=null;
try{const saved=JSON.parse(localStorage.getItem('studio.settings')||'{}');lang=saved.lang||navigator.language.slice(0,2);}catch{lang=navigator.language.slice(0,2);}
const queryLang=new URLSearchParams(location.search).get('lang');if(supported.includes(queryLang))lang=queryLang;
if(!supported.includes(lang))lang='en';
const t=key=>words[key]?.[lang==='de'?1:lang==='ko'?2:0]||key;
const label=value=>value?.labels?.[lang]||value?.labels?.en||value?.value||'—';
const text=(id,value)=>{$(id).textContent=value;};
const number=(value,digits=0)=>Number.isFinite(value)?new Intl.NumberFormat(lang,{maximumFractionDigits:digits}).format(value):'—';
const node=(tag,content,className)=>{const el=document.createElement(tag);if(content!==undefined)el.textContent=content;if(className)el.className=className;return el;};
function localize(){
  document.documentElement.lang=lang;document.title=`${t('polo')} · Maß-DPP`;
  document.querySelectorAll('[data-t]').forEach(el=>el.textContent=t(el.dataset.t));
  document.querySelectorAll('[data-lang]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.lang===lang)));
  text('action-message','');if(errorKey)text('state-message',t(errorKey));if(data)render();
}
function render(){
  const p=data.product;const process=data.process;
  text('record-badge',t(data.recorded?'recorded':'configOnly'));
  text('colour',label(p.colour));$('swatch').style.backgroundColor=p.colour.hex;
  text('size',p.size);text('fit',label(p.fit));
  $('updated').removeAttribute('datetime');
  if(data.generated_at){$('updated').dateTime=data.generated_at;text('updated',new Intl.DateTimeFormat(lang,{dateStyle:'medium',timeStyle:'short'}).format(new Date(data.generated_at)));}
  else text('updated',t('notRecorded'));
  text('snapshot-note',t(data.recorded?'snapshot':'noRecord'));
  $('composition').replaceChildren(...p.composition.map(f=>{
    const row=node('div',undefined,'fibre-row'),line=node('div',undefined,'fibre-label');
    line.append(node('span',f.labels[lang]||f.labels.en),node('strong',`${number(f.percentage,1)}%`));
    const bar=node('div',undefined,'fibre-bar'),fill=node('div',undefined,'fibre-fill');fill.style.width=`${Math.max(0,Math.min(100,f.percentage))}%`;bar.setAttribute('aria-hidden','true');bar.append(fill);row.append(line,bar);return row;
  }));
  text('recycled',`${number(p.recycled_content_pct,1)}%`);
  const hand=p.care.value==='hand';text('care-value',hand?t('handShort'):`${p.care.value}°C`);
  text('care-description',hand?t('hand'):`${t('wash')} · ${label(p.care)}`);
  text('process-caption',process?t(process.status):t('noRecord'));
  const stages=process?.stages||['sizing','pattern','cutting','sewing'].map(id=>({id,status:'unknown'}));
  $('timeline').replaceChildren(...stages.map(s=>{const li=node('li',undefined,s.status);li.append(node('span',t(s.id)),node('b',t(s.status)));return li;}));
  text('sizing-note',process?(t(process.measurement_recorded?'measured':'sizeOnly')+(process.size_source==='manual_override'?' '+t('manualSize'):'')):'');
  const metrics=process?.metrics;const rows=[];
  if(metrics)for(const key of ['cut_length_mm','yield_pct','collected_pieces','sewn_length_mm','stitches','seams_complete','process_time_s','planned_time_s']){
    let value=number(metrics[key]);
    if(key.endsWith('_mm'))value=`${number(metrics[key]/1000,3)} m`;
    if(key==='yield_pct')value=`${number(metrics[key],1)}%`;
    if(key==='collected_pieces')value+=` / ${metrics.total_pieces}`;
    if(key==='seams_complete')value+=` / ${metrics.seams_total}`;
    if(key.endsWith('_s'))value=`${number(metrics[key],1)} s`;
    const row=node('div');row.append(node('dt',t(key)),node('dd',value));rows.push(row);
  }
  $('metrics').replaceChildren(...rows);$('metrics').hidden=!metrics;
  $('time-note').hidden=!metrics;
  text('code',data.code);text('qr-version',data.qr_schema_version);
  text('public-json-title',wt(lang,'publicJson'));text('public-json',JSON.stringify(data,null,2));
  resourceView($('public-resource-card'),process?.resources,process?.planned_resources,process?.run_size||{label:p.size},lang,process?.estimation?.preset);
}
async function load(){
  const token=++loadToken;data=null;errorKey=null;$('passport').hidden=true;$('page-state').hidden=false;$('page-state').classList.remove('error');$('retry').hidden=true;text('state-message',t('loading'));
  try{
    const code=decodeURIComponent(location.pathname.split('/').filter(Boolean).at(-1)||'');
    const response=await fetch(`/api/passports/${encodeURIComponent(code)}/summary`,{cache:'no-store',signal:AbortSignal.timeout(15000)});
    if(!response.ok)throw new Error(response.status===404?'invalid':'loadError');
    const summary=await response.json();if(token!==loadToken)return;
    data=summary;render();$('page-state').hidden=true;$('passport').hidden=false;
  }catch(e){if(token!==loadToken)return;errorKey=e.message==='invalid'?'invalid':'loadError';text('state-message',t(errorKey));$('page-state').classList.add('error');$('retry').hidden=false;}
}
document.querySelectorAll('[data-lang]').forEach(button=>button.addEventListener('click',()=>{
  lang=button.dataset.lang;try{const settings=JSON.parse(localStorage.getItem('studio.settings')||'{}');localStorage.setItem('studio.settings',JSON.stringify({...settings,lang}));}catch{}localize();
}));
$('retry').addEventListener('click',load);
$('copy-link').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(location.origin+location.pathname);text('action-message',t('copied'));}catch{text('action-message',t('copyFailed'));}});
$('download').addEventListener('click',()=>{if(!data)return;const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download=`mass-dpp-${data.code}.json`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);text('action-message',t('saved'));});
$('print').addEventListener('click',()=>window.print());
document.querySelector('.product-photo img').addEventListener('error',e=>{e.target.hidden=true;$('image-unavailable').hidden=false;});
localize();load();
