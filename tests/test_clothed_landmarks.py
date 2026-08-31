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
        waist = estimate_waist_level(mesh, estimate_armpit_level(mesh))
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
        waist = estimate_waist_level(mesh, estimate_armpit_level(mesh))
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


# ------------------------------------------- the shoulder station (#32) ---
_SMPL_OBJ = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "data" / "generated" / "smpl_neutral0_apose.obj"
)
needs_smpl = pytest.mark.skipif(
    not _SMPL_OBJ.exists(), reason="generated SMPL body absent")


@pytest.fixture(scope="module")
def smpl_body():
    from body_measure.adapters.mesh_file import MeshFileAdapter

    return canonicalize(MeshFileAdapter().load(_SMPL_OBJ, unit="m"))


@needs_smpl
def test_the_shoulder_station_comes_from_the_crease_and_is_not_searched(smpl_body):
    """The shoulder ridge declines monotonically from the neck out to the
    arm, so an argmax over height inside a lateral window returns the
    window's medial edge rather than the shoulder. The lateral station is
    therefore fixed by the armpit crease (decision #32)."""
    from body_measure.landmarks.estimated import (
        SHOULDER_SLAB_HALF_MM, _torso_loop_at, body_lateral_axis)

    armpit = estimate_armpit_level(smpl_body)
    assert armpit is not None
    armpit_y = float(armpit.position_mm[1])
    left, right = estimate_shoulder_points(smpl_body, armpit)

    _, selection = _torso_loop_at(smpl_body, armpit_y)
    lateral, _ = body_lateral_axis(smpl_body, armpit_y)
    t_loop = selection.loop.points[:, [0, 2]] @ lateral
    for landmark, crease_t in ((left, t_loop.min()), (right, t_loop.max())):
        t = float(landmark.position_mm[[0, 2]] @ lateral)
        assert abs(t - float(crease_t)) <= SHOULDER_SLAB_HALF_MM, (
            f"{landmark.name} drifted {t - float(crease_t):+.1f} mm off the "
            "crease station")


def _ring_stack(radius=150.0, height=1600.0, step=4.0, sections=48):
    """A vertical tube whose surface never stops rising, sampled finely
    enough that the search ceiling — not the vertex spacing — is what the
    top point lands on."""
    ys = np.arange(0.0, height + step, step)
    angles = np.linspace(0.0, 2.0 * np.pi, sections, endpoint=False)
    ring = np.stack([radius * np.cos(angles), np.zeros_like(angles),
                     radius * np.sin(angles)], axis=1)
    vertices = np.vstack([ring + np.array([0.0, y, 0.0]) for y in ys])
    faces = []
    for i in range(len(ys) - 1):
        lower, upper = i * sections, (i + 1) * sections
        for j in range(sections):
            k = (j + 1) % sections
            faces += [[lower + j, lower + k, upper + k],
                      [lower + j, upper + k, upper + j]]
    return trimesh.Trimesh(vertices=vertices, faces=np.array(faces),
                           process=False)


def test_a_shoulder_pinned_to_the_search_ceiling_says_so():
    """A ceiling that cuts a still-rising surface returns the window's lid.
    Hair does this, and so does a raised arm; the value must not pass as a
    shoulder just because an argmax returned something."""
    from body_measure.landmarks.estimated import Landmark

    mesh = _ring_stack()
    height = float(mesh.bounds[1][1])
    armpit = Landmark("armpit_level", np.array([0.0, 0.40 * height, 0.0]),
                      0.9, "test_fixture", [])
    shoulders = estimate_shoulder_points(mesh, armpit)
    assert shoulders is not None
    for landmark in shoulders:
        assert "shoulder_at_search_ceiling" in landmark.quality_flags


@needs_smpl
def test_a_real_shoulder_is_not_flagged_as_hitting_the_ceiling(smpl_body):
    """The counterpart: on a body whose shoulder the window comfortably
    contains, the flag must stay off, or it says nothing."""
    armpit = estimate_armpit_level(smpl_body)
    for landmark in estimate_shoulder_points(smpl_body, armpit):
        assert "shoulder_at_search_ceiling" not in landmark.quality_flags


@needs_smpl
def test_the_ceiling_flag_sends_the_width_to_manual_review(smpl_body):
    """The flag is only worth having if it reaches the disposition."""
    from body_measure.measure.measurements import _PATH_NOT_TRUSTED

    assert "shoulder_at_search_ceiling" in _PATH_NOT_TRUSTED
    value = _length_value(400.0, ["shoulder_at_search_ceiling"], "surface_path")
    assert value.disposition == "manual_review"
