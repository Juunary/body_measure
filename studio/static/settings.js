// The settings drawer: garment fields from the QR schema (the same
// form-from-schema pattern as qr-configurator), plus the studio's own
// choices. Everything is kept in localStorage and sent with each job.
import { t } from "./i18n.js";
import { st } from "./simulation-i18n.js";
import {wt} from './workflow-i18n.js';

const KEY = "studio.settings";

export function loadSettings(defaults) {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { saved = {}; }
  return {
    lang: saved.lang || defaults.lang,
    chart: saved.chart || defaults.chart,
    population: saved.population ?? null,
    clothed: !!saved.clothed,
    replay: { ...defaults.replay, ...(saved.replay || {}) },
    defaults: { unit: "m", up_axis: "Y", ...(saved.defaults || {}) },
    garment: { ...defaults.garment, ...(saved.garment || {}) },
  };
}

export function saveSettings(settings) {
  try { localStorage.setItem(KEY, JSON.stringify(settings)); } catch (e) { /* ignore */ }
}

/** Render the drawer. `ctx` = {settings, schema, options, size, lang, onChange, onOverride}. */
export function renderDrawer(ctx) {
  renderGarment(ctx);
  renderSizing(ctx);
  renderReplay(ctx);
  renderDefaults(ctx);
}

function field(labelText, control) {
  const wrap = document.createElement("div");
  wrap.className = "field";
  const label = document.createElement("label");
  label.textContent = labelText;
  wrap.append(label, control);
  return wrap;
}

function choices(options, labels, current, onPick, disabled = false) {
  const row = document.createElement("div");
  row.className = "choices";
  options.forEach((value, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = labels[i];
    b.classList.toggle("on", current === value);
    b.disabled = disabled;
    b.onclick = () => onPick(value);
    row.appendChild(b);
  });
  return row;
}

function select(options, labels, current, onPick) {
  const s = document.createElement("select");
  options.forEach((value, i) => {
    const o = document.createElement("option");
    o.value = value; o.textContent = labels[i]; o.selected = current === value;
    s.appendChild(o);
  });
  s.onchange = () => onPick(s.value);
  return s;
}

export function renderGarment(ctx) {
  const { settings, schema } = ctx;
  const form = document.getElementById("garment-form");
  form.innerHTML = "";
  if (!schema) return;
  const config = settings.garment;
  const set = (key, value) => { if (key !== undefined) config[key] = value; ctx.onChange(); renderGarment(ctx); };
  let compositionDone = false;

  for (const key of schema.required) {
    if (ctx.page === 'measure' && key !== 'size') continue;
    const prop = schema.properties[key];
    if(key==='product_type'){form.appendChild(field(prop.title,choices(prop.enum,[wt(ctx.lang,'polo')],config[key],v=>set(key,v))));continue;}
    if (prop["x-ui-group"] === "composition") {
      if (!compositionDone) { form.appendChild(compositionWidget(schema, config, set)); compositionDone = true; }
      continue;
    }
    if (key === "size") { form.appendChild(sizeControl(ctx, prop)); continue; }
    let control;
    if (prop["x-ui-control"] === "swatch") {
      control = document.createElement("div");
      control.className = "swatches";
      prop.enum.forEach((value, i) => {
        const b = document.createElement("button");
        b.type = "button"; b.title = prop["x-ui-labels"][i];
        b.style.background = prop["x-ui-hex"][i];
        b.classList.toggle("on", config[key] === value);
        b.onclick = () => set(key, value);
        control.appendChild(b);
      });
    } else if (prop.enum.length > 8) {
      control = select(prop.enum, prop["x-ui-labels"], config[key], (v) => set(key, v));
    } else {
      control = choices(prop.enum, prop["x-ui-labels"], config[key], (v) => set(key, v));
    }
    form.appendChild(field(prop.title + (prop["x-ui-unit"] ? ` (${prop["x-ui-unit"]})` : ""), control));
  }
}

function compositionWidget(schema, config, set) {
  const wrap = document.createElement("div");
  wrap.className = "field";
  const label = document.createElement("label");
  label.textContent = schema.properties.fibre_1.title.replace(/\s*1$/, "") + " 1–4";
  wrap.appendChild(label);
  const grid = document.createElement("div");
  grid.className = "composition";
  const max = schema["x-max-fibres"] || 4;
  for (let slot = 1; slot <= max; slot++) {
    const fibre = schema.properties[`fibre_${slot}`];
    const pct = schema.properties[`fibre_${slot}_pct`];
    grid.appendChild(select(fibre.enum, fibre["x-ui-labels"], config[`fibre_${slot}`], (v) => {
      config[`fibre_${slot}`] = v;
      if (v === "none" && pct) config[`fibre_${slot}_pct`] = "0";
      set();
    }));
    if (pct) {
      grid.appendChild(select(pct.enum, pct["x-ui-labels"], config[`fibre_${slot}_pct`], (v) => { config[`fibre_${slot}_pct`] = v; set(); }));
    } else {
      const rest = document.createElement("span");
      rest.className = "muted";
      rest.textContent = "rest";
      grid.appendChild(rest);
    }
  }
  wrap.appendChild(grid);
  return wrap;
}

