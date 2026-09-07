"""Surface path lengths, by plane section where the path is planar and by
shortest paths on the mesh edge graph where it is not.

The edge graph is explicitly an approximation
(`edge_graph_approximation`): the path is constrained to mesh edges, so
it depends on triangulation and tends to overestimate true surface
geodesics — measured on this project's data, by 6 to 18 % (decision
#48). The remeshing/decimation robustness tests quantify that error; a
heat-method library is the planned upgrade for the paths that need one
(docs/decisions.md, measurement-spec known_deviations).

A path that is planar by definition needs none of that. Down the spine
the tape stays in the sagittal plane, so `plane_section_arc_mm` cuts the
mesh with that plane and measures the curve, which crosses faces instead
of hopping between vertices and therefore does not staircase.

Connectivity is the other thing this module has to be honest about. A
real scan is never one clean shell: hair, shoes, the floor and stray
fragments arrive as separate pieces, and a waypoint's nearest vertex can
land on one of them. Walking from a fragment to the body is impossible,
so a naive shortest path reports "disconnected" without saying that the
surface was fine and only the landmark was misplaced.

So waypoints are pinned to the main component, the distance that pin
moved them is measured, and a move too large to still be the same
landmark refuses instead of measuring. The duplicate-index shattering
that used to dominate this failure is repaired earlier, in canonicalize.
"""
from __future__ import annotations

import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

METHOD = "edge_graph_approximation"
SECTION_METHOD = "sagittal_slice_polyline"

#: How far a waypoint may be pulled onto the main surface and still be
#: treated as the same landmark. Body measurements move by roughly this
#: much when a landmark moves, so beyond it the honest answer is that the
#: landmark is not on the measurable surface — not a number.
MAX_WAYPOINT_SNAP_MM = 15.0

#: A surface path is always longer than the straight line between its
#: waypoints — it follows the body's curve. It is not *much* longer: down
#: the spine or across the upper back the excess is well under half. When
#: the ratio runs past this, the path is not tracing the body between two
#: landmarks, it is going around it, which happens as soon as the two
#: landmarks are not where they were supposed to be.
#:
#: This exists because a connected mesh always yields *some* number. Once
#: the surface is walkable, a wrong pair of landmarks stops producing a
#: refusal and starts producing a plausible-looking length, and nothing
#: downstream can tell the difference. The ratio can.
MAX_PATH_CHORD_RATIO = 1.5


#: A waypoint further than this from the section plane is not on the
#: midline the arc traces, and the arc would be measuring a curve the
#: landmark does not sit on.
MAX_SECTION_OFFSET_MM = 10.0

#: A body's sagittal section is a closed curve around the whole
#: silhouette, so two points on it are joined by two arcs. The short one
#: is the back; the long one climbs over the head and comes back up
#: through the crotch. Taking the shorter settles it, and this margin
#: catches the case where even the shorter one wanders out of the band
#: the endpoints span.
SECTION_OVERSHOOT_FRACTION = 0.15

#: How far a section vertex may be from a waypoint and still be treated
#: as the place the arc starts. The section passes through the waypoint
#: exactly — both lie on the surface and on the plane — but its vertices
#: are at edge crossings, so the nearest one is up to an edge away.
MAX_SECTION_ENDPOINT_GAP_MM = 30.0


def plane_section_arc_mm(
    mesh: trimesh.Trimesh, a_mm, b_mm, normal
) -> tuple[float | None, np.ndarray | None, list[str]]:
    """Length of the surface curve between two points, cut by the plane
    through them with the given normal, and the curve itself.

    This is what a tape measure does and what the spec asks for
    (`method: sagittal_slice_polyline`). Unlike the edge graph it does not
    staircase: the curve crosses faces instead of hopping between
    vertices, so it does not inflate with triangulation.
    """
    a = np.asarray(a_mm, dtype=np.float64)
    b = np.asarray(b_mm, dtype=np.float64)
    normal = np.asarray(normal, dtype=np.float64)
    normal = normal / np.linalg.norm(normal)
    origin = (a + b) / 2.0
    if max(abs(float((a - origin) @ normal)), abs(float((b - origin) @ normal))) > MAX_SECTION_OFFSET_MM:
        return None, None, ["waypoints_not_coplanar"]

    try:
        section = mesh.section(plane_origin=origin, plane_normal=normal)
    except Exception:
        section = None
    if section is None:
        return None, None, ["no_section_at_plane"]

    span = abs(float(a[1] - b[1]))
    lo = min(a[1], b[1]) - SECTION_OVERSHOOT_FRACTION * span
    hi = max(a[1], b[1]) + SECTION_OVERSHOOT_FRACTION * span

    best: tuple[float, np.ndarray] | None = None
    for poly in section.discrete:
        poly = np.asarray(poly, dtype=np.float64)
        if len(poly) < 2:
            continue
        closed = bool(np.linalg.norm(poly[0] - poly[-1]) < 1e-6)
        ring = poly[:-1] if closed else poly
        da = np.linalg.norm(ring - a, axis=1)
        db = np.linalg.norm(ring - b, axis=1)
        if da.min() > MAX_SECTION_ENDPOINT_GAP_MM or db.min() > MAX_SECTION_ENDPOINT_GAP_MM:
            continue
        i, j = int(np.argmin(da)), int(np.argmin(db))
        lo_i, hi_i = min(i, j), max(i, j)
        arcs = [ring[lo_i:hi_i + 1]]
        if closed:
            arcs.append(np.vstack([ring[hi_i:], ring[:lo_i + 1]]))
        for arc in arcs:
            if len(arc) < 2:
                continue
            # the exact waypoints replace the vertices that stood in for
            # them, so the two ends of the arc are the two landmarks
            arc = arc.copy()
            starts_at_a = np.linalg.norm(arc[0] - a) < np.linalg.norm(arc[0] - b)
            arc[0], arc[-1] = (a, b) if starts_at_a else (b, a)
            if arc[:, 1].min() < lo or arc[:, 1].max() > hi:
                continue
            length = float(np.linalg.norm(np.diff(arc, axis=0), axis=1).sum())
            if best is None or length < best[0]:
                best = (length, arc)

    if best is None:
        return None, None, ["no_section_arc_between_waypoints"]
    length, arc = best
    flags: list[str] = []
    chord = float(np.linalg.norm(a - b))
    if chord > 0.0 and length / chord > MAX_PATH_CHORD_RATIO:
        flags.append("surface_path_detour")
    return length, arc, flags


