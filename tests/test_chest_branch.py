"""The chest profile must be measured one way, not two.

Two methods produce a chest sample — the torso loop measured directly
when the arms are their own loops, and the merged loop clipped at the
armpit's lateral extent when they are not. They measure different things,
so a max taken across a mixture answers "which method returned the
larger number", not "where is the chest". Decision #22 forbade exactly
this for the waist; these tests hold the same line for the chest."""
import numpy as np
import pytest

from body_measure.measure.measurements import _merge_index

from tests.test_hsrd_clothed import HSRD_ROOT, needs_hsrd


# ----------------------------------------------------- the merge split ---
def test_a_clean_profile_splits_where_it_flips():
    # arms separate below, merged above — the shape every unclothed body
    # in the Texel set actually has
    assert _merge_index([True, True, True, False, False]) == 3
    assert _merge_index([True, False]) == 1


def test_arms_never_merging_means_no_clipping():
    assert _merge_index([True, True, True]) == 3   # == len: clip nothing


def test_arms_merged_throughout_clips_everything():
    assert _merge_index([False, False, False]) == 0


def test_an_empty_profile_is_handled():
    assert _merge_index([]) == 0


def test_a_noisy_profile_still_yields_one_split():
    # a jacket sleeve touching and leaving the torso: the split is the
    # least-wrong single flip, and it is always a single flip
    noisy = [True, False, True, True, False, False, False]
    index = _merge_index(noisy)
    assert 0 <= index <= len(noisy)
    # by construction the result maximises agreement with "separate below,
    # merged above" — no other split can score higher
    def score(i):
        return sum(noisy[:i]) + sum(1 for v in noisy[i:] if not v)
    assert score(index) == max(score(i) for i in range(len(noisy) + 1))


# --------------------------------------------------------- HSRD gates ---
@needs_hsrd
def test_a_jacket_flags_its_unstable_arm_merge():
    """HSRD's raw sequence flips eight times at both LODs — the sleeve
    touches and leaves the torso as the triangulation falls. The number
    may still be produced, but it may not present as clean."""
    from body_measure.adapters.hsrd import HsrdAdapter
    from body_measure.canonicalize import canonicalize
    from body_measure.measure.measurements import run_estimated_measurements
    from body_measure.validate.stats import quality_bucket

    adapter = HsrdAdapter(HSRD_ROOT)
    for observation in adapter.observations():
        mesh = canonicalize(adapter.load(observation))
        measurements, _ = run_estimated_measurements(mesh)
        chest = measurements["chest_circumference"]
        assert chest.selected_value_mm is not None
        assert "arm_merge_height_unstable" in chest.quality
        assert quality_bucket(chest) != "clean"


@needs_hsrd
def test_an_untrusted_armpit_disables_clipping_rather_than_using_bad_bounds():
    """lod2's armpit is confidence 0.4 and gave a 289 mm clip window
    against lod1's 420 mm. Bounds that wrong must not be used at all."""
    from body_measure.adapters.hsrd import HsrdAdapter
    from body_measure.canonicalize import canonicalize
    from body_measure.landmarks.estimated import estimate_armpit_level
    from body_measure.measure.measurements import run_estimated_measurements

    adapter = HsrdAdapter(HSRD_ROOT)
    seen = 0
    for observation in adapter.observations():
        mesh = canonicalize(adapter.load(observation))
        armpit = estimate_armpit_level(mesh)
        if armpit is None or armpit.confidence >= 0.5:
            continue
        measurements, _ = run_estimated_measurements(mesh)
        chest = measurements["chest_circumference"]
        assert "clip_bounds_untrusted_low_confidence_armpit" in chest.quality
        assert "arm_clipped_at_merged_level" not in chest.quality
        seen += 1
    assert seen > 0, "expected at least one low-confidence armpit in HSRD"


# ------------------------------------- the girth profile's own tier gate ---
def _barrel_with_bridged_slice(radius=150.0, height=600.0, rings=40, sections=64):
    """A barrel with a wedge of surface missing in one narrow height band.
    The slice there is an open loop whose closing chord is large enough to
    be judged manual_review — not clean, not rejected outright."""
    import trimesh

    ys = np.linspace(0.0, height, rings)
    th = np.linspace(0.0, 2 * np.pi, sections, endpoint=False)
    vertices = np.array(
        [[radius * np.cos(t), y, radius * np.sin(t)] for y in ys for t in th]
    )
    faces = []
    for i in range(rings - 1):
        for j in range(sections):
            a, b = i * sections + j, i * sections + (j + 1) % sections
            faces += [[a, b, b + sections], [a, b + sections, a + sections]]
    mesh = trimesh.Trimesh(vertices=vertices, faces=np.array(faces), process=False)
    centres = mesh.triangles_center
    angle = np.arctan2(centres[:, 2], centres[:, 0])
    cut = (np.abs(centres[:, 1] - 300.0) < 20.0) & (np.abs(angle) < 0.40)
    mesh.update_faces(~cut)
    mesh.remove_unreferenced_vertices()
    return mesh


def test_a_manual_review_slice_never_reaches_a_girth_extremum():
    """A manual_review slice is one the gap-closure tier already judged too
    bridged to stand alone; letting it into an argmin makes that judgement
    on its behalf. On NOMO male_0001 such a slice — 15.5% of its loop
    replaced by a closing chord — won the waist with a 675mm girth on a
    1725mm subject."""
    from body_measure.canonicalize import body_axis_point
    from body_measure.landmarks.estimated import torso_girth_profile
    from body_measure.measure.slicing import (
        project_axis_to_plane,
        select_torso_loop,
        slice_mesh,
    )

    mesh = _barrel_with_bridged_slice()
    up = np.array([0.0, 1.0, 0.0])
    origin = np.array([0.0, 300.0, 0.0])
    selection = select_torso_loop(
        slice_mesh(mesh, origin, up),
        project_axis_to_plane(body_axis_point(mesh), origin, up),
    )
    # the fixture is only meaningful if it really is the middle tier
    assert selection.disposition == "manual_review"
    assert not selection.loop.closed

    heights = [round(h) for h, _ in torso_girth_profile(mesh, 200.0, 400.0, 20.0)]
    # the wedge spans y 280-320, so those three slices are bridged and go
    assert not {280, 300, 320} & set(heights)
    # and nothing outside the damaged band is touched
    assert {200, 220, 240, 260, 340, 360, 380, 400} <= set(heights)


def test_an_intact_barrel_keeps_every_slice():
    """The gate removes bridged slices, not slices in general."""
    import trimesh

    from body_measure.landmarks.estimated import torso_girth_profile

    ys = np.linspace(0.0, 600.0, 40)
    th = np.linspace(0.0, 2 * np.pi, 64, endpoint=False)
    vertices = np.array(
        [[150.0 * np.cos(t), y, 150.0 * np.sin(t)] for y in ys for t in th]
    )
    faces = []
    for i in range(39):
        for j in range(64):
            a, b = i * 64 + j, i * 64 + (j + 1) % 64
            faces += [[a, b, b + 64], [a, b + 64, a + 64]]
    intact = trimesh.Trimesh(vertices=vertices, faces=np.array(faces), process=False)

    heights = [round(h) for h, _ in torso_girth_profile(intact, 200.0, 400.0, 20.0)]
    assert 300 in heights
    damaged = [round(h) for h, _ in torso_girth_profile(
        _barrel_with_bridged_slice(), 200.0, 400.0, 20.0)]
    assert len(heights) == len(damaged) + 3
