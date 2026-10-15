"""The trained encoder, query side: ONNX Runtime on CPU, no torch.

The model file carries no feature space of its own; the sidecar JSON next
to it (written by inference/export_encoder.py) holds the store's feature
space the measurement head was trained in, the store hash, and the
licence class of the training data. A model trained on one store's space
refuses to be read against another's."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .features import FeatureSpace


@dataclass
class EncoderOutput:
    embedding: np.ndarray
    betas: np.ndarray
    meas_z: np.ndarray
    #: the predicted measurement vector in the key's units (mm, deg)
    values: dict[str, float]


class OnnxEncoder:
    def __init__(self, model_path: Path):
        import onnxruntime as ort

        self.path = Path(model_path)
        sidecar = self.path.with_suffix(".json")
        if not sidecar.exists():
            raise FileNotFoundError(f"{sidecar.name} missing: the model cannot be read "
                                    "without the feature space it was trained in")
        self.meta = json.loads(sidecar.read_text(encoding="utf-8"))
        self.space = FeatureSpace.from_dict(self.meta["feature_space"])
        self.session = ort.InferenceSession(str(self.path), providers=["CPUExecutionProvider"])

    def check_space(self, space: FeatureSpace) -> None:
        if space.to_dict() != self.space.to_dict():
            raise ValueError("the store's feature space is not the one this encoder was "
                             "trained in; retrain or query the store it came from")

    def __call__(self, points: np.ndarray) -> EncoderOutput:
        """points: (N, 3) or (B, N, 3) float32 metres, from retrieval.points."""
        p = np.asarray(points, dtype=np.float32)
        single = p.ndim == 2
        if single:
            # the graph was exported with a dynamic batch traced at 2
            p = np.stack([p, p])
        emb, betas, meas = self.session.run(["embedding", "betas", "meas_z"], {"points": p})
        if single:
            emb, betas, meas = emb[:1], betas[:1], meas[:1]
        values = self.space.unstandardise(meas[0])
        return EncoderOutput(emb[0], betas[0], meas[0],
                             {k: float(v) for k, v in zip(self.space.keys, values)})
