"""The feature space a scan is indexed in.

The vector is the pipeline's own measurement vector, standardised: the
seven spec measurements, the five garment prototypes and the stature.
That is the space the size labels live in, which is why it is the index
space and SMPL betas are not. Betas are PCA coefficients with unequal
girth leverage, and |beta - beta'| does not track millimetres: in the C2
battery a beta error of 1.6 was a chest error of -21 mm and a beta error
of 3.5 was +42 mm.

A value the pipeline itself will not accept (`rejected`, `manual_review`)
is masked out rather than imputed; the distance is taken over the keys
both sides have.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SPEC_KEYS = (
    "chest_circumference", "waist_circumference", "neck_circumference",
    "upper_arm_girth", "across_back_shoulder_width", "sleeve_length", "back_length",
)
#: garment_prototypes.POLO_SET, pinned here so this module needs no mesh
#: libraries; a test asserts the two tuples agree
PROTOTYPE_KEYS = (
    "hip_girth", "sleeve_opening_girth", "armhole_depth", "shoulder_slope", "front_back_width",
)
STATURE_KEY = "stature_mm"
FEATURE_KEYS: tuple[str, ...] = SPEC_KEYS + PROTOTYPE_KEYS + (STATURE_KEY,)
FEATURE_SPACE_VERSION = "meas-v2"

#: The keys the DISTANCE reads. Every feature key is still stored,
#: standardised and estimated from the neighbours; only these decide who
#: the neighbours are. Measured on 40 real scans against 2,600 synthetic
#: SMPL bodies (decision #59): with all 13 keys no real scan fell inside
#: the synthetic set, because the prototypes and the landmark-derived
#: lengths carry a systematic synthetic-vs-real offset (armhole depth
#: +45 mm, shoulder slope +7 deg, across-back +42 mm). With these five,
#: 59 % did. They are also the keys a size chart and the ITA_HE_26 chart
#: are read from.
INDEX_KEYS: tuple[str, ...] = (
    "chest_circumference", "waist_circumference", "hip_girth", "neck_circumference",
    STATURE_KEY,
)

#: a key with less spread than this across the fitted records is treated
#: as constant: dividing by a near-zero SD would let one key dominate
SD_FLOOR = 1.0
#: a key fitted on fewer usable values than this is kept but listed in
#: `thin_keys`, so a reader knows its scale is a guess
MIN_FIT_PER_KEY = 5


@dataclass(frozen=True)
class FeatureSpace:
    keys: tuple[str, ...]
    mean: tuple[float, ...]
    sd: tuple[float, ...]
    version: str
    n_fit: int
    thin_keys: tuple[str, ...] = ()
    index_keys: tuple[str, ...] = INDEX_KEYS

    @property
    def dim(self) -> int:
        return len(self.keys)

    def index_of(self, key: str) -> int:
        return self.keys.index(key)

    def index_mask(self) -> np.ndarray:
        """True for the columns the distance reads."""
        return np.array([k in self.index_keys for k in self.keys], dtype=bool)

    def standardise(self, raw: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Standardised vector with 0 where the mask is False, so a masked
        entry contributes nothing even if a caller forgets the mask."""
        raw = np.nan_to_num(np.asarray(raw, dtype=np.float64))
        z = (raw - np.asarray(self.mean)) / np.asarray(self.sd)
        return np.where(mask, z, 0.0)

    def unstandardise(self, z: np.ndarray) -> np.ndarray:
        return np.asarray(z) * np.asarray(self.sd) + np.asarray(self.mean)

    def to_dict(self) -> dict:
        return {
            "keys": list(self.keys), "mean": [float(m) for m in self.mean],
            "sd": [float(s) for s in self.sd], "version": self.version,
            "n_fit": self.n_fit, "thin_keys": list(self.thin_keys),
            "index_keys": list(self.index_keys),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FeatureSpace":
        # a space saved before index_keys existed read every key (meas-v1)
        index_keys = tuple(data.get("index_keys") or data["keys"])
        return cls(
            keys=tuple(data["keys"]), mean=tuple(float(m) for m in data["mean"]),
            sd=tuple(float(s) for s in data["sd"]), version=str(data["version"]),
            n_fit=int(data["n_fit"]), thin_keys=tuple(data.get("thin_keys", ())),
            index_keys=index_keys,
        )


def raw_vector(values: dict[str, float | None], usable: dict[str, bool] | None = None,
               *, keys: tuple[str, ...] = FEATURE_KEYS) -> tuple[np.ndarray, np.ndarray]:
    """(raw, mask) over `keys`. A key is present when its value is not
    None and, if `usable` says anything about it, usable."""
    raw = np.full(len(keys), np.nan)
    mask = np.zeros(len(keys), dtype=bool)
    for i, key in enumerate(keys):
        value = values.get(key)
        if value is None:
            continue
        if usable is not None and not usable.get(key, True):
            continue
        raw[i] = float(value)
        mask[i] = True
    return raw, mask


def fit_standardiser(rows: list[tuple[np.ndarray, np.ndarray]], *,
                     keys: tuple[str, ...] = FEATURE_KEYS,
                     version: str = FEATURE_SPACE_VERSION,
                     index_keys: tuple[str, ...] | None = None) -> FeatureSpace:
    """Per-key mean and SD (ddof=1) over the usable values of `rows`,
    which are (raw, mask) pairs. A key no row has keeps mean 0 and SD
    `SD_FLOOR`, so the space has the same width whatever was available."""
    if not rows:
        raise ValueError("cannot fit a feature space on zero records")
    raw = np.stack([r for r, _ in rows])
    mask = np.stack([m for _, m in rows])
    mean, sd, thin = [], [], []
    for i, key in enumerate(keys):
        col = raw[mask[:, i], i]
        n = int(col.size)
        if n < MIN_FIT_PER_KEY:
            thin.append(key)
        mean.append(float(col.mean()) if n else 0.0)
        s = float(col.std(ddof=1)) if n >= 2 else 0.0
        sd.append(max(s, SD_FLOOR))
    if index_keys is None:
        index_keys = tuple(k for k in INDEX_KEYS if k in keys) or tuple(keys)
    return FeatureSpace(keys=tuple(keys), mean=tuple(mean), sd=tuple(sd),
                        version=version, n_fit=len(rows), thin_keys=tuple(thin),
                        index_keys=tuple(index_keys))


def vectorise(space: FeatureSpace, values: dict[str, float | None],
              usable: dict[str, bool] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(standardised vector, mask) for one body in `space`."""
    raw, mask = raw_vector(values, usable, keys=space.keys)
    return space.standardise(raw, mask), mask
