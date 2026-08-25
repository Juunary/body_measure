"""The chest profile must be measured one way, not two.

Two methods produce a chest sample — the torso loop measured directly
when the arms are their own loops, and the merged loop clipped at the
armpit's lateral extent when they are not. They measure different things,
so a max taken across a mixture answers "which method returned the
larger number", not "where is the chest". Decision #22 forbade exactly
this for the waist; these tests hold the same line for the chest."""
import numpy as np
import pytest

from body_measure.measure.measurements import _merge_index

from tests.test_hsrd_clothed import HSRD_ROOT, needs_hsrd


# ----------------------------------------------------- the merge split ---
def test_a_clean_profile_splits_where_it_flips():
    # arms separate below, merged above — the shape every unclothed body
    # in the Texel set actually has
    assert _merge_index([True, True, True, False, False]) == 3
    assert _merge_index([True, False]) == 1


def test_arms_never_merging_means_no_clipping():
    assert _merge_index([True, True, True]) == 3   # == len: clip nothing


def test_arms_merged_throughout_clips_everything():
    assert _merge_index([False, False, False]) == 0


def test_an_empty_profile_is_handled():
    assert _merge_index([]) == 0


def test_a_noisy_profile_still_yields_one_split():
    # a jacket sleeve touching and leaving the torso: the split is the
    # least-wrong single flip, and it is always a single flip
    noisy = [True, False, True, True, False, False, False]
    index = _merge_index(noisy)
    assert 0 <= index <= len(noisy)
    # by construction the result maximises agreement with "separate below,
    # merged above" — no other split can score higher
    def score(i):
        return sum(noisy[:i]) + sum(1 for v in noisy[i:] if not v)
    assert score(index) == max(score(i) for i in range(len(noisy) + 1))


# --------------------------------------------------------- HSRD gates ---
@needs_hsrd
def test_a_jacket_flags_its_unstable_arm_merge():
    """HSRD's raw sequence flips eight times at both LODs — the sleeve
    touches and leaves the torso as the triangulation falls. The number
    may still be produced, but it may not present as clean."""
    from body_measure.adapters.hsrd import HsrdAdapter
    from body_measure.canonicalize import canonicalize
    from body_measure.measure.measurements import run_estimated_measurements
    from body_measure.validate.stats import quality_bucket

    adapter = HsrdAdapter(HSRD_ROOT)
    for observation in adapter.observations():
        mesh = canonicalize(adapter.load(observation))
        measurements, _ = run_estimated_measurements(mesh)
        chest = measurements["chest_circumference"]
        assert chest.selected_value_mm is not None
        assert "arm_merge_height_unstable" in chest.quality
        assert quality_bucket(chest) != "clean"


@needs_hsrd
def test_an_untrusted_armpit_disables_clipping_rather_than_using_bad_bounds():
    """lod2's armpit is confidence 0.4 and gave a 289 mm clip window
    against lod1's 420 mm. Bounds that wrong must not be used at all."""
    from body_measure.adapters.hsrd import HsrdAdapter
    from body_measure.canonicalize import canonicalize
    from body_measure.landmarks.estimated import estimate_armpit_level
    from body_measure.measure.measurements import run_estimated_measurements

    adapter = HsrdAdapter(HSRD_ROOT)
    seen = 0
    for observation in adapter.observations():
        mesh = canonicalize(adapter.load(observation))
        armpit = estimate_armpit_level(mesh)
        if armpit is None or armpit.confidence >= 0.5:
            continue
        measurements, _ = run_estimated_measurements(mesh)
        chest = measurements["chest_circumference"]
        assert "clip_bounds_untrusted_low_confidence_armpit" in chest.quality
        assert "arm_clipped_at_merged_level" not in chest.quality
        seen += 1
    assert seen > 0, "expected at least one low-confidence armpit in HSRD"
