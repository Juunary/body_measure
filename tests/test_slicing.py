"""Slicing behaviour against shapes with analytic truth."""
import numpy as np
import pytest
import trimesh

from body_measure.measure.circumference import measure_circumference, polyline_length
from body_measure.measure.slicing import select_torso_loop, slice_mesh

Z = np.array([0.0, 0.0, 1.0])


def cylinder(radius, height, sections=128):
    return trimesh.creation.cylinder(radius=radius, height=height, sections=sections)


def slice_at_origin(mesh):
    return slice_mesh(mesh, origin=np.zeros(3), normal=Z)


def test_cylinder_slice_matches_2_pi_r_within_a_tenth_of_a_percent():
    radius = 100.0
    loops = slice_at_origin(cylinder(radius, 400.0, sections=256))
    assert len(loops) == 1 and loops[0].closed
    raw = polyline_length(loops[0].points, closed=True)
    assert raw == pytest.approx(2 * np.pi * radius, rel=1e-3)


def test_cylinder_slice_matches_the_inscribed_polygon_exactly():
    radius, sections = 100.0, 64
    loops = slice_at_origin(cylinder(radius, 400.0, sections=sections))
    expected = 2 * sections * radius * np.sin(np.pi / sections)
    raw = polyline_length(loops[0].points, closed=True)
    assert raw == pytest.approx(expected, rel=1e-9)


def test_torso_selection_picks_the_loop_around_the_axis_not_the_biggest_one():
    # torso r=100 on the axis; a BIGGER foreign cylinder r=150 sits at x=400.
    torso = cylinder(100.0, 400.0)
    other = cylinder(150.0, 400.0)
    other.apply_translation([400.0, 0.0, 0.0])
    scene = trimesh.util.concatenate([torso, other])

    loops = slice_at_origin(scene)
    assert len(loops) == 2
    selection = select_torso_loop(loops, axis2d=np.zeros(2))
    assert selection is not None
    assert selection.method == "axis_containment"
    circ = measure_circumference(selection.loop)
    assert circ.selected_value_mm == pytest.approx(2 * np.pi * 100.0, rel=2e-3)


def test_axis_outside_all_loops_falls_back_to_nearest_centroid_with_low_confidence():
    torso = cylinder(100.0, 400.0)
    loops = slice_at_origin(torso)
    selection = select_torso_loop(loops, axis2d=np.array([500.0, 0.0]))
    assert selection is not None
    assert selection.method == "nearest_centroid"
    assert selection.confidence < 0.5
    assert "axis_not_inside_any_loop" in selection.quality_flags


def test_an_open_surface_yields_an_open_loop_report_not_a_crash():
    # single quad strip crossing the plane z=0
    vertices = np.array(
        [[-50.0, 0.0, -50.0], [50.0, 0.0, -50.0], [50.0, 0.0, 50.0], [-50.0, 0.0, 50.0]]
    )
    faces = np.array([[0, 1, 2], [0, 2, 3]])
    strip = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

    loops = slice_at_origin(strip)
    assert len(loops) == 1
    assert not loops[0].closed
    circ = measure_circumference(loops[0])
    assert circ.selected_value_mm is None
    assert "open_loop" in circ.quality_flags
    assert select_torso_loop(loops, axis2d=np.zeros(2)) is None


def test_slice_outside_the_mesh_returns_no_loops():
    loops = slice_mesh(cylinder(100.0, 400.0), origin=np.array([0.0, 0.0, 1000.0]), normal=Z)
    assert loops == []


def test_rigid_transform_leaves_the_selected_circumference_unchanged():
    torso = cylinder(100.0, 400.0)
    arm = cylinder(40.0, 400.0)
    arm.apply_translation([300.0, 0.0, 0.0])
    scene = trimesh.util.concatenate([torso, arm])

    def measure_scene(mesh, origin, normal, axis2d):
        loops = slice_mesh(mesh, origin=origin, normal=normal)
        from body_measure.measure.slicing import project_axis_to_plane  # noqa: PLC0415

        # axis2d here is already in the slice-plane basis for this test setup
        selection = select_torso_loop(loops, axis2d=axis2d)
        return measure_circumference(selection.loop).selected_value_mm

    before = measure_scene(scene, np.zeros(3), Z, np.zeros(2))

    transform = trimesh.transformations.rotation_matrix(0.7, [0.3, 1.0, 0.2])
    transform[:3, 3] = [123.0, -45.0, 67.0]
    moved = scene.copy()
    moved.apply_transform(transform)
    origin = (transform @ np.array([0.0, 0.0, 0.0, 1.0]))[:3]
    normal = transform[:3, :3] @ Z
    after = measure_scene(moved, origin, normal, np.zeros(2))

    assert after == pytest.approx(before, rel=1e-9)


def test_uniform_scale_scales_the_circumference_by_the_same_factor():
    mesh = cylinder(100.0, 400.0)
    base = measure_circumference(slice_at_origin(mesh)[0]).selected_value_mm
    scaled = mesh.copy()
    scaled.apply_scale(1.01)
    after = measure_circumference(slice_at_origin(scaled)[0]).selected_value_mm
    assert after == pytest.approx(base * 1.01, rel=1e-9)


def test_reversed_face_winding_does_not_change_the_measurement():
    mesh = cylinder(100.0, 400.0)
    base = measure_circumference(slice_at_origin(mesh)[0]).selected_value_mm
    inverted = mesh.copy()
    inverted.invert()
    after = measure_circumference(slice_at_origin(inverted)[0]).selected_value_mm
    assert after == pytest.approx(base, rel=1e-9)
