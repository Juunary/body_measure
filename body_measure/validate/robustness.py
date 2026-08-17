"""Numerical-robustness battery (category: numerical_robustness).

Perturb a canonical mesh, re-run the full estimated pathway, and report
per-measurement deltas. What each perturbation may claim:

- yaw / translation ("rigid within the canonical frame"): measurements
  must be invariant. Full 3D rotations are NOT tested as an invariance —
  a canonical Y-up standing frame is an input contract, not something the
  pipeline is supposed to survive.
- uniform scale s: every measurement must scale by s (linearity).
- vertex permutation + winding flip: invariant.
- gaussian noise / decimation / subdivision: deltas reported; bounded, not zero.
- waist radial expansion (+r mm over a band): waist girth must INCREASE
  by roughly 2*pi*r — a targeted sanity that the minimum-girth search
  tracks actual geometry (replaces the rejected beta-monotonicity test).
"""
from __future__ import annotations

from collections.abc import Callable

import numpy as np
import trimesh

from ..measure.measurements import run_estimated_measurements


def measure_all(mesh: trimesh.Trimesh) -> dict[str, float | None]:
    measurements, _ = run_estimated_measurements(mesh)
    return {name: value.selected_value_mm for name, value in measurements.items()}


def yaw_and_translate(mesh: trimesh.Trimesh, angle_rad: float = 0.6) -> trimesh.Trimesh:
    out = mesh.copy()
    out.apply_transform(trimesh.transformations.rotation_matrix(angle_rad, [0, 1, 0]))
    out.apply_translation([137.0, 0.0, -89.0])
    return out


def uniform_scale(mesh: trimesh.Trimesh, factor: float = 1.01) -> trimesh.Trimesh:
    out = mesh.copy()
    out.apply_scale(factor)
    return out


def permute_and_flip(mesh: trimesh.Trimesh, seed: int = 7) -> trimesh.Trimesh:
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(mesh.vertices))
    inverse = np.empty_like(perm)
    inverse[perm] = np.arange(len(perm))
    faces = inverse[mesh.faces][:, ::-1]  # remap + flip winding
    return trimesh.Trimesh(vertices=mesh.vertices[perm], faces=faces, process=False)


def gaussian_noise(mesh: trimesh.Trimesh, sigma_mm: float = 1.0, seed: int = 11) -> trimesh.Trimesh:
    rng = np.random.default_rng(seed)
    return trimesh.Trimesh(
        vertices=mesh.vertices + rng.normal(0.0, sigma_mm, mesh.vertices.shape),
        faces=mesh.faces.copy(),
        process=False,
    )


def decimate(mesh: trimesh.Trimesh, keep: float) -> trimesh.Trimesh:
    import fast_simplification

    vertices, faces = fast_simplification.simplify(
        mesh.vertices.astype(np.float32), mesh.faces.astype(np.int64), 1.0 - keep
    )
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def subdivide(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    return mesh.subdivide()


def expand_waist(mesh: trimesh.Trimesh, waist_y: float, delta_mm: float = 10.0,
                 band_mm: float = 40.0) -> trimesh.Trimesh:
    vertices = mesh.vertices.copy()
    center = np.array([vertices[:, 0].mean(), vertices[:, 2].mean()])
    dy = np.abs(vertices[:, 1] - waist_y)
    weight = np.clip(1.0 - dy / band_mm, 0.0, 1.0)  # linear falloff
    radial = vertices[:, [0, 2]] - center
    norm = np.linalg.norm(radial, axis=1, keepdims=True)
    norm[norm < 1e-9] = 1.0
    vertices[:, [0, 2]] += radial / norm * (delta_mm * weight)[:, None]
    return trimesh.Trimesh(vertices=vertices, faces=mesh.faces.copy(), process=False)


PERTURBATIONS: dict[str, Callable[[trimesh.Trimesh], trimesh.Trimesh]] = {
    "yaw_translate": yaw_and_translate,
    "scale_1.01": uniform_scale,
    "permute_flip": permute_and_flip,
    "noise_1mm": gaussian_noise,
    "decimate_50": lambda m: decimate(m, 0.5),
    "decimate_25": lambda m: decimate(m, 0.25),
    "subdivide": subdivide,
}


def run_battery(mesh: trimesh.Trimesh, *, skip: set[str] = frozenset()) -> dict:
    """Returns {perturbation: {measurement: delta_mm}} plus 'baseline'."""
    baseline = measure_all(mesh)
    results: dict = {"baseline": baseline}
    for name, perturb in PERTURBATIONS.items():
        if name in skip:
            continue
        values = measure_all(perturb(mesh))
        expected_scale = 1.01 if name == "scale_1.01" else 1.0
        results[name] = {
            key: (values[key] - baseline[key] * expected_scale)
            if values.get(key) is not None and baseline.get(key) is not None
            else None
            for key in baseline
        }
    return results