function sizeControl(ctx, prop) {
  const { size, lang } = ctx;
  const wrap = document.createElement("div");
  wrap.className = "field";
  const label = document.createElement("label");
  label.textContent = prop.title;
  wrap.appendChild(label);
  const measured = size && size.qr_status === "ok" ? size.qr_option : null;
  const override = size && size.override ? size.override.size : null;
  const current = override || measured || null;
  const locked = !override;
  wrap.appendChild(choices(prop.enum, prop["x-ui-labels"], current, (v) => ctx.onOverride(v), locked || ctx.page==='qr'));
  const note = document.createElement("div");
  note.className = "locked-note";
  if (override) {
    note.innerHTML = `<b class="override">${t(lang, "override")}</b> · ${t(lang, "overrideNote")}`;
  } else if (measured) {
    note.textContent = t(lang, "lockedScan", { size: measured.toUpperCase() });
  } else {
    note.textContent = size && size.qr_reason ? size.qr_reason : t(lang, "lockedNone");
  }
  wrap.appendChild(note);
  if (ctx.page === 'qr') {
    const link=document.createElement('a');link.className='doclink';link.href='/measure'+(ctx.job?'?job='+encodeURIComponent(ctx.job):'');link.textContent=t(lang,'sizing');wrap.append(link);return wrap;
  }
  const unlock = document.createElement("label");
  unlock.className = "locked-note";
  const box = document.createElement("input");
  box.type = "checkbox"; box.checked = !!override;
  box.onchange = () => ctx.onOverride(box.checked ? (current || "m") : null);
  unlock.append(box, " ", t(lang, "unlock"));
  wrap.appendChild(unlock);
  return wrap;
}

function renderSizing(ctx) {
  const { settings, options, lang } = ctx;
  const el = document.getElementById("sizing-form");
  el.innerHTML = "";
  const charts = options.charts;
  el.appendChild(labelled(t(lang, "sizeChart"), select(
    charts.map((c) => c.key), charts.map((c) => `${c.name} (${c.range_cm[0]}–${c.range_cm[1]} cm)`),
    settings.chart, (v) => { settings.chart = v; ctx.onChange(); }), "wide"));
  el.appendChild(labelled(t(lang, "population"), select(
    ["", ...options.populations], ["—", ...options.populations],
    settings.population || "", (v) => { settings.population = v || null; ctx.onChange(); })));
  const clothed = document.createElement("label");
  clothed.className = "check";
  const box = document.createElement("input");
  box.type = "checkbox"; box.checked = settings.clothed;
  box.onchange = () => { settings.clothed = box.checked; ctx.onChange(); };
  clothed.append(box, t(lang, "clothed"));
  el.appendChild(clothed);
}

function renderReplay(ctx) {
  const { settings, lang } = ctx;
  const el = document.getElementById("replay-form");
  el.innerHTML = "";
  document.getElementById('h-replay').textContent=st(lang,'title');
  const button=document.createElement('button');button.type='button';button.textContent=st(lang,'inputs');
  button.onclick=()=>{window.location.href='/simulation'+(ctx.job?'?job='+encodeURIComponent(ctx.job):'');};
  el.appendChild(button);
}

function renderDefaults(ctx) {
  const { settings, options, lang } = ctx;
  const el = document.getElementById("defaults-form");
  el.innerHTML = "";
  el.appendChild(labelled(t(lang, "defUnit"), select(options.units, options.units, settings.defaults.unit,
    (v) => { settings.defaults.unit = v; ctx.onChange(); })));
  el.appendChild(labelled(t(lang, "defUp"), select(options.up_axes, options.up_axes, settings.defaults.up_axis,
    (v) => { settings.defaults.up_axis = v; ctx.onChange(); })));
  el.appendChild(labelled(t(lang, "lang"), select(options.langs, options.langs.map((l) => l.toUpperCase()), settings.lang,
    (v) => ctx.onLang(v))));
}

function labelled(text, control, cls = "") {
  const l = document.createElement("label");
  if (cls) l.className = cls;
  const span = document.createElement("span");
  span.textContent = text;
  l.append(span, control);
  return l;
}
