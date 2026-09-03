"""Draw a measured scan in 3D, with every measurement shown where it was
actually taken.

A girth is a closed curve wrapping the body and a length is a path walking
over its surface, so those are what get drawn: the slice polyline the
circumference was summed from, and the edge-graph path the length was
summed along, rebuilt from the same shortest-path tree. Nothing here is an
illustration of a measurement — each curve is the measurement.

matplotlib is imported lazily. The measurement core does not depend on it,
and `body_measure measure` without --view never loads it.
"""
from __future__ import annotations

import numpy as np
import trimesh
from scipy.sparse.csgraph import dijkstra

from .garment_prototypes import torso_girth_at
from .landmarks import estimated as E
from .measure.surface_path import MAX_WAYPOINT_SNAP_MM, EdgeGraph

MESH_FACE, MESH_EDGE = "#C7D2DA", "#B3C0CA"
SPEC_C, PROTO_C, INK, MUTED = "#1E5F8C", "#B85042", "#20303F", "#7A8B99"

#: Poly3DCollection is a pure-Python painter's-algorithm renderer, so face
#: count is the whole cost. The scan is quantised to this grid for DISPLAY
#: ONLY — every measurement is computed on the full mesh before anything is
#: drawn. Quantise-and-merge rather than the compiled decimator, which
#: application control blocks on this machine.
DISPLAY_VOXEL_MM = 22.0

_GIRTH_CURVES = (
    ("neck_circumference", "Neck girth"),
    ("chest_circumference", "Chest girth"),
    ("waist_circumference", "Waist girth"),
)
_ARM_CURVES = (("upper_arm_girth", "Upper arm girth"),)


def _for_display(mesh):
    quantised = np.round(mesh.vertices / DISPLAY_VOXEL_MM) * DISPLAY_VOXEL_MM
    coarse = trimesh.Trimesh(vertices=quantised, faces=mesh.faces.copy(), process=False)
    coarse.merge_vertices()
    coarse.update_faces(coarse.nondegenerate_faces())
    coarse.remove_unreferenced_vertices()
    return coarse


def surface_path_points(graph: EdgeGraph, waypoints):
    """The vertex chain the length was summed along, from the same tree."""
    indices = []
    for point in waypoints:
        index = graph.nearest_vertex(point)
        if not graph.on_main_component(index):
            index, distance = graph.nearest_vertex_on_main(point)
            if distance > MAX_WAYPOINT_SNAP_MM:
                return None
        indices.append(index)
    chain: list[int] = []
    for a, b in zip(indices, indices[1:]):
        _, predecessors = dijkstra(graph.matrix, directed=False, indices=a,
                                   return_predecessors=True)
        leg, node, guard = [], b, 0
        while node != a and node >= 0 and guard < 500000:
            leg.append(node)
            node = int(predecessors[node])
            guard += 1
        if node != a:
            return None
        leg.append(a)
        leg.reverse()
        chain.extend(leg if not chain else leg[1:])
    return graph.mesh.vertices[chain]