class EdgeGraph:
    def __init__(self, mesh: trimesh.Trimesh):
        self.mesh = mesh
        edges = mesh.edges_unique
        lengths = mesh.edges_unique_length
        n = len(mesh.vertices)
        self.matrix = coo_matrix(
            (
                np.concatenate([lengths, lengths]),
                (
                    np.concatenate([edges[:, 0], edges[:, 1]]),
                    np.concatenate([edges[:, 1], edges[:, 0]]),
                ),
            ),
            shape=(n, n),
        ).tocsr()

        # One component decomposition, reused by every waypoint and every
        # leg. The "main" component is the largest by vertex count: on a
        # standing body scan that is the body, and everything else is hair,
        # footwear, floor or debris.
        self.n_components, self.labels = connected_components(
            self.matrix, directed=False
        )
        counts = np.bincount(self.labels, minlength=self.n_components)
        self.main_label = int(np.argmax(counts))
        self.main_fraction = float(counts[self.main_label] / max(n, 1))
        self._main_indices = np.flatnonzero(self.labels == self.main_label)
        self._main_tree = cKDTree(mesh.vertices[self._main_indices])

    def nearest_vertex(self, point_mm: np.ndarray) -> int:
        return int(self.mesh.kdtree.query(np.asarray(point_mm, dtype=np.float64))[1])

    def on_main_component(self, index: int) -> bool:
        return bool(self.labels[index] == self.main_label)

    def nearest_vertex_on_main(self, point_mm: np.ndarray) -> tuple[int, float]:
        """Nearest vertex restricted to the main component, and how far the
        query point is from it."""
        distance, local = self._main_tree.query(
            np.asarray(point_mm, dtype=np.float64)
        )
        return int(self._main_indices[local]), float(distance)

    def distance(self, a: int, b: int) -> float | None:
        dist = dijkstra(self.matrix, directed=False, indices=a, min_only=True)
        value = float(dist[b])
        return None if np.isinf(value) else value


def surface_path_length_mm(
    graph: EdgeGraph, waypoints_mm: list[np.ndarray]
) -> tuple[float | None, list[str]]:
    """Sum of edge-graph shortest paths through the waypoint sequence.
    Returns (length, quality_flags); None when the path cannot be walked."""
    if len(waypoints_mm) < 2:
        return None, ["not_enough_waypoints"]

    indices: list[int] = []
    snap_mm = 0.0
    for point in waypoints_mm:
        index = graph.nearest_vertex(point)
        if graph.on_main_component(index):
            indices.append(index)
            continue
        # the landmark's nearest vertex sits on a fragment; pull it onto
        # the body, but only if that is a small correction
        index, distance = graph.nearest_vertex_on_main(point)
        if distance > MAX_WAYPOINT_SNAP_MM:
            return None, ["waypoint_off_main_surface"]
        indices.append(index)
        snap_mm = max(snap_mm, distance)

    flags: list[str] = []
    if snap_mm > 0.0:
        flags.append("waypoint_snapped_to_main_component")

    total = 0.0
    chord = 0.0
    for a, b in zip(indices, indices[1:]):
        leg = graph.distance(a, b)
        if leg is None:
            # both endpoints are on the main component, so this is a real
            # break in the surface rather than a misplaced landmark
            return None, ["disconnected_surface_path"]
        total += leg
        chord += float(
            np.linalg.norm(graph.mesh.vertices[a] - graph.mesh.vertices[b])
        )

    if chord > 0.0 and total / chord > MAX_PATH_CHORD_RATIO:
        flags.append("surface_path_detour")
    return total, flags
