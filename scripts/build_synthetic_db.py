"""Build a retrieval store of synthetic SMPL bodies (needs torch + smplx).

Each body: betas from a prior -> SmplBody.canonical_mesh (A pose, mm, floor
at 0) -> pose gate -> the estimated pathway + garment prototypes -> labels
on every chart -> one ScanRecord. No mesh is stored; `gen` regenerates it.

Priors
  normal       beta ~ N(0, sd^2) clipped to +-clip, the rule of
               generate_smpl_bodies.py. Licence-clean: synthetic_smpl.
  cape         per-beta normal fitted to the CAPE TRAIN subjects of the same
               gender (reports/cape-split-manifest.json). A CAPE derivative,
               so every record is local_only_licensed and the store cannot
               be exported.
  cape-subjects  the 15 CAPE subjects' own betas, split as the manifest
               splits them. local_only_licensed.

The cost is the measurement (2.5-4 s a body on this workstation); the
SMPL forward pass is negligible. Bodies are spread over worker processes
and the store is saved every --save-every records, so an interrupted run
resumes with --resume.

Run (PowerShell; the Bash tool's numpy DLLs are blocked by the
application-control policy on this machine):
  $env:PYTHONUTF8=1
  .venv\\Scripts\\python scripts\\build_synthetic_db.py --db syn-neutral --n 10000 --workers 7
  .venv\\Scripts\\python scripts\\build_synthetic_db.py --db syn-neutral --n 20 --probe
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

# One BLAS / OpenMP thread per worker. Without this every worker spawns a
# thread per core and seven workers measured a body in 14 s instead of 3
# (reports/retrieval_cost.json, first probe). Set before numpy is imported,
# and inherited by the spawned workers.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_SEED = 20261015
GENDER_TO_POPULATION = {"neutral": None, "male": "men", "female": "women"}
SPLIT_MANIFEST = PROJECT_ROOT / "reports" / "cape-split-manifest.json"
COST_REPORT = PROJECT_ROOT / "reports" / "retrieval_cost.json"

_body = None  # one SmplBody per worker process


def _init_worker(gender: str) -> None:
    global _body
    import torch

    from body_measure.inference.smpl_body import SmplBody

    torch.set_num_threads(1)
    _body = SmplBody(gender=gender)


def _measure_one(job: dict) -> dict:
    """Runs in a worker. Returns the record as a dict, or a skip reason."""
    from body_measure.retrieval.ingest import measure_mesh, record_from_measured
    from body_measure.retrieval.record import LicenceClass

    t0 = time.perf_counter()
    mesh = _body.canonical_mesh(np.asarray(job["betas"], dtype=np.float32),
                                source_id=job["record_id"])
    m = measure_mesh(mesh)
    if m is None:
        return {"skip": job["record_id"], "reason": "pose_gate", "seconds": time.perf_counter() - t0}
    rec = record_from_measured(
        m, record_id=job["record_id"], source_type="synthetic_smpl", source_id=job["record_id"],
        licence_class=LicenceClass(job["licence"]), population=job["population"],
        spec_version=job["spec_version"], pipeline_hash=job["pipeline_hash"],
        split=job["split"], betas=job["betas"], smpl_model_id=_body.model_id, gen=job["gen"])
    return {"record": rec.to_dict(), "seconds": time.perf_counter() - t0}


def _split_of(record_id: str, holdout: float) -> str:
    """Deterministic from the id, so a resumed run splits identically."""
    h = int(hashlib.sha256(record_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "holdout" if h < holdout else "train"


def _cape_train_betas(gender: str) -> np.ndarray:
    from body_measure.inference.cape_release import CapeRelease

    split = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))
    release = CapeRelease()
    rows = [release.betas(s) for s in split["train_subjects"]
            if gender == "neutral" or release.gender(s) == gender]
    if len(rows) < 3:
        raise SystemExit(f"only {len(rows)} CAPE train subjects of gender {gender}")
    return np.stack(rows)


def make_jobs(args, spec_version: int, phash: str) -> tuple[list[dict], dict]:
    from body_measure.retrieval.record import LicenceClass

    population = GENDER_TO_POPULATION[args.gender]
    rng = np.random.default_rng(args.seed)
    jobs, prior = [], {"kind": args.prior, "seed": args.seed}

    if args.prior == "cape-subjects":
        from body_measure.inference.cape_release import CapeRelease

        split = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))
        release = CapeRelease()
        for subject in release.subjects():
            gender = release.gender(subject)
            if args.gender != "neutral" and gender != args.gender:
                continue
            rid = f"cape-{subject}"
            jobs.append({
                "record_id": rid, "betas": release.betas(subject).tolist(),
                "licence": LicenceClass.LOCAL_ONLY.value,
                "population": GENDER_TO_POPULATION.get(gender),
                "split": "test" if subject in split["test_subjects"] else "train",
                "gen": {"prior": "cape-subjects", "subject": f"cape/{subject}",
                        "cape_gender": gender, "smpl_gender": args.gender},
                "spec_version": spec_version, "pipeline_hash": phash,
            })
        prior["split_manifest_sha256"] = split["sha256"]
        return jobs, prior

    if args.prior == "normal":
        mean, sd = np.zeros(10), np.full(10, args.sd)
        licence = LicenceClass.SYNTHETIC
    else:
        train = _cape_train_betas(args.gender)
        mean, sd = train.mean(axis=0), np.maximum(train.std(axis=0, ddof=1), 0.1) * args.widen
        licence = LicenceClass.LOCAL_ONLY
        prior["n_cape_train"] = int(train.shape[0])
    prior.update({"mean": mean.round(4).tolist(), "sd": sd.round(4).tolist(), "clip": args.clip})

    for i in range(args.n):
        betas = np.clip(rng.normal(mean, sd), -args.clip, args.clip)
        rid = f"smpl-{args.gender}-{args.prior}-{args.seed}-{i:06d}"
        jobs.append({
            "record_id": rid, "betas": betas.round(6).tolist(), "licence": licence.value,
            "population": population, "split": _split_of(rid, args.holdout),
            "gen": {"prior": args.prior, "seed": args.seed, "i": i, "smpl_gender": args.gender,
                    "abduction_deg": 50.0},
            "spec_version": spec_version, "pipeline_hash": phash,
        })
    return jobs, prior


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--gender", choices=sorted(GENDER_TO_POPULATION), default="neutral")
    ap.add_argument("--prior", choices=["normal", "cape", "cape-subjects"], default="normal")
    ap.add_argument("--sd", type=float, default=1.2, help="normal prior SD")
    ap.add_argument("--clip", type=float, default=3.0)
    ap.add_argument("--widen", type=float, default=1.5,
                    help="cape prior: SD multiplier, 11 subjects under-cover the population")
    ap.add_argument("--holdout", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--save-every", type=int, default=200)
    ap.add_argument("--resume", action="store_true", help="skip ids already in the store")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--probe", action="store_true",
                    help="time the bodies and write reports/retrieval_cost.json; no store")
    args = ap.parse_args()

    from body_measure.retrieval.calibration import fit_calibration
    from body_measure.retrieval.features import FEATURE_SPACE_VERSION
    from body_measure.retrieval.record import RECORD_SCHEMA_VERSION, ScanRecord
    from body_measure.retrieval.store import RecordStore, StoreError
    from body_measure.retrieval.versioning import pipeline_hash
    from body_measure.spec import load_spec

    spec = load_spec()
    phash = pipeline_hash(feature_space_version=FEATURE_SPACE_VERSION,
                          record_schema_version=RECORD_SCHEMA_VERSION)
    jobs, prior = make_jobs(args, spec.version, phash)

    store = None
    if not args.probe:
        if args.resume:
            try:
                store = RecordStore.open(args.db)
            except StoreError:
                store = None
        if store is None:
            store = RecordStore.create(args.db, overwrite=args.overwrite,
                                       note=f"synthetic SMPL, prior {args.prior}, {args.gender}")
        store.manifest["prior"] = prior
        done = set(store.ids)
        jobs = [j for j in jobs if j["record_id"] not in done]
    print(f"{len(jobs)} bodies to measure on {args.workers} workers", file=sys.stderr)

    seconds, skipped = [], []
    t_start = time.perf_counter()
    done_n = 0
    # Batches of --save-every: each batch is mapped, then saved, so a crash
    # loses at most one batch and --resume picks up from the store.
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init_worker,
                             initargs=(args.gender,)) as pool:
        for start in range(0, len(jobs), args.save_every):
            batch = jobs[start:start + args.save_every]
            pending = []
            for out in pool.map(_measure_one, batch, chunksize=2):
                seconds.append(out["seconds"])
                if "skip" in out:
                    skipped.append(out["skip"])
                else:
                    pending.append(ScanRecord.from_dict(out["record"]))
            done_n += len(batch)
            if store is not None and pending:
                store.append(pending)
                store.manifest["skipped_pose_gate"] = sorted(
                    set(store.manifest.get("skipped_pose_gate", [])) | set(skipped))
                store.save()
            rate = (time.perf_counter() - t_start) / done_n
            print(f"  {done_n}/{len(jobs)}  {rate:.2f} s/body wall  "
                  f"eta {rate * (len(jobs) - done_n) / 60:.0f} min", file=sys.stderr, flush=True)

    wall = time.perf_counter() - t_start
    cost = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n": len(seconds), "workers": args.workers, "gender": args.gender,
        "per_body_s_median": round(float(np.median(seconds)), 3) if seconds else None,
        "per_body_s_p95": round(float(np.quantile(seconds, 0.95)), 3) if seconds else None,
        "wall_s": round(wall, 1),
        "wall_s_per_body": round(wall / max(len(seconds), 1), 3),
        "skipped_pose_gate": len(skipped),
        "projection_10k_hours": round(wall / max(len(seconds), 1) * 10000 / 3600, 2),
    }
    if args.probe:
        COST_REPORT.parent.mkdir(exist_ok=True)
        COST_REPORT.write_text(json.dumps(cost, indent=2), encoding="utf-8")
        print(json.dumps(cost, indent=2))
        return 0

    store.manifest["build_cost"] = cost
    store.save()
    if len(store) >= 3:
        cal = fit_calibration(store)
        store.save_calibration(cal.to_dict())
        print(f"calibrated: threshold {cal.threshold:.3f} on {cal.n} ({cal.split_used})",
              file=sys.stderr)
    print(f"{len(store)} records -> {store.path}  ({len(skipped)} refused by the pose gate)")
    print(json.dumps(cost, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
