"""The two back points share one midline, and the length between them is
the plane section through it (decision #48).

The old placement — most-backward point of the torso loop — was an argmax
over a nearly flat surface, so it held at the nape and slid at the waist:
26 to 89 mm apart across this project's data. A path between two points
that are not on the same vertical line runs diagonally and reads long, so
the agreement of their lateral coordinates is the invariant, not a
by-product.
"""
from pathlib import Path

import numpy as np
import pytest

from body_measure.adapters.mesh_file import MeshFileAdapter
from body_measure.canonicalize import body_axis_point, canonicalize
from body_measure.landmarks.estimated import sagittal_normal
from body_measure.measure.measurements import run_estimated_measurements
from body_measure.measure.surface_path import SECTION_METHOD, plane_section_arc_mm

SMPL_OBJ = (
    Path(__file__).resolve().parents[1] / "data" / "generated" / "smpl_neutral0_apose.obj"
)

pytestmark = pytest.mark.skipif(not SMPL_OBJ.exists(), reason="generated SMPL body absent")

#: How far apart the two points' lateral coordinates may sit. Both are
#: crossings of the same plane, so the only thing between them is the
#: interpolation on the crossing segment — a fraction of an edge.
MAX_MIDLINE_GAP_MM = 2.0


@pytest.fixture(scope="module")
def measured():
    mesh = canonicalize(MeshFileAdapter().load(SMPL_OBJ, unit="m"))
    measurements, landmarks = run_estimated_measurements(mesh)
    return mesh, measurements, landmarks


def _lateral(point_mm, mesh, facing) -> float:
    """Coordinate across the facing direction, from the body axis."""
    axis = body_axis_point(mesh)
    normal = sagittal_normal(facing.direction)
    return float((np.asarray(point_mm) - np.array([axis[0], 0.0, axis[1]])) @ normal)


def test_both_back_points_sit_on_the_same_midline(measured):
    mesh, _, landmarks = measured
    facing = landmarks["facing"]
    neck = _lateral(landmarks["back_neck_point"].position_mm, mesh, facing)
    waist = _lateral(landmarks["back_waist_point"].position_mm, mesh, facing)
    assert abs(neck - waist) <= MAX_MIDLINE_GAP_MM, (neck, waist)


def test_the_back_points_are_crossings_not_extrema(measured):
    _, _, landmarks = measured
    for key in ("back_neck_point", "back_waist_point"):
        assert landmarks[key].method == "midline_crossing_behind_body_axis", key
        assert "midline_crossing_not_found" not in landmarks[key].quality_flags, key


def test_back_length_is_the_section_the_spec_declares(measured):
    _, measurements, _ = measured
    value = measurements["back_length"]
    assert value.selected_value_mm is not None
    assert value.method == SECTION_METHOD


def test_the_section_arc_is_shorter_than_the_edge_graph_walk(measured):
    """The staircase is the thing being removed, so it must come off."""
    from body_measure.measure.surface_path import EdgeGraph, surface_path_length_mm

    mesh, _, landmarks = measured
    a = landmarks["back_neck_point"].position_mm
    b = landmarks["back_waist_point"].position_mm
    arc, points, _ = plane_section_arc_mm(mesh, a, b, sagittal_normal(landmarks["facing"].direction))
    walk, _ = surface_path_length_mm(EdgeGraph(mesh), [a, b])
    assert arc is not None and walk is not None
    assert arc < walk
    # and it is still a surface path, not the chord
    assert arc > float(np.linalg.norm(np.asarray(a) - np.asarray(b)))
    assert len(points) > 2
