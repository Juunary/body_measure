"""One-garment desktop plan from cutting through QC, stopping before QR."""
from __future__ import annotations

import bisect
import hashlib
import json
import math

from ..factory.stages import readouts
from ..simulation import engine as base_engine
from . import shirt_steps
from .config import DesktopConfig

PLAN_VERSION = "polo-plan/2"
SEWING_MACHINES = ("pfaff", "overlock")
STATIONS = ("zund", "pfaff", "overlock", "button", "qc")
ACTIVE_KINDS = frozenset(("feed", "mark", "cut_internal", "cut_outer", "travel", "tool_up", "tool_down",
                          "stitch", "buttonhole_stitch", "button_attach_stitch", "qc_scan"))
UNATTENDED = frozenset(("qc_scan",))


def process_timeline(plan):
    """Five contiguous chapters. The sewing chapter is exactly the work-step table:
    the transfer into sewing closes the cutting chapter, later transfers open theirs."""
    b, end = plan["boundaries"], plan["totals"]["duration_s"]
    rows = (("cutting", "zund", 0., b["sewing_start_s"]),
            ("sewing", "pfaff", b["sewing_start_s"], b["sewing_end_s"]),
            ("buttons", "button", b["sewing_end_s"], b["buttons_end_s"]),
            ("qc", "qc", b["buttons_end_s"], b["qc_end_s"]),
            ("ready_for_qr", "qc", b["qc_end_s"], end))
    return [{"id": key, "machine_id": machine, "start_s": start, "end_s": stop,
             "duration_s": stop - start} for key, machine, start, stop in rows]


def _append(operations, clock, kind, duration, window, *, machine_id, piece_id=None,
            seam_id=None, button_index=None, step_no=None, tool="up"):
    op = {"index": len(operations), "kind": kind, "start_s": clock, "end_s": clock + duration,
          "window": window, "piece_id": piece_id, "path_id": None, "tool": tool,
          "head_mm": [0., 0.], "machine_id": machine_id, "seam_id": seam_id,
          "button_index": button_index, "step_no": step_no}
    operations.append(op)
    return op["end_s"]


def _rate(config: DesktopConfig, machine_id: str):
    if machine_id == "zund":
        r = config.resources
        return r.zund_active_kw, r.zund_idle_kw, r.zund_eur_h
    s = {"pfaff": config.process.lockstitch, "overlock": config.process.overlock,
         "button": config.process.buttons, "qc": config.process.qc}.get(machine_id)
    if s:
        return s.active_kw, s.idle_kw, s.equipment_eur_h
    return 0., 0., 0.


def _resource_rows(plan, config: DesktopConfig):
    windows = {w["id"]: w for w in plan["windows"]}
    seams = {s["id"]: s for s in plan["sewing_seams"]}
    vacuum = False
    rows = []
    for op in plan["operations"]:
        kind = op["kind"]
        machine_id = op.get("machine_id", "zund")
        if kind == "vacuum_on":
            vacuum = True
        active_kw, idle_kw, equipment = _rate(config, machine_id)
        duration = op["end_s"] - op["start_s"]
        active = kind in ACTIVE_KINDS
        machine_kwh = (active_kw if active else idle_kw) * duration / 3600
        vacuum_kwh = config.resources.vacuum_kw * duration / 3600 if vacuum and machine_id == "zund" else 0.
        thread_m = 0.
        # Steps without polo seam geometry have no measurable thread length.
        seam_stitch = kind == "stitch" and op.get("seam_id") is not None
        if seam_stitch:
            thread_m = seams[op["seam_id"]]["length_mm"] / 1000 * config.resources.thread_ratio
        elif kind in ("buttonhole_stitch", "button_attach_stitch"):
            stitches = (config.process.buttons.hole_stitches if kind == "buttonhole_stitch"
                        else config.process.buttons.attach_stitches)
            thread_m = stitches * config.process.buttons.hole_length_mm / 1000 * config.resources.thread_ratio / 4
        material, area, fabric_cost = "body", 0., 0.
        if kind == "load":
            window = windows[op["window"]]
            material = "rib" if window["material"] == "rib" else "body"
            area = window["width_mm"] * window["length_mm"] / 1e6
            fabric_cost = area * getattr(config.resources, material + "_eur_m2")
        rows.append({"start_s": op["start_s"], "end_s": op["end_s"], "machine": machine_id,
                     "machine_kwh": machine_kwh, "vacuum_kwh": vacuum_kwh,
                     "overhead_kwh": config.resources.overhead_kw * duration / 3600,
                     "labour_s": 0. if kind in UNATTENDED else duration,
                     "equipment_eur": equipment * duration / 3600,
                     "thread_m": thread_m,
                     "tail_m_at_end": config.resources.thread_tail_m if seam_stitch or kind == "buttonhole_cut" else 0.,
                     "material": material, "area_m2_at_end": area, "fabric_eur_at_end": fabric_cost})
        if kind == "vacuum_off":
            vacuum = False
    return rows


