"""Jobs: one per loaded scan, held in memory, worked on by one thread at a
time, watched by any number of event streams.

A job owns the mesh and everything derived from it. Stages (`load`,
`measure`, `size`, `replay`) run in a daemon thread so the HTTP layer
never blocks on a dijkstra; the thread appends events under a condition
variable and the SSE generator waits on it. A second stage request while
one is running is refused, not queued — the page has one button per
stage and disables it while the stage runs.
"""
from __future__ import annotations

import asyncio
import threading
import time
import traceback
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable

from . import events as ev

MAX_JOBS = 8
HEARTBEAT_S = 15.0


@dataclass
class Job:
    id: str
    params: dict
    entry: dict
    state: str = "new"
    events: list = field(default_factory=list)
    cond: threading.Condition = field(default_factory=threading.Condition)
    worker: threading.Thread | None = None
    active_stage: str | None = None
    # what the stages produce
    surface: Any = None
    mesh: Any = None
    mesh_info: dict = field(default_factory=dict)
    measurements: dict = field(default_factory=dict)
    landmarks: dict = field(default_factory=dict)
    prototypes: dict = field(default_factory=dict)
    curves: list = field(default_factory=list)
    curve_notes: list = field(default_factory=list)
    sizing: Any = None
    size_view: dict = field(default_factory=dict)
    customer_size: Any = None
    document_path: Any = None
    replay: dict = field(default_factory=dict)
    simulation: Any = None
    simulation_document: dict | None = None
    action_lock: threading.RLock = field(default_factory=threading.RLock)
    passport: dict = field(default_factory=dict)
    #: what a person flagged as wrongly measured, from the 3D view
    reports: list = field(default_factory=list)

    # ---------------------------------------------------------------- events
    def emit(self, type_: str, phase: str, **payload) -> dict:
        with self.cond:
            event = {"id": len(self.events) + 1, "t": round(time.time(), 3),
                     "job": self.id, "phase": phase, "type": type_, **payload}
            self.events.append(event)
            self.cond.notify_all()
        return event

    def line(self, phase: str, segments: list, kind: str = "note") -> None:
        self.emit("line", phase, segments=segments, kind=kind)

    def stage(self, phase: str, name: str, status: str, detail: str = "",
              elapsed_s: float | None = None) -> None:
        payload = {"name": name, "status": status, "detail": detail}
        if elapsed_s is not None:
            payload["elapsed_s"] = round(elapsed_s, 2)
        self.emit("stage", phase, **payload)

    @property
    def busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def _wait_for_new(self, last_id: int, timeout: float) -> bool:
        with self.cond:
            return self.cond.wait_for(lambda: len(self.events) > last_id, timeout)

    async def stream(self, last_id: int, is_disconnected: Callable):
        """Server-sent events: buffered ones after `last_id`, then live."""
        while True:
            with self.cond:
                pending = [e for e in self.events if e["id"] > last_id]
            for event in pending:
                last_id = event["id"]
                yield event
            if await is_disconnected():
                return
            fresh = await asyncio.to_thread(self._wait_for_new, last_id, HEARTBEAT_S)
            if not fresh:
                yield None    # heartbeat comment


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()

    def create(self, params: dict, entry: dict) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], params=params, entry=entry)
        with self._lock:
            self._jobs[job.id] = job
            while len(self._jobs) > MAX_JOBS:
                _, old = self._jobs.popitem(last=False)
                if old.simulation:
                    old.simulation.close()
                old.mesh = old.surface = None    # free the geometry
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def start(self, job: Job, phase: str, target: Callable[[Job], None]) -> bool:
        """Run `target(job)` in a thread. False if the job is busy."""
        if job.busy:
            return False

        def run() -> None:
            try:
                target(job)
            except Exception as exc:      # the stream must say what happened
                job.state = "error"
                tail = traceback.format_exc().strip().splitlines()[-6:]
                job.emit("error", phase, stage=phase, message=str(exc),
                         traceback_tail=tail)
                job.line(phase, ev.warn_line(f"{type(exc).__name__}: {exc}"), "error")
            finally:
                job.active_stage = None
                job.emit("end", phase)

        job.active_stage = phase
        job.worker = threading.Thread(target=run, name=f"job-{job.id}-{phase}", daemon=True)
        job.worker.start()
        return True


REGISTRY = JobRegistry()
