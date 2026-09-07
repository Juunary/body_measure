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
    EN_13402_3_WOMEN,
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
    # 1439 mm is smpl_rand1's chest — the body decision #50 was asked for
    # and still does not size, since the page's last row ends at 141 cm
    for value in (700.0, 1439.0):
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
    assert low.label == EN_13402_3.bands[0].label and low.alternative is None
    assert high.label == EN_13402_3.bands[-1].label and high.alternative is None


@pytest.mark.parametrize("chest_cm, label, alternative", [
    # the S/M edge is 94, exclusive on S's side: [86, 94) then [94, 102)
    (93.0, "S", "M"),     # window 92-94 reaches M, which begins AT 94
    (94.0, "M", "S"),     # window 93-95 reaches S, which runs up to 94
    (95.0, "M", None),    # window 94-96: 94 is already M, S ends below it
])
def test_the_alternative_is_a_band_the_error_window_reaches(chest_cm, label, alternative):
    """Decision #49. 95.0 is exactly the margin from the edge and used to
    name S; a measurement of 95 +/- 1 cm is 94 at its lowest, and 94 is
    M. The window has to overlap the neighbour, not merely approach it."""
    result = assign(chest(chest_cm * 10.0), population="men")
    assert result.label == label
    assert result.alternative == alternative
    assert ("near_size_boundary" in result.flags) == (alternative is not None)


@pytest.mark.parametrize("chest_cm, label, alternative", [
    (105.5, "L", None),   # 5 mm from L's edge, but XL starts 15 mm away
    (107.5, "XL", None),  # 5 mm from XL's start, but L ended 15 mm below
    (105.0, "L", None),   # window 104-106: 106 is not in L and not in XL
    (108.0, "XL", None),  # window 107-109: 107 is XL's own start
])
def test_no_alternative_reaches_across_the_womens_gap(chest_cm, label, alternative):
    """Before #49 both 105.5 and 107.5 named the band on the far side of
    the 106-107 gap as 'equally defensible', when no measurement within
    the margin could land there."""
    result = assign(chest(chest_cm * 10.0), chart=EN_13402_3_WOMEN, population="women")
    assert result.label == label
    assert result.alternative is alternative
    assert "near_size_boundary" not in result.flags


def test_the_gap_itself_is_still_refused():
    """Unchanged by #49: the bands and the refusal policy are as before."""
    for chest_cm in (106.0, 106.5, 106.9):
        result = assign(chest(chest_cm * 10.0), chart=EN_13402_3_WOMEN, population="women")
        assert not result.assigned
        assert "between_bands" in result.flags


@pytest.mark.parametrize("chest_cm, label, alternative", [
    (141.0, "3XL", None),   # the last band's top edge is inclusive
    (140.5, "3XL", None),   # nothing above 3XL to be an alternative
    (129.0, "3XL", "XXL"),  # 129 is 3XL's start; window 128-130 reaches XXL
    (128.5, "XXL", "3XL"),  # window 127.5-129.5 reaches 3XL at 129
    (130.0, "3XL", None),   # window 129-131: 129 is 3XL's own start
    (118.5, "XXL", "XL"),   # window 117.5-119.5 reaches XL, which ends at 118
    (119.0, "XXL", None),   # window 118-120: 118 is XXL's own start
    (117.5, "XL", "XXL"),   # window 116.5-118.5 reaches XXL at 118
])
def test_the_last_band_keeps_its_inclusive_top_and_its_one_neighbour(chest_cm, label, alternative):
    result = assign(chest(chest_cm * 10.0), population="men")
    assert result.label == label
    assert result.alternative == alternative


def test_just_past_the_last_band_is_outside_the_chart():
    result = assign(chest(1411.0), population="men")
    assert not result.assigned
    assert "outside" in result.reason


def test_the_charts_end_where_their_source_page_ends():
    """Decision #50: 3XL is the page's last row for both populations, and
    the body that prompted it (smpl_rand1, chest 143.9 cm) is still
    outside — the chart is not extended past what the page prints."""
    assert EN_13402_3.range_cm == (86.0, 141.0)
    assert EN_13402_3_WOMEN.range_cm == (74.0, 143.0)
    assert EN_13402_3.bands[-1].label == "3XL" and EN_13402_3_WOMEN.bands[-1].label == "3XL"
    refused = assign(chest(1439.0), population="men")
    assert not refused.assigned and "outside" in refused.reason
    assert assign(chest(1350.0), population="men").label == "3XL"
    assert assign(chest(1400.0), chart=EN_13402_3_WOMEN, population="women").label == "3XL"
    # the Lacoste conversion is not guessed past the labels it records
    assert LACOSTE_MEN.bands[-1].label == "7 (XXL)"


def test_the_lacoste_table_is_a_label_conversion_of_the_en_bands():
    """Not a brand check — there is no brand data to check against. The
    table is EN 13402-3's bands with Lacoste's numbers on them, and this
    pins exactly that: every edge equal, every label a number plus the
    letter it stands for, and the chart saying so in its own name."""
    # a prefix of the EN table: the recorded label mapping ends at 7 = XXL,
    # so EN's 3XL (decision #50) has no Lacoste row rather than a guessed one
    assert len(LACOSTE_MEN.bands) == 5 and len(EN_13402_3.bands) == 6
    for numbered, standard, number in zip(LACOSTE_MEN.bands, EN_13402_3.bands, "34567"):
        assert (numbered.chest_min_cm, numbered.chest_max_cm) ==             (standard.chest_min_cm, standard.chest_max_cm)
        assert numbered.label == f"{number} ({standard.label})"
    assert "derived" in LACOSTE_MEN.name.lower()
    assert "not the brand's own table" in LACOSTE_MEN.source.lower()
    assert "label conversion" in LACOSTE_MEN.note.lower()


def test_the_assignment_carries_the_charts_note():
    """The note is where a chart says what it is not — the Lacoste table
    that it is derived, the women's table that its gap is unverified. A
    consumer that sees only the name would take both at face value."""
    for chart in CHARTS.values():
        result = assign(chest(1000.0), chart=chart, population=chart.population)
        assert result.to_dict()["chart_note"] == chart.note
        assert result.to_dict()["chart_note"]


def test_the_module_says_what_it_is_not():
    import body_measure.sizing as sizing
    doc = " ".join(sizing.__doc__.lower().split())
    assert "not a fit recommendation" in doc
    assert "chest-girth classifier" in doc


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
         "--input-unit", "m", "--up-axis", "Z", "--estimate", "--skip-pose-gate",
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
