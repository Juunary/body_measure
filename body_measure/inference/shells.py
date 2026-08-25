"""Synthetic clothing shells — the C2 gate battery.

A shell is a surface that encloses a known body at a known distance. The
body's betas are the `synthetic_latent` reference, so a fit can be scored
on recovery rather than on agreement with another estimate.

The battery exists because a single isotropic inflation is too easy: an
optimiser that only penalises the body poking out of the shell will
happily shrink the body to nothing, and a uniform shell never punishes
that. Each case below breaks one assumption a fitter might be leaning on.

Shells are built on SMPL topology by displacing the body's own vertices
along their normals — correspondence is known at generation time and
discarded before the fit sees the shell. Corruptions (holes, decimation,
flipped normals, protrusions) are applied after displacement, so that the
mesh the fitter receives is no longer the clean SMPL surface.

All geometry in millimetres, canonical frame (Y-up, floor 0).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh

_FORWARD = np.array([0.0, 0.0, 1.0])


@dataclass
class ShellCase:
    name: str
    mesh: trimesh.Trimesh
    #: per-body-vertex true gap in mm (before corruption), for reference
    true_gap_mm: np.ndarray
    #: what the fit is being tested on
    breaks: str
    #: expected gap band the fitter is told (d_min, d_max) per part — the
    #: honest prior a real pipeline would get from the gap atlas (C1b)
    gap_band_mm: dict[str, tuple[float, float]]
    meta: dict = field(default_factory=dict)


def _displace(body: trimesh.Trimesh, gap_mm: np.ndarray) -> trimesh.Trimesh:
    vertices = body.vertices + body.vertex_normals * gap_mm[:, None]
    return trimesh.Trimesh(vertices=vertices, faces=body.faces.copy(), process=False)


def _band(lo: float, hi: float) -> dict[str, tuple[float, float]]:
    return {p: (lo, hi) for p in ("torso", "head", "arm", "leg")}


# ----------------------------------------------------------------- cases ---
def identity_shell(body: trimesh.Trimesh, part: np.ndarray) -> ShellCase:
    """Offset 0: the shell IS the body. A fitter that cannot recover the
    body from its own surface has no business being run on a clothed one."""
    gap = np.zeros(len(body.vertices))
    return ShellCase("identity", _displace(body, gap), gap,
                     "nothing — the floor of the battery", _band(0.0, 3.0))


def uniform_shell(body: trimesh.Trimesh, part: np.ndarray, gap_mm: float = 15.0) -> ShellCase:
    gap = np.full(len(body.vertices), gap_mm)
    return ShellCase("uniform_15mm", _displace(body, gap), gap,
                     "the easy case every fitter passes", _band(5.0, 25.0))


def partwise_shell(body: trimesh.Trimesh, part: np.ndarray) -> ShellCase:
    """Jacket over jeans: torso and arms stand off more than legs; the head
    is bare. A single global offset prior is wrong everywhere here."""
    per_part = {"torso": 30.0, "arm": 22.0, "leg": 10.0, "head": 0.0}
    gap = np.array([per_part[p] for p in part])
    band = {"torso": (15.0, 45.0), "arm": (10.0, 35.0), "leg": (3.0, 18.0), "head": (0.0, 4.0)}
    return ShellCase("partwise_jacket_jeans", _displace(body, gap), gap,
                     "a global offset prior", band)


def asymmetric_shell(body: trimesh.Trimesh, part: np.ndarray) -> ShellCase:
    """Open jacket: the front stands off far more than the back. A fitter
    that centres the body inside the shell lands it too far forward."""
    frontness = np.clip(body.vertex_normals @ _FORWARD, 0.0, 1.0)
    torso = part == "torso"
    gap = np.where(torso, 8.0 + 32.0 * frontness, 8.0)
    return ShellCase("front_back_asymmetric", _displace(body, gap), gap,
                     "centring the body inside the shell",
                     {"torso": (5.0, 45.0), "arm": (4.0, 14.0), "leg": (4.0, 14.0), "head": (4.0, 14.0)})


def holed_shell(body: trimesh.Trimesh, part: np.ndarray, rng: np.random.Generator) -> ShellCase:
    """Uniform shell with the holes a real scan has — armpits, crotch,
    under the chin — as removed face patches. Signed distance is unreliable
    at a hole edge; a fitter that trusts every sample falls into them."""
    base = uniform_shell(body, part)
    mesh = base.mesh.copy()
    centres = mesh.triangles_center
    keep = np.ones(len(mesh.faces), dtype=bool)
    height = mesh.bounds[1][1]
    # three patches at plausible hole sites, radius 60 mm
    for target_frac in (0.72, 0.47, 0.86):   # armpit, crotch, chin heights
        level = target_frac * height
        band_faces = np.flatnonzero(np.abs(centres[:, 1] - level) < 40.0)
        if len(band_faces) == 0:
            continue
        seed = band_faces[rng.integers(len(band_faces))]
        d = np.linalg.norm(centres - centres[seed], axis=1)
        keep &= d > 60.0
    mesh.update_faces(keep)
    mesh.remove_unreferenced_vertices()
    return ShellCase("uniform_with_holes", mesh, base.true_gap_mm,
                     "trusting signed distance near hole edges", base.gap_band_mm,
                     {"faces_removed": int((~keep).sum())})


def decimated_shell(body: trimesh.Trimesh, part: np.ndarray, voxel_mm: float = 30.0) -> ShellCase:
    """Uniform shell at coarse resolution — a coarse scanner.

    Decimated by quantising vertices to a voxel grid and re-merging, not
    by trimesh's quadric decimation: that path imports the compiled
    `fast_simplification` extension, which Windows Defender Application
    Control blocks on this machine ("app control policy blocked this
    file") — a system security policy, not a bug to route around with
    admin rights. Quantise-and-merge needs nothing beyond numpy plus the
    welding this project already relies on (canonicalize.py), and produces
    the same thing the test needs: a materially coarser mesh.

    `voxel_mm` has to be read against the source density, not guessed. The
    SMPL shell's median edge is ~18 mm, so the first value tried (6 mm)
    merged almost nothing — 94 % of faces survived and the case silently
    stopped testing resolution at all. 30 mm removes ~62 % of faces, which
    is a coarse scanner rather than a rounding error."""
    base = uniform_shell(body, part)
    quantised = np.round(base.mesh.vertices / voxel_mm) * voxel_mm
    mesh = trimesh.Trimesh(vertices=quantised, faces=base.mesh.faces.copy(), process=False)
    mesh.merge_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    return ShellCase("uniform_decimated", mesh, base.true_gap_mm,
                     "resolution dependence", base.gap_band_mm,
                     {"faces": int(len(mesh.faces)), "voxel_mm": voxel_mm,
                      "faces_before": int(len(base.mesh.faces))})


def flipped_shell(body: trimesh.Trimesh, part: np.ndarray, rng: np.random.Generator,
                  fraction: float = 0.3) -> ShellCase:
    """Uniform shell with a third of its faces wound the wrong way. Any
    sign a fitter reads from normals is wrong there."""
    base = uniform_shell(body, part)
    mesh = base.mesh.copy()
    flip = rng.random(len(mesh.faces)) < fraction
    faces = mesh.faces.copy()
    faces[flip] = faces[flip][:, ::-1]
    mesh = trimesh.Trimesh(vertices=mesh.vertices, faces=faces, process=False)
    return ShellCase("uniform_normals_flipped", mesh, base.true_gap_mm,
                     "sign read from face normals", base.gap_band_mm,
                     {"fraction_flipped": fraction})


def protrusion_shell(body: trimesh.Trimesh, part: np.ndarray) -> ShellCase:
    """Uniform shell plus hair on top and shoes at the feet: surface that
    belongs to no body part and must not pull the body toward it."""
    base = uniform_shell(body, part)
    mesh = base.mesh.copy()
    top = mesh.bounds[1][1]
    head_vertices = mesh.vertices[:, 1] > top - 60.0
    hair = trimesh.creation.icosphere(subdivisions=2, radius=70.0)
    hair.apply_translation(mesh.vertices[head_vertices].mean(axis=0) + np.array([0, 40.0, -15.0]))
    shoe_l = trimesh.creation.box(extents=[110.0, 60.0, 280.0])
    shoe_r = shoe_l.copy()
    feet = mesh.vertices[mesh.vertices[:, 1] < 60.0]
    left_x = feet[feet[:, 0] < 0][:, 0].mean() if (feet[:, 0] < 0).any() else -90.0
    right_x = feet[feet[:, 0] > 0][:, 0].mean() if (feet[:, 0] > 0).any() else 90.0
    shoe_l.apply_translation([left_x, 30.0, feet[:, 2].mean() + 30.0])
    shoe_r.apply_translation([right_x, 30.0, feet[:, 2].mean() + 30.0])
    mesh = trimesh.util.concatenate([mesh, hair, shoe_l, shoe_r])
    return ShellCase("uniform_hair_shoes", mesh, base.true_gap_mm,
                     "surface that belongs to no body part", base.gap_band_mm)


def build_battery(body: trimesh.Trimesh, part_of_vertex: np.ndarray,
                  seed: int) -> list[ShellCase]:
    rng = np.random.default_rng(seed)
    return [
        identity_shell(body, part_of_vertex),
        uniform_shell(body, part_of_vertex),
        partwise_shell(body, part_of_vertex),
        asymmetric_shell(body, part_of_vertex),
        holed_shell(body, part_of_vertex, rng),
        decimated_shell(body, part_of_vertex),
        flipped_shell(body, part_of_vertex, rng),
        protrusion_shell(body, part_of_vertex),
    ]
