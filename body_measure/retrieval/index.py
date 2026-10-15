"""Nearest neighbours by masked standardised distance.

Brute force on purpose: a store of tens of thousands of 13-vectors is a
few megabytes, and one query is a single vectorised pass. The distance
is taken over the keys BOTH sides have, divided by how many there were,
so a scan missing its sleeve is compared on what it does have instead of
on a guessed sleeve. A pair sharing fewer than `min_shared` keys is not
comparable at all (infinite distance)."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np

MIN_SHARED_KEYS = 4


class BruteForceIndex:
    def __init__(self, Z: np.ndarray, mask: np.ndarray, ids: Sequence[str], *,
                 min_shared: int = MIN_SHARED_KEYS):
        Z = np.asarray(Z, dtype=np.float64)
        mask = np.asarray(mask, dtype=bool)
        if Z.ndim != 2 or Z.shape != mask.shape or Z.shape[0] != len(ids):
            raise ValueError("Z, mask and ids disagree in shape")
        self.Z = np.where(mask, Z, 0.0)
        self.mask = mask
        self.ids = tuple(ids)
        self._pos = {rid: i for i, rid in enumerate(self.ids)}
        self.min_shared = min_shared

    def __len__(self) -> int:
        return len(self.ids)

    @property
    def dim(self) -> int:
        return self.Z.shape[1]

    def position(self, record_id: str) -> int:
        return self._pos[record_id]

    def distances(self, z: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(distance, n_shared) to every row; inf where too few keys are shared."""
        z = np.asarray(z, dtype=np.float64)
        q = np.asarray(mask, dtype=bool)
        shared = self.mask & q[None, :]
        n_shared = shared.sum(axis=1)
        diff = np.where(shared, self.Z - z[None, :], 0.0)
        d = np.sqrt((diff * diff).sum(axis=1) / np.maximum(n_shared, 1))
        d = np.where(n_shared >= self.min_shared, d, np.inf)
        return d, n_shared

    def query(self, z: np.ndarray, mask: np.ndarray, k: int, *,
              exclude: Iterable[str | int] = ()) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The up-to-k nearest comparable rows as (positions, distances,
        n_shared), nearest first. Fewer than k when fewer are comparable."""
        d, n_shared = self.distances(z, mask)
        for item in exclude:
            pos = int(item) if isinstance(item, (int, np.integer)) else self._pos.get(item)
            if pos is not None:
                d[pos] = np.inf
        finite = np.flatnonzero(np.isfinite(d))
        if finite.size == 0:
            empty = np.array([], dtype=int)
            return empty, np.array([]), empty
        k = max(0, min(int(k), finite.size))
        order = finite[np.argsort(d[finite], kind="stable")[:k]]
        return order, d[order], n_shared[order]
