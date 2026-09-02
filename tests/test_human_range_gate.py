"""The human-range gate (decision #39).

Two values reached `accepted` that no body could have — a 140.9 mm waist
and a 3808 mm chest — and both are pinned here as the cases that must now
be refused. What is pinned just as hard is that the gate REFUSES rather
than corrects, and that a value inside its range is left exactly as it
was: a last-line check that quietly edited numbers would be worse than
none.
"""
from dataclasses import asdict

import pytest

from body_measure.measure.range_gate import NO_RANGE, OUTSIDE_RANGE, gate_human_range
from body_measure.result import MeasurementValue
from body_measure.spec import Spec, SpecError, load_spec, _parse_plausible_mm


def value(mm, *, disposition="accepted", quality=("ok",), raw=None):
    return MeasurementValue(
        selected_value_mm=mm,
        raw_contour_mm=raw,
        method="plane_slice",
        quality=list(quality),
        disposition=disposition,
    )


# ------------------------------------------------------------- the spec ---
def test_every_measurement_carries_a_bound():
    for name, entry in load_spec().measurements.items():
        assert entry.plausible_mm is not None, name
        lo, hi = entry.plausible_mm
        assert 0.0 <= lo < hi, (name, lo, hi)


def test_a_malformed_bound_is_refused_not_ignored():
    for bad in ([1600, 600], [600], [600, 900, 1200], ["a", "b"], [-1, 500]):
        with pytest.raises(SpecError):
            _parse_plausible_mm("x", bad)
    assert _parse_plausible_mm("x", None) is None
    assert _parse_plausible_mm("x", [600, 1600]) == (600.0, 1600.0)


# -------------------------------------------------------- what it stops ---
def test_a_wrist_sized_waist_is_refused():
    """Decision #22's 140.9 mm: a jacket-fold loop won a minimum."""
    got = gate_human_range({"waist_circumference": value(140.9, raw=141.5)})
    waist = got["waist_circumference"]
    assert waist.selected_value_mm is None
    assert waist.disposition == "rejected"
    assert OUTSIDE_RANGE in waist.quality
    assert "raw_value_141mm" in waist.quality
    # the number stays readable for diagnosis, just not as a measurement
    assert waist.raw_contour_mm == 141.5


def test_a_chest_around_two_outstretched_arms_is_refused():
    """Decision #34's 3808 mm, from a correctly selected loop on a T-posed
    body. No trust rule can catch this one; only a range can."""
    got = gate_human_range({"chest_circumference": value(3808.0)})
    chest = got["chest_circumference"]
    assert chest.selected_value_mm is None
    assert chest.disposition == "rejected"
    assert "raw_value_3808mm" in chest.quality


def test_it_refuses_a_value_it_was_already_asked_to_review():
    got = gate_human_range({"waist_circumference": value(
        140.9, disposition="manual_review", quality=["some_flag"])})
    assert got["waist_circumference"].disposition == "rejected"


# ------------------------------------------------------- what it leaves ---
def test_a_normal_value_is_untouched():
    before = value(949.0)
    snapshot = asdict(before)
    gate_human_range({"waist_circumference": before})
    assert asdict(before) == snapshot


def test_a_clothed_girth_is_not_punished_for_being_inflated():
    got = gate_human_range({"chest_circumference": value(1336.0)})
    assert got["chest_circumference"].selected_value_mm == 1336.0


def test_a_null_passes_through_without_a_new_flag():
    got = gate_human_range({"waist_circumference": value(None)})
    assert got["waist_circumference"].quality == ["ok"]


def test_it_is_idempotent():
    once = gate_human_range({"waist_circumference": value(140.9)})
    flags = list(once["waist_circumference"].quality)
    twice = gate_human_range(once)
    assert twice["waist_circumference"].quality == flags


def test_a_measurement_the_spec_does_not_bound_says_so():
    spec = load_spec()
    stripped = Spec(
        version=spec.version, standard=spec.standard,
        measurements={n: type(m)(**{**{f: getattr(m, f) for f in m.__dataclass_fields__},
                                    "plausible_mm": None})
                      for n, m in spec.measurements.items()},
    )
    got = gate_human_range({"waist_circumference": value(140.9)}, stripped)
    waist = got["waist_circumference"]
    assert waist.selected_value_mm == 140.9      # not refused without a bound
    assert NO_RANGE in waist.quality


# --------------------------------------------------------- end to end -----
def test_the_public_pathway_gates_and_the_private_one_does_not():
    """The gate sits on the way out of the core, so a caller cannot get an
    ungated number by accident — but the producers stay reachable for
    diagnosis, which is how the two absurdities were characterised."""
    import numpy as np
    import trimesh

    from body_measure.measure import measurements as M

    torso = trimesh.creation.cylinder(radius=150.0, height=1600.0, sections=96)
    torso.apply_transform(np.array([[1, 0, 0, 0], [0, 0, 1, 0],
                                    [0, -1, 0, 0], [0, 0, 0, 1]], dtype=float))
    torso.apply_translation([0.0, -torso.bounds[0][1], 0.0])

    spec = load_spec()
    narrow = Spec(
        version=spec.version, standard=spec.standard,
        measurements={n: type(m)(**{**{f: getattr(m, f) for f in m.__dataclass_fields__},
                                    "plausible_mm": (0.1, 1.0)})
                      for n, m in spec.measurements.items()},
    )
    gated, _ = M.run_estimated_measurements(torso, spec=narrow)
    for name, got in gated.items():
        if got.selected_value_mm is not None:
            pytest.fail(f"{name} survived a 0.1-1.0 mm bound")
    assert any(OUTSIDE_RANGE in got.quality for got in gated.values())
