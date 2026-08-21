"""W1 — landmark trust on clothed scans.

The connectivity fix (decision #21) made clothed surfaces walkable and
thereby exposed that the landmarks were wrong: a jacket-fold loop won the
waist minimum through the nearest-centroid fallback, the "back" point of
that fold sat 104 degrees off the back, and one "shoulder" was a collar.
The common rule under all three fixes: a fallback loop selection may feed
a girth measurement (flagged), but it may not anchor a landmark."""
import numpy as np
import pytest
import trimesh

from body_measure.canonicalize import canonicalize
from body_measure.landmarks.estimated import (
    estimate_armpit_level,
    estimate_back_point_at,
    estimate_shoulder_points,
    torso_girth_profile,
)
from body_measure.measure.measurements import _length_value

from tests.test_hsrd_clothed import HSRD_ROOT, needs_hsrd
from body_measure.adapters.hsrd import HsrdAdapter


# ---------------------------------------------------------- unit tests ---
def _torso_with_ring_above():
    """A dense body-axis cylinder (y 0..400) with a light closed ring
    floating off-axis ABOVE it (y ~448..456). Slices through the torso are
    trustworthy; slices through the ring alone can only ever be selected
    by the nearest-centroid fallback, because the global axis point stays
    under the torso, far outside the ring."""
    torso = trimesh.creation.cylinder(radius=150.0, height=400.0, sections=96)
    torso.apply_translation([0.0, 0.0, 200.0])
    ring = trimesh.creation.annulus(r_min=20.0, r_max=22.0, height=8.0, sections=8)
    ring.apply_translation([250.0, 0.0, 452.0])
    mesh = trimesh.util.concatenate([torso, ring])
    mesh.apply_transform(
        np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]], dtype=float)
    )
    mesh.apply_translation([0.0, -mesh.bounds[0][1], 0.0])
    return mesh


def test_girth_profile_never_uses_a_fallback_loop():
    mesh = _torso_with_ring_above()
    profile = torso_girth_profile(mesh, 50.0, 460.0, 25.0)
    girths = [g for _, g in profile]
    assert girths, "profile must not be empty"
    # the torso is ~942 mm around; the floating ring is ~130 mm. If the
    # fallback ever feeds the profile, the minimum collapses to the ring.
    assert min(girths) > 800.0
    # and the ring-only heights were skipped, not measured
    assert max(h for h, _ in profile) < 410.0


def test_back_point_refuses_a_fallback_loop():
    mesh = _torso_with_ring_above()
    # at the ring's height the only loops do not contain the body axis,
    # so selection is nearest-centroid — and a back point on a guessed
    # loop can face anywhere (it was 104 degrees off on HSRD)
    point = estimate_back_point_at(
        mesh, 452.0, np.array([0.0, 1.0]), "back_test_point"
    )
    assert point is None
    # sanity: at torso height the same call succeeds
    assert estimate_back_point_at(
        mesh, 200.0, np.array([0.0, 1.0]), "back_test_point"
    ) is not None


def test_asymmetric_shoulders_are_never_accepted():
    value = _length_value(500.0, ["shoulder_vertical_asymmetry"], "m")
    assert value.disposition == "manual_review"
    assert value.selected_value_mm == 500.0  # the number survives, demoted


# ------------------------------------------------------------ HSRD gates ---
@needs_hsrd
def test_clothed_waist_is_no_longer_a_jacket_fold():
    """Before the trust fix, lod2's waist minimum was a 140.9 mm fold loop
    selected by the fallback at one specific height. The two LODs now have
    to agree on the waist within a few mm, like any two resolutions of the
    same surface should."""
    from body_measure.landmarks.estimated import estimate_waist_level

    adapter = HsrdAdapter(HSRD_ROOT)
    levels = {}
    for observation in adapter.observations():
        mesh = canonicalize(adapter.load(observation))
        waist = estimate_waist_level(mesh)
        assert waist is not None
        height = float(mesh.bounds[1][1])
        fraction = float(waist.position_mm[1]) / height
        assert 0.40 < fraction < 0.80
        levels[observation.name] = float(waist.position_mm[1])
    assert max(levels.values()) - min(levels.values()) < 20.0


@needs_hsrd
def test_clothed_back_point_is_actually_on_the_back():
    from body_measure.canonicalize import body_axis_point
    from body_measure.landmarks.estimated import (
        estimate_facing,
        estimate_waist_level,
    )

    adapter = HsrdAdapter(HSRD_ROOT)
    for observation in adapter.observations():
        mesh = canonicalize(adapter.load(observation))
        facing = estimate_facing(mesh)
        waist = estimate_waist_level(mesh)
        point = estimate_back_point_at(
            mesh, float(waist.position_mm[1]), facing.direction, "back_waist_point"
        )
        assert point is not None
        axis = body_axis_point(mesh)
        radial = point.position_mm[[0, 2]] - axis
        backness = -(radial @ facing.direction) / max(np.linalg.norm(radial), 1e-9)
        assert backness > 0.8  # was -0.25 on lod2 before the fix


@needs_hsrd
def test_collar_shoulders_carry_the_asymmetry_flag():
    adapter = HsrdAdapter(HSRD_ROOT)
    checked = 0
    for observation in adapter.observations():
        mesh = canonicalize(adapter.load(observation))
        armpit = estimate_armpit_level(mesh)
        if armpit is None:
            continue
        shoulders = estimate_shoulder_points(mesh, armpit)
        if shoulders is None:
            continue
        left, right = shoulders
        dy = abs(float(left.position_mm[1]) - float(right.position_mm[1]))
        flagged = "shoulder_vertical_asymmetry" in left.quality_flags
        # the flag and the geometry must agree, in both directions
        assert flagged == (dy > 0.05 * float(mesh.bounds[1][1]))
        checked += 1
    assert checked > 0
