"""The pattern-readiness gate.

The gate exists to answer a question the project cannot yet answer by
building: is this body measured well enough to draft from? Its value is
entirely in what it refuses to say, so that is what these tests pin.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
import trimesh

from body_measure.garment_prototypes import PrototypeValue
from body_measure.pattern_readiness import (
    COMPLETE_UNVERIFIED,
    NOT_READY,
    POLO_REQUIREMENTS,
    Requirement,
    assess,
)
from body_measure.result import MeasurementValue

PYTHON = sys.executable
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def measured(**by_key):
    """by_key: name -> (value_mm, disposition)"""
    return {
        name: MeasurementValue(selected_value_mm=value, method="plane_slice",
                               quality=["ok"], disposition=disposition)
        for name, (value, disposition) in by_key.items()
    }


# ------------------------------------------------------ what it refuses ---
def test_ready_is_not_a_verdict_the_gate_can_reach():
    """No value has been compared against a tape, so none can be called
    accurate to a pattern's tolerance. The best available verdict says
    complete and unverified, and the module offers no better one."""
    import body_measure.pattern_readiness as module

    verdicts = {v for k, v in vars(module).items()
                if k.isupper() and isinstance(v, str) and not k.endswith("BUCKETS")}
    assert verdicts == {NOT_READY, COMPLETE_UNVERIFIED}
    assert "ready" not in verdicts


def test_every_readiness_says_no_accuracy_claim_exists():
    readiness = assess(measured(chest_circumference=(1000.0, "accepted")))
    joined = " ".join(readiness.notes)
    assert "measurement_accuracy is unreachable" in joined
    assert "trained measurer" in joined


def test_a_prototype_is_present_but_never_draftable():
    """A prototype has no definition audit and no reference. Having a
    number is not the same as being allowed to cut cloth against it."""
    readiness = assess(
        measured(),
        {"hem_girth": PrototypeValue("hem_girth", "Hem girth", 1100.0)},
    )
    hem = next(s for s in readiness.statuses if s.requirement.key == "hem_girth")
    assert hem.value == 1100.0
    assert not hem.draftable
    assert "no ISO definition audit" in hem.note


def test_a_measurement_the_pipeline_flagged_cannot_carry_a_line():
    readiness = assess(measured(
        chest_circumference=(1000.0, "manual_review"),
        waist_circumference=(900.0, "accepted"),
    ))
    by_key = {s.requirement.key: s for s in readiness.statuses}
    assert not by_key["chest_circumference"].draftable
    assert by_key["waist_circumference"].draftable


def test_an_unimplemented_requirement_blocks_and_says_so():
    readiness = assess(measured())
    unimplemented = [s for s in readiness.statuses
                     if s.requirement.provision == "unimplemented"]
    assert unimplemented
    for status in unimplemented:
        assert not status.draftable
        assert status.value is None
        assert "nothing computes this" in status.note


# ------------------------------------------------- the requirement list ---
def test_every_requirement_names_what_it_drafts_and_where_it_came_from():
    for requirement in POLO_REQUIREMENTS:
        assert requirement.drafts
        assert requirement.source
        assert requirement.provision in ("spec", "prototype", "unimplemented")


def test_the_unsourced_requirements_are_declared_as_such():
    """Three entries were identified by reading, not taken from a drafting
    system. The gate reports the provenance of its own requirements."""
    unsourced = [r for r in POLO_REQUIREMENTS if "unsourced" in r.source]
    assert len(unsourced) == 3
    readiness = assess(measured())
    assert any("unsourced" in note for note in readiness.notes)


def test_the_spec_requirements_are_all_real_spec_keys():
    from body_measure.spec import load_spec

    names = set(load_spec().names)
    for requirement in POLO_REQUIREMENTS:
        if requirement.provision == "spec":
            assert requirement.key in names


# -------------------------------------------------------------- verdict ---
def test_a_body_missing_a_dimension_is_not_ready():
    assert assess(measured()).verdict == NOT_READY


def test_complete_unverified_is_reachable_when_everything_is_draftable():
    """Constructed with a requirement list of one so the verdict logic
    itself can be exercised; the polo list cannot reach it today."""
    one = (Requirement("chest_circumference", "body width", "spec", "test"),)
    readiness = assess(measured(chest_circumference=(1000.0, "accepted")),
                       requirements=one)
    assert readiness.verdict == COMPLETE_UNVERIFIED
    assert not readiness.blocking


# ------------------------------------------------------------------ CLI ---
@pytest.fixture()
def body_like_ply(tmp_path):
    torso = trimesh.creation.cylinder(radius=0.16, height=1.6, sections=96)
    arm = trimesh.creation.cylinder(radius=0.04, height=1.6, sections=48)
    arm.apply_translation([0.4, 0.0, 0.0])
    scene = trimesh.util.concatenate([torso, arm])
    scene.apply_translation([0.0, 0.0, 0.8])
    path = tmp_path / "body.ply"
    scene.export(path)
    return path


def test_the_cli_records_readiness_with_its_requirement_sources(body_like_ply, tmp_path):
    out = tmp_path / "r.json"
    proc = subprocess.run(
        [PYTHON, "-m", "body_measure", "measure", str(body_like_ply),
         "--input-unit", "m", "--up-axis", "Z", "--estimate",
         "--pattern", "polo", "--out", str(out)],
        capture_output=True, text=True, encoding="utf-8", cwd=PROJECT_ROOT)
    assert proc.returncode == 0, proc.stderr
    block = json.loads(out.read_text(encoding="utf-8"))["meta"]["pattern_readiness"]
    assert block["verdict"] in (NOT_READY, COMPLETE_UNVERIFIED)
    assert block["n_required"] == len(POLO_REQUIREMENTS)
    for entry in block["requirements"]:
        assert entry["requirement_source"]
    assert block["notes"]


def test_the_cli_refuses_readiness_without_estimate(body_like_ply):
    proc = subprocess.run(
        [PYTHON, "-m", "body_measure", "measure", str(body_like_ply),
         "--input-unit", "m", "--up-axis", "Z", "--pattern", "polo"],
        capture_output=True, text=True, encoding="utf-8", cwd=PROJECT_ROOT)
    assert proc.returncode == 1
    assert "--estimate" in proc.stderr
