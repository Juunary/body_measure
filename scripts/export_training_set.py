"""Write the encoder's training set from a synthetic store (needs torch + smplx).

For every record with betas: the canonical A-pose body, plus --shells
procedural clothing shells around it (random per-part stand-off, a random
front/back asymmetry, random holes), each sampled to 4096 surface points.
Every variant is labelled with the BODY's betas and the BODY's
standardised measurement vector, which is what the encoder must learn to
see through the cloth.

Licence. The store must be entirely exportable (synthetic_smpl or
public_hsrd) — `RecordStore.assert_exportable` refuses otherwise — and the
shells are procedural, never CAPE displacements, so the shards may go to
the personal GPU server under the docs/licenses/scope.md entry. The
manifest records the store hash so the server copy is traceable and
deletable.

  .venv\\Scripts\\python scripts\\export_training_set.py --db syn-neutral --out data/training/syn-neutral
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

SHARD = 1000
_body = None


def _init(gender: str) -> None:
    global _body
    import torch

    from body_measure.inference.smpl_body import SmplBody

    torch.set_num_threads(1)
    _body = SmplBody(gender=gender)


def _shell(body_mesh, part, rng):
    """One procedural shell: per-part stand-off, front/back asymmetry on the
    torso, and a few holes. All numbers are drawn, none is a garment model."""
    import trimesh

    stand = {"torso": rng.uniform(3, 35), "arm": rng.uniform(2, 30),
             "leg": rng.uniform(0, 20), "head": rng.uniform(0, 3)}
    gap = np.array([stand[p] for p in part])
    front = np.clip(body_mesh.vertex_normals @ np.array([0.0, 0.0, 1.0]), 0.0, 1.0)
    gap = gap + np.where(part == "torso", rng.uniform(0, 20) * front, 0.0)
    gap = gap * rng.uniform(0.85, 1.15, size=gap.shape)          # cloth is not smooth
    verts = body_mesh.vertices + body_mesh.vertex_normals * gap[:, None]
    faces = body_mesh.faces
    if rng.random() < 0.5:                                       # scan holes
        keep = np.ones(len(faces), dtype=bool)
        centroids = verts[faces].mean(axis=1)
        for _ in range(rng.integers(1, 4)):
            c = verts[rng.integers(len(verts))]
            keep &= np.linalg.norm(centroids - c, axis=1) > rng.uniform(30, 80)
        faces = faces[keep]
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


def _one(job: dict) -> dict:
    from body_measure.retrieval.points import sample_surface

    rng = np.random.default_rng(job["seed"])
    mesh = _body.canonical_mesh(np.asarray(job["betas"], dtype=np.float32),
                                source_id=job["record_id"])
    clouds = [sample_surface(mesh, seed=job["seed"])]
    kinds = ["body"]
    for s in range(job["shells"]):
        clouds.append(sample_surface(_shell(mesh, _body.part_of_vertex, rng),
                                     seed=job["seed"] + 1 + s))
        kinds.append("shell")
    return {"record_id": job["record_id"], "points": np.stack(clouds).astype(np.float16),
            "kinds": kinds}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--shells", type=int, default=3, help="procedural shells per body")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = ap.parse_args()

    from body_measure.retrieval.features import vectorise
    from body_measure.retrieval.store import RecordStore

    store = RecordStore.open(args.db)
    store.assert_exportable()
    records = [r for r in store.records if r.betas is not None][: args.limit]
    genders = {(r.gen or {}).get("smpl_gender", "neutral") for r in records}
    if len(genders) != 1:
        print(f"error: one SMPL gender per training set, got {sorted(genders)}", file=sys.stderr)
        return 1
    gender = genders.pop()
    args.out.mkdir(parents=True, exist_ok=True)

    jobs = [{"record_id": r.record_id, "betas": list(r.betas), "shells": args.shells,
             "seed": int(hashlib.sha256(r.record_id.encode()).hexdigest()[:8], 16)}
            for r in records]
    by_id = {r.record_id: r for r in records}
    shards, t0 = [], time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init,
                             initargs=(gender,)) as pool:
        for start in range(0, len(jobs), SHARD):
            batch = list(pool.map(_one, jobs[start:start + SHARD], chunksize=8))
            pts, betas, meas, mask, split, kind, ids = [], [], [], [], [], [], []
            for out in batch:
                rec = by_id[out["record_id"]]
                z, m = vectorise(store.space, rec.feature_values(), rec.feature_usable())
                for cloud, k in zip(out["points"], out["kinds"]):
                    pts.append(cloud)
                    betas.append(rec.betas)
                    meas.append(z)
                    mask.append(m)
                    split.append(rec.split)
                    kind.append(k)
                    ids.append(rec.record_id)
            name = f"shard_{start // SHARD:04d}.npz"
            np.savez_compressed(args.out / name, points=np.stack(pts),
                                betas=np.array(betas, np.float32), meas_z=np.array(meas, np.float32),
                                mask=np.array(mask), split=np.array(split), kind=np.array(kind),
                                record_id=np.array(ids))
            shards.append(name)
            print(f"  {min(start + SHARD, len(jobs))}/{len(jobs)} bodies "
                  f"({time.perf_counter() - t0:.0f} s)", file=sys.stderr, flush=True)

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "store": store.db_name, "store_records_sha256": store.records_sha256(),
        "store_pipeline_hash": store.manifest.get("pipeline_hash"),
        "licence_classes": sorted({r.licence_class.value for r in records}),
        "smpl_gender": gender, "shells_per_body": args.shells,
        "shell_source": "procedural (scripts/export_training_set.py _shell); no CAPE data",
        "n_bodies": len(records), "shards": shards,
        "feature_space": store.space.to_dict(),
        "retention": "delete the server copy after training (docs/licenses/scope.md)",
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"{len(records)} bodies x {1 + args.shells} clouds -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
