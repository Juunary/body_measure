// Measurement page. The shared job continues on /simulation and /qr.
import { Viewer } from "./viewer.js";
import { Terminal } from "./terminal.js";
import { t as tr } from "./i18n.js";
import { loadSettings, saveSettings, renderDrawer } from "./settings.js";
import {initialJob,rememberJob,navigation,subscribe,wt,processPhase} from "./workflow.js";

const $ = (id) => document.getElementById(id);
const origin = window.location.origin;

const state = {
  lang: "en",
  options: null,
  schema: null,
  settings: null,
  files: [],
  poseFilter: "a",       // the list shows A-pose scans unless asked otherwise
  entry: null,
  job: null,
  source: null,
  busy: null,            // stage running
  meshLoaded: false,
  measured: false,
  size: null,
  replayed: false,
  passport: null,
  curves: [],
  landmarks: {},
};
const t = (key, vars) => tr(state.lang, key, vars);

const viewer = new Viewer($("viewer"), $("viewer-labels"));
const terminal = new Terminal($("terminal"));
// ------------------------------------------------------------------ boot
async function boot() {
  const [options, files] = await Promise.all([
    fetch("/api/settings/options").then((r) => r.json()),
    fetch("/api/files").then((r) => r.json()),
  ]);
  state.options = options;
  state.files = files;
  // Share the saved language across all workflow pages.
  state.lang = options.default_lang || "en";
  state.settings = loadSettings({
    lang: state.lang, chart: options.default_chart, replay: options.replay, garment: options.default_config,
  });
  state.lang = state.settings.lang;
  const requestedLang=new URLSearchParams(location.search).get('lang');
  if(['en','de','ko'].includes(requestedLang))state.lang=requestedLang;
  state.settings.lang=state.lang;saveSettings(state.settings);
  state.schema = await fetch(`/api/schema/active?lang=${state.lang}`).then((r) => r.json());
  renderChrome();
  renderPoseFilter();
  renderFiles();
  renderResults();
  wire();
  if(initialJob())await restoreJob();else await demo();
}

/** A fresh ?demo=<file id> loads and measures once on this page. */
async function demo() {
  const params = new URLSearchParams(window.location.search);
  const fileId = params.get("demo");
  if (!fileId) return;
  if (params.get("lang") && params.get("lang") !== state.lang) await setLang(params.get("lang"));
  const entry = state.files.find((e) => e.id === fileId);
  if (!entry) { terminal.text(`demo: no file ${fileId}`, "red", "error"); return; }
  selectFile(entry);
  state.settings.replay.delay = 0;
  await createJobAndLoad();
  const settled = (pred) => new Promise((resolve) => {
    const tick = () => (pred() ? resolve() : setTimeout(tick, 200));
    tick();
  });
  await settled(() => state.meshLoaded && !state.busy);
  await runStage("measure");
  await settled(() => !state.busy);
  document.documentElement.dataset.demo = "done";
}

function renderChrome() {
  document.documentElement.lang = state.lang;
  $("subtitle").textContent = wt(state.lang,'measure');
  document.title = wt(state.lang,'measure')+' · Maß-DPP';
  $("l-settings").textContent = t("settings");
  $("h-files").textContent = t("files");
  $("l-upload").textContent = t("upload");
  $("l-unit").textContent = t("unit"); $("l-up").textContent = t("up");
  $("l-population").textContent = t("population"); $("l-clothed").textContent = t("clothed");
  $("btn-load").textContent = t("load");
  $("h-viewer").textContent = t("viewer");
  $("l-tg-mesh").textContent = t("tgMesh"); $("l-tg-curves").textContent = t("tgCurves");
  $("l-tg-landmarks").textContent = t("tgLandmarks"); $("l-tg-labels").textContent = t("tgLabels");
  $("viewer-empty").textContent = state.meshLoaded ? "" : t("viewerEmpty");
  $("h-terminal").textContent = t("terminal");
  $("btn-measure").textContent = t("measure"); $("btn-size").textContent = t("size");
  $("btn-clear").textContent = t("clear");
  $("h-measurements").textContent = t("measurements");
  $("h-size").textContent = t("sizeH");
  $("h-settings").textContent = t("settings"); $("h-garment").textContent = t("sizing");
  $("h-sizing").textContent = t("sizing"); $("h-replay").textContent = t("replayS"); $("h-defaults").textContent = t("defaults");
  $("legend").innerHTML = `<span><i style="background:#1E5F8C"></i>${t("legendSpec")}</span>` +
    `<span><i style="background:#B85042"></i>${t("legendProto")}</span><span><i style="background:#20303f;height:8px;width:8px;border-radius:50%"></i>${t("legendLm")}</span>`;
  document.querySelectorAll("#langs button").forEach((b) => b.classList.toggle("on", b.dataset.lang === state.lang));
  renderSteps();
  renderButtons();
}

