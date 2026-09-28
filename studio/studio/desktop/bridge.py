"""Small pywebview API; all simulation work remains in pure Python modules."""
from __future__ import annotations

import json
from pathlib import Path
import threading

from .config import DesktopConfig
from .engine import build_plan
from .playback import DesktopPlayback
from . import storage

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"


def _read_json(path):
    def invalid(value):
        raise ValueError(f"non-finite JSON number: {value}")
    with open(path, encoding="utf-8-sig") as stream:
        value = json.load(stream, parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


class DesktopSession:
    def __init__(self):
        self.document = None
        self.source = None
        self.config = DesktopConfig()
        self.plan = None
        self.player = None
        self.project_path = None
        self.lock = threading.RLock()

    def options(self):
        return {"defaults": self.config.model_dump(), "schema": DesktopConfig.model_json_schema(),
                "source": self.source, "has_document": self.document is not None}

    def load_measurement(self, path):
        value = _read_json(path)
        if not isinstance(value.get("measurements", {}), dict) or not isinstance(value.get("meta", {}), dict):
            raise ValueError("expected body_measure JSON with measurements and meta objects")
        with self.lock:
            self.document, self.source = value, {"kind": "measurement_json", "path": str(Path(path).resolve())}
            self.plan = self.player = None
            self.project_path = None
        return {"source": self.source, "summary": Path(path).name}

    def load_example(self):
        document = _read_json(EXAMPLES / "cutting-measurements.json")
        config = _read_json(EXAMPLES / "cutting-config.json")
        with self.lock:
            self.document = document
            self.source = {"kind": "synthetic_example", "path": None}
            self.config = DesktopConfig.model_validate(config)
            self.plan = self.player = None
            self.project_path = None
        return {"source": self.source, "config": self.config.model_dump(), "summary": "Synthetic research example"}

    def generate(self, config=None, *, autoplay=True):
        with self.lock:
            if self.document is None:
                raise ValueError("open a measurement JSON or load the research example first")
            candidate = DesktopConfig.model_validate(config or self.config.model_dump())
            candidate_plan = build_plan(self.document, candidate)
            self.config, self.plan = candidate, candidate_plan
            self.player = DesktopPlayback(self.plan)
            if autoplay:
                self.player.control("play")
            return {"plan": self.plan, "state": self.player.get(), "source": self.source}

    def state(self):
        with self.lock:
            if self.player is None:
                return None
            return self.player.get()

    def control(self, action, value=None):
        with self.lock:
            if self.player is None:
                raise ValueError("generate a simulation first")
            return self.player.control(action, value)

    def save_project(self, path):
        with self.lock:
            if self.player is None:
                raise ValueError("generate a simulation before saving")
            value = storage.save(path, {"source": self.source, "document": self.document,
                                        "config": self.config.model_dump(), "plan": self.plan,
                                        "playback": self.player.saved_position()})
            self.project_path = str(Path(path).resolve())
            return {"path": self.project_path, "content_hash": value["content_hash"]}

    def open_project(self, path):
        value = storage.load(path)
        config = DesktopConfig.model_validate(value["config"])
        with self.lock:
            self.document, self.source, self.config = value["document"], value["source"], config
            self.plan = value["plan"]
            self.player = DesktopPlayback(self.plan, position=value["playback"]["position_s"],
                                          speed=value["playback"]["speed"])
            self.project_path = str(Path(path).resolve())
            return {"path": self.project_path, "plan": self.plan, "state": self.player.get(),
                    "config": self.config.model_dump(), "source": self.source}


class DesktopBridge:
    def __init__(self, session=None):
        # pywebview recursively inspects every public attribute on a js_api
        # object. Keep native UI objects and Python state out of that surface.
        self._session = session or DesktopSession()
        self._window = None

    @staticmethod
    def _ok(callable_):
        try:
            return {"ok": True, "data": callable_()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_options(self): return self._ok(self._session.options)
    def load_example(self): return self._ok(self._session.load_example)
    def generate(self, config): return self._ok(lambda: self._session.generate(config))
    def get_state(self): return self._ok(self._session.state)
    def control(self, action, value=None): return self._ok(lambda: self._session.control(action, value))

    def choose_measurement(self):
        def choose():
            import webview
            paths = self._window.create_file_dialog(webview.FileDialog.OPEN,
                file_types=("Measurement JSON (*.json)", "All files (*.*)"))
            return None if not paths else self._session.load_measurement(paths[0])
        return self._ok(choose)

    def choose_project(self):
        def choose():
            import webview
            paths = self._window.create_file_dialog(webview.FileDialog.OPEN,
                file_types=("Polo simulation (*.polo-sim.json;*.json)", "All files (*.*)"))
            return None if not paths else self._session.open_project(paths[0])
        return self._ok(choose)

    def save_project(self):
        def choose():
            import webview
            path = self._window.create_file_dialog(webview.FileDialog.SAVE,
                save_filename="polo-simulation.polo-sim.json",
                file_types=("Polo simulation (*.polo-sim.json)",))
            if not path: return None
            selected = path[0] if isinstance(path, (tuple, list)) else path
            if not selected.lower().endswith(".json"): selected += ".polo-sim.json"
            return self._session.save_project(selected)
        return self._ok(choose)
