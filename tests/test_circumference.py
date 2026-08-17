"""Circumference invariants: hull <= raw, ellipse vs Ramanujan."""
import numpy as np
import pytest
import trimesh
from shapely.geometry import Polygon

from body_measure.measure.circumference import hull_perimeter, measure_circumference
from body_measure.measure.slicing import slice_mesh

Z = np.array([0.0, 0.0, 1.0])


def _slice_one(mesh):
    loops = slice_mesh(mesh, origin=np.zeros(3), normal=Z)
    assert len(loops) == 1
    return loops[0]


def test_hull_perimeter_is_never_longer_than_the_raw_contour():
    # star-shaped (concave) prism: hull bridges the concavities
    angles = np.linspace(0, 2 * np.pi, 20, endpoint=False)
    radii = np.where(np.arange(20) % 2 == 0, 120.0, 70.0)
    outline = np.column_stack([radii * np.cos(angles), radii * np.sin(angles)])
    prism = trimesh.creation.extrude_polygon(Polygon(outline), height=100.0)
    prism.apply_translation([0.0, 0.0, -50.0])

    circ = measure_circumference(_slice_one(prism))
    assert circ.taut_tape_hull_mm is not None
    assert circ.taut_tape_hull_mm <= circ.raw_contour_mm + 1e-9


def test_convex_cylinder_hull_equals_raw_contour():
    circ = measure_circumference(
        _slice_one(trimesh.creation.cylinder(radius=100.0, height=200.0, sections=128))
    )
    assert circ.taut_tape_hull_mm == pytest.approx(circ.raw_contour_mm, rel=1e-9)


def test_ellipse_hull_matches_ramanujan_approximation():
    a, b = 200.0, 100.0
    mesh = trimesh.creation.cylinder(radius=1.0, height=200.0, sections=512)
    mesh.apply_scale([a, b, 1.0])
    circ = measure_circumference(_slice_one(mesh))
    ramanujan = np.pi * (3 * (a + b) - np.sqrt((3 * a + b) * (a + 3 * b)))
    assert circ.taut_tape_hull_mm == pytest.approx(ramanujan, rel=5e-3)


def test_collinear_points_report_a_degenerate_hull_instead_of_a_number():
    assert hull_perimeter(np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])) is None