function renderSteps() {
  navigation({job:state.job,lang:state.lang,size:state.size,busy:state.busy,error:state.workflowError,phase:processPhase(state.lang,state.simulation)});
}

function renderButtons() {
  const busy = !!state.busy;
  $("btn-load").disabled = !state.entry || busy;
  $("btn-measure").disabled = !state.meshLoaded || busy;
  $("btn-size").disabled = !state.measured || busy;
  for (const id of ["btn-load", "btn-measure", "btn-size"]) $(id).classList.remove("running");
  if (state.busy) {
    const id = { load: "btn-load", measure: "btn-measure", size: "btn-size", sizing:"btn-size" }[state.busy];
    if (id) $(id).classList.add("running");
  }
}

// ----------------------------------------------------------------- files
function badgeClass(licence) {
  if (licence.public) return "public";
  if (licence.badge.includes("NC")) return "nc";
  if (licence.badge.startsWith("uploaded")) return "uploaded";
  return "internal";
}

function renderPoseFilter() {
  const row = $("pose-filter");
  row.innerHTML = "";
  const counts = {};
  for (const entry of state.files) counts[entry.pose] = (counts[entry.pose] || 0) + 1;
  for (const [value, label] of [["a", t("poseA")], ["t", t("poseT")], ["other", t("poseOther")], ["all", t("poseAll")]]) {
    const b = document.createElement("button");
    b.type = "button";
    const n = value === "all" ? state.files.length : (counts[value] || 0);
    b.textContent = `${label} · ${n}`;
    b.classList.toggle("on", state.poseFilter === value);
    b.onclick = () => { state.poseFilter = value; renderPoseFilter(); renderFiles(); };
    row.appendChild(b);
  }
}

function renderFiles() {
  const list = $("file-list");
  list.innerHTML = "";
  const groups = new Map();
  const shown = state.files.filter((e) => state.poseFilter === "all" || e.pose === state.poseFilter);
  if (!shown.length) {
    list.innerHTML = `<div class="file-group">${t("poseNone")}</div>`;
  }
  for (const entry of shown) {
    if (!groups.has(entry.group)) groups.set(entry.group, []);
    groups.get(entry.group).push(entry);
  }
  for (const [group, entries] of groups) {
    const head = document.createElement("div");
    head.className = "file-group";
    head.textContent = `${group} · ${entries.length}`;
    list.appendChild(head);
    for (const entry of entries) {
      const item = document.createElement("div");
      item.className = "file-item" + (state.entry && state.entry.id === entry.id ? " on" : "");
      item.innerHTML = `<span class="name"></span><span class="badge ${badgeClass(entry.licence)}"></span>`;
      item.querySelector(".name").textContent = entry.label;
      item.querySelector(".badge").textContent = entry.licence.badge;
      item.title = entry.path_display;
      item.onclick = () => selectFile(entry);
      // a double-click is "pick it and load it" in one
      item.ondblclick = () => { selectFile(entry); createJobAndLoad(); };
      list.appendChild(item);
    }
  }
}

function selectFile(entry) {
  state.entry = entry;
  renderFiles();
  const detail = $("file-detail");
  detail.hidden = false;
  const badge = $("fd-badge");
  badge.textContent = entry.licence.badge;
  badge.className = `badge ${badgeClass(entry.licence)}`;
  $("fd-name").textContent = entry.label;
  $("fd-detail").textContent = [entry.path_display, entry.detail, entry.licence.text].filter(Boolean).join(" · ");
  fillSelect($("fd-unit"), state.options.units, entry.defaults.unit || state.settings.defaults.unit, !!entry.fixed.unit);
  fillSelect($("fd-up"), state.options.up_axes, entry.defaults.up_axis || state.settings.defaults.up_axis, !!entry.fixed.up_axis);
  fillSelect($("fd-population"), ["", ...state.options.populations], entry.defaults.population || state.settings.population || "", false, ["—", ...state.options.populations]);
  $("fd-clothed").checked = !!entry.defaults.clothed;
  $("fd-fixed").textContent = entry.fixed.unit ? t("fixed", { unit: entry.fixed.unit, up: entry.fixed.up_axis }) : "";
  $("file-error").textContent = "";
  renderChrome();
}

