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
    from body_measure.pattern_readiness import VERDICTS

    assert set(VERDICTS) == {NOT_READY, COMPLETE_UNVERIFIED}
    assert "ready" not in VERDICTS
    # and nothing reaches a verdict the list does not contain
    assert assess(measured()).verdict in VERDICTS
    assert assess(measured(chest_circumference=(1000.0, "accepted"))).verdict in VERDICTS


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
        {"hip_girth": PrototypeValue("hip_girth", "Hip girth", 1100.0)},
    )
    hip = next(s for s in readiness.statuses if s.requirement.key == "hip_girth")
    assert hip.value == 1100.0
    assert not hip.draftable
    assert "no ISO definition audit" in hip.note


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
def test_every_requirement_separates_the_body_from_the_pattern_piece():
    """`measures` is what a tape would read off a body; `feeds` is what a
    draft does with it. Collapsing them is how `hem_girth` came to be
    described as "hem width" when it is the hip underneath (decision #42)."""
    from body_measure.pattern_readiness import BY_ANATOMY, BY_DESIGN

    for requirement in POLO_REQUIREMENTS:
        assert requirement.measures and requirement.feeds
        assert requirement.measures != requirement.feeds
        assert requirement.source
        assert requirement.provision in ("spec", "prototype", "unimplemented")
        assert requirement.location in (BY_ANATOMY, BY_DESIGN)


def test_not_one_requirement_is_a_finished_garment_measurement():
    """A draft is cut to ISO 18890 points, which are these plus ease. This
    gate has no garment to measure, so it covers the body link only, and
    the verdict says so."""
    readiness = assess(measured())
    joined = " ".join(readiness.notes)
    assert "measured ON A BODY" in joined
    assert "plus ease" in joined
    assert "INPUT to a draft" in joined


def test_a_design_located_requirement_is_named_as_such():
    """sleeve_opening_girth is taken wherever the sleeve ends, so it moves
    when SLEEVE_END_FRACTION does — it is not a property of the body."""
    from body_measure.pattern_readiness import BY_DESIGN

    located = {r.key for r in POLO_REQUIREMENTS if r.location == BY_DESIGN}
    assert located == {"sleeve_opening_girth"}
    joined = " ".join(assess(measured()).notes)
    assert "design parameter puts them" in joined
    assert "sleeve_opening_girth" in joined


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


def test_the_gate_never_requires_a_measurement_the_spec_defers():
    """`priority` in the spec is scope, not difficulty: `deferred` means the
    dimension is outside the garment being built. A gate that demanded one
    would report NOT_READY for something the product does not need, which is
    how sleeve_length -- a measurement to the WRIST -- came to be listed as
    drafting a short sleeve (decision #35)."""
    from body_measure.spec import load_spec

    spec = load_spec()
    for requirement in POLO_REQUIREMENTS:
        if requirement.provision == "spec":
            assert spec.measurements[requirement.key].priority == "core", (
                f"{requirement.key} is {spec.measurements[requirement.key].priority}"
                " in the spec but required by the polo gate")


def test_a_short_sleeves_length_is_named_as_a_design_choice():
    readiness = assess(measured())
    joined = " ".join(readiness.notes)
    assert "chosen, not measured" in joined
    assert "sleeve_length" not in {r.key for r in POLO_REQUIREMENTS}


# -------------------------------------------------------------- verdict ---
def test_a_body_missing_a_dimension_is_not_ready():
    assert assess(measured()).verdict == NOT_READY


def test_complete_unverified_is_reachable_when_everything_is_draftable():
    """Constructed with a requirement list of one so the verdict logic
    itself can be exercised; the polo list cannot reach it today."""
    from body_measure.pattern_readiness import BY_ANATOMY

    one = (Requirement("chest_circumference", "chest girth", "body width",
                       "spec", BY_ANATOMY, "test"),)
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
         "--input-unit", "m", "--up-axis", "Z", "--estimate", "--skip-pose-gate",
         "--pattern", "polo", "--out", str(out)],
        capture_output=True, text=True, encoding="utf-8", cwd=PROJECT_ROOT)
    assert proc.returncode == 0, proc.stderr
    block = json.loads(out.read_text(encoding="utf-8"))["meta"]["pattern_readiness"]
    assert block["verdict"] in (NOT_READY, COMPLETE_UNVERIFIED)
    assert block["n_required"] == len(POLO_REQUIREMENTS)
    for entry in block["requirements"]:
        assert entry["requirement_source"]
        assert entry["measures_on_the_body"] and entry["feeds"]
        assert entry["measured_at"] in ("anatomy", "design_parameter")
    assert block["notes"]


def test_the_cli_refuses_readiness_without_estimate(body_like_ply):
    proc = subprocess.run(
        [PYTHON, "-m", "body_measure", "measure", str(body_like_ply),
         "--input-unit", "m", "--up-axis", "Z", "--pattern", "polo"],
        capture_output=True, text=True, encoding="utf-8", cwd=PROJECT_ROOT)
    assert proc.returncode == 1
    assert "--estimate" in proc.stderr
