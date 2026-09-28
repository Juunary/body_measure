"""Authoritative desktop clock. The UI polls this object at 10 Hz."""
import math
import threading
import time
import uuid

from .engine import snapshot, terminal_lines


class DesktopPlayback:
    def __init__(self, plan, *, clock=time.monotonic, position=0., speed=None):
        self.plan, self.clock = plan, clock
        self.run_id = uuid.uuid4().hex[:16]
        self.position = float(position)
        self.speed = float(speed if speed is not None else plan["config"]["speed"])
        self.status = "paused"
        self.seq = 0
        self.revision = 0
        self.last = clock()
        self.lock = threading.RLock()

    def _advance(self):
        now = self.clock()
        if self.status == "playing":
            self.position = min(self.plan["totals"]["duration_s"], self.position + (now-self.last)*self.speed)
            if self.position >= self.plan["totals"]["duration_s"]:
                self.status = "completed"
        self.last = now

    def _state(self):
        self.seq += 1
        state = {**snapshot(self.plan, self.position), "run_id": self.run_id,
                 "plan_id": self.plan["plan_id"], "seq": self.seq,
                 "revision": self.revision, "status": self.status, "speed": self.speed}
        state["terminal_lines"] = terminal_lines(state)
        return state

    def get(self):
        with self.lock:
            self._advance()
            return self._state()

    def control(self, action, value=None):
        with self.lock:
            self._advance()
            if action in ("seek", "speed") and (value is None or isinstance(value, bool) or not math.isfinite(value)):
                raise ValueError("a finite control value is required")
            if action == "speed" and not .1 <= value <= 100:
                raise ValueError("speed must be 0.1–100")
            if action == "seek" and not 0 <= value <= self.plan["totals"]["duration_s"]:
                raise ValueError("seek is outside the simulation timeline")
            if action not in ("play", "pause", "seek", "speed", "restart", "next", "previous"):
                raise ValueError("unknown playback action")
            if action == "play":
                if self.status == "completed":
                    self.position = 0.
                    self.revision += 1
                self.status = "playing"
            elif action == "pause":
                self.status = "paused"
            elif action == "speed":
                self.speed = value
            else:
                if action == "restart":
                    self.position, self.status = 0., "playing"
                elif action == "seek":
                    self.position, self.status = value, "paused"
                else:
                    ignored = ("travel", "tool_up", "tool_down")
                    boundaries = [op["start_s"] for op in self.plan["operations"] if op["kind"] not in ignored]
                    candidates = ([t for t in boundaries if t > self.position+.001] if action == "next"
                                  else [t for t in boundaries if t < self.position-.001])
                    fallback = self.plan["totals"]["duration_s"] if action == "next" else 0.
                    self.position = ((min(candidates) if action == "next" else max(candidates))
                                     if candidates else fallback)
                    self.status = "paused"
                self.revision += 1
            self.last = self.clock()
            return self._state()

    def saved_position(self):
        with self.lock:
            self._advance()
            return {"position_s": self.position, "speed": self.speed, "status": "paused"}