function fillSelect(select, values, current, disabled, labels) {
  select.innerHTML = "";
  values.forEach((v, i) => {
    const o = document.createElement("option");
    o.value = v; o.textContent = labels ? labels[i] : v; o.selected = v === current;
    select.appendChild(o);
  });
  select.disabled = disabled;
}

async function uploadFile(file) {
  const body = new FormData();
  body.append("file", file);
  $("file-error").textContent = "";
  const r = await fetch("/api/files/upload", { method: "POST", body });
  if (!r.ok) { $("file-error").textContent = (await r.json()).detail; return; }
  const entry = await r.json();
  state.files = await fetch("/api/files").then((x) => x.json());
  state.poseFilter = "all";          // an upload's pose is unknown; show it
  renderPoseFilter();
  selectFile(state.files.find((e) => e.id === entry.id) || entry);
}

// ------------------------------------------------------------------ jobs
async function createJobAndLoad() {
  const entry = state.entry;
  if (!entry) return;
  const s = state.settings;
  s.population = $("fd-population").value || null;
  s.clothed = $("fd-clothed").checked;
  saveSettings(s);
  const request = {
    file_id: entry.id,
    unit: entry.kind === "mesh_file" ? $("fd-unit").value : null,
    up_axis: entry.kind === "mesh_file" ? $("fd-up").value : null,
    clothed: s.clothed, population: s.population, chart: s.chart, replay: s.replay,
  };
  if (entry.kind === "mesh_file" && (!request.unit || !request.up_axis)) {
    $("file-error").textContent = t("unitNeeded"); return;
  }
  const r = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) });
  if (!r.ok) { $("file-error").textContent = (await r.json()).detail; return; }
  const { job_id } = await r.json();
  resetJob(job_id);
  terminal.clear();
  openStream(job_id);
  await runStage("load");
}

function resetJob(jobId) {
  if (state.source) state.source.close();
  closeBubble();
  viewer.hideProbe();
  Object.assign(state, { job: jobId, source: null, busy: null, meshLoaded: false, measured: false,
    size: null, replayed: false, passport: null, simulation: null, curves: [], landmarks: {}, reports: [], totals: null });
  rememberJob(jobId); state.workflowError=null;
  viewer.clearCurves();
  renderResults();
  renderChrome();
  return Promise.resolve();
}

async function restoreJob() {
  let id=initialJob();
  if(!id)return;
  const r=await fetch(`/api/jobs/${encodeURIComponent(id)}/result`);
  if(!r.ok){if(r.status===404){rememberJob(null);state.workflowError=wt(state.lang,"expired");}else state.workflowError=wt(state.lang,"connection");renderSteps();return;}
  const data=await r.json();await resetJob(id);
  const entry=state.files.find(e=>e.id===data.entry.id);if(entry)selectFile(entry);
  Object.assign(state,{measurements:data.measurements,prototypes:data.prototypes,measured:!!data.measurements.length,
    busy:data.busy_stage,size:data.size,simulation:data.simulation_state,passport:Object.keys(data.passport).length?data.passport:null,curves:data.curves,landmarks:data.landmarks,reports:data.reports});
  if(Object.keys(data.mesh).length){
    const mesh=await fetch(`/api/jobs/${id}/mesh`);if(mesh.ok){viewer.setMeshFromBuffer(await mesh.arrayBuffer());state.meshLoaded=true;viewer.setLandmarks(data.landmarks);viewer.setCurves(data.curves);}
  }
  renderResults();renderChrome();openStream(id,data.last_event_id);
}

