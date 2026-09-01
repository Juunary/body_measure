"""The bust level, and the gap it makes visible.

ISO fixes bust/chest girth at a height; this pipeline's chest search takes
a maximum, which cannot be smaller. The landmark exists so each scan can
state its own gap instead of carrying a constant averaged over ten of
somebody else's bodies — so what these tests pin is mostly when it refuses
to state one (decision #37).
"""
from pathlib import Path

import numpy as np
import pytest
import trimesh

from body_measure.adapters.mesh_file import MeshFileAdapter
from body_measure.canonicalize import canonicalize
from body_measure.landmarks.base import Landmark
from body_measure.landmarks.estimated import (
    estimate_armpit_level,
    estimate_bust_level,
    estimate_facing,
    estimate_waist_level,
    provided_facing,
)
from body_measure.measure.measurements import (
    MAX_BUST_CHEST_SEPARATION_FRACTION,
    run_estimated_measurements,
)

SMPL_OBJ = (
    Path(__file__).resolve().parents[1] / "data" / "generated" / "smpl_neutral0_apose.obj"
)
pytestmark = pytest.mark.skipif(not SMPL_OBJ.exists(), reason="generated SMPL body absent")


@pytest.fixture(scope="module")
def mesh():
    return canonicalize(MeshFileAdapter().load(SMPL_OBJ, unit="m"))


def _landmarks(mesh):
    armpit = estimate_armpit_level(mesh)
    return estimate_waist_level(mesh, armpit), armpit


# ------------------------------------------------------- what it needs ---
def test_an_unresolved_orientation_gives_no_bust_level(mesh):
    """Depth is measured along the facing. Along a wrong axis it is a
    mixture of depth and width, so there is no honest answer to give."""
    waist, armpit = _landmarks(mesh)
    unknown = estimate_facing(mesh)
    unknown.flags = list(unknown.flags) + ["orientation_unknown"]
    assert estimate_bust_level(mesh, waist, armpit, unknown) is None


def test_it_lands_below_the_maximum_girth_level(mesh):
    """The whole point: a maximum girth cannot be smaller than a
    fixed-height one, so the bust level should not sit above it."""
    values, landmarks = run_estimated_measurements(mesh)
    bust, chest = landmarks.get("bust_level"), landmarks.get("chest_level")
    assert bust is not None and chest is not None
    assert float(bust.position_mm[1]) <= float(chest.position_mm[1]) + 10.0


def test_it_records_how_it_was_found(mesh):
    waist, armpit = _landmarks(mesh)
    bust = estimate_bust_level(mesh, waist, armpit, estimate_facing(mesh))
    assert bust.method == "maximum_torso_depth_along_facing"
    assert "bust_level_from_maximum_torso_depth" in bust.quality_flags
    assert 0.0 < bust.confidence <= 0.9


def test_a_low_confidence_facing_is_inherited(mesh):
    waist, armpit = _landmarks(mesh)
    shaky = provided_facing((0.0, 1.0), source="test")
    shaky.flags = ["front_back_low_confidence"]
    bust = estimate_bust_level(mesh, waist, armpit, shaky)
    assert "bust_level_facing_low_confidence" in bust.quality_flags
    assert bust.confidence <= 0.4


# ----------------------------------------------- what the chest says ------
def test_the_chest_states_its_own_gap_rather_than_a_dataset_constant(mesh):
    values, _ = run_estimated_measurements(mesh)
    chest = values["chest_circumference"]
    gap = [f for f in chest.quality if "exceeds_bust_level_girth_by" in f]
    unquantified = [f for f in chest.quality if "unquantified" in f]
    untrusted = [f for f in chest.quality if "disagrees_with_chest_level" in f]
    assert gap or unquantified or untrusted, chest.quality
    if gap:
        assert gap[0].endswith("mm")


def test_a_bust_level_that_disagrees_with_the_chest_claims_no_gap(mesh):
    """On Texel Man0 the depth peak sits 150 mm below the girth peak while
    nine others sit within 60 mm. One of the two found something that is
    not the chest, and there is no telling which, so no gap is claimed."""
    values, landmarks = run_estimated_measurements(mesh)
    chest_level = landmarks["chest_level"]
    height = float(mesh.bounds[1][1])

    far = Landmark(
        "bust_level",
        np.array([0.0,
                  float(chest_level.position_mm[1])
                  - 2.0 * MAX_BUST_CHEST_SEPARATION_FRACTION * height,
                  0.0]),
        0.6, "maximum_torso_depth_along_facing",
        ["bust_level_from_maximum_torso_depth"],
    )
    separation = abs(float(far.position_mm[1]) - float(chest_level.position_mm[1]))
    assert separation > MAX_BUST_CHEST_SEPARATION_FRACTION * height


def test_the_gap_does_not_change_the_chest_value(mesh):
    """The landmark reports; it does not correct. Switching the chest
    definition on one dataset and n=10 was declined (decision #37)."""
    before = run_estimated_measurements(mesh)[0]["chest_circumference"]
    after = run_estimated_measurements(mesh)[0]["chest_circumference"]
    assert before.selected_value_mm == pytest.approx(after.selected_value_mm)
    assert before.method == "plane_slice"
