"""Export a trained PointEncoder to ONNX for CPU queries, and prove it.

The path is the one decision #19 proved with a throwaway model: export
with a batch of 2 (torch.export specialises a dimension it only ever sees
as 1), onnxscript installed, PYTHONUTF8=1 on a cp949 console. The sidecar
JSON next to the .onnx carries the feature space the measurement head
predicts in, so retrieval/onnx_query.py can refuse a mismatched store.

  python -m body_measure.inference.export_encoder checkpoints/encoder.pt checkpoints/encoder.onnx
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

from .encoder import N_POINTS, PointEncoder

PARITY_TOLERANCE = 1e-4


def export_onnx(checkpoint: Path, out: Path, *, n_points: int = N_POINTS, seed: int = 0) -> dict:
    ckpt = torch.load(checkpoint, map_location="cpu", weights_only=False)
    model = PointEncoder(n_meas=ckpt["n_meas"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    torch.manual_seed(seed)
    sample = torch.rand(2, n_points, 3) * torch.tensor([0.5, 1.8, 0.3]) - torch.tensor([0.25, 0.0, 0.15])
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    batch = torch.export.Dim("batch", min=1, max=256)
    torch.onnx.export(
        model, (sample,), str(out),
        input_names=["points"], output_names=["embedding", "betas", "meas_z"],
        dynamic_shapes={"points": {0: batch}},
        opset_version=18,
    )
    sidecar = {
        "feature_space": ckpt["feature_space"],
        "training_store": ckpt["training_manifest"].get("store"),
        "training_store_records_sha256": ckpt["training_manifest"].get("store_records_sha256"),
        "licence_classes": ckpt["training_manifest"].get("licence_classes"),
        "n_points": n_points,
        "checkpoint": str(checkpoint),
        "pathway_note": "predictions are an inference of the body, never a measurement",
    }
    out.with_suffix(".json").write_text(json.dumps(sidecar, indent=2), encoding="utf-8")

    import onnxruntime as ort

    session = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    with torch.no_grad():
        eager = [t.numpy() for t in model(sample)]
    got = session.run(["embedding", "betas", "meas_z"], {"points": sample.numpy()})
    parity = max(float(np.abs(a - b).max()) for a, b in zip(eager, got))
    three = np.concatenate([sample.numpy(), sample.numpy()[:1]])
    dyn = session.run(["betas"], {"points": three})[0].shape[0] == 3
    report = {"onnx": str(out), "parity_max_abs_diff": parity,
              "parity_ok": parity < PARITY_TOLERANCE, "dynamic_batch_ok": dyn}
    out.with_suffix(".export.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 1
    report = export_onnx(Path(argv[0]), Path(argv[1]))
    print(json.dumps(report, indent=2))
    return 0 if report["parity_ok"] and report["dynamic_batch_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