def resources_at(plan: dict, time_s: float):
    rows, r = plan["resource_ledger"], plan["config"]["resources"]
    energy = {m: 0. for m in STATIONS + ("vacuum", "overhead")}
    cost = {m: 0. for m in ("fabric", "thread", "labour", "electricity", "equipment")}
    area = {"body": 0., "rib": 0.}
    thread = labour = 0.
    for row in rows:
        if time_s <= row["start_s"]:
            break
        f = min(1., (time_s - row["start_s"]) / (row["end_s"] - row["start_s"]))
        if row["machine"] in energy:
            energy[row["machine"]] += row["machine_kwh"] * f
        energy["vacuum"] += row["vacuum_kwh"] * f
        energy["overhead"] += row["overhead_kwh"] * f
        labour += row["labour_s"] * f
        cost["equipment"] += row["equipment_eur"] * f
        thread += row["thread_m"] * f
        if f == 1:
            thread += row["tail_m_at_end"]
            area[row["material"]] += row["area_m2_at_end"]
            cost["fabric"] += row["fabric_eur_at_end"]
    kwh = sum(energy.values())
    cost.update(thread=thread * r["thread_eur_m"], labour=labour / 3600 * r["labour_eur_h"],
                electricity=kwh * r["electricity_eur_kwh"])
    return {"flow_time_s": max(0., min(time_s, plan["totals"]["duration_s"])),
            "energy_kwh": kwh, "co2e_g": kwh * r["grid_gco2e_kwh"],
            "cost_eur": sum(cost.values()), "cost_breakdown_eur": cost,
            "energy_breakdown_kwh": energy, "labour_time_s": labour,
            "fabric_used_m2": area, "thread_used_m": thread}


def _sew_work_steps(operations, sewing_start, window, seams, config):
    """Lay the scheduled shirt steps end to end. A step that closes polo seams is
    split across them by seam length; its end stays the table's cumulative time."""
    by_id = {s["id"]: s for s in seams}
    table = shirt_steps.rows(config.process.shirt_size, config.machine.stitches_per_min)
    closed = [sid for row in table if row["scheduled"] for sid in row["seam_ids"]]
    if sorted(closed) != sorted(by_id):
        raise ValueError("the work-step table must close every pattern seam exactly once")
    work_steps, ordered, elapsed = [], [], 0
    for row in table:
        row.update(start_s=None, end_s=None, machine_id=None)
        work_steps.append(row)
        if not row["scheduled"]:
            continue
        kind, station = shirt_steps.TOOLS[row["tool"]]
        start = sewing_start + elapsed
        elapsed += row["duration_s"]
        end = sewing_start + elapsed
        row.update(start_s=start, end_s=end, machine_id=station)
        common = {"machine_id": station, "step_no": row["no"]}
        parts = [by_id[sid] for sid in row["seam_ids"]]
        if not parts:
            _append(operations, start, kind, end - start, window, **common)
            continue
        stitch_mm = row["stitch_length_mm"] or shirt_steps.DEFAULT_STITCH_MM
        total = sum(s["length_mm"] for s in parts)
        done, left = 0., start
        for seam in parts:
            stitches = math.ceil(seam["length_mm"] / stitch_mm)
            seam.update(machine_id=station, step_no=row["no"], stitches=stitches,
                        actual_stitch_mm=seam["length_mm"] / stitches)
            ordered.append(seam)
            done += seam["length_mm"]
            right = end if seam is parts[-1] else start + row["duration_s"] * done / total
            _append(operations, left, "stitch", right - left, window, tool="needle",
                    piece_id=seam["piece_ids"][0], seam_id=seam["id"], **common)
            operations[-1]["end_s"] = right
            left = right
    return work_steps, ordered, elapsed


