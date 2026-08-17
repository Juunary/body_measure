"""Surface path lengths via shortest paths on the mesh edge graph.

This is explicitly an approximation (`edge_graph_approximation`): the
path is constrained to mesh edges, so it depends on triangulation and
tends to overestimate true surface geodesics on coarse meshes. The
remeshing/decimation robustness tests quantify that error; a heat-method
library is the planned upgrade (docs/decisions.md, measurement-spec
known_deviations).
"""
from __future__ import annotations

import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

METHOD = "edge_graph_approximation"


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

    def nearest_vertex(self, point_mm: np.ndarray) -> int:
        return int(self.mesh.kdtree.query(np.asarray(point_mm, dtype=np.float64))[1])

    def distance(self, a: int, b: int) -> float | None:
        dist = dijkstra(self.matrix, directed=False, indices=a, min_only=True)
        value = float(dist[b])
        return None if np.isinf(value) else value


def surface_path_length_mm(
    graph: EdgeGraph, waypoints_mm: list[np.ndarray]
) -> tuple[float | None, list[str]]:
    """Sum of edge-graph shortest paths through the waypoint sequence.
    Returns (length, quality_flags); None when any leg is disconnected."""
    if len(waypoints_mm) < 2:
        return None, ["not_enough_waypoints"]
    indices = [graph.nearest_vertex(p) for p in waypoints_mm]
    total = 0.0
    for a, b in zip(indices, indices[1:]):
        leg = graph.distance(a, b)
        if leg is None:
            return None, ["disconnected_surface_path"]
        total += leg
    return total, []
