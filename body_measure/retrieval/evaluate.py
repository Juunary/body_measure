"""How well retrieval reproduces what the pipeline measured, per track.

Each query is a record of the store, searched with itself (and its whole
subject) excluded. The reference is that record's own pipeline values and
labels, so every number here is an AGREEMENT between retrieval and the
pipeline, labelled through validate.claims:

  real scans       (retrieved_neighbours, minimal_scan_surface)
                   -> reference_surface_agreement
  synthetic bodies (retrieved_neighbours, synthetic_latent)
                   -> synthetic_recovery

Neither is accuracy: the pipeline is the reference, not a tape.
"""
from __future__ import annotations

import statistics
from collections.abc import Callable

from ..validate.claims import Comparison
from .calibration import Calibration
from .estimator import estimate
from .features import STATURE_KEY
from .record import ScanRecord

TRACK_REFERENCE = {
    "real": ("minimal_scan_surface", "the subject's own scan, measured by this pipeline"),
    "synthetic": ("synthetic_latent", "the generating SMPL body, measured by this pipeline"),
}


def subject_of(record: ScanRecord) -> str:
    """The person a record belongs to. Several records of one subject
    (captures, garments) must leave the search together (decision #18)."""
    return (record.gen or {}).get("subject") or record.source_id


def _summary(deltas: list[float]) -> dict:
    if not deltas:
        return {"n": 0, "bias": None, "sd": None, "mae": None}
    return {
        "n": len(deltas),
        "bias": round(statistics.mean(deltas), 2),
        "sd": round(statistics.stdev(deltas), 2) if len(deltas) >= 2 else None,
        "mae": round(statistics.mean(abs(d) for d in deltas), 2),
    }


def run_track(store, cal: Calibration, track: str, queries: list[ScanRecord], *,
              k: int | None = None, keep_rows: bool = True,
              progress: Callable[[int, int], None] | None = None) -> dict:
    reference_kind, method = TRACK_REFERENCE[track]
    comparison = Comparison(pathway="retrieved_neighbours", reference_kind=reference_kind,
                            reference_method=method)
    index = store.index()
    by_subject: dict[str, list[str]] = {}
    for r in store.records:
        by_subject.setdefault(subject_of(r), []).append(r.record_id)

    rows, abstained = [], {}
    deltas: dict[str, list[float]] = {key: [] for key in store.space.keys}
    agree: dict[str, list[bool]] = {}
    for i, rec in enumerate(queries):
        est = estimate(store, index, cal, rec.feature_values(), rec.feature_usable(),
                       population=rec.population, k=k,
                       exclude_ids=by_subject[subject_of(rec)])
        if progress:
            progress(i + 1, len(queries))
        row = {"record_id": rec.record_id, "abstained": est.abstained,
               "abstain_reason": est.abstain_reason,
               "nearest_distance": est.nearest_distance}
        if est.abstained:
            # grouped by cause, not by the sentence (which carries numbers)
            key = ("out_of_reference_manifold" if "out_of_reference_manifold" in est.flags
                   else (est.abstain_reason or "").split(";")[0][:100])
            abstained[key] = abstained.get(key, 0) + 1
            rows.append(row)
            continue
        for key in store.space.keys:
            own = rec.stature_mm if key == STATURE_KEY else rec.values.get(key)
            got = est.values.get(key)
            if rec.usable(key) and got is not None:
                deltas[key].append(float(got) - float(own))
        labels = {}
        for chart_key, own_label in rec.size_labels.items():
            votes = est.size_votes.get(chart_key) or {}
            top = next(iter(votes), None)
            winner = top if top and votes[top] >= 0.5 else None
            labels[chart_key] = {"own": own_label, "retrieved": winner,
                                 "share": votes.get(top) if top else None}
            if own_label is not None:
                agree.setdefault(chart_key, []).append(winner == own_label)
        row["labels"] = labels
        rows.append(row)

    n = len(queries)
    n_answered = sum(1 for r in rows if not r["abstained"])
    return {
        "track": track,
        **comparison.to_dict(),
        "db_name": store.db_name,
        "k": k or cal.k,
        "calibration": {"threshold": cal.threshold, "sigma": cal.sigma, "n": cal.n,
                        "split_used": cal.split_used, "coverage_target": cal.coverage},
        "n_queries": n,
        "n_answered": n_answered,
        "coverage": round(n_answered / n, 4) if n else None,
        "abstentions": abstained,
        "label_agreement": {
            chart: {"n": len(v), "agree": sum(v), "rate": round(sum(v) / len(v), 4)}
            for chart, v in sorted(agree.items()) if v
        },
        "delta_retrieved_minus_own": {key: _summary(v) for key, v in deltas.items()},
        "rows": rows if keep_rows else [],
    }


def markdown(result: dict) -> str:
    lines = [
        f"## Retrieval — {result['track']} track, store `{result['db_name']}`",
        "",
        f"Claim: **{result['claim_category']}** "
        f"({result['pathway']} against {result['reference_kind']}: {result['reference_method']}). "
        "An agreement with this pipeline, not accuracy.",
        "",
        f"| queries | answered | coverage | k | threshold | calibrated on |",
        f"|---|---|---|---|---|---|",
        f"| {result['n_queries']} | {result['n_answered']} | "
        f"{(result['coverage'] or 0):.0%} | {result['k']} | "
        f"{result['calibration']['threshold']:.3f} | "
        f"{result['calibration']['n']} ({result['calibration']['split_used']}) |",
        "",
    ]
    if result["abstentions"]:
        lines += ["Abstentions:", ""]
        lines += [f"- {n} × {why}" for why, n in sorted(result["abstentions"].items(),
                                                       key=lambda kv: -kv[1])]
        lines.append("")
    if result["label_agreement"]:
        lines += ["| chart | n | same label as the pipeline | rate |", "|---|---|---|---|"]
        for chart, v in result["label_agreement"].items():
            lines.append(f"| {chart} | {v['n']} | {v['agree']} | {v['rate']:.0%} |")
        lines.append("")
    lines += ["Retrieved (neighbour weighted median) minus the query's own value:", "",
              "| key | n | bias | SD | MAE |", "|---|---|---|---|---|"]
    def num(v, sign=False):
        if v is None:
            return "—"
        return f"{v:+.1f}" if sign else f"{v:.1f}"

    for key, s in result["delta_retrieved_minus_own"].items():
        lines.append(f"| {key} | {s['n']} | {num(s['bias'], True)} | "
                     f"{num(s['sd'])} | {num(s['mae'])} |")
    lines.append("")
    return "\n".join(lines)
