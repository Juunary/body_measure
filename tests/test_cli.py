"""CLI behaviour: exit codes, unit enforcement, waist measurement path."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

PYTHON = sys.executable
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    return subprocess.run(
        [PYTHON, "-m", "body_measure", *args],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )


@pytest.fixture()
def body_like_ply(tmp_path):
    """A torso-and-arm stand-in, Z-up like most scanner exports, in metres."""
    torso = trimesh.creation.cylinder(radius=0.15, height=1.6, sections=128)
    arm = trimesh.creation.cylinder(radius=0.04, height=1.6, sections=64)
    arm.apply_translation([0.4, 0.0, 0.0])
    scene = trimesh.util.concatenate([torso, arm])
    scene.apply_translation([0.0, 0.0, 0.8])  # floor at z=0
    path = tmp_path / "body.ply"
    scene.export(path)
    return path


def test_measure_without_a_unit_fails_with_exit_1(body_like_ply):
    proc = run_cli("measure", str(body_like_ply))
    assert proc.returncode == 1
    assert "unit" in proc.stderr.lower()


def test_measure_emits_the_full_schema_with_nulls_by_default(body_like_ply, tmp_path):
    out = tmp_path / "r.json"
    proc = run_cli("measure", str(body_like_ply), "--input-unit", "m",
                   "--up-axis", "Z", "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    from body_measure.spec import load_spec

    assert set(payload["measurements"]) == set(load_spec().names)
    assert payload["measurements"]["waist_circumference"]["selected_value_mm"] is None


def test_measure_with_a_waist_height_slices_the_torso_not_the_arm(body_like_ply, tmp_path):
    out = tmp_path / "r.json"
    proc = run_cli("measure", str(body_like_ply), "--input-unit", "m",
                   "--up-axis", "Z", "--waist-height", "800", "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    waist = json.loads(out.read_text(encoding="utf-8"))["measurements"]["waist_circumference"]
    assert waist["selected_value_mm"] == pytest.approx(2 * np.pi * 150.0, rel=2e-3)
    assert waist["selection_method"] == "convex_hull"
    assert waist["taut_tape_hull_mm"] <= waist["raw_contour_mm"] + 1e-9


def test_validate_rejects_an_unknown_category():
    proc = run_cli("validate", "--category", "bogus")
    assert proc.returncode == 2  # argparse usage error
    assert "category" in proc.stderr