function openStream(jobId, cursor=0) {
  state.source?.close();
  const handlers={};
  // the browser's own "error" event (connection lost) carries no data and
  // must not be mistaken for the job's `error` event
  const on = (type, fn) => {handlers[type]=fn;};
  on("stage", (ev) => { if(['load','measure','size'].includes(ev.phase)){terminal.stage(ev.name, ev.status, ev.detail, ev.elapsed_s);if(ev.status==="start"){state.busy=ev.phase;renderChrome();}} });
  on("line", (ev) => {if(['load','measure','size'].includes(ev.phase))terminal.line(ev.segments, ev.kind);});
  on("frame", (ev) => terminal.frame(ev.station_index, ev.segments, ev.final));
  on("error", (ev) => { terminal.text(`error in ${ev.stage}: ${ev.message}`, "red", "error"); });
  on("mesh_ready", async (ev) => {
    const buffer = await fetch(`/api/jobs/${jobId}/mesh`).then((r) => r.arrayBuffer());
    const info = viewer.setMeshFromBuffer(buffer);
    state.meshLoaded = true;
    $("viewer-empty").textContent = "";
    $("viewer-info").textContent = `${ev.source_id} · ${ev.n_vertices.toLocaleString()} v · ${ev.n_faces.toLocaleString()} f` +
      (info.decimated ? ` · ${t("decimated")}` : "");
    renderChrome();
  });
  on("pose", (ev) => { if (!ev.ok) { state.measured = false; renderResults(); } });
  on("measurements", (ev) => { state.measured = true; state.measurements = ev.rows; renderResults(); });
  on("prototypes", (ev) => { state.prototypes = ev.rows; renderResults(); });
  on("landmarks", (ev) => { state.landmarks = ev.points; viewer.setLandmarks(ev.points); });
  on("curves", (ev) => { state.curves = ev.curves; state.curveNotes = ev.notes; viewer.setCurves(ev.curves); renderResults(); });
  on("size", (ev) => { state.size = ev; renderResults(); renderChrome(); renderDrawerIfOpen(); });
  on("report", (ev) => { state.reports = ev.reports; renderResults(); });
  on("totals", (ev) => { state.totals = ev; state.replayed = true; renderResults(); });
  on("passport", (ev) => { state.passport = ev; renderResults(); renderChrome(); });
  on("simulation_state", (ev) => {if(!state.simulation||state.simulation.run_id!==ev.run_id||ev.seq>state.simulation.seq){state.simulation=ev;renderSteps();}});
  on("simulation_reset", () => {state.simulation=null;renderSteps();});
  on("end", () => { state.busy = null; renderChrome(); });
  state.source=subscribe(jobId,cursor,handlers,()=>{state.workflowError=null;renderSteps();},()=>{state.workflowError=wt(state.lang,'connection');renderSteps();});
}

