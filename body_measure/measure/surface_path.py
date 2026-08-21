"""Surface path lengths via shortest paths on the mesh edge graph.

This is explicitly an approximation (`edge_graph_approximation`): the
path is constrained to mesh edges, so it depends on triangulation and
tends to overestimate true surface geodesics on coarse meshes. The
remeshing/decimation robustness tests quantify that error; a heat-method
library is the planned upgrade (docs/decisions.md, measurement-spec
known_deviations).

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
