"""When to abstain, fitted on the store itself.

The threshold is the 95th percentile of leave-one-out nearest-neighbour
distances among the calibration records: by construction 95 % of bodies
like the ones already in the store pass, and a query further from every
reference than that is outside what the store knows. The kernel width
is the median of the same distances, so the weights adapt to the store's
own density instead of to a constant someone typed.

Calibration records are the store's `train` split when it has one, else
everything except `test` and `holdout` — test subjects contribute to no
threshold (decision #18).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .index import BruteForceIndex

DEFAULT_K = 15
COVERAGE = 0.95


def space_key(space) -> str:
    """The feature space a distance was taken in: version and index keys."""
    return f"{space.version}:{','.join(space.index_keys)}"


@dataclass(frozen=True)
class Calibration:
    threshold: float
    sigma: float
    k: int
    coverage: float
    n: int
    records_sha256: str
    split_used: str
    #: per key, the median absolute difference between a calibration body
    #: and its neighbours' median (standardised units), over every feature
    #: key, index or not; it shows which keys the neighbours pin down
    per_key_spread: dict[str, float]
    #: `space_key` of the space the distances were taken in; a calibration
    #: from another space is refitted, never reused
    space_key: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Calibration":
        return cls(**data)


def calibration_positions(store) -> tuple[np.ndarray, str]:
    train = [i for i, r in enumerate(store.records) if r.split == "train"]
    if train:
        return np.array(train, dtype=int), "train"
    rest = [i for i, r in enumerate(store.records) if r.split not in ("test", "holdout")]
    return np.array(rest, dtype=int), "all_but_test_holdout"


def loo_nearest(index: BruteForceIndex, positions: np.ndarray,
                k: int = 1) -> tuple[np.ndarray, list[np.ndarray]]:
    """For each position: its nearest distance among the OTHER calibration
    positions, and its k neighbour positions. inf when none is comparable."""
    allowed = np.zeros(len(index), dtype=bool)
    allowed[positions] = True
    nearest, neighbours = [], []
    for pos in positions:
        d, _ = index.distances(index.Z[pos], index.mask[pos])
        d = np.where(allowed, d, np.inf)
        d[pos] = np.inf
        finite = np.flatnonzero(np.isfinite(d))
        if finite.size == 0:
            nearest.append(np.inf)
            neighbours.append(np.array([], dtype=int))
            continue
        order = finite[np.argsort(d[finite], kind="stable")[:k]]
        nearest.append(float(d[order[0]]))
        neighbours.append(order)
    return np.array(nearest), neighbours


def fit_calibration(store, *, k: int = DEFAULT_K, coverage: float = COVERAGE,
                    max_points: int = 5000, seed: int = 0) -> Calibration:
    """Fit on the store's calibration split. Above `max_points` records a
    seeded subsample is used; the quantile does not need every row."""
    index = store.index()
    Z, M = store.matrix()                       # every key, for the spread
    positions, split_used = calibration_positions(store)
    if positions.size < 3:
        raise ValueError(f"need at least 3 calibration records, have {positions.size}")
    if positions.size > max_points:
        rng = np.random.default_rng(seed)
        positions = np.sort(rng.choice(positions, size=max_points, replace=False))
    k_eff = int(max(1, min(k, positions.size - 1)))
    nearest, neighbours = loo_nearest(index, positions, k=k_eff)
    finite = nearest[np.isfinite(nearest)]
    if finite.size == 0:
        raise ValueError("no calibration record has a comparable neighbour")
    threshold = float(np.quantile(finite, coverage))
    sigma = float(np.median(finite))
    spread = {}
    for j, key in enumerate(store.space.keys):
        devs = []
        for pos, nb in zip(positions, neighbours):
            if not M[pos, j] or nb.size == 0:
                continue
            ok = nb[M[nb, j]]
            if ok.size:
                devs.append(abs(float(np.median(Z[ok, j])) - float(Z[pos, j])))
        spread[key] = round(float(np.median(devs)), 4) if devs else float("nan")
    return Calibration(threshold=threshold, sigma=max(sigma, 1e-6), k=k_eff,
                       coverage=coverage, n=int(positions.size),
                       records_sha256=store.records_sha256(), split_used=split_used,
                       per_key_spread=spread, space_key=space_key(store.space))


def load_or_fit(store, **kwargs) -> tuple[Calibration, list[str]]:
    """The store's saved calibration if it still describes these records
    in this feature space, else a fresh fit (not saved). Flags say which."""
    saved = store.load_calibration()
    if saved is not None:
        cal = Calibration.from_dict(saved)
        if (cal.records_sha256 == store.records_sha256()
                and cal.space_key == space_key(store.space)):
            return cal, []
        return fit_calibration(store, **kwargs), ["calibration_stale_refitted"]
    return fit_calibration(store, **kwargs), ["calibration_fitted_on_the_fly"]
