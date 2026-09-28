"""Desktop plan, clock, validation and persistence regressions."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from studio.desktop import DesktopConfig, DesktopPlayback, build_plan, snapshot
from studio.desktop.bridge import DesktopBridge, DesktopSession
from studio.desktop import shirt_steps, storage


@pytest.fixture
def example():
    root = Path(__file__).parents[1] / "examples"
    return (json.loads((root / "cutting-measurements.json").read_text()),
            json.loads((root / "cutting-config.json").read_text()))


@pytest.fixture
def plan(example):
    return build_plan(*example)


def test_shirt_steps_skip_ironing_and_total_30_11(plan):
    rows = shirt_steps.rows()
    assert len(rows) == 35 and [r["no"] for r in rows] == list(range(1, 36))
    assert sum(r["duration_s"] or 0 for r in rows) == 42*60 + 35
    assert sum(r["duration_s"] for r in rows if r["ironing"]) == 744
    assert plan["totals"]["sewing_duration_s"] == 30*60 + 11
    assert plan["totals"]["work_steps"] == 18
    sewing = next(c for c in plan["timeline"] if c["id"] == "sewing")
    assert sewing["duration_s"] == pytest.approx(1811, abs=1e-9)
    numbers = [op["step_no"] for op in plan["operations"] if op["step_no"] is not None]
    assert not set(numbers) & shirt_steps.IRONING
    assert list(dict.fromkeys(numbers)) == [5, 8, 9, 10, 11, 12, 14, 15, 18, 19, 20, 23, 24, 25, 28, 29, 31, 32]
    assert numbers == sorted(numbers)
    for row in plan["work_steps"]:
        if row["scheduled"]:
            ops = [op for op in plan["operations"] if op["step_no"] == row["no"]]
            assert ops[0]["start_s"] == row["start_s"] and ops[-1]["end_s"] == row["end_s"]
            assert row["end_s"] - row["start_s"] == pytest.approx(row["duration_s"])


def test_seams_are_assigned_once_in_process_order(plan):
    ids = [s["id"] for s in plan["sewing_seams"]]
    assert len(ids) == len(set(ids)) == 18
    stitched = [op["seam_id"] for op in plan["operations"] if op["kind"] == "stitch" and op["seam_id"]]
    assert stitched == ids
    assert {s["id"]: s["step_no"] for s in plan["sewing_seams"]} == {
        "shoulder_left": 15, "shoulder_right": 15, "placket_left": 18, "placket_right": 18,
        "side_left": 19, "underarm_left": 19, "side_right": 19, "underarm_right": 19,
        "cuff_left": 23, "cuff_right": 23, "armhole_left_front": 24, "armhole_left_back": 24,
        "armhole_right_front": 24, "armhole_right_back": 24, "hem_front": 28, "hem_back": 28,
        "collar_front": 29, "collar_back": 29}
    assert {op["machine_id"] for op in plan["operations"] if op["step_no"] in (20, 25)} == {"overlock"}
    end = snapshot(plan, plan["boundaries"]["sewing_end_s"])
    assert end["metrics"]["seams_complete"] == 18 and end["metrics"]["steps_complete"] == 18


def test_buttons_and_qc_stop_before_qr_without_finishing(plan):
    kinds = [op["kind"] for op in plan["operations"]]
    assert not [k for k in kinds if k.startswith("press_")]
    assert kinds.index("buttonhole_stitch") > max(i for i, op in enumerate(plan["operations"]) if op["step_no"])
    assert kinds.index("qc_load") > kinds.index("button_attach_stitch")
    assert kinds[-1] == "ready_for_qr"
    final = snapshot(plan, plan["totals"]["duration_s"])
    assert final["qc_complete"] and final["ready_for_qr"]
    assert final["qc_verdict"] == "pass"
    assert final["metrics"]["buttons_attached"] == final["metrics"]["buttons_total"] == 2
    assert plan["qc"]["dpp_label_or_qr_issued"] == 0
    assert plan["finished_garment"] is False


def test_rewind_restores_all_state_and_resources(plan):
    at = plan["boundaries"]["buttons_start_s"] + 10
    first = snapshot(plan, at)
    snapshot(plan, plan["totals"]["duration_s"])
    again = snapshot(plan, at)
    assert first == again
    assert snapshot(plan, 0)["resources"]["energy_kwh"] == 0
    assert first["resources"]["energy_kwh"] < plan["totals"]["resources"]["energy_kwh"]


def test_button_layout_is_bounded_and_non_overlapping(example):
    _, data = example
    bad = {**data, "process": {"buttons": {"count": 4, "top_offset_mm": 20,
                                               "spacing_mm": 20, "hole_length_mm": 18}}}
    with pytest.raises(ValidationError, match="overlap"):
        DesktopConfig.model_validate(bad)
    outside = {**data, "process": {"buttons": {"count": 2, "top_offset_mm": 140,
                                                   "spacing_mm": 70}}}
    with pytest.raises(ValidationError, match="inside the placket"):
        DesktopConfig.model_validate(outside)
    wide_buttons = {**data, "process": {"buttons": {"diameter_mm": 25,
                                                       "hole_length_mm": 8, "spacing_mm": 28}}}
    with pytest.raises(ValidationError, match="overlap"):
        DesktopConfig.model_validate(wide_buttons)


def test_playback_pause_seek_speed_and_restart(plan):
    now = [10.]
    player = DesktopPlayback(plan, clock=lambda: now[0])
    player.control("play")
    now[0] += 2
    running = player.get()
    assert running["sim_time_s"] == pytest.approx(20)
    paused = player.control("seek", plan["boundaries"]["qc_start_s"])
    assert paused["status"] == "paused" and paused["stage"] == "qc"
    player.control("speed", 25)
    restarted = player.control("restart")
    assert restarted["status"] == "playing" and restarted["sim_time_s"] == 0
    assert restarted["revision"] >= 2


def test_project_round_trip_unicode_path_and_tamper(tmp_path, example):
    session = DesktopSession()
    session.load_example()
    session.generate(autoplay=False)
    session.control("seek", session.plan["boundaries"]["buttons_start_s"])
    target = tmp_path / "한글 폴더" / "폴로.polo-sim.json"
    saved = session.save_project(target)
    reopened = DesktopSession().open_project(target)
    assert reopened["state"]["status"] == "paused"
    assert reopened["state"]["sim_time_s"] == pytest.approx(session.player.position)
    assert saved["content_hash"] == storage.load(target)["content_hash"]
    value = json.loads(target.read_text(encoding="utf-8"))
    value["playback"]["position_s"] += 1
    target.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        storage.load(target)


def test_measurement_loader_rejects_wrong_shapes_and_nonfinite(tmp_path):
    wrong = tmp_path / "wrong.json"
    wrong.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        DesktopSession().load_measurement(wrong)
    nan = tmp_path / "nan.json"
    nan.write_text('{"measurements":{},"meta":{},"value":NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="non-finite"):
        DesktopSession().load_measurement(nan)


def test_pywebview_bridge_does_not_publish_native_state():
    bridge = DesktopBridge()
    assert vars(bridge)
    assert all(name.startswith("_") for name in vars(bridge))


def test_chapters_cover_the_line_and_transport_rewinds(plan):
    chapters = plan["timeline"]
    assert [r["id"] for r in chapters] == [
        "cutting", "sewing", "buttons", "qc", "ready_for_qr"]
    assert sum(r["duration_s"] for r in chapters) == pytest.approx(plan["totals"]["duration_s"])
    for left, right in zip(chapters, chapters[1:]):
        assert left["end_s"] == right["start_s"]
    for op in plan["operations"]:
        if not op["kind"].startswith("transfer_to_"):
            continue
        middle = (op["start_s"] + op["end_s"]) / 2
        state = snapshot(plan, middle)
        assert state["transport"]["progress"] == pytest.approx(.5)
        assert state["focus_machine_id"] == op["kind"].removeprefix("transfer_to_")
        snapshot(plan, plan["totals"]["duration_s"])
        assert snapshot(plan, middle) == state


def test_failed_generation_keeps_the_current_project_consistent():
    session = DesktopSession()
    session.load_example()
    session.generate(autoplay=False)
    original = session.config, session.plan, session.player
    invalid = session.config.model_dump()
    invalid["manual"]["armhole_depth"]["value"] = 450
    with pytest.raises(ValueError):
        session.generate(invalid)
    assert (session.config, session.plan, session.player) == original
