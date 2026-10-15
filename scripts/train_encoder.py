"""Train the point encoder on a training set from export_training_set.py.

Meant for the personal GPU server (CUDA picked up automatically); runs on
CPU too, slowly, which is how the smoke test runs it. Validation is the
store's `holdout` split, which no gradient sees. The checkpoint carries
the feature space and the training-set manifest so export and query can
check they agree.

  python scripts/train_encoder.py --data data/training/syn-neutral --out checkpoints/encoder-syn-neutral.pt
  python scripts/train_encoder.py --data ... --epochs 1 --max-batches 5    # smoke
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from body_measure.inference.encoder import PointEncoder, losses  # noqa: E402


def load(data: Path):
    manifest = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
    parts = [np.load(data / s) for s in manifest["shards"]]
    cat = {k: np.concatenate([p[k] for p in parts]) for k in
           ("points", "betas", "meas_z", "mask", "split", "kind", "record_id")}
    return manifest, cat


def augment(points: torch.Tensor, gen: torch.Generator) -> torch.Tensor:
    """Yaw within +-10 degrees and 2 mm jitter. No scaling: a scaled body
    has scaled girths, and its labels would be wrong."""
    b = points.shape[0]
    yaw = (torch.rand(b, generator=gen) * 2 - 1) * np.deg2rad(10.0)
    c, s = torch.cos(yaw), torch.sin(yaw)
    rot = torch.zeros(b, 3, 3)
    rot[:, 0, 0], rot[:, 0, 2], rot[:, 1, 1], rot[:, 2, 0], rot[:, 2, 2] = c, s, 1.0, -s, c
    out = points @ rot.transpose(1, 2).to(points)
    return out + torch.randn(out.shape, generator=gen).to(points) * 0.002


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-batches", type=int, default=None, help="per epoch; for a smoke run")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    gen = torch.Generator().manual_seed(args.seed)
    manifest, d = load(args.data)
    train = np.flatnonzero(d["split"] != "holdout")
    val = np.flatnonzero(d["split"] == "holdout")
    if val.size == 0:
        print("no holdout rows; validating on the last 10 % of train", file=sys.stderr)
        val, train = train[-max(1, train.size // 10):], train[: -max(1, train.size // 10)]
    sd = np.array(manifest["feature_space"]["sd"], dtype=np.float32)
    keys = manifest["feature_space"]["keys"]

    dev = torch.device(args.device)
    model = PointEncoder(n_meas=len(keys)).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(args.epochs, 1))

    def tensors(idx):
        return (torch.from_numpy(d["points"][idx].astype(np.float32)).to(dev),
                torch.from_numpy(d["betas"][idx]).to(dev),
                torch.from_numpy(d["meas_z"][idx]).to(dev),
                torch.from_numpy(d["mask"][idx]).to(dev))

    best, history = float("inf"), []
    for epoch in range(args.epochs):
        model.train()
        order = train[torch.randperm(train.size, generator=gen).numpy()]
        t0, seen = time.perf_counter(), 0
        for bi, start in enumerate(range(0, order.size - 1, args.batch)):
            if args.max_batches is not None and bi >= args.max_batches:
                break
            idx = np.sort(order[start:start + args.batch])
            if idx.size < 2:
                continue
            pts, betas, meas, mask = tensors(idx)
            pts = augment(pts.cpu(), gen).to(dev)
            emb, b_hat, m_hat = model(pts)
            loss = losses(emb, b_hat, m_hat, betas, meas, mask)
            opt.zero_grad()
            loss["total"].backward()
            opt.step()
            seen += idx.size
        sched.step()

        model.eval()
        err, n, l_val = np.zeros(len(keys)), np.zeros(len(keys)), 0.0
        with torch.no_grad():
            for start in range(0, val.size, args.batch):
                idx = val[start:start + args.batch]
                if idx.size < 2:
                    continue
                pts, betas, meas, mask = tensors(idx)
                emb, b_hat, m_hat = model(pts)
                l_val += float(losses(emb, b_hat, m_hat, betas, meas, mask)["meas"]) * idx.size
                m = mask.cpu().numpy()
                diff = np.abs((m_hat - meas).cpu().numpy()) * sd
                err += (diff * m).sum(0)
                n += m.sum(0)
                if args.max_batches is not None and start // args.batch >= args.max_batches:
                    break
        mae = {k: (round(float(e / c), 1) if c else None) for k, e, c in zip(keys, err, n)}
        l_val /= max(int(n.max()), 1)
        history.append({"epoch": epoch, "val_meas_loss": l_val, "val_mae": mae,
                        "seconds": round(time.perf_counter() - t0, 1), "seen": seen})
        print(f"epoch {epoch}: val meas loss {l_val:.4f}  chest MAE "
              f"{mae.get('chest_circumference')} mm  ({history[-1]['seconds']} s)", flush=True)
        if l_val < best:
            best = l_val
            args.out.parent.mkdir(parents=True, exist_ok=True)
            torch.save({"state_dict": model.state_dict(), "n_meas": len(keys),
                        "feature_space": manifest["feature_space"],
                        "training_manifest": manifest, "history": history,
                        "args": {k: str(v) for k, v in vars(args).items()}}, args.out)
    (args.out.with_suffix(".history.json")).write_text(json.dumps(history, indent=2),
                                                       encoding="utf-8")
    print(f"best val meas loss {best:.4f} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
