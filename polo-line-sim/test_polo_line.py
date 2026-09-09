# -*- coding: utf-8 -*-
"""스모크 테스트 — 표준 라이브러리 unittest 만 쓴다.

    python -m unittest -v
"""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from polo_line import live, machines, measurements, simulate, term
from polo_line.spec import (
    MEASUREMENTS,
    SEWING_KEYS,
    STATIONS,
    TARGET_COST_EUR,
    active_stations,
)
from run import main


def capture(fn, *args, **kwargs) -> str:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        fn(*args, **kwargs)
    return buffer.getvalue()


class TestSpec(unittest.TestCase):
    def test_base_line_is_345_minutes(self):
        """계획서 표 4 를 폴로로 분해한 결과가 34.5분이어야 한다."""
        base = sum(st.minutes for st in active_stations())
        self.assertAlmostEqual(base, 34.5, places=2)

    def test_optional_modules_excluded_by_default(self):
        keys = {st.key for st in active_stations()}
        self.assertNotIn("emb", keys)
        self.assertNotIn("prn", keys)
        self.assertIn("emb", {st.key for st in active_stations(embroidery=True)})

    def test_attended_fraction_is_a_ratio(self):
        for st in STATIONS:
            self.assertGreaterEqual(st.attended, 0.0, st.key)
            self.assertLessEqual(st.attended, 1.0, st.key)

    def test_station_keys_unique(self):
        keys = [st.key for st in STATIONS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_sewing_keys_exist(self):
        keys = {st.key for st in STATIONS}
        for key in SEWING_KEYS:
            self.assertIn(key, keys)

    def test_every_origin_has_a_label(self):
        """origin 값을 바꾸면 라벨 사전도 함께 바뀌어야 한다."""
        for st in STATIONS:
            self.assertIn(st.origin, machines.ORIGIN_STYLE, st.key)

    def test_every_labelled_group_is_used(self):
        """쓰이지 않는 라벨이 남아 표기 체계가 흐려지지 않게 한다."""
        used = {st.origin for st in STATIONS}
        self.assertEqual(used, set(machines.ORIGIN_STYLE))

    def test_machine_groups_cover_every_station(self):
        """설비 표에서 조용히 빠지는 기계가 없어야 한다."""
        listed = set()
        for _group, _caption, keys in machines.GROUPS:
            listed.update(keys)
        self.assertEqual(listed, {st.key for st in STATIONS})

    def test_every_station_emits_a_dpp_module(self):
        for st in STATIONS:
            self.assertIn("module", st.dpp, st.key)

    def test_every_dpp_block_identifies_its_machine(self):
        """제품별 추적이 DPP 의 목적이다 — 기계 없는 공정 블록은 그 목적을 깬다."""
        for st in STATIONS:
            block = live.build_block(st)
            self.assertEqual(block["machine"], st.machine, st.key)

    def test_dpp_blocks_carry_time_and_energy(self):
        for st in STATIONS:
            block = live.build_block(st)
            self.assertEqual(block["duration_min"], st.minutes, st.key)
            self.assertGreater(block["energy_kWh"], 0, st.key)

    def test_machine_is_not_duplicated_in_spec(self):
        """machine 은 Station 에서 파생한다 — dpp 에 또 적으면 두 값이 갈린다."""
        for st in STATIONS:
            self.assertNotIn("machine", st.dpp, st.key)

    def test_readouts_render_at_both_ends(self):
        for st in STATIONS:
            for label, _unit, fn in st.readouts:
                for progress in (0.0, 0.5, 1.0):
                    self.assertIsInstance(fn(progress), str, f"{st.key}/{label}")


class TestMeasurements(unittest.TestCase):
    def test_measurement_keys_unique(self):
        keys = [m.key for m in MEASUREMENTS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_gaps_are_flagged_not_silently_dropped(self):
        """명세에 없는 치수는 빠지지 않고 '—' 로 표시되어야 한다."""
        gaps = [m for m in MEASUREMENTS if not measurements.covered(m)]
        self.assertTrue(gaps)
        for m in gaps:
            self.assertEqual(m.spec_status, "—")
            self.assertTrue(m.polo_note, f"{m.key} 는 사유가 비어 있다")


class TestSimulation(unittest.TestCase):
    def setUp(self):
        self.result = simulate.run(runs=400, seed=7)

    def test_reproducible(self):
        again = simulate.run(runs=400, seed=7)
        self.assertEqual(self.result.flow_times, again.flow_times)

    def test_flow_time_near_nominal(self):
        self.assertAlmostEqual(self.result.mean_time, self.result.nominal_minutes, delta=2.0)

    def test_attended_is_less_than_flow(self):
        self.assertLess(self.result.attended_minutes, self.result.mean_time)

    def test_parallel_model_is_cheaper_than_dedicated(self):
        kwh = self.result.mean_energy
        dedicated = simulate.unit_cost(self.result.mean_time, kwh)["total"]
        parallel = simulate.unit_cost(self.result.attended_minutes, kwh)["total"]
        self.assertLess(parallel, dedicated)

    def test_required_attended_minutes_hits_the_target(self):
        kwh = self.result.mean_energy
        need = simulate.required_attended_minutes(TARGET_COST_EUR[1], kwh)
        self.assertAlmostEqual(simulate.unit_cost(need, kwh)["total"], TARGET_COST_EUR[1], places=6)

    def test_higher_rate_never_needs_fewer_machines(self):
        previous = 0
        for rate in (2, 5, 10, 20):
            plan = simulate.balance(self.result.stations, rate, self.result.attended_minutes)
            self.assertGreaterEqual(plan["machines"], previous)
            previous = plan["machines"]

    def test_balance_meets_the_requested_rate(self):
        """복제 후 병목이 takt 를 넘지 않아야 목표 생산율이 실제로 나온다."""
        for rate in (2, 5, 10, 20):
            plan = simulate.balance(self.result.stations, rate, self.result.attended_minutes)
            self.assertLessEqual(plan["bottleneck_takt"], plan["takt"] + 1e-9, f"{rate}/h")

    def test_optional_modules_extend_the_line(self):
        loaded = simulate.run(runs=200, seed=7, embroidery=True, printing=True)
        self.assertGreater(loaded.nominal_minutes, self.result.nominal_minutes)


class TestLiveLineFits(unittest.TestCase):
    """덮어쓰는 진행 줄이 터미널 폭을 넘으면 잔상이 쌓인다."""

    def setUp(self):
        term.init(use_color=False)

    def _plain(self, pieces):
        return "  ".join(
            f"{label} {value}" + (f" {unit}" if unit else "") for label, value, unit in pieces
        )

    def test_intermediate_frames_fit_any_width(self):
        for width in (40, 60, 80, 96, 120):
            for st in STATIONS:
                for step in range(1, live.STEPS_PER_STATION):
                    progress = step / live.STEPS_PER_STATION
                    pieces = live.fit_readouts(st, progress, width - 1)
                    rendered = live.PREFIX_WIDTH + term.dwidth(self._plain(pieces))
                    self.assertLessEqual(rendered, width - 1, f"{st.key} @ {width}")

    def test_final_frame_keeps_every_readout(self):
        """마지막 줄은 화면에 남는다 — 판독값이 잘리면 정보가 사라진다."""
        for st in STATIONS:
            pieces = live.fit_readouts(st, 1.0, None)
            self.assertEqual(len(pieces), len(st.readouts), st.key)

    def test_wide_terminal_shows_everything(self):
        for st in STATIONS:
            pieces = live.fit_readouts(st, 0.5, 200)
            self.assertEqual(len(pieces), len(st.readouts), st.key)


class TestLiveLineEvents(unittest.TestCase):
    """run() 은 frames() 를 출력할 뿐이다 — 다른 소비자도 같은 줄을 받아야 한다."""

    def test_events_come_in_line_order_with_one_frame_per_step(self):
        events = list(live.frames(width=200))
        stations = active_stations()
        self.assertEqual(events[0]["type"], "header")
        self.assertEqual(events[-2]["type"], "totals")
        self.assertEqual(events[-1]["type"], "dpp")
        frames = [e for e in events if e["type"] == "frame"]
        self.assertEqual(len(frames), live.STEPS_PER_STATION * len(stations))
        starts = [e["key"] for e in events if e["type"] == "station_start"]
        self.assertEqual(starts, [st.key for st in stations])
        self.assertEqual(len([e for e in events if e["type"] == "station_done"]), len(stations))
        self.assertIn("customer_spec", events[-1]["document"])

    def test_a_rendered_frame_is_the_printed_line(self):
        """세그먼트를 term.render 로 합치면 터미널이 찍던 그 줄이어야 한다."""
        term.init(use_color=False)
        first = next(e for e in live.frames(width=200) if e["type"] == "frame")
        line = term.render(first["segments"])
        self.assertTrue(line.startswith("      00:"), line)
        self.assertIn("█", line)
        self.assertIn("░", line)
        for readout in first["readouts"]:
            self.assertIn(f"{readout['label']} {readout['value']}", line)

    def test_every_style_name_is_one_term_knows(self):
        for event in live.frames(width=200):
            lines = [event["segments"]] if "segments" in event else event.get("lines", [])
            for segments in lines:
                for _, styles in segments:
                    for style in styles:
                        self.assertIn(style, term._CODES)


class TestTerminalWidth(unittest.TestCase):
    def test_hangul_counts_as_two_columns(self):
        self.assertEqual(term.dwidth("폴로"), 4)
        self.assertEqual(term.dwidth("polo"), 4)

    def test_ansi_escapes_have_no_width(self):
        term.init(use_color=False)
        self.assertEqual(term.dwidth("\033[31m폴로\033[0m"), 4)

    def test_pad_aligns_mixed_scripts(self):
        self.assertEqual(term.dwidth(term.pad("폴로", 10)), 10)
        self.assertEqual(term.dwidth(term.pad("polo", 10)), 10)


class TestReportsRun(unittest.TestCase):
    """보고 함수가 예외 없이 내용을 출력하는지만 본다."""

    def setUp(self):
        term.init(use_color=False)

    def test_measurements_report(self):
        out = capture(measurements.report, True)
        self.assertIn("Chest girth", out)
        self.assertIn("Shoulder slope", out)

    def test_machines_report(self):
        out = capture(machines.report, True)
        self.assertIn("Zünd S3", out)
        self.assertIn("Overlock", out)
        self.assertIn("Veit SF 27", out)

    def test_simulation_report(self):
        result = simulate.run(runs=100, seed=1)
        out = capture(simulate.report, result, True)
        self.assertIn("Flow time", out)
        self.assertIn("Scaling", out)

    def test_live_runs_without_delay(self):
        out = capture(live.run, False, False, 0.0, True)
        self.assertIn("DPP", out)
        self.assertIn("dpp_label", out)

    def test_cli_entry_point(self):
        out = capture(main, ["--no-color", "--runs", "50"])
        self.assertIn("Polo shirt", out)

    def test_cli_rejects_zero_runs(self):
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = main(["--no-color", "--runs", "0"])
        self.assertEqual(code, 2)
        self.assertIn("--runs", err.getvalue())


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------- passport ---
def test_a_passport_without_a_measurement_document_says_so():
    """The line used to claim size_source '3d_scan' while carrying no size.
    An unknown size is a field with a reason, not a silent omission."""
    from polo_line import passport

    block = passport.UNKNOWN.to_dpp()
    assert block["size"] is None
    assert block["size_source"] == "unknown"
    assert block["size_reason"]


def test_a_missing_or_broken_document_is_refused_not_guessed(tmp_path):
    from polo_line import passport

    missing = passport.load(tmp_path / "nope.json")
    assert not missing.known and "not found" in missing.reason

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert not passport.load(broken).known


def test_a_result_written_without_a_size_chart_carries_no_size(tmp_path):
    import json

    from polo_line import passport

    path = tmp_path / "r.json"
    path.write_text(json.dumps({"meta": {}, "measurements": {}}), encoding="utf-8")
    size = passport.load(path)
    assert not size.known
    assert "--size-chart" in size.reason


def test_the_size_travels_with_the_chart_it_came_from(tmp_path):
    """A label without its chart cannot answer the question a return asks."""
    import json

    from polo_line import passport

    path = tmp_path / "r.json"
    path.write_text(json.dumps({"meta": {"size": {
        "size": "L", "chart": "en13402", "chart_name": "EN 13402-3 letter codes, men",
        "chart_source": "EN 13402-3 ...", "chart_checked": "2026-08-28",
        "chest_mm": 1050.0, "alternative": None, "reason": "", "flags": [],
    }}}), encoding="utf-8")
    size = passport.load(path)
    block = size.to_dpp()
    assert block["size"] == "L"
    assert block["size_source"] == "3d_scan"
    assert block["size_chart_source"] and block["size_chart_checked"]
    assert "size_alternative" not in block
    # the passport records the garment, not the body: body dimensions are
    # excluded from the DPP by design, and that is the system's main privacy
    # boundary (body-measure docs/licenses/ethics.md). The value is read and
    # kept, so the boundary case can be decided from it — it just does not
    # travel.
    assert size.chest_mm == 1050.0
    assert not any("chest" in key or "_mm" in key for key in block), block


def test_a_boundary_case_names_both_labels_in_the_passport(tmp_path):
    import json

    from polo_line import passport

    path = tmp_path / "r.json"
    path.write_text(json.dumps({"meta": {"size": {
        "size": "M", "chart": "en13402", "chart_name": "EN 13402-3 letter codes, men",
        "chart_source": "x", "chart_checked": "2026-08-28", "chest_mm": 941.0,
        "alternative": "S", "reason": "", "flags": ["near_size_boundary"],
    }}}), encoding="utf-8")
    size = passport.load(path)
    assert size.on_boundary
    block = size.to_dpp()
    assert block["size_alternative"] == "S"
    assert "equally defensible" in block["size_note"]
