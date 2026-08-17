"""One-time conversion: legacy SMPL .pkl (chumpy arrays) -> plain-numpy .pkl.

The v1.1.0 release pickles chumpy arrays, and chumpy itself no longer
installs on modern Python/numpy. Instead of installing it, a custom
Unpickler maps every chumpy class to a stub; the wrapped array lives in
the instance __dict__ (attribute 'x'). The rewritten file contains plain
numpy (+ scipy sparse) only, so smplx loads it without chumpy.

Run:  .venv\\Scripts\\python scripts\\convert_smpl_pkl.py
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np

MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "smpl"


class ChumpyStub:
    """Reconstruction target for any chumpy class in the pickle."""


class SmplUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module.startswith("chumpy"):
            return ChumpyStub
        return super().find_class(module, name)


def _plain(value):
    if isinstance(value, ChumpyStub):
        inner = value.__dict__.get("x")
        if inner is None:
            raise ValueError(f"chumpy object without 'x': keys={list(value.__dict__)}")
        return np.asarray(inner)
    return value


def convert(path: Path) -> None:
    raw = path.with_name(path.stem + "_chumpy.pkl")
    if not raw.exists():
        path.rename(raw)
    with open(raw, "rb") as handle:
        data = SmplUnpickler(handle, encoding="latin1").load()
    clean = {key: _plain(value) for key, value in data.items()}
    with open(path, "wb") as handle:
        pickle.dump(clean, handle, protocol=2)
    kinds = {key: type(value).__name__ for key, value in clean.items()}
    print(f"converted {path.name}: {kinds}")


def main() -> int:
    for name in ("SMPL_NEUTRAL.pkl", "SMPL_MALE.pkl", "SMPL_FEMALE.pkl"):
        target = MODEL_DIR / name
        if target.exists() or target.with_name(target.stem + "_chumpy.pkl").exists():
            convert(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
