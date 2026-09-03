"""The natural waist is the middle of a band, not the narrowest slice
(decision #47). Gated on the generated SMPL bodies; the Texel numbers
live in the validation report, not here."""
from pathlib import Path

import numpy as np
import pytest

from body_measure.adapters.mesh_file import MeshFileAdapter
from body_measure.canonicalize import canonicalize
from body_measure.landmarks.estimated import (
    estimate_armpit_level, estimate_back_landmarks, estimate_waist_band, provided_facing)
from body_measure.measure.measurements import run_estimated_measurements

GENERATED = Path(__file__).resolve().parents[1] / "data" / "generated"
pytestmark = pytest.mark.skipif(
    not (GENERATED / "smpl_rand1_apose.obj").exists(), reason="generated SMPL bodies absent")
SMPL_FACING = provided_facing((0.0, 1.0), source="smpl_frame")


def _body(name):
    return canonicalize(MeshFileAdapter().load(GENERATED / f"{name}.obj", unit="m"))


def test_the_waist_is_the_midpoint_of_its_two_bounds():
    mesh = _body("smpl_neutral0_apose")
    band = estimate_waist_band(mesh, estimate_armpit_level(mesh), facing=SMPL_FACING)
    assert {"waist_level", "girth_minimum_level", "lumbar_concavity_level",
            "buttock_prominence_level"} <= set(band)
    top = band["girth_minimum_level"].position_mm[1]
    bottom = band["lumbar_concavity_level"].position_mm[1]
    assert bottom < band["waist_level"].position_mm[1] < top
    assert band["waist_level"].position_mm[1] == pytest.approx(0.5 * (top + bottom))
    assert band["waist_level"].method == "natural_waist_midpoint_of_girth_minimum_and_lumbar_concavity"


def test_a_body_with_no_narrowing_takes_the_lumbar_concavity_alone():
    """smpl_rand1's belly hangs past its hips: the girth rises all the way
    from the crotch to the chest, so the 'minimum' is the search floor.
    That is not a waist, and the band says so."""
    mesh = _body("smpl_rand1_apose")
    band = estimate_waist_band(mesh, estimate_armpit_level(mesh), facing=SMPL_FACING)
    assert "minimum_at_search_boundary" in band["girth_minimum_level"].quality_flags
    waist = band["waist_level"]
    assert waist.method == "natural_waist_lumbar_concavity_only"
    assert waist.position_mm[1] == band["lumbar_concavity_level"].position_mm[1]
    assert "girth_minimum_at_search_boundary_not_a_narrowing" in waist.quality_flags
    # reported by a reviewer: navel near 1178 mm, hips between 920 and 1120
    assert 1150 < waist.position_mm[1] < 1260
    assert 920 < band["buttock_prominence_level"].position_mm[1] < 1120


def test_the_hip_sits_at_the_buttocks_not_the_belly():
    from body_measure.garment_prototypes import run_prototypes
    mesh = _body("smpl_rand1_apose")
    measurements, landmarks = run_estimated_measurements(mesh, facing=SMPL_FACING)
    hip = run_prototypes(mesh, measurements, landmarks)["hip_girth"]
    assert hip.available and 920 < hip.level_mm < 1120
    assert "buttocks" in hip.note


def test_without_an_orientation_the_girth_minimum_is_used_and_flagged():
    mesh = _body("smpl_neutral0_apose")
    band = estimate_waist_band(mesh, estimate_armpit_level(mesh), facing=None)
    waist = band["waist_level"]
    assert waist.method == "minimum_torso_circumference"
    assert any(f.startswith("lumbar_concavity_unavailable") for f in waist.quality_flags)
    assert estimate_back_landmarks(mesh, estimate_armpit_level(mesh), None) == (None, None)


def test_the_measured_waist_moves_down_from_the_narrowing():
    """On every A-pose body the narrowing under the ribs sits above the
    natural waist, so v2's waist is lower than v1's and its girth larger."""
    mesh = _body("smpl_rand6_apose")
    band = estimate_waist_band(mesh, estimate_armpit_level(mesh), facing=SMPL_FACING)
    assert band["waist_level"].position_mm[1] < band["girth_minimum_level"].position_mm[1]
    measurements, landmarks = run_estimated_measurements(mesh, facing=SMPL_FACING)
    assert landmarks["waist_level"].position_mm[1] == pytest.approx(band["waist_level"].position_mm[1])
    assert measurements["waist_circumference"].selected_value_mm is not None
