"""The CLI's terminal and 3-D outputs.

`measure` is the pipeline's front door: a mesh path in, numbers on the
terminal or a 3-D view out. These tests hold the two rules that matter —
garment prototypes never enter the spec's `measurements` block, and both
new outputs refuse rather than guess when they have no landmarks."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
import trimesh

PYTHON = sys.executable
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    return subprocess.run([PYTHON, "-m", "body_measure", *args],
                          capture_output=True, text=True, encoding="utf-8",
                          cwd=PROJECT_ROOT)


@pytest.fixture()
def body_like_ply(tmp_path):
    torso = trimesh.creation.cylinder(radius=0.15, height=1.6, sections=96)
    arm = trimesh.creation.cylinder(radius=0.04, height=1.6, sections=48)
    arm.apply_translation([0.4, 0.0, 0.0])
    scene = trimesh.util.concatenate([torso, arm])
    scene.apply_translation([0.0, 0.0, 0.8])
    path = tmp_path / "body.ply"
    scene.export(path)
    return path


def test_the_terminal_report_names_every_spec_measurement(body_like_ply):
    from body_measure.spec import load_spec

    proc = run_cli("measure", str(body_like_ply), "--input-unit", "m",
                   "--up-axis", "Z", "--estimate", "--skip-pose-gate")
    assert proc.returncode == 0, proc.stderr
    for name in load_spec().names:
        assert name in proc.stdout


def test_json_is_still_available_on_stdout(body_like_ply):
    proc = run_cli("measure", str(body_like_ply), "--input-unit", "m",
                   "--up-axis", "Z", "--format", "json")
    assert proc.returncode == 0, proc.stderr
    json.loads(proc.stdout)


def test_prototypes_stay_out_of_the_spec_block(body_like_ply, tmp_path):
    """The result schema is exactly the spec's keys. A prototype may be
    reported beside them, never among them."""
    from body_measure.garment_prototypes import POLO_SET
    from body_measure.spec import load_spec

    out = tmp_path / "r.json"
    proc = run_cli("measure", str(body_like_ply), "--input-unit", "m", "--up-axis", "Z",
                   "--estimate", "--skip-pose-gate", "--garment", "polo", "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert set(payload["measurements"]) == set(load_spec().names)
    prototypes = payload["meta"]["garment_prototypes"]
    assert set(prototypes) == set(POLO_SET)
    for value in prototypes.values():
        assert value["status"] == "prototype_not_in_spec"


def test_prototypes_and_view_refuse_without_landmarks(body_like_ply, tmp_path):
    for extra in (["--garment", "polo"], ["--view", str(tmp_path / "v.png")]):
        proc = run_cli("measure", str(body_like_ply), "--input-unit", "m",
                       "--up-axis", "Z", *extra)
        assert proc.returncode == 1
        assert "--estimate" in proc.stderr


def test_the_view_writes_a_png_and_says_how_many_curves(body_like_ply, tmp_path):
    pytest.importorskip("matplotlib")
    png = tmp_path / "view.png"
    proc = run_cli("measure", str(body_like_ply), "--input-unit", "m", "--up-axis", "Z",
                   "--estimate", "--skip-pose-gate", "--view", str(png))
    assert proc.returncode == 0, proc.stderr
    assert png.is_file() and png.stat().st_size > 10_000
    assert "measured curves drawn" in proc.stdout


def test_the_core_still_does_not_import_matplotlib(body_like_ply):
    """--view loads it lazily; a plain measure must not."""
    code = (
        "import sys, importlib;"
        "importlib.import_module('body_measure.cli');"
        "importlib.import_module('body_measure.measure.measurements');"
        "print('LEAK' if 'matplotlib' in sys.modules else 'CLEAN')"
    )
    proc = subprocess.run([PYTHON, "-c", code], cwd=PROJECT_ROOT,
                          capture_output=True, text=True, timeout=120)
    assert proc.stdout.strip() == "CLEAN", proc.stdout


def test_a_stand_in_body_is_refused_by_the_pose_gate_unless_told_otherwise(body_like_ply, tmp_path):
    """The cylinder stand-in has one arm and no feet: not a standing A pose.
    Without the override the CLI says so and measures nothing; the document
    it still writes carries the verdict and every measurement rejected."""
    out = tmp_path / "r.json"
    proc = run_cli("measure", str(body_like_ply), "--input-unit", "m", "--up-axis", "Z",
                   "--estimate", "--out", str(out))
    assert proc.returncode == 1
    assert "pose" in proc.stderr and "--skip-pose-gate" in proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["meta"]["pose"]["ok"] is False and payload["meta"]["pose"]["enforced"] is True
    assert all(v["quality"] == ["pose_rejected"] and v["selected_value_mm"] is None
               for v in payload["measurements"].values())
