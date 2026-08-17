"""Landmarks carry provenance, not just coordinates."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Landmark:
    name: str
    position_mm: np.ndarray        # (3,) canonical frame
    confidence: float              # 0..1
    method: str
    quality_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "position_mm": [float(v) for v in self.position_mm],
            "confidence": self.confidence,
            "method": self.method,
            "quality_flags": list(self.quality_flags),
        }
