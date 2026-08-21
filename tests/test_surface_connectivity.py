"""A surface path can fail in three different ways and they must not look
alike: the mesh is shattered into duplicate indices (repairable — weld
it), a landmark sits on a stray fragment (repairable — pin it, within
limits), or the path walks around the body because the landmarks are
wrong (not repairable here — say so and refuse to call it accepted)."""
import numpy as np
import trimesh

from body_measure.adapters.base import NormalizedBodySurface
from body_measure.canonicalize import canonicalize
from body_measure.measure.measurements import _length_value
from body_measure.measure.surface_path import (
    MAX_PATH_CHORD_RATIO,
    MAX_WAYPOINT_SNAP_MM,
    EdgeGraph,
    surface_path_length_mm,
)


def _surface(vertices, faces):
    return NormalizedBodySurface(
        vertices_mm=np.asarray(vertices, dtype=np.float64),
        faces=np.asarray(faces, dtype=np.int64),
        source_type="mesh_file",
        source_id="test",
    )


def _components(mesh):
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    e = mesh.edges_unique
    n = len(mesh.vertices)
    g = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
    return connected_components(g, directed=False)[0]


# ------------------------------------------------------------- welding ---
# two triangles forming a square, sharing an edge geometrically but not by
# index — exactly what a texture-chart split does to a photogrammetry OBJ
_SPLIT_QUAD_V = [[0, 0, 0], [10, 0, 0], [0, 0, 10],
                 [10, 0, 0], [10, 0, 10], [0, 0, 10]]
_SPLIT_QUAD_F = [[0, 1, 2], [3, 4, 5]]


def test_canonicalize_welds_duplicate_position_vertices():
    mesh = canonicalize(_surface(_SPLIT_QUAD_V, _SPLIT_QUAD_F))
    assert mesh.metadata["weld"]["merged"] == 2
    assert len(mesh.vertices) == 4
    assert _components(mesh) == 1


def test_welding_leaves_geometry_untouched():
    split = canonicalize(_surface(_SPLIT_QUAD_V, _SPLIT_QUAD_F))
    unwelded = canonicalize(_surface(_SPLIT_QUAD_V, _SPLIT_QUAD_F), weld=False)
    # a weld is a topology repair, not a shape change
    assert np.allclose(split.bounds, unwelded.bounds)
    assert np.isclose(split.area, unwelded.area)


def test_welding_can_be_declined_for_fixed_topology_callers():
    mesh = canonicalize(_surface(_SPLIT_QUAD_V, _SPLIT_QUAD_F), weld=False)
    assert mesh.metadata["weld"]["applied"] is False
    assert mesh.metadata["weld"]["merged"] == 0
    assert len(mesh.vertices) == 6
    assert _components(mesh) == 2  # still shattered, as asked


# ------------------------------------------------- waypoints and pinning ---
def _sphere(count=(64, 64)):
    """A closed body-like surface. A cylinder is unusable here: trimesh
    builds it with only two rings of vertices and a cap centre, so a path
    across it takes the cap as a shortcut and never traces the surface."""
    return trimesh.creation.uv_sphere(radius=100.0, count=count)


def _sphere_with_fragment(offset_mm: float):
    """A sphere plus a small detached triangle floating `offset_mm`
    outside its surface near (radius, 0, 0)."""
    x = 100.0 + offset_mm
    fragment = trimesh.Trimesh(
        vertices=np.array([[x, -2.0, 0.0], [x, 2.0, 0.0], [x, 0.0, 4.0]]),
        faces=np.array([[0, 1, 2]]),
        process=False,
    )
    return trimesh.util.concatenate([_sphere(), fragment])


def test_a_landmark_on_a_stray_fragment_is_pinned_to_the_body():
    mesh = _sphere_with_fragment(offset_mm=5.0)
    graph = EdgeGraph(mesh)
    assert graph.n_components == 2
    off_body = np.array([106.0, 0.0, 0.0])
    assert not graph.on_main_component(graph.nearest_vertex(off_body))

    on_body = np.array([86.6, 0.0, 50.0])  # 30 degrees away on the sphere
    length, flags = surface_path_length_mm(graph, [off_body, on_body])
    assert length is not None
    assert "waypoint_snapped_to_main_component" in flags
    assert "disconnected_surface_path" not in flags


def test_a_landmark_far_from_the_body_refuses_instead_of_being_dragged():
    offset = 3 * MAX_WAYPOINT_SNAP_MM
    graph = EdgeGraph(_sphere_with_fragment(offset_mm=offset))
    far = np.array([100.0 + offset, 0.0, 0.0])
    length, flags = surface_path_length_mm(
        graph, [far, np.array([86.6, 0.0, 50.0])]
    )
    assert length is None
    assert flags == ["waypoint_off_main_surface"]


# --------------------------------------------------------- detour guard ---
def test_a_path_that_wraps_the_body_is_flagged():
    # antipodal points on a sphere: the surface must travel half a great
    # circle (pi*r) to cover a chord of 2r, so the ratio tends to pi/2
    graph = EdgeGraph(_sphere())
    length, flags = surface_path_length_mm(
        graph, [np.array([100.0, 0.0, 0.0]), np.array([-100.0, 0.0, 0.0])]
    )
    assert length is not None
    assert length / 200.0 > MAX_PATH_CHORD_RATIO
    assert "surface_path_detour" in flags


def test_a_path_along_the_body_is_not_flagged():
    # 30 degrees apart: chord and arc differ by about 1 %
    graph = EdgeGraph(_sphere())
    length, flags = surface_path_length_mm(
        graph, [np.array([100.0, 0.0, 0.0]), np.array([86.6, 0.0, 50.0])]
    )
    assert length is not None
    assert "surface_path_detour" not in flags


def test_a_detoured_length_is_never_accepted():
    assert _length_value(500.0, [], "m").disposition == "accepted"
    for flag in ("surface_path_detour", "waypoint_off_main_surface"):
        assert _length_value(500.0, [flag], "m").disposition == "manual_review"


def test_a_detoured_length_keeps_its_number():
    # the geometry is real; what is wrong is calling it the measurement
    value = _length_value(500.0, ["surface_path_detour"], "m")
    assert value.selected_value_mm == 500.0
