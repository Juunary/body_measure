"""HSRD is the clothed-scan skeleton's only dataset until SIZER clears
licence review. These tests fix the two things that must not drift: it
ships no body reference, so no offset may be emitted; and a clothed scan
is taller than its subject, so unit verification must be one-sided."""
import importlib.util
from pathlib import Path

import pytest

from body_measure.adapters.hsrd import (
    STATURE_TOLERANCE_HIGH,
    STATURE_TOLERANCE_LOW,
    HsrdAdapter,
)
from body_measure.validate.claims import REFERENCE_KINDS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HSRD_ROOT = PROJECT_ROOT / "data" / "external" / "hsrd"

SCRIPT = PROJECT_ROOT / "scripts" / "clothing_offset_report.py"
_spec = importlib.util.spec_from_file_location("clothing_offset_report", SCRIPT)
report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report)


# ------------------------------------------------ no-data tests (always) ---
def test_hsrd_declares_no_measurement_and_no_body_reference():
    adapter = HsrdAdapter(HSRD_ROOT)
    assert adapter.provides == frozenset()
    assert adapter.fit_references == frozenset()


def test_no_offset_claim_is_emitted_without_a_reference():
    block = report.offset_block(reference_available=False)
    assert block["status"] == "unavailable"
    assert block["claim_category"] is None
    assert block["reference_kind"] is None
    assert "reason" in block
    # the report still records what the claim WOULD be, so the wording is
    # fixed in advance rather than invented once SIZER lands
    assert block["would_be_claim_with_a_minimal_scan"] == "clothing_offset"


def test_an_offset_claim_names_its_reference_when_one_exists():
    block = report.offset_block(reference_available=True)
    assert block["status"] == "available"
    assert block["claim_category"] == "clothing_offset"
    assert block["reference_kind"] in REFERENCE_KINDS


def test_stature_tolerance_is_one_sided_because_boots_add_height():
    # a clothed scan may be much taller than the person, never much shorter
    assert STATURE_TOLERANCE_HIGH - 1.0 > 1.0 - STATURE_TOLERANCE_LOW


def test_implausible_catches_a_wrist_sized_waist():
    assert report.implausible("waist_circumference", 140.9) is True
    assert report.implausible("waist_circumference", 949.0) is False
    # a clothed girth is inflated; the range must not punish that
    assert report.implausible("chest_circumference", 1336.0) is False
    assert report.implausible("waist_circumference", None) is False


def test_every_spec_measurement_has_a_plausible_range():
    from body_measure.spec import load_spec

    assert set(report.PLAUSIBLE_MM) == set(load_spec().names)


# --------------------------------------------------- gated on real data ---
needs_hsrd = pytest.mark.skipif(
    not HSRD_ROOT.is_dir(), reason="HSRD not downloaded"
)


@needs_hsrd
def test_the_unit_is_verified_against_the_recorded_stature():
    adapter = HsrdAdapter(HSRD_ROOT)
    surface = adapter.load(adapter.observations()[0])
    assert surface.meta["verified_unit"] == "m"
    # the scan is taller than the person, and by how much is recorded
    assert surface.meta["stature_excess_mm"] > 0


@needs_hsrd
def test_garment_metadata_is_read_from_the_shipped_spelling():
    adapter = HsrdAdapter(HSRD_ROOT)
    garment = adapter.garment_description(adapter.observations()[0])
    # shipped JSON uses "Upper Body Clothing", not the web API's snake_case
    assert garment["upper"] == "Jacket"
    assert garment["lower"] == "Jeans"
    assert garment["footwear"] == "Boots"


@needs_hsrd
def test_a_clothed_scan_yields_a_canonical_upright_body():
    from body_measure.canonicalize import canonicalize

    adapter = HsrdAdapter(HSRD_ROOT)
    mesh = canonicalize(adapter.load(adapter.observations()[0]))
    extent = mesh.bounds[1] - mesh.bounds[0]
    # Y must be the long axis after canonicalisation (source ships Z-up)
    assert extent[1] == max(extent)
    assert abs(mesh.bounds[0][1]) < 1e-6  # floor at y=0
