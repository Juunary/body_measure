"""Extract the polo-shirt measurement list from a 3D scan and draw where
each one is taken.

Twelve measurements matter to a polo. Seven are in measurement-spec and
come from the validated pipeline. Five are not in the spec, and this
script computes them as **prototypes** — no ISO definition audit, no
reference comparison, no robustness battery. They are drawn and reported
so their shape can be discussed, and they are labelled at every point of
output so a prototype number never reads as a validated one.

Run (PowerShell — torch is not needed, but PYTHONUTF8 is):
  $env:PYTHONUTF8=1; .venv\\Scripts\\python scripts\\polo_measurement_map.py --dataset hsrd
  $env:PYTHONUTF8=1; .venv\\Scripts\\python scripts\\polo_measurement_map.py --dataset texel --subject Man0

Public-material note: figures made from HSRD-100 (CC BY 4.0) may leave the
project. Figures made from Texel or NOMO may not — see
docs/licenses/public-material.md. The output filename records which.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import trimesh  # noqa: E402

from body_measure.canonicalize import body_axis_point, canonicalize  # noqa: E402
from body_measure.landmarks import estimated as E  # noqa: E402
from body_measure.measure.circumference import measure_circumference  # noqa: E402
from body_measure.measure.measurements import run_estimated_measurements  # noqa: E402
from body_measure.measure.slicing import (  # noqa: E402
    project_axis_to_plane,
    select_torso_loop,
    slice_mesh,
)
from body_measure.garment_prototypes import (  # noqa: E402
    SLEEVE_END_FRACTION,
    run_prototypes,
)
from body_measure.spec import load_spec  # noqa: E402
from body_measure.validate.stats import quality_bucket  # noqa: E402

OUT_DIR = PROJECT_ROOT / "reports" / "polo_map"
UP = np.array([0.0, 1.0, 0.0])

INK, MUTED = "#20303F", "#7A8B99"
SPEC_C, PROTO_C, FAIL_C = "#1E5F8C", "#B85042", "#C9CFD4"

#: A short sleeve ends part-way down the upper arm. Where exactly is a
#: design choice; this is the fraction of the armpit-to-wrist drop used to
#: place the probe, and it is a parameter of THIS SCRIPT, not a definition.
SLEEVE_END_FRACTION = 0.30


@dataclass
class Result:
    key: str
    label: str
    value_mm: float | None
    status: str                      # spec | prototype | unavailable
    bucket: str = ""
    flags: list[str] = field(default_factory=list)
    note: str = ""
    level_mm: float | None = None    # where a horizontal girth was taken


# ------------------------------------------------------------- pipeline ---
SPEC_LABEL = {
    "neck_circumference": "Neck base girth",
    "chest_circumference": "Chest girth",
    "waist_circumference": "Waist girth",
    "across_back_shoulder_width": "Across-back shoulder width",
    "back_length": "Back length",
    "upper_arm_girth": "Upper arm girth",
    "sleeve_length": "Sleeve length",
}


def collect(mesh, facing=None):
    spec = load_spec()
    values, landmarks = run_estimated_measurements(mesh, facing=facing)
    results: list[Result] = []
    for name in spec.names:
        v = values[name]
        level = None
        for key in ("neck_base_level", "chest_level", "waist_level"):
            if key.split("_")[0] in name:
                lm = landmarks.get(key)
                level = None if lm is None else float(lm.position_mm[1])
        results.append(Result(
            name, SPEC_LABEL.get(name, name), v.selected_value_mm,
            "spec" if v.selected_value_mm is not None else "unavailable",
            bucket=quality_bucket(v),
            flags=[f for f in v.quality if f != "ok"],
            note=f"{spec.measurements[name].priority} / {spec.measurements[name].implementation_status}",
            level_mm=level,
        ))

    # the five prototypes now live in body_measure/garment_prototypes.py so
    # the CLI and both figures share one implementation
    for value in run_prototypes(mesh, values, landmarks).values():
        results.append(Result(
            value.key, value.label, value.value,
            "prototype" if value.available else "unavailable",
            flags=list(value.flags), note=value.note, level_mm=value.level_mm,
        ))
    return results, landmarks


# ---------------------------------------------------------------- figure ---
def silhouette(mesh, axis_index, n_bands=220):
    """(lo, hi, y) profile of the mesh projected on one horizontal axis."""
    v = mesh.vertices
    y0, y1 = v[:, 1].min(), v[:, 1].max()
    edges = np.linspace(y0, y1, n_bands + 1)
    band = np.clip(np.digitize(v[:, 1], edges) - 1, 0, n_bands - 1)
    lo = np.full(n_bands, np.nan)
    hi = np.full(n_bands, np.nan)
    for b in range(n_bands):
        m = band == b
        if m.any():
            lo[b], hi[b] = v[m, axis_index].min(), v[m, axis_index].max()
    centres = 0.5 * (edges[:-1] + edges[1:])
    ok = ~np.isnan(lo)
    return lo[ok], hi[ok], centres[ok]


def draw(mesh, results, landmarks, title, subtitle, out_path):
    fig = plt.figure(figsize=(15.5, 9.2), dpi=150)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.05, 1.05, 2.5], wspace=0.18)
    v = mesh.vertices
    height = float(v[:, 1].max())

    for col, (axis_index, view) in enumerate([(0, "front"), (2, "side")]):
        ax = fig.add_subplot(gs[0, col])
        lo, hi, ys = silhouette(mesh, axis_index)
        ax.fill_betweenx(ys, lo, hi, color="#DCE3E8", zorder=1)
        ax.set_title(f"{view} view", fontsize=11, color=MUTED)
        ax.set_ylim(-40, height + 60)
        span = max(hi.max() - lo.min(), 400)
        mid = 0.5 * (hi.max() + lo.min())
        ax.set_xlim(mid - span * 0.72, mid + span * 0.72)
        ax.set_aspect("equal")
        ax.axis("off")

        drawn = [r for r in results if r.level_mm is not None and r.value_mm is not None]
        drawn.sort(key=lambda r: r.level_mm)
        last_label_y = -1e9
        for r in drawn:
            colour = SPEC_C if r.status == "spec" else PROTO_C
            ax.axhline(r.level_mm, color=colour, lw=1.4, alpha=0.85, zorder=3)
            if col != 0:
                continue
            # nudge a label up when the level above it is too close to read
            label_y = max(r.level_mm + 8, last_label_y + 0.045 * height)
            last_label_y = label_y
            if abs(label_y - r.level_mm) > 12:
                ax.plot([mid - span * 0.70, mid - span * 0.62],
                        [label_y + 4, r.level_mm], color=colour, lw=0.6, alpha=0.6, zorder=3)
            ax.text(mid - span * 0.70, label_y, f"{r.label}  {r.value_mm:.0f}",
                    fontsize=7.5, color=colour, va="bottom")

        if col == 0:
            for key, marker in (("shoulder_point_left", "o"), ("shoulder_point_right", "o"),
                                ("back_neck_point", "s")):
                lm = landmarks.get(key)
                if lm is not None:
                    ax.plot(lm.position_mm[axis_index], lm.position_mm[1], marker,
                            ms=5, color=INK, zorder=5)
            sl = landmarks.get("shoulder_point_left")
            sr = landmarks.get("shoulder_point_right")
            bn = landmarks.get("back_neck_point")
            if bn is not None and sl is not None and sr is not None:
                for tip in (sl, sr):
                    ax.plot([bn.position_mm[0], tip.position_mm[0]],
                            [bn.position_mm[1], tip.position_mm[1]],
                            color=PROTO_C, lw=1.2, ls="--", zorder=4)
            ap = landmarks.get("armpit_level")
            if ap is not None and sl is not None:
                x = mid + span * 0.52
                ax.annotate("", xy=(x, sl.position_mm[1]), xytext=(x, ap.position_mm[1]),
                            arrowprops=dict(arrowstyle="<->", color=PROTO_C, lw=1.2))
                ax.text(x + span * 0.03, 0.5 * (sl.position_mm[1] + ap.position_mm[1]),
                        "armhole\ndepth", fontsize=7.5, color=PROTO_C, va="center")

    # ------------------------------------------------------------- table --
    ax = fig.add_subplot(gs[0, 2])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0, 0.985, title, fontsize=14, color=INK, weight="bold", va="top")
    ax.text(0, 0.945, subtitle, fontsize=9.5, color=MUTED, va="top")

    y = 0.885
    for group, label in (("spec", "In measurement-spec  ·  validated pipeline"),
                         ("prototype", "NOT in the spec  ·  prototype, unvalidated"),
                         ("unavailable", "No value on this scan")):
        rows = [r for r in results if r.status == group]
        if not rows:
            continue
        colour = SPEC_C if group == "spec" else (PROTO_C if group == "prototype" else MUTED)
        ax.text(0, y, label, fontsize=10, color=colour, weight="bold", va="top")
        y -= 0.038
        for r in rows:
            if r.value_mm is None:
                shown = "—"
            elif r.key == "shoulder_slope":
                shown = f"{r.value_mm:.1f} deg"
            elif r.key == "front_back_width":
                shown = f"{r.value_mm:+.0f} mm"
            else:
                shown = f"{r.value_mm:.0f} mm"
            ax.text(0.005, y, r.label, fontsize=9, color=INK, va="top")
            ax.text(0.46, y, shown, fontsize=9.5, color=colour, va="top", weight="bold")
            extra = r.bucket if r.status == "spec" else ""
            if r.flags:
                extra = (extra + "  " + ",".join(r.flags[:2])).strip()
            ax.text(0.60, y, extra[:46], fontsize=7.5, color=MUTED, va="top")
            y -= 0.030
            if r.note:
                ax.text(0.02, y, r.note[:96], fontsize=7, color=MUTED, va="top", style="italic")
                y -= 0.026
        y -= 0.016

    # the caption lives on the figure rather than in the table axes, so a
    # long table can never grow into it
    fig.text(0.09, 0.030,
             "Blue lines and values come from the validated pipeline.\n"
             "Red ones are prototypes: no ISO definition audit, no reference\n"
             "comparison, no robustness battery. They are drawn so their\n"
             "shape can be discussed, not so they can be used.",
             fontsize=8.5, color=MUTED, va="bottom")

    fig.subplots_adjust(bottom=0.13, top=0.96)
    fig.savefig(out_path, facecolor="white")
    plt.close(fig)


# ------------------------------------------------------------------ main ---
def load(dataset, subject):
    if dataset == "hsrd":
        from body_measure.adapters.hsrd import HsrdAdapter
        adapter = HsrdAdapter(PROJECT_ROOT / "data" / "external" / "hsrd")
        # the finest LOD, by actual mesh size rather than by directory name:
        # the coarse one returns an upper-arm girth no human has (#20)
        surfaces = [adapter.load(o) for o in adapter.observations()]
        surface = max(surfaces, key=lambda s: len(s.faces))
        return canonicalize(surface), f"HSRD-100 · {surface.meta['lod']} · clothed (jacket, jeans, boots)", True
    if dataset == "texel":
        from body_measure.adapters.texel import TexelAdapter
        adapter = TexelAdapter()
        people = sorted(adapter.persons(PROJECT_ROOT / "data" / "external" / "texel"))
        chosen = next((p for p in people if p.name == subject), people[0])
        return canonicalize(adapter.load(chosen)), f"Texel BodyScan · {chosen.name} · unclothed", False
    raise SystemExit(f"unknown dataset {dataset!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="hsrd", choices=["hsrd", "texel"])
    ap.add_argument("--subject", default="Man0")
    args = ap.parse_args()

    mesh, label, shareable = load(args.dataset, args.subject)
    facing = None
    results, landmarks = collect(mesh, facing)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = args.dataset if args.dataset == "hsrd" else f"{args.dataset}_{args.subject}"
    suffix = "" if shareable else "_INTERNAL_ONLY"
    png = OUT_DIR / f"polo_map_{tag}{suffix}.png"

    draw(mesh, results, landmarks, "Polo measurement map", label, png)

    payload = {
        "source": label,
        "shareable_outside_project": shareable,
        "sleeve_end_fraction": SLEEVE_END_FRACTION,
        "measurements": [
            {"key": r.key, "label": r.label, "value_mm": r.value_mm, "status": r.status,
             "bucket": r.bucket, "flags": r.flags, "note": r.note, "level_mm": r.level_mm}
            for r in results
        ],
    }
    (OUT_DIR / f"polo_map_{tag}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    width = max(len(r.label) for r in results)
    for group in ("spec", "prototype", "unavailable"):
        rows = [r for r in results if r.status == group]
        if not rows:
            continue
        print(f"\n--- {group} ---")
        for r in rows:
            if r.value_mm is None:
                shown = "—"
            elif r.key == "shoulder_slope":
                shown = f"{r.value_mm:8.1f}°"
            else:
                shown = f"{r.value_mm:8.1f} mm"
            print(f"  {r.label:{width}s} {shown:>12s}  {r.bucket:14s} {','.join(r.flags[:2])}")
    print(f"\nwrote {png.relative_to(PROJECT_ROOT)}")
    if not shareable:
        print("  NOT cleared to leave the project (docs/licenses/public-material.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