async function runStage(stage, body) {
  if (!state.job) return;
  state.busy = stage;
  renderChrome();
  const r = await fetch(`/api/jobs/${state.job}/run/${stage}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}),
  });
  if (!r.ok) {
    state.busy = null;
    terminal.text((await r.json()).detail, "red", "error");
    renderChrome();
  }
}

async function overrideSize(option) {
  if (!state.job) return;
  const r = await fetch(`/api/jobs/${state.job}/size/override`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ size: option, reason: option ? "user override in studio settings" : "" }),
  });
  if (r.ok) { state.size = await r.json(); renderResults(); renderChrome(); renderDrawerIfOpen(); }
}

// --------------------------------------------------------------- reports
function closeBubble() {
  const old = document.querySelector(".bubble");
  if (old) old.remove();
}

function valueText(meta) {
  if (meta.value === null || meta.value === undefined) return "";
  return Array.isArray(meta.value) ? `[${meta.value.join(", ")}] ${meta.unit}` : `${meta.value} ${meta.unit}`;
}

/** The speech bubble a double-clicked label opens: cancel files nothing,
 *  add files a report on that one value. */
function levelText(key) {
  const of = {
    chest_circumference: "chest_level", waist_circumference: "waist_level",
    neck_circumference: "neck_base_level", upper_arm_girth: "upper_arm_girth_station_right",
    hip_girth: "buttock_prominence_level", back_length: "back_neck_point",
    across_back_shoulder_width: "back_neck_point", sleeve_length: "shoulder_point_right",
    armhole_depth: "armpit_level",
  }[key];
  const lm = (state.landmarks || {})[of];
  if (!lm) return "";
  const y = lm.position_mm[1];
  // the axilla is where the arm joins; armpit_level is the clip-bound
  // height, up to a grid step lower (decision #54)
  const ref = (state.landmarks || {})["axilla_level"] || (state.landmarks || {})["armpit_level"];
  if (!ref) return `  ·  y ${y.toFixed(0)} mm`;
  const named = (state.landmarks || {})["axilla_level"] ? "axilla" : "armpit";
  const d = y - ref.position_mm[1];
  return `  ·  y ${y.toFixed(0)} mm (${d >= 0 ? "+" : ""}${d.toFixed(0)} vs ${named})`;
}


function openBubble(label, at) {
  closeBubble();
  if (!state.job) return;
  const wrap = document.querySelector(".viewer-wrap");
  const meta = label.meta || {};
  const key = meta.key || label.text;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML =
    `<div class="bubble-head"><b>${t("reportTitle")}</b></div>` +
    `<div class="bubble-target"><span class="k"></span> <span class="v"></span>` +
    `<span class="lvl"></span></div>` +
    `<textarea rows="3"></textarea>` +
    `<div class="bubble-actions"><button type="button" class="ghost cancel"></button>` +
    `<button type="button" class="primary add"></button></div>`;
  bubble.querySelector(".k").textContent = key;
  bubble.querySelector(".v").textContent = valueText(meta);
  bubble.querySelector(".lvl").textContent = levelText(key);
  const area = bubble.querySelector("textarea");
  area.placeholder = t("reportPlaceholder");
  bubble.querySelector(".cancel").textContent = t("cancel");
  bubble.querySelector(".add").textContent = t("add");
  bubble.querySelector(".cancel").onclick = closeBubble;
  bubble.querySelector(".add").onclick = async () => {
    const text = area.value.trim();
    if (!text) { area.focus(); return; }
    const r = await fetch(`/api/jobs/${state.job}/reports`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: meta.target || "measurement", key, value: meta.value ?? null,
                             unit: meta.unit || "mm", text }),
    });
    if (!r.ok) { area.setCustomValidity((await r.json()).detail); area.reportValidity(); return; }
    closeBubble();
  };
  // keep the bubble inside the viewer, pointing at the label
  const w = wrap.clientWidth, h = wrap.clientHeight;
  bubble.style.left = `${Math.min(Math.max(at.x + 12, 8), w - 300)}px`;
  bubble.style.top = `${Math.min(Math.max(at.y - 20, 8), h - 190)}px`;
  wrap.appendChild(bubble);
  area.focus();
}

/** The coordinate bubble a click on the body opens, up and to the right
 *  of the cursor; null hides it. */
function showProbe(probe) {
  const old = document.querySelector(".probe-tip");
  if (old) old.remove();
  if (!probe) return;
  const wrap = document.querySelector(".viewer-wrap");
  const tip = document.createElement("div");
  tip.className = "probe-tip";
  const [x, y, z] = probe.mm.map((v) => v.toFixed(1));
  tip.innerHTML = `<b>x</b> ${x}&nbsp; <b>y</b> ${y}&nbsp; <b>z</b> ${z} <span class="u">mm</span>`;
  tip.style.left = `${Math.min(probe.x + 14, wrap.clientWidth - 230)}px`;
  tip.style.top = `${Math.max(probe.y - 34, 4)}px`;
  wrap.appendChild(tip);
}

function reportsFor(key) {
  return (state.reports || []).filter((r) => r.key === key && r.target !== "landmark");
}

function reportHtml(report) {
  const div = document.createElement("div");
  div.className = "report";
  div.textContent = `⚑ ${report.text}`;
  div.title = `${report.filed_utc} · ${report.scan}`;
  return div.outerHTML;
}

// --------------------------------------------------------------- results
function chip(bucket) { return `<span class="chip ${bucket}">${bucket}</span>`; }

function renderResults() {
  // measurements
  const tbody = $("mtable").querySelector("tbody");
  tbody.innerHTML = "";
  if (!state.measurements) {
    tbody.innerHTML = `<tr><td class="muted">${t("noMeasurements")}</td></tr>`;
  } else {
    for (const row of state.measurements) {
      const tr = document.createElement("tr");
      const value = row.selected_value_mm === null ? "—" : `${row.selected_value_mm.toFixed(1)} mm`;
      const flags = row.quality.filter((f) => f !== "ok").join(", ");
      const reports = reportsFor(row.name).map(reportHtml).join("");
      tr.innerHTML = `<td>${row.name}</td><td class="num">${value}</td><td>${chip(row.bucket)}</td><td class="flags">${flags}${reports}</td>`;
      tbody.appendChild(tr);
    }
    for (const row of state.prototypes || []) {
      const tr = document.createElement("tr");
      tr.className = "proto";
      const value = row.value === null ? "—" : `${row.value.toFixed(1)} ${row.unit}`;
      const reports = reportsFor(row.key).map(reportHtml).join("");
      tr.innerHTML = `<td>${row.key}</td><td class="num">${value}</td><td>${chip("proto")}</td><td class="flags">${(row.flags || []).join(", ")}${reports}</td>`;
      tbody.appendChild(tr);
    }
  }
  const landmarkReports = (state.reports || []).filter((r) => r.target === "landmark")
    .map((r) => `⚑ ${r.key} ${valueText(r)}: ${r.text}`);
  $("m-notes").textContent = [...(state.curveNotes || []), ...landmarkReports].join(" · ");
  const link = $("doc-link");
  link.hidden = !state.measured;
  if (state.measured) { link.href = `/api/jobs/${state.job}/measurement.json`; link.textContent = t("docLink"); }

  // size
  const size = state.size;
  const card = $("size-card");
  if (!size) {
    card.innerHTML = `<div class="muted">${t("noMeasurements")}</div>`;
  } else {
    const label = size.override ? size.override.size.toUpperCase() : size.size;
    const cls = label ? "" : " none";
    const src = size.override ? `<span class="chip override">${t("override")}</span>` :
      size.size ? `<span class="chip scan">3d_scan</span>` : "";
    card.innerHTML = `<div class="big${cls}">${label || t("sizeNone")}</div>${src}<dl>` +
      (size.override && size.size ? `<dt>measured</dt><dd>${size.size}</dd>` : "") +
      `<dt>${t("chart")}</dt><dd>${size.chart_name || "—"}</dd>` +
      `<dt>${t("chartSource")}</dt><dd>${size.chart_source || "—"}</dd>` +
      (size.chart_note ? `<dt>${t("chartNote")}</dt><dd class="note">${size.chart_note}</dd>` : "") +
      (size.alternative ? `<dt>${t("alt")}</dt><dd>${size.alternative}</dd>` : "") +
      `<dt>${t("sizeReason")}</dt><dd>${size.reason || "—"}</dd>` +
      `<dt>${t("qrStatus")}</dt><dd>${size.qr_status}${size.qr_reason ? " — " + size.qr_reason : ""}</dd></dl>` +
      (size.flags && size.flags.length ? `<div class="muted">${t("flagsH")}</div><ul>${size.flags.map((f) => `<li>${f}</li>`).join("")}</ul>` : "") +
      `<div class="muted scope">${t("sizeScope")}</div>`;
  }

}

// --------------------------------------------------------------- drawer
function drawerCtx() {
  return {
    page:"measure", job:state.job, settings: state.settings, schema: state.schema, options: state.options, size: state.size, lang: state.lang,
    onChange: () => saveSettings(state.settings),
    onOverride: (option) => overrideSize(option),
    onLang: (lang) => setLang(lang),
  };
}

function renderDrawerIfOpen() {
  if (!$("drawer").hidden) renderDrawer(drawerCtx());
}

async function setLang(lang) {
  state.lang = lang;
  state.settings.lang = lang;
  saveSettings(state.settings);
  state.schema = await fetch(`/api/schema/active?lang=${lang}`).then((r) => r.json());
  renderChrome();
  renderPoseFilter();
  renderResults();
  renderDrawerIfOpen();
}

// ----------------------------------------------------------------- wire
function wire() {
  document.querySelectorAll("#langs button").forEach((b) => (b.onclick = () => setLang(b.dataset.lang)));
  $("btn-settings").onclick = () => { $("drawer").hidden = false; renderDrawer(drawerCtx()); };
  $("btn-drawer-close").onclick = () => { $("drawer").hidden = true; };
  $("btn-load").onclick = createJobAndLoad;
  $("btn-measure").onclick = () => runStage("measure");
  $("btn-size").onclick = () => {
    const s = state.settings;
    runStage("size", { chart: s.chart, population: s.population, clothed: s.clothed });
  };
  $("btn-clear").onclick = () => terminal.clear();
  viewer.onReport = openBubble;
  viewer.onProbe = showProbe;
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeBubble(); viewer.hideProbe(); } });
  for (const what of ["mesh", "curves", "landmarks", "labels"]) {
    $(`tg-${what}`).onchange = (e) => viewer.toggle(what, e.target.checked);
  }
  $("upload-input").onchange = (e) => { if (e.target.files[0]) uploadFile(e.target.files[0]); };
  const zone = $("upload-zone");
  zone.ondragover = (e) => { e.preventDefault(); zone.classList.add("drag"); };
  zone.ondragleave = () => zone.classList.remove("drag");
  zone.ondrop = (e) => { e.preventDefault(); zone.classList.remove("drag"); if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]); };
  // population / clothed in the file panel mirror the settings
  $("fd-population").onchange = () => { state.settings.population = $("fd-population").value || null; saveSettings(state.settings); };
  $("fd-clothed").onchange = () => { state.settings.clothed = $("fd-clothed").checked; saveSettings(state.settings); };
}

boot().catch(e=>{document.getElementById("workflow-message").textContent=e.message;});
