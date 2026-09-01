"""Size assignment — the end of the pipeline.

A size is the first output of this project a customer would ever see, so
the rules that keep it honest are worth pinning: it comes from a cited
chart, it comes from a body rather than a garment, it refuses rather than
extrapolates, and a chest sitting on a band edge says so instead of
picking a side the measurement error cannot support.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
import trimesh

from body_measure.result import MeasurementValue
from body_measure.sizing import (
    BOUNDARY_MARGIN_MM,
    CHARTS,
    EN_13402_3,
    LACOSTE_MEN,
    assign,
)

PYTHON = sys.executable
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def chest(value_mm, *, quality=("ok",), disposition="accepted"):
    return {"chest_circumference": MeasurementValue(
        selected_value_mm=value_mm, method="plane_slice",
        quality=list(quality), disposition=disposition)}


# ------------------------------------------------------------- the bands ---
@pytest.mark.parametrize("chest_cm, expected", [
    (88.0, "S"), (94.5, "M"), (101.9, "M"), (105.0, "L"), (114.0, "XL"), (125.0, "XXL"),
])
def test_a_chest_lands_in_its_band(chest_cm, expected):
    result = assign(chest(chest_cm * 10.0), population="men")
    assert result.label == expected


def test_the_bands_are_ordered_and_never_overlap():
    """An overlap would make the assignment depend on iteration order.
    A gap is allowed — the published women's table has one — but it must
    be a gap, not a reversal."""
    for chart in CHARTS.values():
        for lower, upper in zip(chart.bands, chart.bands[1:]):
            assert lower.chest_min_cm < lower.chest_max_cm
            assert lower.chest_max_cm <= upper.chest_min_cm


def test_the_womens_table_gap_is_recorded_not_smoothed():
    """EN 13402-3's women's table leaves 106-107 cm uncovered. Closing it
    would make the table tidier and no longer the published table, so a
    bust in the gap is refused with that as the reason."""
    from body_measure.sizing import EN_13402_3_WOMEN

    labels = {b.label: (b.chest_min_cm, b.chest_max_cm) for b in EN_13402_3_WOMEN.bands}
    assert labels["L"][1] == 106.0 and labels["XL"][0] == 107.0

    result = assign(chest(1065.0), chart=EN_13402_3_WOMEN, population="women")
    assert not result.assigned
    assert "between_bands" in result.flags
    assert "gap" in result.reason


def test_the_womens_chart_sizes_a_womans_body():
    from body_measure.sizing import EN_13402_3_WOMEN

    result = assign(chest(900.0), chart=EN_13402_3_WOMEN, population="women")
    assert result.label == "M"


def test_every_assignment_says_which_way_the_definition_gap_runs():
    """"Approximate" does not tell a reader whether the label is likely one
    size high or one size low. The gap is measured and signed: this
    pipeline's maximum sits ~42 mm above the height the reference matches
    and reads ~27 mm high, a third of an 80 mm band (decision #36)."""
    result = assign(chest(1000.0), population="men")
    signed = [f for f in result.flags if "reads_high" in f]
    assert signed, result.flags
    assert "27mm" in signed[0] and "texel" in signed[0]


def test_every_assignment_carries_the_iso_definition_caveat():
    """chest_circumference maps to ISO m5 'Bust/Chest Girth' only
    approximately — ISO fixes the height at the bust point, this pipeline
    searches for the maximum. Every size says so."""
    for chart_key, population in (("en13402", "men"), ("en13402-women", "women")):
        result = assign(chest(950.0), chart=CHARTS[chart_key], population=population)
        assert "chest_definition_approximate_iso_m5" in result.flags


def test_every_chart_states_its_source_and_what_it_measures():
    for chart in CHARTS.values():
        assert chart.source and chart.checked
        assert chart.dimension_kind == "body"
        assert chart.population in ("men", "women")


# ---------------------------------------------------------- the refusals ---
def test_a_clothed_scan_gets_no_size():
    """The girth of a dressed subject is the garment's."""
    result = assign(chest(1000.0), pathway="measured_clothed", population="men")
    assert not result.assigned
    assert "clothed_pathway" in result.flags


def test_a_chest_outside_the_chart_is_refused_not_extrapolated():
    for value in (700.0, 1400.0):
        result = assign(chest(value), population="men")
        assert not result.assigned
        assert "outside the chart" in result.reason


def test_a_measurement_the_pipeline_rejected_cannot_carry_a_size():
    for disposition in ("rejected", "manual_review"):
        result = assign(chest(1000.0, disposition=disposition), population="men")
        assert not result.assigned
        assert disposition in result.reason


def test_a_missing_chest_gets_no_size():
    assert not assign(chest(None), population="men").assigned
    assert not assign({}, population="men").assigned


def test_a_womans_body_is_refused_by_a_mens_chart():
    """EN 13402 designates the same letter by bust girth for women and
    chest girth for men, so the band would be read off the wrong
    dimension — not merely a size out."""
    result = assign(chest(900.0), population="women")
    assert not result.assigned
    assert "population_mismatch" in result.flags


def test_an_unstated_population_is_flagged_rather_than_assumed():
    result = assign(chest(1000.0))
    assert result.assigned
    assert any(f.startswith("population_unverified") for f in result.flags)


# ---------------------------------------------------------- the boundary ---
def test_a_chest_on_a_band_edge_names_the_other_size_too():
    """940 mm is the S/M edge, and this pipeline's girth error is larger
    than the distance to it."""
    result = assign(chest(940.0 + BOUNDARY_MARGIN_MM / 2), population="men")
    assert result.label == "M"
    assert result.alternative == "S"
    assert "near_size_boundary" in result.flags


def test_a_chest_well_inside_a_band_names_only_one_size():
    result = assign(chest(980.0), population="men")
    assert result.label == "M"
    assert result.alternative is None
    assert "near_size_boundary" not in result.flags


def test_the_lowest_and_highest_bands_have_no_outward_neighbour():
    low = assign(chest(EN_13402_3.bands[0].chest_min_cm * 10.0), population="men")
    high = assign(chest(EN_13402_3.bands[-1].chest_max_cm * 10.0), population="men")
    assert low.label == "S" and low.alternative is None
    assert high.label == "XXL" and high.alternative is None


def test_the_brand_chart_agrees_with_the_standard_on_the_size_taken():
    """The cross-check is only useful while it agrees; if Lacoste's bands
    are ever changed to real per-size cut points this will say so."""
    for value_mm in (880.0, 980.0, 1050.0, 1140.0, 1250.0):
        standard = assign(chest(value_mm), chart=EN_13402_3, population="men")
        brand = assign(chest(value_mm), chart=LACOSTE_MEN, population="men")
        # the brand labels its bands "3 (S)", "4 (M)" and so on, so the
        # standard's letter is contained in, not equal to, the brand's
        assert f"({standard.label})" in brand.label


# ---------------------------------------------------------------- the CLI ---
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


def test_the_cli_records_the_size_with_its_source(body_like_ply, tmp_path):
    out = tmp_path / "r.json"
    proc = subprocess.run(
        [PYTHON, "-m", "body_measure", "measure", str(body_like_ply),
         "--input-unit", "m", "--up-axis", "Z", "--estimate",
         "--size-chart", "en13402", "--out", str(out)],
        capture_output=True, text=True, encoding="utf-8", cwd=PROJECT_ROOT)
    assert proc.returncode == 0, proc.stderr
    size = json.loads(out.read_text(encoding="utf-8"))["meta"]["size"]
    assert size["chart"] == "en13402"
    assert size["chart_source"] and size["chart_checked"]
    assert size["dimension_kind"] == "body"
    assert "reason" in size


def test_the_cli_refuses_a_size_without_estimate(body_like_ply):
    proc = subprocess.run(
        [PYTHON, "-m", "body_measure", "measure", str(body_like_ply),
         "--input-unit", "m", "--up-axis", "Z", "--size-chart", "en13402"],
        capture_output=True, text=True, encoding="utf-8", cwd=PROJECT_ROOT)
    assert proc.returncode == 1
    assert "--estimate" in proc.stderr
