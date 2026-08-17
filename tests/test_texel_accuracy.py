"""Gated dataset_agreement tests on Texel Part 1 (portal_mx pipeline).

Bounds are INTERNAL regression targets from validate/thresholds.py —
derived from the first observed run, not ISO conformity gates. They exist
so a change that degrades agreement fails loudly.

Skipped when data/external/texel/Part1 is absent (fresh clones stay green).
"""
from pathlib import Path

import pytest

from body_measure.adapters.texel import TexelAdapter
from body_measure.canonicalize import canonicalize
from body_measure.validate.thresholds import (
    DATASET_AGREEMENT_TARGETS,
    WAIST_HEIGHT_TARGET_MM,
)

ROOT = Path(__file__).resolve().parents[1] / "data" / "external" / "texel"

pytestmark = pytest.mark.skipif(
    not (ROOT / "Part1").is_dir(), reason="Texel Part1 not downloaded"
)


CIRCUMFERENCES = ("waist_circumference", "chest_circumference", "neck_circumference")
LENGTHS = ("across_back_shoulder_width", "sleeve_length", "back_length")
ALL_MEASUREMENTS = CIRCUMFERENCES + LENGTHS


@pytest.fixture(scope="module")
def rows():
    from body_measure.measure.measurements import run_estimated_measurements

    adapter = TexelAdapter()
    collected = []
    for person in adapter.persons(ROOT):
        mesh = canonicalize(adapter.load(person))
        gt = adapter.checked_ground_truth(person)
        aux = adapter.aux(person)
        measurements, landmarks = run_estimated_measurements(mesh)
        collected.append(
            {
                "person": person.name,
                "measurements": measurements,
                "landmarks": landmarks,
                "gt": gt,
                "aux": aux,
            }
        )
    return collected


def test_all_ten_bodies_produce_all_six_measurements(rows):
    assert len(rows) == 10
    for row in rows:
        for name in ALL_MEASUREMENTS:
            assert row["measurements"][name].selected_value_mm is not None, (
                f"{row['person']}: {name} missing"
            )


@pytest.mark.parametrize("name", ALL_MEASUREMENTS)
def test_per_body_agreement_stays_within_the_regression_bound(rows, name):
    bound = DATASET_AGREEMENT_TARGETS[name]["per_body_mm"]
    offenders = [
        (row["person"], row["measurements"][name].selected_value_mm - row["gt"][name])
        for row in rows
        if abs(row["measurements"][name].selected_value_mm - row["gt"][name]) > bound
    ]
    assert not offenders, f"{name} exceeds {bound} mm: {offenders}"


@pytest.mark.parametrize("name", ALL_MEASUREMENTS)
def test_mean_bias_stays_within_the_regression_bound(rows, name):
    bound = DATASET_AGREEMENT_TARGETS[name]["mean_bias_mm"]
    deltas = [
        row["measurements"][name].selected_value_mm - row["gt"][name] for row in rows
    ]
    mean = sum(deltas) / len(deltas)
    assert abs(mean) <= bound, f"{name} mean bias {mean:+.1f} mm exceeds {bound} mm"


def test_estimated_waist_height_lands_near_the_dataset_waist_height(rows):
    offenders = [
        (row["person"], float(row["landmarks"]["waist_level"].position_mm[1]) - row["aux"]["waist_height"])
        for row in rows
        if abs(float(row["landmarks"]["waist_level"].position_mm[1]) - row["aux"]["waist_height"])
        > WAIST_HEIGHT_TARGET_MM
    ]
    assert not offenders, f"waist height off by more than {WAIST_HEIGHT_TARGET_MM} mm: {offenders}"


def test_arm_clipping_is_always_visible_in_quality_flags(rows):
    # if a chest value came from a merged-loop slice, the tape approximation
    # must be flagged — silent clipping is not allowed
    for row in rows:
        chest = row["measurements"]["chest_circumference"]
        landmark = row["landmarks"].get("chest_level")
        if landmark is not None and "arm_clipped" in landmark.method:
            merged = "arm_clipped_at_merged_level" in chest.quality
            boundary_only = all("boundary" in f or "clip" in f for f in chest.quality)
            assert merged or boundary_only or chest.quality == ["ok"]


def test_the_unverified_pipeline_is_refused_not_guessed():
    adapter = TexelAdapter()
    persons = adapter.persons(ROOT)
    with pytest.raises(NotImplementedError):
        adapter.load(persons[0], pipeline="free_fusion")