def gather_curves(mesh, measurements, landmarks, prototypes=None):
    """(label, colour, points, kind) for everything with real geometry."""
    curves = []
    prototypes = prototypes or {}

    def level_of(key):
        for landmark_key in ("neck_base_level", "chest_level", "waist_level"):
            if landmark_key.split("_")[0] in key and landmark_key in landmarks:
                return float(landmarks[landmark_key].position_mm[1])
        return None

    for key, label in _GIRTH_CURVES:
        value = measurements.get(key)
        level = level_of(key)
        if value is None or value.selected_value_mm is None or level is None:
            continue
        _, selection = torso_girth_at(mesh, level)
        if selection is not None:
            curves.append((f"{label}  {value.selected_value_mm:.0f} mm", SPEC_C,
                           np.asarray(selection.loop.points, dtype=float), "loop"))

    hem = prototypes.get("hip_girth")
    if hem is not None and hem.available and hem.level_mm is not None:
        _, selection = torso_girth_at(mesh, hem.level_mm)
        if selection is not None:
            curves.append((f"{hem.label}  {hem.value:.0f} mm", PROTO_C,
                           np.asarray(selection.loop.points, dtype=float), "loop"))

    armpit = landmarks.get("armpit_level")
    if armpit is not None:
        # the upper-arm ring, cut where and how it was measured: at the
        # station landmark, perpendicular to the arm axis (decision #46)
        for key, label in _ARM_CURVES:
            value = measurements.get(key)
            if value is None or value.selected_value_mm is None:
                continue
            for side in ("right", "left"):
                station = landmarks.get(f"{key}_station_{side}")
                axis = landmarks.get(f"arm_axis_{side}")
                if station is None:
                    continue
                loop = None
                if axis is not None and getattr(axis, "usable", False):
                    s = float((station.position_mm - axis.origin_mm) @ axis.direction)
                    loop = E.arm_loop_perpendicular(mesh, axis, s)
                else:
                    loops, _ = E.arm_loops_at(mesh, float(station.position_mm[1]), armpit)
                    loop = loops.get(side)
                if loop is not None:
                    curves.append((f"{label}  {value.selected_value_mm:.0f} mm", SPEC_C,
                                   np.asarray(loop.points, dtype=float), "loop"))
        sleeve = prototypes.get("sleeve_opening_girth")
        if sleeve is not None and sleeve.available and sleeve.level_mm is not None:
            label = f"{sleeve.label}  {sleeve.value:.0f} mm"
            drawn = 0
            for side in ("right", "left"):
                axis = landmarks.get(f"arm_axis_{side}")
                loop = None
                if axis is not None and getattr(axis, "usable", False):
                    loop = E.arm_loop_perpendicular(mesh, axis, axis.station_at_height(sleeve.level_mm))
                if loop is not None:
                    curves.append((label if drawn == 0 else None, PROTO_C,
                                   np.asarray(loop.points, dtype=float), "loop"))
                    drawn += 1
            if drawn == 0:
                loops, _ = E.arm_loops_at(mesh, sleeve.level_mm, armpit)
                for i, loop in enumerate(loops.values()):
                    curves.append((label if i == 0 else None, PROTO_C,
                                   np.asarray(loop.points, dtype=float), "loop"))

    graph = EdgeGraph(mesh)
    back_neck = landmarks.get("back_neck_point")
    back_waist = landmarks.get("back_waist_point")
    left = landmarks.get("shoulder_point_left")
    right = landmarks.get("shoulder_point_right")
    wrist = landmarks.get("wrist_point_right") or landmarks.get("wrist_point_left")

    routes = []
    if back_neck is not None and back_waist is not None:
        routes.append(("back_length", "Back length",
                       [back_neck.position_mm, back_waist.position_mm]))
    if back_neck is not None and left is not None and right is not None:
        routes.append(("across_back_shoulder_width", "Across-back width",
                       [left.position_mm, back_neck.position_mm, right.position_mm]))
    if back_neck is not None and wrist is not None:
        shoulder = right if (right is not None and "right" in wrist.name) else (left or right)
        if shoulder is not None:
            routes.append(("sleeve_length", "Sleeve length",
                           [back_neck.position_mm, shoulder.position_mm, wrist.position_mm]))
    for key, label, waypoints in routes:
        value = measurements.get(key)
        if value is None or value.selected_value_mm is None:
            continue
        points = surface_path_points(graph, waypoints)
        if points is not None and len(points) > 1:
            curves.append((f"{label}  {value.selected_value_mm:.0f} mm", SPEC_C,
                           points, "path"))
    return curves


def _panel(ax, coarse, curves, landmarks, elev, azim, title):
    # the scan is Y-up and matplotlib's 3-D axes are Z-up, so every drawn
    # coordinate takes the same (x, z, y) swap — the mesh included, or the
    # body lies down while its measurement rings stand up
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    v = coarse.vertices[:, [0, 2, 1]]
    tri = Poly3DCollection(v[coarse.faces], alpha=0.30, facecolor=MESH_FACE,
                           edgecolor=MESH_EDGE, linewidths=0.15)
    tri.set_zsort("average")
    ax.add_collection3d(tri)

    for _label, colour, points, kind in curves:
        p = np.vstack([points, points[0]]) if kind == "loop" else points
        ax.plot(p[:, 0], p[:, 2], p[:, 1], color=colour,
                lw=2.4 if kind == "path" else 1.9,
                ls="-" if kind == "loop" else "--", zorder=10)

    for key in ("shoulder_point_left", "shoulder_point_right",
                "back_neck_point", "back_waist_point"):
        lm = landmarks.get(key)
        if lm is not None:
            ax.scatter(lm.position_mm[0], lm.position_mm[2], lm.position_mm[1],
                       s=22, color=INK, depthshade=False, zorder=12)

    # a cube aspect leaves a standing body as a thin column of empty panel
    lo, hi = v.min(axis=0), v.max(axis=0)
    mid = 0.5 * (hi + lo)
    horizontal = float(max(hi[0] - lo[0], hi[1] - lo[1])) * 0.62
    vertical = float(hi[2] - lo[2]) * 0.52
    ax.set_xlim(mid[0] - horizontal, mid[0] + horizontal)
    ax.set_ylim(mid[1] - horizontal, mid[1] + horizontal)
    ax.set_zlim(mid[2] - vertical, mid[2] + vertical)
    ax.set_box_aspect((2 * horizontal, 2 * horizontal, 2 * vertical))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    ax.set_title(title, fontsize=10, color=MUTED, pad=-4)


