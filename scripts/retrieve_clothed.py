"""Size a CLOTHED scan by retrieval: recover the body, then search with it.

A clothed scan's girths are the garment's, so the scan itself is never the
query. C2 recovers an SMPL body under the cloth (inference/fit.py), the
recovered body is measured in the canonical A pose by the same pipeline
the store was built with, and THAT vector is searched. Retrieval then
says how far the recovered body is from every reference body (abstaining
outside the store), how much bodies like it vary, and which size they
were given. It cannot correct a biased recovery: if C2 reads the chest
40 mm wide, so does the query.

Two modes (needs torch + smplx; PowerShell, PYTHONUTF8=1):

  --battery   re-measure the bodies C2 already recovered in
              reports/c2_synthetic_battery.json (8 procedural shells on one
              latent body, 10 CAPE garments on subjects 00096 and 00215) and
              score retrieval against the truth body. No new fit is run.
              Claim: (retrieved_neighbours, synthetic_latent) ->
              synthetic_recovery. CAPE rows are local-only (reports/ is not
              in git).

  --shell F   fit one shell mesh (3 starts), then retrieve. A real clothed
              scan has no gap atlas (decision #41), so the gap band is an
              assumption passed with --band and recorded as one.

  .venv\\Scripts\\python scripts\\retrieve_clothed.py --db syn-neutral --battery
  .venv\\Scripts\\python scripts\\retrieve_clothed.py --db syn-neutral --shell scan.ply --input-unit mm
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

BATTERY = PROJECT_ROOT / "reports" / "c2_synthetic_battery.json"
QUERY_PATHWAY = "inferred_smpl_under_clothing"
CHART = "en13402"


def _measure_betas(body, betas, source_id):
    from body_measure.retrieval.estimator import query_from_measurements
    from body_measure.retrieval.ingest import measure_mesh
    from body_measure.retrieval.labels import label_record

    mesh = body.canonical_mesh(np.asarray(betas, dtype=np.float32), source_id=source_id)
    m = measure_mesh(mesh, check_pose=False)
    values, usable = query_from_measurements(m.measurements, m.prototypes, m.stature_mm)
    shirt_values = {k: v for k, v in values.items() if k != "stature_mm"}
    labels = label_record(m.measurements, population=None,
                          shirt_values=shirt_values, shirt_usable=usable)
    return m, values, usable, labels


def _query(store, index, cal, values, usable, k):
    from body_measure.retrieval.estimator import estimate

    return estimate(store, index, cal, values, usable, query_pathway=QUERY_PATHWAY, k=k)


def _winner(votes: dict | None):
    if not votes:
        return None, None
    top = next(iter(votes))
    return (top if votes[top] >= 0.5 and top != "neighbour_refused" else None), votes[top]


def battery_mode(args, store, index, cal) -> dict:
    from body_measure.inference.smpl_body import SmplBody
    from body_measure.validate.claims import Comparison

    report = json.loads(BATTERY.read_text(encoding="utf-8"))
    body = SmplBody(gender="neutral")
    truth_cache: dict = {}

    def truth(key, betas):
        if key not in truth_cache:
            truth_cache[key] = _measure_betas(body, betas, f"truth-{key}")
        return truth_cache[key]

    cape = None
    rows = []
    cases = [(c, "synthetic_shell", report["latent"]["betas"], "latent")
             for c in report.get("cases", [])]
    for c in report.get("cape_cases", []):
        src = c["meta"].get("shell_source", {})
        if cape is None:
            from body_measure.inference.cape_release import CapeRelease
            cape = CapeRelease()
        subject = src.get("subject")
        cases.append((c, "cape_garment", cape.betas(subject).tolist(), f"cape-{subject}"))

    for case, kind, truth_betas, truth_key in cases:
        t_m, t_values, _, t_labels = truth(truth_key, truth_betas)
        r_m, r_values, r_usable, r_labels = _measure_betas(
            body, case["fit"]["params"]["betas"], f"recovered-{case['case']}")
        est = _query(store, index, cal, r_values, r_usable, args.k)
        ret_label, ret_share = _winner(est.size_votes.get(CHART))
        ret_shirt, _ = _winner(est.size_votes.get("ita_he_26"))

        def d(key):
            a, b = r_values.get(key), t_values.get(key)
            return None if a is None or b is None else round(a - b, 1)

        rows.append({
            "case": case["case"], "kind": kind, "truth": truth_key,
            "beta_l2_error": round(case["beta_l2_error"], 3),
            "abstained": est.abstained, "abstain_reason": est.abstain_reason,
            "nearest_distance": est.nearest_distance,
            "truth_label": t_labels.get(CHART),
            "recovered_direct_label": r_labels.get(CHART),
            "retrieved_label": ret_label, "retrieved_share": ret_share,
            "truth_shirt": t_labels.get("ita_he_26"),
            "recovered_direct_shirt": r_labels.get("ita_he_26"),
            "retrieved_shirt": ret_shirt,
            "delta_recovered_minus_truth_mm": {
                k: d(k) for k in ("chest_circumference", "waist_circumference",
                                  "neck_circumference", "upper_arm_girth")},
            "retrieval_chest_spread_mm": est.spread.get("chest_circumference"),
            "flags": est.flags,
        })
        print(f"  {case['case']:28s} truth {t_labels.get(CHART)}  direct "
              f"{r_labels.get(CHART)}  retrieved {ret_label} ({ret_share})  "
              f"{'ABSTAIN' if est.abstained else ''}", file=sys.stderr)

    def agree(field):
        scored = [r for r in rows if r["truth_label"] is not None and not r["abstained"]]
        return {"n": len(scored), "agree": sum(r[field] == r["truth_label"] for r in scored)}

    comparison = Comparison(pathway="retrieved_neighbours", reference_kind="synthetic_latent",
                            reference_method="the truth body (latent or CAPE subject betas), "
                                             "measured by this pipeline")
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **comparison.to_dict(),
        "db_name": store.db_name, "k": args.k or cal.k,
        "calibration_threshold": cal.threshold,
        "query_pathway": QUERY_PATHWAY,
        "note": ("Self-consistency on recovered bodies, not accuracy on a real clothed "
                 "scan: the shells are procedural or CAPE displacements on known bodies "
                 "(decisions #40, #41). CAPE rows are licence-restricted."),
        "n_cases": len(rows),
        "n_abstained": sum(r["abstained"] for r in rows),
        "label_agreement_retrieved_vs_truth": agree("retrieved_label"),
        "label_agreement_direct_vs_truth": agree("recovered_direct_label"),
        "chest_delta_recovered_minus_truth": {
            "mean": round(statistics.mean(
                r["delta_recovered_minus_truth_mm"]["chest_circumference"] for r in rows
                if r["delta_recovered_minus_truth_mm"]["chest_circumference"] is not None), 1)
            if rows else None},
        "rows": rows,
    }


def shell_mode(args, store, index, cal) -> dict:
    from body_measure.adapters.mesh_file import MeshFileAdapter
    from body_measure.canonicalize import canonicalize
    from body_measure.inference.fit import FitConfig, multi_start
    from body_measure.inference.smpl_body import SmplBody

    shell = canonicalize(MeshFileAdapter().load(args.shell, unit=args.input_unit),
                         up_axis=args.up_axis)
    band = {p: (args.band[0], args.band[1]) for p in ("torso", "head", "arm", "leg")}
    body = SmplBody(gender="neutral")
    # as in c2_synthetic_battery.py: the first start (zero betas) is the
    # fit, the perturbed starts measure how much the shell pins it down
    runs = multi_start(body, shell, band, FitConfig(), starts=args.starts)
    best = runs[0]
    spread = float(np.linalg.norm(np.stack([r.betas for r in runs]).std(axis=0)))
    m, values, usable, labels = _measure_betas(body, best.betas, f"recovered-{args.shell.stem}")
    est = _query(store, index, cal, values, usable, args.k)
    from body_measure import sizing
    size = est.to_size_assignment(sizing.CHARTS[CHART], population=args.population,
                                  chest_mm=values.get("chest_circumference"))
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shell": str(args.shell), "gap_band_mm": band,
        "gap_band_source": "assumed on the command line; no gap atlas exists (decision #41)",
        "query_pathway": QUERY_PATHWAY,
        "fit": best.to_dict(), "starts": len(runs),
        "betas_spread_l2_across_starts": round(spread, 3),
        "fit_flags": best.flags,
        "recovered_body": {"values": values, "labels": labels},
        "retrieval": est.to_dict(),
        "size": size.to_dict(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--k", type=int, default=None)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--battery", action="store_true")
    mode.add_argument("--shell", type=Path)
    ap.add_argument("--input-unit", choices=["mm", "cm", "m"])
    ap.add_argument("--up-axis", choices=["Y", "Z"], default="Y")
    ap.add_argument("--band", type=float, nargs=2, default=(5.0, 25.0), metavar=("LO", "HI"))
    ap.add_argument("--starts", type=int, default=3)
    ap.add_argument("--population", choices=["men", "women"], default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    from body_measure.retrieval.calibration import load_or_fit
    from body_measure.retrieval.store import RecordStore

    store = RecordStore.open(args.db)
    cal, flags = load_or_fit(store)
    if flags:
        print("calibration: " + ", ".join(flags), file=sys.stderr)
    index = store.index()
    if args.battery:
        if not BATTERY.is_file():
            print(f"no {BATTERY.name}; run scripts/c2_synthetic_battery.py --cape", file=sys.stderr)
            return 1
        result = battery_mode(args, store, index, cal)
        out = args.out or PROJECT_ROOT / "reports" / f"retrieval_clothed_{store.db_name}.json"
    else:
        if not args.input_unit:
            print("error: --shell needs --input-unit", file=sys.stderr)
            return 1
        result = shell_mode(args, store, index, cal)
        out = args.out or PROJECT_ROOT / "reports" / f"retrieval_clothed_{args.shell.stem}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    summary = {k: v for k, v in result.items() if k != "rows"}
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str)[:4000])
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
