"""Size study: ITA_HE_26 chart, graded step times, per-size plans and the runner."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from studio.desktop import build_plan, shirt_steps, size_chart
from studio.desktop.config import Process

EXAMPLES = Path(__file__).parents[1] / "examples"


@pytest.fixture
def base():
    return json.loads((EXAMPLES / "cutting-config.json").read_text())


def test_chart_has_ten_sizes_and_reference_ratio_is_one():
    assert size_chart.SIZES == tuple(range(40, 60, 2))
    assert all(len(v) == 10 for v in size_chart.DIMS.values())
    assert all(size_chart.ratio(dim, 52) == 1 for dim in size_chart.DIMS)
    assert size_chart.dims(52)["oberweite_half"] == 59 and size_chart.dims(52)["kragenweite"] == 41


def test_corrections_touch_only_the_sleeve_hem_typos():
    changed = {(k, s) for k in size_chart.DIMS for i, s in enumerate(size_chart.SIZES)
               if size_chart.DIMS[k][i] != size_chart.RAW[k][i]}
    assert changed == {("ae_saumweite_half", 48), ("ae_saumweite_half", 50), ("ae_saumweite_half", 54)}


def test_reference_size_reproduces_the_measured_table():
    assert shirt_steps.rows(52) == shirt_steps.rows()
    assert sum(r["duration_s"] for r in shirt_steps.rows() if r["scheduled"]) == 1811


def test_scheduled_time_grows_with_size():
    totals = [sum(r["duration_s"] for r in shirt_steps.rows(s) if r["scheduled"]) for s in size_chart.SIZES]
    assert totals == sorted(totals) and totals[0] < 1811 < totals[-1]
    for r in shirt_steps.rows(40):   # never below the fixed handling time, never negative
        assert r["measured_s"] is None or 0 < r["duration_s"] <= r["measured_s"] * 1.0001


@pytest.mark.parametrize("size", size_chart.SIZES)
def test_every_size_builds_a_plan(size, base):
    plan = build_plan(size_chart.document(size), size_chart.config_for(size, base))
    assert plan["size"]["label"] == str(size) and plan["totals"]["shirt_size"] == size
    assert len(plan["sewing_seams"]) == 18


def test_size_52_plan_matches_the_measured_sewing_time(base):
    plan = build_plan(size_chart.document(52), size_chart.config_for(52, base))
    assert plan["totals"]["sewing_duration_s"] == pytest.approx(1811, abs=1e-9)


def test_larger_size_costs_more_time_thread_and_energy(base):
    small, large = (build_plan(size_chart.document(s), size_chart.config_for(s, base)) for s in (44, 58))
    from studio.desktop.engine import resources_at
    a, b = (resources_at(p, p["totals"]["duration_s"]) for p in (small, large))
    assert large["totals"]["sewing_duration_s"] > small["totals"]["sewing_duration_s"]
    assert b["thread_used_m"] > a["thread_used_m"] and b["energy_kwh"] > a["energy_kwh"]


def test_unknown_size_is_rejected():
    with pytest.raises(ValidationError):
        Process(shirt_size=39)
    with pytest.raises(ValueError):
        size_chart.document(39)


def test_runner_writes_csv_md_json(tmp_path):
    from studio.desktop import size_study
    rows = size_study.main(["--out", str(tmp_path), "--sizes", "44,52", "--no-nesting"])
    assert [r["size"] for r in rows] == [44, 52]
    assert (tmp_path / "size-study.csv").exists() and (tmp_path / "size-study.md").exists()
    assert rows[1]["duration_s_vs52_pct"] == 0 and rows[0]["net_piece_area_m2"] < rows[1]["net_piece_area_m2"]
