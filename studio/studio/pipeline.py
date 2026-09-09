"""The measurement phase: body-measure's CLI path, one call at a time,
with an event between the calls.

Mirrors `body_measure/cli.py:_measure` — adapter, canonicalize, one
`run_estimated_measurements` call (the range gate runs inside it, decision
#39), garment prototypes, then sizing — and writes the same result
document, so what the page shows is a genuine body-measure result, and
polo-line reads its size block the way it always has.

Granularity is honest: body-measure has no progress hooks, so the stream
says when the measurement call starts and when it returns. It does not
pretend to know which girth is being sliced in between.
"""
from __future__ import annotations

import json
import time

from . import curves as C
from . import events as ev
from . import meshio
from . import pose
from . import sizing_map
from .jobs import Job
from .paths import RUNS
from body_measure.garment_prototypes import run_prototypes
from body_measure.measure.measurements import run_estimated_measurements
from body_measure.result import empty_result
from body_measure.spec import load_spec
from body_measure.validate.stats import quality_bucket

PHASE = ev.PHASE_MEASURE
BUCKET_STYLE = {
    "clean": "green", "arm_clipped": "green", "fallback": "yellow",
    "low_confidence": "yellow", "gap_closed": "yellow",
    "manual_review": "red", "rejected": "red",
}


def _timed(job: Job, index: int, total: int, name: str, detail: str = ""):
    class _Stage:
        def __enter__(self):
            self.t0 = time.perf_counter()
            job.stage(PHASE, name, "start", detail)
            job.line(PHASE, ev.stage_line(index, total, name, detail), "head")
            return self

        def __exit__(self, exc_type, exc, tb):
            if exc_type is None:
                elapsed = time.perf_counter() - self.t0
                job.stage(PHASE, name, "done", detail, elapsed)
            return False
    return _Stage()


def run_load(job: Job) -> None:
    """Stage `load`: adapter + canonicalize → mesh_ready."""
    job.state = "loading"
    params, entry = job.params, job.entry
    with _timed(job, 1, 2, "load", entry["label"]):
        surface, mesh, info = meshio.load_surface(entry, params.get("unit"), params.get("up_axis"))
        job.surface, job.mesh, job.mesh_info = surface, mesh, info
        job.line(PHASE, ev.done_line(
            f"{info['source_id']} · {info['n_vertices']:,} vertices · {info['n_faces']:,} faces"
            f" · unit {info['unit']} · up {info['up_axis']}"))
    with _timed(job, 2, 2, "canonicalize", "Y-up, floor at 0, welded"):
        weld = info.get("weld") or {}
        job.line(PHASE, ev.done_line(
            f"floor at y=0 · bounds {info['bounds_mm'][0]} .. {info['bounds_mm'][1]} mm"
            f" · weld merged {weld.get('merged', 0)} vertices"))
    decimated = len(mesh.faces) > meshio.DISPLAY_FACE_LIMIT
    job.emit("mesh_ready", PHASE, decimated=decimated, **info)
    job.state = "ready"


