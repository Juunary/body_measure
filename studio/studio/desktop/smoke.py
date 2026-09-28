"""End-to-end checks runnable using only the packaged executable."""
import json
from pathlib import Path
import tempfile
import threading
import traceback


def exercise_session(session):
    session.load_example()
    run = session.generate(autoplay=False)
    plan = run["plan"]
    assert plan["totals"]["pieces"] == 9
    assert len({s["id"] for s in plan["sewing_seams"]}) == 18
    final = session.control("seek", plan["totals"]["duration_s"])
    assert final["ready_for_qr"] and final["qc_verdict"] == "pass"
    assert final["metrics"]["buttons_attached"] == 2
    assert abs(final["resources"]["cost_eur"] - plan["totals"]["resources"]["cost_eur"]) < 1e-8
    middle = session.control("seek", plan["boundaries"]["buttons_start_s"])
    assert not middle["ready_for_qr"] and middle["metrics"]["buttons_attached"] == 0
    session.control("speed", .1)
    with tempfile.TemporaryDirectory(prefix="polo-check-") as temp:
        path = Path(temp) / "한글 폴더" / "연구 예제.polo-sim.json"
        session.save_project(path)
        restored = session.open_project(path)["state"]
        assert restored["status"] == "paused" and restored["speed"] == .1
        assert restored["sim_time_s"] == middle["sim_time_s"]
        assert restored["metrics"] == middle["metrics"]
    return {"pieces": 9, "unique_seams": 18, "buttons": 2, "qc": "pass",
            "unicode_save_reopen": True, "rewind": True}


def run(report_path=None, *, ui=False):
    from .bridge import DesktopSession
    report = {"ok": False}
    try:
        report["engine"] = exercise_session(DesktopSession())
        if ui:
            report["ui"] = exercise_window()
            assert report["ui"].get("ok"), report["ui"]
        report["ok"] = True
    except Exception:
        report["error"] = traceback.format_exc()
    if report_path:
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not report["ok"]:
        raise RuntimeError(report.get("error", "Desktop smoke test failed"))
    return report


def exercise_window():
    import webview
    from .app import asset
    from .bridge import DesktopBridge
    bridge = DesktopBridge()
    window = webview.create_window("Polo Simulator verification", str(asset("desktop.html")),
                                  js_api=bridge, width=1440, height=920, hidden=True)
    bridge._window = window
    result = {}

    def verify():
        finished = threading.Event()

        def done(value):
            result.update(value if isinstance(value, dict) else {"error": str(value)})
            finished.set()

        try:
            window.evaluate_js(asset("desktop-smoke.js").read_text(encoding="utf-8"), callback=done)
            if not finished.wait(50):
                result.update(ok=False, error="UI verification timed out")
        except Exception:
            result.update(ok=False, error=traceback.format_exc())
        finally:
            window.destroy()

    webview.start(verify, gui="edgechromium", debug=False, private_mode=True)
    return result
