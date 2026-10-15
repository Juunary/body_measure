"""Surface points for the encoder, sampled outside the network (decision
#19: no neighbour search in the graph). numpy + trimesh only, so the query
side stays torch-free; training uses the same function, so the two frames
cannot drift apart."""
from __future__ import annotations

import numpy as np

N_POINTS = 4096


def normalise(points_mm: np.ndarray) -> np.ndarray:
    """Millimetres in the canonical frame (Y up, floor 0) -> metres,
    centred in x and z. Height is kept: stature is information."""
    p = np.asarray(points_mm, dtype=np.float64) / 1000.0
    p[:, 0] -= p[:, 0].mean()
    p[:, 2] -= p[:, 2].mean()
    return p.astype(np.float32)


def sample_surface(mesh, n: int = N_POINTS, seed: int = 0) -> np.ndarray:
    """Area-uniform points on a canonical mesh, (n, 3) float32 metres."""
    rng = np.random.default_rng(seed)
    areas = mesh.area_faces
    face = rng.choice(len(areas), size=n, p=areas / areas.sum())
    tri = mesh.triangles[face]
    u, v = rng.random(n), rng.random(n)
    flip = u + v > 1.0
    u[flip], v[flip] = 1.0 - u[flip], 1.0 - v[flip]
    pts = tri[:, 0] + u[:, None] * (tri[:, 1] - tri[:, 0]) + v[:, None] * (tri[:, 2] - tri[:, 0])
    return normalise(pts)