def run_measure(job: Job) -> None:
    """Stage `measure`: landmarks + measurements + prototypes + curves,
    then sizing, then the document on disk."""
    if job.mesh is None:
        raise RuntimeError("load the scan first")

    job.state = "measuring"
    params = job.params
    spec = load_spec()
    mesh = job.mesh
    total = 5

    # The pose gate comes first and ends the stage on its own: a scan that
    # is not a standing A pose gets a verdict, not a table of refusals.
    job.stage(PHASE, "pose", "start", "standing A pose: orientation, arms clear of the torso")
    job.line(PHASE, ev.stage_line(0, total, "pose", "standing A pose: orientation, arms clear of the torso"), "head")
    verdict = pose.check_pose(mesh)
    job.emit("pose", PHASE, **verdict.to_dict())
    if not verdict.ok:
        for reason in verdict.reasons:
            job.line(PHASE, ev.warn_line(reason), "error")
        job.line(PHASE, ev.seg("      ", ("✗ pose rejected — measurement stopped; ", ["red", "bold"]),
                               ("pick a scan in a standing A pose", ["red"])), "error")
        job.stage(PHASE, "pose", "rejected", "; ".join(verdict.reasons))
        job.state = "pose_rejected"
        return
    arms = verdict.checks.get("arms") or {}
    job.line(PHASE, ev.done_line(
        f"stature {verdict.checks['stature_mm']:.0f} mm · facing confidence "
        f"{verdict.checks['facing']['confidence']:.2f} · both arms clear at "
        f"{arms.get('levels_with_both_arms', 0)}/{arms.get('levels', 0)} upper-arm levels"))
    job.stage(PHASE, "pose", "done")

    with _timed(job, 1, total, "landmarks_measurements",
                f"{len(spec.names)} spec measurements, ISO 8559-1, gate included"):
        measurements, landmarks = run_estimated_measurements(mesh)
        job.measurements, job.landmarks = measurements, landmarks
        facing = landmarks.get("facing")
        if facing is not None:
            job.line(PHASE, ev.note(
                f"facing {facing.method} · confidence {facing.confidence:.2f}"
                + (f" · {', '.join(facing.flags)}" if facing.flags else "")))
        for name in spec.names:
            value = measurements[name]
            bucket = quality_bucket(value)
            shown = "—" if value.selected_value_mm is None else f"{value.selected_value_mm:7.1f} mm"
            flags = [f for f in value.quality if f != "ok"]
            job.line(PHASE, ev.seg(
                "      ", (f"{name:<28s}", "grey"),
                (f"{shown:>11s}", "yellow" if value.selected_value_mm is not None else "red"),
                ("  ", []), (f"{bucket:<14s}", BUCKET_STYLE.get(bucket, "grey")),
                (("  " + ", ".join(flags)) if flags else "", "grey")), "row")
        ok = sum(1 for n in spec.names if measurements[n].selected_value_mm is not None)
        job.line(PHASE, ev.done_line(f"{ok}/{len(spec.names)} measurements carry a value"))

    with _timed(job, 2, total, "prototypes", "polo prototypes, not in the spec"):
        prototypes = run_prototypes(mesh, measurements, landmarks)
        job.prototypes = prototypes
        for key, proto in prototypes.items():
            shown = "—" if proto.value is None else f"{proto.value:7.1f} {proto.unit}"
            job.line(PHASE, ev.seg("      ", (f"{key:<28s}", "grey"), (f"{shown:>11s}", "yellow"),
                                   ("  prototype", "grey"),
                                   (("  " + ", ".join(proto.flags)) if proto.flags else "", "grey")), "row")

    with _timed(job, 3, total, "curves", "re-slicing rings, rebuilding surface paths"):
        curves, notes = C.gather(mesh, measurements, landmarks, prototypes)
        job.curves, job.curve_notes = curves, notes
        for note in notes:
            job.line(PHASE, ev.warn_line(note))
        job.line(PHASE, ev.done_line(f"{len(curves)} curves drawable"))

    points, facing_json = C.landmarks_json(landmarks)
    job.emit("measurements", PHASE, rows=measurement_rows(job, spec))
    job.emit("landmarks", PHASE, points=points, facing=facing_json)
    job.emit("prototypes", PHASE, rows=[{"key": k, **v.to_dict(), "label": v.label}
                                        for k, v in prototypes.items()])
    job.emit("curves", PHASE, curves=curves, notes=notes)

    with _timed(job, 4, total, "sizing", f"chart {params.get('chart')}"):
        sizing_map.assign_size(job, params.get("chart"), params.get("population"),
                               bool(params.get("clothed")), spec=spec)

    with _timed(job, 5, total, "document", "body-measure result document"):
        path = write_document(job, spec)
        job.line(PHASE, ev.done_line(f"wrote {path.name}"))
        sizing_map.load_customer_size(job)
    job.state = "measured"


def measurement_rows(job: Job, spec=None) -> list[dict]:
    spec = spec or load_spec()
    rows = []
    for name in spec.names:
        value = job.measurements.get(name)
        if value is None:
            continue
        rows.append({
            "name": name,
            "selected_value_mm": value.selected_value_mm,
            "raw_contour_mm": value.raw_contour_mm,
            "taut_tape_hull_mm": value.taut_tape_hull_mm,
            "method": value.method,
            "selection_method": value.selection_method,
            "quality": list(value.quality),
            "disposition": value.disposition,
            "bucket": quality_bucket(value),
            "definition": spec.measurements[name].definition,
        })
    return rows