def build_plan(document: dict, config: DesktopConfig | dict | None = None) -> dict:
    config = config if isinstance(config, DesktopConfig) else DesktopConfig.model_validate(config or {})
    base = base_engine.build_plan(document, config.base_config())
    first_sewing = next(i for i, op in enumerate(base["operations"])
                        if op["kind"] == "transfer_to_sewing")
    operations = [dict(op, machine_id="zund", seam_id=None, button_index=None, step_no=None)
                  for op in base["operations"][:first_sewing]]
    for i, op in enumerate(operations):
        op["index"] = i
    clock = operations[-1]["end_s"]
    window = base["windows"][-1]["id"]
    cut_end = clock

    sewing_start = _append(operations, clock, "transfer_to_pfaff", config.process.transfer_s,
                           window, machine_id="transport")
    work_steps, seams, sewing_work = _sew_work_steps(operations, sewing_start, window, base["sewing_seams"], config)
    clock = sewing_end = operations[-1]["end_s"]

    b = config.process.buttons
    buttons = [{"index": i, "x_mm": 0., "y_mm": b.top_offset_mm + i * b.spacing_mm,
                "hole_length_mm": b.hole_length_mm, "diameter_mm": b.diameter_mm}
               for i in range(b.count)]
    clock = _append(operations, clock, "transfer_to_button", config.process.transfer_s,
                    window, machine_id="transport")
    clock = _append(operations, clock, "button_setup", b.setup_s, window, machine_id="button")
    button_start = clock
    for button in buttons:
        common = {"machine_id": "button", "piece_id": "front", "button_index": button["index"]}
        clock = _append(operations, clock, "buttonhole_align", b.align_s, window, **common)
        clock = _append(operations, clock, "buttonhole_stitch", b.hole_stitches * 60 / b.stitches_per_min,
                        window, tool="needle", **common)
        clock = _append(operations, clock, "buttonhole_cut", b.cut_s, window, tool="knife", **common)
        clock = _append(operations, clock, "button_attach_align", b.align_s, window, **common)
        clock = _append(operations, clock, "button_attach_stitch", b.attach_stitches * 60 / b.stitches_per_min,
                        window, tool="needle", **common)
    buttons_end = clock

    q = config.process.qc
    clock = _append(operations, clock, "transfer_to_qc", config.process.transfer_s,
                    window, machine_id="transport")
    qc_start = clock
    for kind, duration in (("qc_load", q.load_s), ("qc_scan", q.scan_s), ("qc_release", q.release_s)):
        clock = _append(operations, clock, kind, duration, window, machine_id="qc", piece_id="garment")
    qc_end = clock
    clock = _append(operations, clock, "ready_for_qr", .01, window, machine_id="qc", piece_id="garment")

    machines = base["machines"]
    for machine in machines:
        if machine["id"] in STATIONS:
            machine["role"] = "active"
    totals = dict(base["totals"])
    totals.update(duration_s=clock, cutting_duration_s=cut_end, sewing_duration_s=sewing_work,
                  button_duration_s=buttons_end-sewing_end, qc_duration_s=qc_end-qc_start,
                  work_steps=sum(r["scheduled"] for r in work_steps),
                  ironing_skipped_s=sum(r["duration_s"] for r in work_steps if r["ironing"]),
                  sewn_length_mm=sum(s["length_mm"] for s in seams),
                  stitches=sum(s["stitches"] for s in seams) + b.count * (b.hole_stitches + b.attach_stitches),
                  seams=len(seams), buttons=b.count, shirt_size=config.process.shirt_size)
    plan = {**base, "schema_version": PLAN_VERSION, "scope": "through_qc", "config": config.model_dump(),
            "operations": operations, "sewing_seams": seams, "work_steps": work_steps,
            "buttons": buttons, "machines": machines, "totals": totals,
            "boundaries": {"cutting_end_s": cut_end, "sewing_start_s": sewing_start, "sewing_end_s": sewing_end,
                           "buttons_start_s": button_start, "buttons_end_s": buttons_end,
                           "qc_start_s": qc_start, "qc_end_s": qc_end},
            "finished_garment_geometry": base.get("finished_garment"), "finished_garment": False,
            "qc": {"verdict_model": "deterministic_pass_no_defect_model",
                   "dpp_label_or_qr_issued": 0},
            "assumptions": [
                "Research simulation only; no textile physics, live equipment or manufactured-product claim.",
                "Sewing follows the measured men's-shirt work-step table with every ironing step skipped "
                "(30:11 of sewing work); steam finishing is not simulated.",
                "A step's measured time is split across the polo seams it closes by seam length; collar and "
                "overlock steps without a matching polo seam run as timed operations without thread length.",
                "Machine power is drawn at the active rate for the whole measured sewing step.",
                "Button and QC timings, power and costs are editable research assumptions.",
                "QC deterministically passes; there is no defect, rework or scrap model.",
                "The run stops ready for a DPP label or QR and never issues one.",
            ]}
    plan["resource_ledger"] = _resource_rows(plan, config)
    plan["totals"]["resources"] = resources_at(plan, clock)
    plan["timeline"] = process_timeline(plan)
    digest = json.dumps({k: v for k, v in plan.items() if k != "plan_id"}, sort_keys=True,
                        ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    plan["plan_id"] = hashlib.sha256(digest.encode()).hexdigest()[:20]
    return plan


def _progress(op, t):
    return min(1., max(0., (t - op["start_s"]) / (op["end_s"] - op["start_s"])))


def snapshot(plan: dict, time_s: float) -> dict:
    if isinstance(time_s, bool) or not math.isfinite(time_s):
        raise ValueError("time must be finite")
    duration = plan["totals"]["duration_s"]
    t = max(0., min(float(time_s), duration))
    ops = plan["operations"]
    ends = [op["end_s"] for op in ops]
    idx = min(len(ops)-1, bisect.bisect_right(ends, t))
    current = ops[idx]
    current_progress = _progress(current, t)
    completed_paths, cut = [], {"cut": 0., "travel": 0., "mark": 0.}
    pieces = {p["id"]: "waiting" for p in plan["pieces"]}
    vacuum = False
    for op in ops[:idx+1]:
        f = _progress(op, t)
        if op["kind"] == "vacuum_on" and f == 1: vacuum = True
        if op["kind"] == "vacuum_off" and f == 1: vacuum = False
        if op["path_id"] is not None:
            path = plan["paths"][op["path_id"]]
            if op["kind"].startswith("cut"): cut["cut"] += path["distance_mm"] * f
            elif op["kind"] == "travel": cut["travel"] += path["distance_mm"] * f
            else: cut["mark"] += path["distance_mm"] * f
            if f == 1: completed_paths.append(path["id"])
            if op["kind"] == "cut_outer": pieces[op["piece_id"]] = "cut" if f == 1 else "cutting"
        if op["kind"] == "pickup" and f == 1: pieces[op["piece_id"]] = "collected"
    cut_parts = sum(v in ("cut", "collected") for v in pieces.values())
    collected = sum(v == "collected" for v in pieces.values())

    # Measured steps include handling, so a seam is sewn once its stitch share ends.
    seam_states = {s["id"]: "waiting" for s in plan["sewing_seams"]}
    sewn_length, stitches = 0., 0
    active_seam, seam_progress = None, 0.
    presser = current["kind"] == "stitch" and current["start_s"] <= t < current["end_s"]
    seam_by_id = {s["id"]: s for s in plan["sewing_seams"]}
    for op in ops:
        if op["start_s"] > t: break
        key = op.get("seam_id")
        if not key or op["kind"] != "stitch": continue
        f = _progress(op, t)
        if op["start_s"] <= t < op["end_s"]:
            active_seam, seam_progress = key, f
        seam = seam_by_id[key]
        sewn_length += seam["length_mm"] * f
        stitches += math.floor(seam["stitches"] * f + 1e-8)
        seam_states[key] = "sewn" if f == 1 else "sewing"
    for piece in plan["pieces"]:
        relevant = [s["id"] for s in plan["sewing_seams"] if piece["id"] in s["piece_ids"]]
        if relevant and all(seam_states[s] == "sewn" for s in relevant): pieces[piece["id"]] = "sewn"
        elif any(seam_states[s] != "waiting" for s in relevant): pieces[piece["id"]] = "sewing"

    scheduled = [r for r in plan["work_steps"] if r["scheduled"]]
    step = next((r for r in scheduled if r["no"] == current.get("step_no")), None)
    steps_complete = sum(t >= r["end_s"] for r in scheduled)

    button_states = ["waiting"] * len(plan["buttons"])
    button_stitches = 0
    for op in ops:
        bi = op.get("button_index")
        if bi is None or op["start_s"] > t: continue
        f = _progress(op, t)
        if op["kind"] == "buttonhole_stitch":
            button_states[bi] = "buttonhole_sewing" if f < 1 else "buttonhole_sewn"
            button_stitches += math.floor(plan["config"]["process"]["buttons"]["hole_stitches"] * f)
        elif op["kind"] == "buttonhole_cut" and f == 1: button_states[bi] = "buttonhole_cut"
        elif op["kind"] == "button_attach_stitch":
            button_states[bi] = "attaching" if f < 1 else "attached"
            button_stitches += math.floor(plan["config"]["process"]["buttons"]["attach_stitches"] * f)

    b = plan["boundaries"]
    stage = ("cutting" if t < b["cutting_end_s"] else "sewing" if t < b["sewing_end_s"] else
             "buttons" if t < b["buttons_end_s"] else "qc" if t < b["qc_end_s"] else "ready_for_qr")
    machine_id = current.get("machine_id", "zund")
    machines = {m["id"]: ("waiting" if m["id"] in STATIONS else m["role"]) for m in plan["machines"]}
    for mid in STATIONS:
        own = [o for o in ops if o.get("machine_id", "zund") == mid]
        if own and t >= own[-1]["end_s"]: machines[mid] = "complete"
    if machine_id in machines and t < duration: machines[machine_id] = "working"
    head = current["head_mm"]
    if current["path_id"] is not None:
        head = base_engine.path_position(plan["paths"][current["path_id"]], current_progress)
    station_readouts = readouts(machine_id, current["kind"], current_progress) if machine_id == "qc" else {}
    ready = t >= b["qc_end_s"]
    chapters = plan.get("timeline") or process_timeline(plan)
    chapter = next((row for row in chapters if t < row["end_s"]), chapters[-1])
    transport = None
    if current["kind"].startswith("transfer_to_"):
        destination = current["kind"].removeprefix("transfer_to_")
        previous = next((op["machine_id"] for op in reversed(ops[:idx])
                         if op["machine_id"] != "transport"), "zund")
        transport = {"from": previous, "to": destination, "progress": current_progress}
    focus = (transport["to"] if transport else machine_id if chapter["id"] == "sewing"
             else chapter["machine_id"])
    state = {"sim_time_s": t, "duration_s": duration, "finished": ready, "stage": stage,
             "chapter": chapter["id"], "chapter_progress": _progress(chapter, t),
             "chapter_start_s": chapter["start_s"], "chapter_end_s": chapter["end_s"],
             "focus_machine_id": focus, "transport": transport,
             "operation_start_s": current["start_s"], "operation_end_s": current["end_s"],
             "operation_index": idx, "operation": current["kind"], "operation_progress": current_progress,
             "machine_id": machine_id, "piece_id": current["piece_id"], "window": current["window"],
             "step": ({"no": step["no"], "name": step["name"], "tool": step["tool"]} if step else None),
             "head_mm": head, "tool": current["tool"], "vacuum": vacuum,
             "path_id": current["path_id"], "path_progress": current_progress,
             "completed_paths": completed_paths, "pieces": pieces,
             "size": plan.get("size"), "scope": "through_qc",
             "cutting_complete": t >= b["cutting_end_s"], "sewing_complete": t >= b["sewing_end_s"],
             "buttons_complete": t >= b["buttons_end_s"],
             "qc_complete": ready, "ready_for_qr": ready, "qc_verdict": "pass" if ready else "scanning" if stage == "qc" else None,
             "readouts": station_readouts, "buttons": button_states,
             "sewing": {"seams": seam_states, "seam_id": active_seam, "seam_progress": seam_progress,
                        "presser_down": presser, "sewn_length_mm": sewn_length, "stitches": stitches,
                        "seams_complete": sum(v == "sewn" for v in seam_states.values()),
                        "seams_total": len(seam_states), "assembly_collected": t >= b["sewing_end_s"]},
             "metrics": {"cut_length_mm": cut["cut"], "travel_mm": cut["travel"], "mark_length_mm": cut["mark"],
                         "cut_pieces": cut_parts, "collected_pieces": collected,
                         "sewn_length_mm": sewn_length, "stitches": stitches + button_stitches,
                         "seams_complete": sum(v == "sewn" for v in seam_states.values()),
                         "seams_total": len(seam_states), "steps_complete": steps_complete,
                         "steps_total": len(scheduled), "sewing_work_s": plan["totals"]["sewing_duration_s"],
                         "ironing_skipped_s": plan["totals"]["ironing_skipped_s"],
                         "buttons_attached": sum(v == "attached" for v in button_states),
                         "buttons_total": len(button_states), "yield_pct": plan["totals"]["yield_pct"],
                         "waste_area_mm2": plan["totals"]["waste_area_mm2"]},
             "resources": resources_at(plan, t), "machines": machines}
    return state


def _clock(seconds):
    total = int(math.floor(seconds + 1e-7))
    return f"{total // 60}:{total % 60:02d}"


def terminal_lines(state: dict):
    r, m = state["resources"], state["metrics"]
    readout = " | ".join(f"{k} {v}" for k, v in state.get("readouts", {}).items())
    lines = [f"RESEARCH POLO | {state['stage']} | {state['operation']} | {state['sim_time_s']:.2f}/{state['duration_s']:.2f} s",
             f"Machine {state['machine_id']} | operation {state['operation_progress']*100:.1f}% | size {(state.get('size') or {}).get('label') or 'unknown'}"]
    if state.get("step"):
        step = state["step"]
        lines.append(f"Step {step['no']:02d} {step['name']} | {step['tool']} | {m['steps_complete']}/{m['steps_total']} steps done")
    lines += [f"Cut {m['cut_length_mm']/1000:.3f} m | Sewn {m['sewn_length_mm']/1000:.3f} m | Stitches {m['stitches']} | Buttons {m['buttons_attached']}/{m['buttons_total']}",
              f"Sewing work {_clock(m['sewing_work_s'])} | ironing skipped {_clock(m['ironing_skipped_s'])}",
              f"Energy {r['energy_kwh']:.5f} kWh | CO2e {r['co2e_g']:.2f} g | Cost {r['cost_eur']:.4f} EUR",
              f"Direct labour {r['labour_time_s']:.2f} s | Thread {r['thread_used_m']:.3f} m"]
    if readout: lines.append(readout)
    if state["ready_for_qr"]:
        lines.append("QC PASS | READY FOR DPP LABEL / QR | QR ISSUED 0")
    return lines