def render(mesh, measurements, landmarks, out_path, *, prototypes=None,
           title="Measurements on the scan", subtitle=""):
    """Write a four-view 3-D figure. Returns the number of curves drawn."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    curves = gather_curves(mesh, measurements, landmarks, prototypes)
    coarse = _for_display(mesh)

    fig = plt.figure(figsize=(16.5, 10.0), dpi=150)
    gs = fig.add_gridspec(2, 4, width_ratios=[1, 1, 0.9, 1.45], wspace=0.0, hspace=0.04)
    for i, (elev, azim, name) in enumerate(
            [(8, -88, "front"), (14, -35, "three-quarter"),
             (8, 2, "side"), (12, 145, "back")]):
        ax = fig.add_subplot(gs[i // 2, i % 2], projection="3d")
        _panel(ax, coarse, curves, landmarks, elev, azim, name)

    ax = fig.add_subplot(gs[:, 2:])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.02, 0.985, title, fontsize=15, color=INK, weight="bold", va="top")
    ax.text(0.02, 0.945, subtitle, fontsize=10, color=MUTED, va="top")

    from .spec import load_spec
    from .validate.stats import quality_bucket

    spec = load_spec()
    y = 0.885
    ax.text(0.02, y, "In measurement-spec  ·  validated pipeline",
            fontsize=10.5, color=SPEC_C, weight="bold", va="top")
    y -= 0.040
    for name in spec.names:
        value = measurements.get(name)
        if value is None:
            continue
        shown = "—" if value.selected_value_mm is None else f"{value.selected_value_mm:.0f} mm"
        colour = SPEC_C if value.selected_value_mm is not None else MUTED
        ax.text(0.035, y, name.replace("_", " "), fontsize=9.5, color=INK, va="top")
        ax.text(0.52, y, shown, fontsize=10, color=colour, weight="bold", va="top")
        ax.text(0.68, y, quality_bucket(value)[:30], fontsize=7.5, color=MUTED, va="top")
        y -= 0.034
    if prototypes:
        y -= 0.014
        ax.text(0.02, y, "NOT in the spec  ·  prototype, unvalidated",
                fontsize=10.5, color=PROTO_C, weight="bold", va="top")
        y -= 0.040
        for value in prototypes.values():
            if value.value is None:
                shown, colour = "—", MUTED
            elif value.unit == "deg":
                shown, colour = f"{value.value:.1f}°", PROTO_C
            else:
                shown, colour = f"{value.value:+.0f} mm" if value.key == "front_back_width" \
                    else f"{value.value:.0f} mm", PROTO_C
            ax.text(0.035, y, value.label, fontsize=9.5, color=INK, va="top")
            ax.text(0.52, y, shown, fontsize=10, color=colour, weight="bold", va="top")
            ax.text(0.68, y, (",".join(value.flags[:1]) or "")[:30],
                    fontsize=7.5, color=MUTED, va="top")
            y -= 0.034

    ax.text(0.02, y - 0.02,
            "Solid rings are the slice polylines the girths were computed from.\n"
            "Dashed lines are the edge-graph paths the lengths were summed along,\n"
            "rebuilt from the same shortest-path tree. Dots are the landmarks they\n"
            "start and end on. Nothing here is an illustration — each curve is the\n"
            "measurement.\n\n"
            f"The surface is quantised to a {DISPLAY_VOXEL_MM:.0f} mm grid so it can be drawn;\n"
            "every measurement was computed on the full-resolution mesh first.",
            fontsize=8.5, color=MUTED, va="top")

    fig.savefig(out_path, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return len(curves)