def write_document(job: Job, spec=None):
    """The same document `body_measure measure --out` writes."""
    spec = spec or load_spec()
    params = job.params
    result = empty_result(
        spec, source_type=job.surface.source_type, source_id=job.surface.source_id,
        pathway="measured_clothed" if params.get("clothed") else "estimated")
    result.meta["input"] = {"path": job.entry["path"], "unit": job.mesh_info.get("unit"),
                            "up_axis": job.mesh_info.get("up_axis"), "kind": job.entry["kind"]}
    result.measurements.update(job.measurements)
    result.landmarks.update({name: lm.to_dict() for name, lm in job.landmarks.items()})
    if job.prototypes:
        result.meta["garment_prototypes"] = {k: v.to_dict() for k, v in job.prototypes.items()}
    if job.sizing is not None:
        result.meta["size"] = job.sizing.to_dict()
    result.meta["studio"] = {"job": job.id, "file": job.entry["id"],
                             "licence": job.entry["licence"]["badge"]}
    if job.reports:
        # a reader of the document sees what a person disputed, next to the
        # number they disputed; the number itself is left as measured
        result.meta["reports"] = list(job.reports)
    folder = RUNS / job.id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "measurement.json"
    path.write_text(result.to_json(), encoding="utf-8")
    job.document_path = path
    return path


def document_json(job: Job) -> dict | None:
    if job.document_path is None or not job.document_path.is_file():
        return None
    return json.loads(job.document_path.read_text(encoding="utf-8"))


#: Which landmark fixes the height a value was taken at. A report that
#: says "measured above the armpit" is only checkable if the report itself
#: records the height — the four filed on 2026-09-08 did not, and the
#: level had to be recomputed to read them.
LEVEL_LANDMARKS = {
    "chest_circumference": "chest_level",
    "waist_circumference": "waist_level",
    "neck_circumference": "neck_base_level",
    "upper_arm_girth": "upper_arm_girth_station_right",
    "hip_girth": "buttock_prominence_level",
    "back_length": "back_neck_point",
    "across_back_shoulder_width": "back_neck_point",
    "sleeve_length": "shoulder_point_right",
    "armhole_depth": "armpit_level",
}


def _level_of(job: Job, key: str) -> dict | None:
    """The height a measurement was taken at, and the armpit it can be read
    against — the reference the reports keep pointing at."""
    name = LEVEL_LANDMARKS.get(key)
    landmark = job.landmarks.get(name) if name else None
    if landmark is None or not hasattr(landmark, "position_mm"):
        return None
    y = round(float(landmark.position_mm[1]), 1)
    out = {"landmark": name, "y_mm": y}
    # the axilla is where a person sees the arm join the torso; armpit_level
    # is the highest grid height with both arms still separate, which is
    # what the clip bounds need and is up to a step lower (decision #54).
    # A report about WHERE a value was taken is read against the axilla, so
    # that is the reference when it exists.
    for key, prefix in (("axilla_level", "axilla"), ("armpit_level", "armpit")):
        landmark = job.landmarks.get(key)
        if landmark is None or not hasattr(landmark, "position_mm"):
            continue
        ref = round(float(landmark.position_mm[1]), 1)
        out[f"{prefix}_y_mm"] = ref
        if "above_armpit_mm" not in out:
            out["above_armpit_mm"] = round(y - ref, 1)
            out["above_relative_to"] = key
    return out


def add_report(job: Job, target: str, key: str, value, unit: str, text: str) -> dict:
    """File a report against one value of this scan and keep it with the
    document. `target` is "measurement", "prototype" or "landmark"."""
    text = (text or "").strip()
    if not text:
        raise ValueError("a report needs a text")
    if target not in ("measurement", "prototype", "landmark"):
        raise ValueError("target must be measurement, prototype or landmark")
    report = {
        "id": len(job.reports) + 1,
        "filed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scan": job.entry["id"], "source_id": job.mesh_info.get("source_id"),
        "target": target, "key": key, "value": value, "unit": unit,
        "text": text,
    }
    level = _level_of(job, key)
    if level is not None:
        report["level"] = level
    job.reports.append(report)
    if job.measurements:
        write_document(job)
    job.emit("report", ev.PHASE_MEASURE, report=report, reports=list(job.reports))
    where = ""
    if level is not None:
        where = f"  @ y {level['y_mm']:.0f} mm"
        if "above_armpit_mm" in level:
            against = "axilla" if level.get("above_relative_to") == "axilla_level" else "armpit"
            where += f" ({level['above_armpit_mm']:+.0f} vs {against})"
    job.line(ev.PHASE_MEASURE, ev.seg("      ", ("⚑ report ", ["yellow"]),
                                      (f"{key} {value if value is not None else ''} {unit}".strip(), ["bold"]),
                                      (where, ["cyan"]),
                                      (f" — {text}", ["grey"])), "report")
    return report
