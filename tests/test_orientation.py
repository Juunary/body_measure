"""Front/back orientation: 180-degree ambiguity handling and propagation
into orientation-dependent measurements (spec `requires`). Gated on the
generated SMPL A-pose body."""
from pathlib import Path

import numpy as np
import pytest
import trimesh

from body_measure.adapters.mesh_file import MeshFileAdapter
from body_measure.canonicalize import canonicalize
from body_measure.landmarks.estimated import estimate_facing
from body_measure.measure.measurements import run_estimated_measurements
from body_measure.spec import load_spec

SMPL_OBJ = (
    Path(__file__).resolve().parents[1] / "data" / "generated" / "smpl_neutral0_apose.obj"
)

pytestmark = pytest.mark.skipif(not SMPL_OBJ.exists(), reason="generated SMPL body absent")

ORIENTATION_DEPENDENT = ("across_back_shoulder_width", "sleeve_length", "back_length")


@pytest.fixture(scope="module")
def mesh():
    return canonicalize(MeshFileAdapter().load(SMPL_OBJ, unit="m"))


def test_the_spec_declares_orientation_dependencies():
    spec = load_spec()
    for name in ORIENTATION_DEPENDENT:
        assert "front_back_orientation" in spec.measurements[name].requires


def test_facing_reports_direction_confidence_and_method(mesh):
    facing = estimate_facing(mesh)
    assert facing.method == "toe_projection"
    assert 0.0 <= facing.confidence <= 1.0
    assert abs(np.linalg.norm(facing.direction) - 1.0) < 1e-9


def test_missing_feet_null_all_orientation_dependent_measurements(mesh):
    cropped = mesh.copy()
    height = cropped.bounds[1][1]
    keep = cropped.vertices[:, 1] > 0.06 * height  # cut the feet away
    mask = keep[cropped.faces].all(axis=1)
    no_feet = trimesh.Trimesh(
        vertices=cropped.vertices, faces=cropped.faces[mask], process=False
    )
    facing = estimate_facing(no_feet)
    assert "orientation_unknown" in facing.flags
    assert facing.confidence == 0.0

    measurements, _ = run_estimated_measurements(no_feet)
    for name in ORIENTATION_DEPENDENT:
        assert measurements[name].selected_value_mm is None, name
        assert "orientation_unknown" in measurements[name].quality, name
    # circumferences do not require orientation and must survive
    assert measurements["waist_circumference"].selected_value_mm is not None


def test_180_degree_yaw_gives_the_same_back_length(mesh):
    base, _ = run_estimated_measurements(mesh)
    rotated = mesh.copy()
    rotated.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [0, 1, 0]))
    turned, _ = run_estimated_measurements(rotated)
    for name in ("back_length", "waist_circumference", "chest_circumference"):
        a, b = base[name].selected_value_mm, turned[name].selected_value_mm
        assert a is not None and b is not None, name
        assert b == pytest.approx(a, abs=1.0), name


def test_mirror_reflection_leaves_circumferences_unchanged(mesh):
    mirrored = trimesh.Trimesh(
        vertices=mesh.vertices * np.array([-1.0, 1.0, 1.0]),
        faces=mesh.faces[:, ::-1],  # restore winding
        process=False,
    )
    base, _ = run_estimated_measurements(mesh)
    refl, _ = run_estimated_measurements(mirrored)
    for name in ("waist_circumference", "chest_circumference", "neck_circumference"):
        assert refl[name].selected_value_mm == pytest.approx(
            base[name].selected_value_mm, abs=1.0
        ), name


def test_single_arm_body_propagates_the_pca_fallback_flag(mesh):
    # remove everything on the +x side above the hip that is far from the
    # body axis: crude one-arm amputation
    height = mesh.bounds[1][1]
    vertices = mesh.vertices
    arm_side = (
        (vertices[:, 0] > 120.0)
        & (vertices[:, 1] > 0.55 * height)
        & (vertices[:, 1] < 0.95 * height)
    )
    mask = ~arm_side[mesh.faces].any(axis=1)
    one_arm = trimesh.Trimesh(vertices=vertices, faces=mesh.faces[mask], process=False)
    measurements, _ = run_estimated_measurements(one_arm)
    chest = measurements["chest_circumference"]
    if chest.selected_value_mm is not None:
        assert (
            "lateral_axis_pca_fallback" in chest.quality
            or "armpit_not_detected_window_is_stature_relative" in chest.quality
        )


def test_a_provided_facing_is_used_and_recorded_not_estimated():
    """A body model's frame defines its front; the core must take that as
    given (flagged as such) instead of estimating it from the feet."""
    import numpy as np
    import trimesh

    from body_measure.landmarks.estimated import provided_facing

    facing = provided_facing((0.0, 1.0), source="smpl_frame")
    assert facing.confidence == 1.0
    assert facing.flags == ["orientation_provided"]
    assert facing.method == "provided_by_smpl_frame"
    assert np.allclose(facing.direction, [0.0, 1.0])
    # direction is normalised, zero is refused
    assert np.allclose(provided_facing((0.0, 3.0), source="x").direction, [0.0, 1.0])
    import pytest
    with pytest.raises(ValueError):
        provided_facing((0.0, 0.0), source="x")
