"""C2 synthetic gate battery — can the optimiser recover a known body from
a shell around it, and does it know when it cannot?

For each battery case a body with known betas (the `synthetic_latent`
reference) is wrapped in a shell, the shell is fitted, and the recovered
body is measured **in the canonical pose by the same measurement core**
that measures the latent body. The claim is `synthetic_recovery`, derived
from (inferred_smpl_under_clothing, synthetic_latent) — never typed.

Evaluation order (the plan's, deliberately): canonical-measurement
agreement first, then surface gap, then beta error, then collapse and
outside violation. A fitter is judged on the numbers a tailor would use,
not on how close its latent code is.

Run (PowerShell — torch's DLLs do not load from Git Bash here):
  $env:PYTHONUTF8=1; .venv\\Scripts\\python scripts\\c2_synthetic_battery.py [--quick] [--multistart]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from body_measure.inference.fit import FitConfig, fit_shell, multi_start  # noqa: E402
from body_measure.inference.shells import build_battery  # noqa: E402
from body_measure.inference.smpl_body import NUM_BETAS, SmplBody  # noqa: E402
from body_measure.landmarks.estimated import provided_facing  # noqa: E402
from body_measure.measure.measurements import run_estimated_measurements  # noqa: E402
from body_measure.spec import load_spec  # noqa: E402
from body_measure.validate.claims import Comparison, claim_category_for  # noqa: E402
from body_measure.validate.stats import quality_bucket  # noqa: E402

OUT = PROJECT_ROOT / "reports" / "c2_synthetic_battery.json"
SEED = 20260821
PATHWAY = "inferred_smpl_under_clothing"


#: SMPL's frame defines its front (+Z). Estimating it from the toes is
#: unreliable on a body model — the latent body came out facing a diagonal
#: at low confidence — and unnecessary, because nothing is unknown here.
SMPL_FACING = provided_facing((0.0, 1.0), source="smpl_frame")


def measure(mesh) -> dict:
    values, _ = run_estimated_measurements(mesh, facing=SMPL_FACING)
    return {
        name: {"value_mm": v.selected_value_mm, "bucket": quality_bucket(v),
               "flags": [f for f in v.quality if f != "ok"]}
        for name, v in values.items()
    }


def pick_latent_body(body: SmplBody, names, *, max_tries: int = 20):
    """A reference body has to be one the measurement core measures
    cleanly. A latent body whose waist sits on a search boundary gives a
    `low_confidence` number that jumps by hundreds of mm under a tiny
    shape change — and then recovery error is measuring landmark
    instability, not the fit. Candidates are drawn from a fixed seed
    sequence so the choice is reproducible and the rejections are on
    record."""
    rejected = 0
    for k in range(max_tries):
        seed = SEED + k
        betas = np.random.default_rng(seed).normal(0.0, 0.8, size=NUM_BETAS)
        mesh = body.canonical_mesh(betas, source_id=f"latent/seed{seed}")
        truth = measure(mesh)
        if all(truth[n]["value_mm"] is not None and truth[n]["bucket"] in ("clean", "arm_clipped")
               for n in names):
            return betas, mesh, truth, seed, rejected
        rejected += 1
    raise RuntimeError("no candidate latent body measured cleanly — inspect the landmark estimator on SMPL A-pose bodies")


def compare(truth: dict, recovered: dict, names) -> dict:
    out = {}
    for n in names:
        a, b = truth[n]["value_mm"], recovered[n]["value_mm"]
        out[n] = {
            "latent_mm": a, "recovered_mm": b,
            "delta_mm": None if (a is None or b is None) else round(b - a, 2),
            "recovered_bucket": recovered[n]["bucket"],
        }
    return out


#: the last fit per case, so main() can print its timing and flags without
#: run_case having to return two things
FITS: dict = {}


def run_case(body, case, truth, latent_betas, cfg, names) -> dict:
    """Fit one shell and score the body it recovers. Extracted from the
    loop so a CAPE case, which brings its own subject and its own truth,
    can be scored by exactly the same code."""
    fit = fit_shell(body, case.mesh, case.gap_band_mm, cfg)
    recovered = measure(body.canonical_mesh(fit.betas, source_id=f"recovered/{case.name}"))
    FITS[case.name] = fit
    return {
        "case": case.name, "breaks": case.breaks, "meta": case.meta,
        "gap_band_mm": case.gap_band_mm,
        "fit": fit.to_dict(),
        "beta_l2_error": round(float(np.linalg.norm(fit.betas - latent_betas)), 3),
        "measurements": compare(truth, recovered, names),
    }


def cape_cases(cfg, names, quick: bool) -> list[dict]:
    """Shells built from real CAPE clothing, one per (subject, outfit).

    Each has its own subject, so it gets its own SmplBody — SMPL's shape
    space is gendered — and its own truth, measured from that subject's
    published betas. The eight synthetic cases keep the single shared
    latent body they have always had; these are appended, never mixed in.
    """
    from body_measure.inference.cape_release import CapeRelease, displacement_T_m
    from body_measure.inference.cape_transfer import transfer_displacement
    from body_measure.inference.smpl_body import SmplBody as _SmplBody

    release = CapeRelease()
    entries = []
    for subject in release.subjects():
        try:
            outfits = sorted(release.outfits(subject))
        except Exception:
            continue          # not downloaded; the audit lists who is
        if not outfits:
            continue
        subject_body = _SmplBody(gender=release.gender(subject))
        betas = release.betas(subject)
        truth = measure(subject_body.canonical_mesh(betas, source_id=f"cape/{subject}"))
        body_T = release.minimal_body_T_m(subject)
        for outfit in (outfits[:1] if quick else outfits):
            frame = release.first_valid_frame(subject, outfit)
            case = transfer_displacement(
                subject_body, betas, displacement_T_m(frame, body_T),
                name=f"cape_{subject}_{outfit}",
                meta={"shell_source": {**frame.provenance(),
                                       "gender": release.gender(subject)}})
            entry = run_case(subject_body, case, truth, betas, cfg, names)
            entry["subject"] = subject
            entries.append(entry)
            fit = FITS[case.name]
            score = fit.fit_quality_score
            print(f"{case.name:26s} {fit.seconds:5.0f} {score['coverage_fraction']:5.2f} "
                  f"{100*score['outside_fraction']:5.1f} "
                  f"{100*score['collapse_fraction']:5.1f} "
                  f"{entry['beta_l2_error']:7.2f}  (subject's own betas)")
    return entries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="fewer iterations, two cases")
    ap.add_argument("--multistart", action="store_true", help="3 starts on the two hardest cases")
    ap.add_argument("--cape", action="store_true",
                    help="also fit shells built from real CAPE clothing displacements")
    args = ap.parse_args()

    spec = load_spec()
    body = SmplBody()
    latent_betas, latent_mesh, truth, latent_seed, rejected = pick_latent_body(body, spec.names)
    print(f"latent body: seed {latent_seed} ({rejected} candidate(s) rejected for a non-clean measurement)")

    cfg = FitConfig(seed=SEED)
    if args.quick:
        cfg = FitConfig(seed=SEED, iters_coarse=60, iters_pose=30, iters_shape=60, iters_refine=20,
                        n_shell_samples=6000, n_body_subsample=1500)

    cases = build_battery(latent_mesh, body.part_of_vertex, SEED)
    if args.quick:
        cases = [c for c in cases if c.name in ("identity", "partwise_jacket_jeans")]

    comparison = Comparison(pathway=PATHWAY, reference_kind="synthetic_latent",
                            reference_method="body_measure_pipeline_on_latent_canonical_body")
    report = {
        "stage": "C2",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": SEED,
        "latent_seed": latent_seed,
        "latent_candidates_rejected": rejected,
        "claim": {"category": claim_category_for(PATHWAY, "synthetic_latent"), **comparison.to_dict()},
        "latent": {"betas": latent_betas.tolist(), "measurements": truth},
        "config": cfg.__dict__,
        "cases": [],
    }

    print(f"latent measurements: {', '.join(f'{n[:5]}={truth[n]['value_mm']:.0f}' for n in spec.names if truth[n]['value_mm'])}\n")
    print(f"{'case':26s} {'s':>5s} {'cov':>5s} {'out%':>5s} {'col%':>5s} {'|β−β*|':>7s}  chest  waist   neck  flags")
    for case in cases:
        entry = run_case(body, case, truth, latent_betas, cfg, spec.names)
        fit = FITS[case.name]
        beta_err = entry["beta_l2_error"]
        per = entry["measurements"]
        if args.multistart and case.name in ("front_back_asymmetric", "uniform_with_holes"):
            runs = multi_start(body, case.mesh, case.gap_band_mm, cfg, starts=3)
            betas = np.stack([r.betas for r in runs])
            meas = [measure(body.canonical_mesh(r.betas, source_id="ms")) for r in runs]
            entry["multi_start"] = {
                "betas_spread_l2": round(float(np.linalg.norm(betas.std(axis=0))), 3),
                "measurement_spread_mm": {
                    n: round(float(np.std([m[n]["value_mm"] for m in meas if m[n]["value_mm"] is not None])), 2)
                    for n in spec.names
                },
            }
        report["cases"].append(entry)
        s = fit.fit_quality_score
        d = lambda n: per[n]["delta_mm"]
        fmt = lambda x: "  null" if x is None else f"{x:+6.0f}"
        print(f"{case.name:26s} {fit.seconds:5.0f} {s['coverage_fraction']:5.2f} "
              f"{100*s['outside_fraction']:5.1f} {100*s['collapse_fraction']:5.1f} {beta_err:7.2f} "
              f"{fmt(d('chest_circumference'))} {fmt(d('waist_circumference'))} {fmt(d('neck_circumference'))}  "
              f"{','.join(fit.flags) or '-'}")

    if args.cape:
        print()
        print(f"{'cape case':26s} {'s':>5s} {'cov':>5s} {'out%':>5s} "
              f"{'col%':>5s} {'|β−β*|':>7s}")
        report["cape_cases"] = cape_cases(cfg, spec.names, args.quick)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nclaim: {report['claim']['category']} (reference: synthetic_latent)")
    print(f"wrote {OUT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
