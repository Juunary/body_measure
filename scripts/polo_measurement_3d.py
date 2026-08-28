"""Draw the polo measurement set on the scan itself, in 3D.

The 2D map (polo_measurement_map.py) shows each girth as a horizontal
line at the height it was taken. That is enough to check a level and not
enough to see what was actually measured: a girth is a closed curve
wrapping the body, and a length is a path walking over its surface. This
script draws those curves and paths where they really are.

Everything drawn is the geometry the measurement used — the slice
polyline the circumference was computed from, and the edge-graph path the
length was summed along, reconstructed from the same Dijkstra tree. No
curve here is an illustration of a measurement; each one IS the
measurement.

Run (PowerShell):
  $env:PYTHONUTF8=1; .venv\\Scripts\\python scripts\\polo_measurement_3d.py --dataset hsrd
  $env:PYTHONUTF8=1; .venv\\Scripts\\python scripts\\polo_measurement_3d.py --dataset texel --subject Man0

Public-material note: HSRD-100 is CC BY 4.0 and may leave the project;
Texel and NOMO may not. The output filename records which.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import trimesh  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402
from scipy.sparse.csgraph import dijkstra  # noqa: E402

from body_measure.canonicalize import body_axis_point  # noqa: E402
from body_measure.landmarks import estimated as E  # noqa: E402
from body_measure.measure.slicing import (  # noqa: E402
    project_axis_to_plane,
    select_torso_loop,
    slice_mesh,
)
from body_measure.measure.surface_path import EdgeGraph  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "polo_map", PROJECT_ROOT / "scripts" / "polo_measurement_map.py")
polo = importlib.util.module_from_spec(_spec)
# @dataclass resolves its own module through sys.modules, so the module has
# to be registered before it executes or the decorator raises
sys.modules["polo_map"] = polo
_spec.loader.exec_module(polo)

OUT_DIR = PROJECT_ROOT / "reports" / "polo_map"
UP = np.array([0.0, 1.0, 0.0])

MESH_FACE = "#C7D2DA"
MESH_EDGE = "#B3C0CA"
SPEC_C, PROTO_C, INK, MUTED = "#1E5F8C", "#B85042", "#20303F", "#7A8B99"

#: Poly3DCollection is a painter's-algorithm renderer in pure Python, so
#: face count is the whole cost. The scan is quantised to this grid before
#: display only — every measurement on the figure was computed on the full
#: mesh first. Same quantise-and-merge used by the C2 battery, for the
#: same reason: the compiled decimator is blocked on this machine.
DISPLAY_VOXEL_MM = 22.0


def for_display(mesh):
    quantised = np.round(mesh.vertices / DISPLAY_VOXEL_MM) * DISPLAY_VOXEL_MM
    coarse = trimesh.Trimesh(vertices=quantised, faces=mesh.faces.copy(), process=False)
    coarse.merge_vertices()
    coarse.update_faces(coarse.nondegenerate_faces())
    coarse.remove_unreferenced_vertices()
    return coarse


# ------------------------------------------------- the measured geometry ---
def torso_loop_points(mesh, level_mm):
    axis = body_axis_point(mesh)
    origin = np.array([0.0, float(level_mm), 0.0])
    selection = select_torso_loop(
        slice_mesh(mesh, origin, UP), project_axis_to_plane(axis, origin, UP))
    if selection is None or selection.method != "axis_containment":
        return None
    return np.asarray(selection.loop.points, dtype=float)


def surface_path_points(graph: EdgeGraph, waypoints):
    """The actual vertex chain the length was summed along, rebuilt from the
    same shortest-path tree the measurement used."""
    indices = []
    for point in waypoints:
        i = graph.nearest_vertex(point)
        if not graph.on_main_component(i):
            i, distance = graph.nearest_vertex_on_main(point)
            if distance > 15.0:
                return None
        indices.append(i)
    chain: list[int] = []
    for a, b in zip(indices, indices[1:]):
        _, predecessors = dijkstra(
            graph.matrix, directed=False, indices=a, return_predecessors=True)
        leg, node = [], b
        guard = 0
        while node != a and node >= 0 and guard < 200000:
            leg.append(node)
            node = int(predecessors[node])
            guard += 1
        if node != a:
            return None
        leg.append(a)
        leg.reverse()
        chain.extend(leg if not chain else leg[1:])
    return graph.mesh.vertices[chain]


def gather_curves(mesh, results, landmarks):
    """(label, colour, points, kind) for everything that has real geometry."""
    curves = []
    by_key = {r.key: r for r in results}

    for key, label in (("neck_circumference", "Neck girth"),
                       ("chest_circumference", "Chest girth"),
                       ("waist_circumference", "Waist girth"),
                       ("hem_girth", "Hem girth")):
        r = by_key.get(key)
        if r is None or r.value_mm is None or r.level_mm is None:
            continue
        pts = torso_loop_points(mesh, r.level_mm)
        if pts is not None:
            colour = SPEC_C if r.status == "spec" else PROTO_C
            curves.append((f"{label}  {r.value_mm:.0f} mm", colour, pts, "loop"))

    armpit = landmarks.get("armpit_level")
    for key, label in (("upper_arm_girth", "Upper arm girth"),
                       ("sleeve_opening_girth", "Sleeve opening")):
        r = by_key.get(key)
        if r is None or r.value_mm is None or r.level_mm is None or armpit is None:
            continue
        loops, _ = E.arm_loops_at(mesh, r.level_mm, armpit)
        colour = SPEC_C if r.status == "spec" else PROTO_C
        for i, loop in enumerate(loops.values()):
            curves.append((f"{label}  {r.value_mm:.0f} mm" if i == 0 else None,
                           colour, np.asarray(loop.points, dtype=float), "loop"))

    graph = EdgeGraph(mesh)
    bn = landmarks.get("back_neck_point")
    bw = landmarks.get("back_waist_point")
    sl = landmarks.get("shoulder_point_left")
    sr = landmarks.get("shoulder_point_right")
    wrist = landmarks.get("wrist_point_right") or landmarks.get("wrist_point_left")

    paths = []
    if bn is not None and bw is not None and by_key["back_length"].value_mm is not None:
        paths.append(("back_length", "Back length", [bn.position_mm, bw.position_mm]))
    if bn is not None and sl is not None and sr is not None \
            and by_key["across_back_shoulder_width"].value_mm is not None:
        paths.append(("across_back_shoulder_width", "Across-back width",
                      [sl.position_mm, bn.position_mm, sr.position_mm]))
    if bn is not None and wrist is not None and by_key["sleeve_length"].value_mm is not None:
        shoulder = sr if (sr is not None and "right" in wrist.name) else (sl or sr)
        if shoulder is not None:
            paths.append(("sleeve_length", "Sleeve length",
                          [bn.position_mm, shoulder.position_mm, wrist.position_mm]))
    for key, label, waypoints in paths:
        pts = surface_path_points(graph, waypoints)
        if pts is not None and len(pts) > 1:
            r = by_key[key]
            colour = SPEC_C if r.status == "spec" else PROTO_C
            curves.append((f"{label}  {r.value_mm:.0f} mm", colour, pts, "path"))
    return curves


# ------------------------------------------------------------- rendering ---
def draw_panel(ax, coarse, curves, landmarks, elev, azim, title):
    # the scan is Y-up; matplotlib's 3-D axes are Z-up, so every drawn
    # coordinate goes through the same (x, z, y) swap — the mesh included,
    # or the body lies down while the measurement rings stand up
    v, f = coarse.vertices[:, [0, 2, 1]], coarse.faces
    tri = Poly3DCollection(v[f], alpha=0.30, facecolor=MESH_FACE,
                           edgecolor=MESH_EDGE, linewidths=0.15)
    tri.set_zsort("average")
    ax.add_collection3d(tri)

    for label, colour, pts, kind in curves:
        p = np.vstack([pts, pts[0]]) if kind == "loop" else pts
        ax.plot(p[:, 0], p[:, 2], p[:, 1], color=colour,
                lw=2.4 if kind == "path" else 1.9,
                ls="-" if kind == "loop" else "--", zorder=10)

    for key, colour in (("shoulder_point_left", INK), ("shoulder_point_right", INK),
                        ("back_neck_point", INK), ("back_waist_point", INK)):
        lm = landmarks.get(key)
        if lm is not None:
            ax.scatter(lm.position_mm[0], lm.position_mm[2], lm.position_mm[1],
                       s=22, color=colour, depthshade=False, zorder=12)

    # a cube would leave a standing body as a thin column of empty panel;
    # the box aspect follows the real extents so the scan fills the frame
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


def draw(mesh, results, landmarks, title, subtitle, out_path):
    coarse = for_display(mesh)
    curves = gather_curves(mesh, results, landmarks)

    fig = plt.figure(figsize=(16.5, 10.4), dpi=150)
    gs = fig.add_gridspec(2, 4, width_ratios=[1, 1, 0.9, 1.45],
                          wspace=0.0, hspace=0.04)
    views = [(8, -88, "front"), (14, -35, "three-quarter"),
             (8, 2, "side"), (12, 145, "back")]
    for i, (elev, azim, name) in enumerate(views):
        ax = fig.add_subplot(gs[i // 2, i % 2], projection="3d")
        draw_panel(ax, coarse, curves, landmarks, elev, azim, name)

    ax = fig.add_subplot(gs[:, 2:])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.02, 0.985, title, fontsize=15, color=INK, weight="bold", va="top")
    ax.text(0.02, 0.945, subtitle, fontsize=10, color=MUTED, va="top")

    y = 0.885
    for group, heading in (("spec", "In measurement-spec  ·  validated pipeline"),
                           ("prototype", "NOT in the spec  ·  prototype, unvalidated"),
                           ("unavailable", "No value on this scan")):
        rows = [r for r in results if r.status == group]
        if not rows:
            continue
        colour = SPEC_C if group == "spec" else (PROTO_C if group == "prototype" else MUTED)
        ax.text(0.02, y, heading, fontsize=10.5, color=colour, weight="bold", va="top")
        y -= 0.040
        for r in rows:
            if r.value_mm is None:
                shown = "—"
            elif r.key == "shoulder_slope":
                shown = f"{r.value_mm:.1f}°"
            elif r.key == "front_back_width":
                shown = f"{r.value_mm:+.0f} mm"
            else:
                shown = f"{r.value_mm:.0f} mm"
            ax.text(0.035, y, r.label, fontsize=9.5, color=INK, va="top")
            ax.text(0.52, y, shown, fontsize=10, color=colour, weight="bold", va="top")
            extra = r.bucket if r.status == "spec" else ""
            if r.flags:
                extra = (extra + "  " + ",".join(r.flags[:1])).strip()
            ax.text(0.68, y, extra[:34], fontsize=7.5, color=MUTED, va="top")
            y -= 0.034
        y -= 0.014

    ax.text(0.02, y - 0.01,
            "Solid rings are the slice polylines the girths were computed from.\n"
            "Dashed lines are the edge-graph paths the lengths were summed along,\n"
            "rebuilt from the same shortest-path tree. Dots are the landmarks they\n"
            "start and end on. Nothing here is an illustration — each curve is the\n"
            "measurement.\n\n"
            f"The surface shown is quantised to a {DISPLAY_VOXEL_MM:.0f} mm grid so it can be drawn;\n"
            "every measurement was computed on the full-resolution mesh first.",
            fontsize=8.5, color=MUTED, va="top")

    fig.savefig(out_path, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return len(curves)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="hsrd", choices=["hsrd", "texel"])
    ap.add_argument("--subject", default="Man0")
    args = ap.parse_args()

    mesh, label, shareable = polo.load(args.dataset, args.subject)
    results, landmarks = polo.collect(mesh, None)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = args.dataset if args.dataset == "hsrd" else f"{args.dataset}_{args.subject}"
    suffix = "" if shareable else "_INTERNAL_ONLY"
    png = OUT_DIR / f"polo_3d_{tag}{suffix}.png"

    n = draw(mesh, results, landmarks, "Polo measurements on the scan", label, png)
    print(f"{n} measured curves drawn")
    print(f"wrote {png.relative_to(PROJECT_ROOT)}")
    if not shareable:
        print("  NOT cleared to leave the project (docs/licenses/public-material.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
