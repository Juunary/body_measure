"""HTTP surface of the studio. Routes only; the work is in the modules.

Run (PowerShell, from ITA/studio):
  $env:PYTHONUTF8=1; .venv\\Scripts\\python -m uvicorn studio.server:app --port 8010
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import paths
from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import files, meshio, passport_doc, passport_summary, pipeline, replay, settings, sizing_map
from .jobs import REGISTRY, Job
from .paths import QRBACK, STATIC
from .simulation import service as simulation
from .simulation.config import SimulationConfig, Control, REQUIRED, machine_catalogue
from .simulation.inputs import InputError
from pydantic import ValidationError
from app.access import Role
from app.schemas import LANGS

RESOLVED = paths.verify()

app = FastAPI(title="Maß-DPP studio", version="0.1.0")
DPP_VIEW = QRBACK / "static" / "dppview"


class BasicAuth:
    """One shared password in front of every route but the health check.

    The deployed page carries scans that are not public material (SMPL
    bodies, anything a reviewer uploads), so a public link must not be an
    open one. HTTP Basic is enough for that: the browser asks once, keeps
    the credentials for the origin, and sends them on every request the
    page makes — the event stream and the QR image included. Set
    STUDIO_PASSWORD to turn it on; the user name is ignored."""

    def __init__(self, app, password: str, realm: str = "Mass-DPP studio",   # header: ASCII only
                 exempt: tuple[str, ...] = ("/healthz",)) -> None:
        self.app, self.password, self.realm, self.exempt = app, password, realm, exempt

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in self.exempt:
            return await self.app(scope, receive, send)
        header = dict(scope.get("headers") or {}).get(b"authorization", b"")
        if self._ok(header):
            return await self.app(scope, receive, send)
        body = b"password required"
        await send({"type": "http.response.start", "status": 401, "headers": [
            (b"www-authenticate", f'Basic realm="{self.realm}", charset="UTF-8"'.encode()),
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"content-length", str(len(body)).encode()),
            (b"cache-control", b"no-store"),
        ]})
        await send({"type": "http.response.body", "body": body})

    def _ok(self, header: bytes) -> bool:
        import base64
        import hmac
        if not header.startswith(b"Basic "):
            return False
        try:
            _, _, given = base64.b64decode(header[6:]).decode("utf-8").partition(":")
        except Exception:
            return False
        return hmac.compare_digest(given.encode(), self.password.encode())


if os.environ.get("STUDIO_PASSWORD"):
    app.add_middleware(BasicAuth, password=os.environ["STUDIO_PASSWORD"])

_ASSET_REF = re.compile(r'(src|href)="(/static/[^"?]+)"')


# ---------------------------------------------------------------- pages ---
def _stamp(match: re.Match) -> str:
    attribute, url = match.group(1), match.group(2)
    asset = STATIC / url[len("/static/"):]
    stamp = int(asset.stat().st_mtime) if asset.exists() else 0
    return f'{attribute}="{url}?v={stamp}"'


def _page(path: Path) -> HTMLResponse:
    html = _ASSET_REF.sub(_stamp, path.read_text(encoding="utf-8"))
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def index(request: Request) -> RedirectResponse:
    return RedirectResponse('/measure' + ('?' + request.url.query if request.url.query else ''), status_code=302)


@app.api_route('/measure', methods=['GET', 'HEAD'], include_in_schema=False)
def measure_page():
    return _page(STATIC / 'measure.html')


@app.api_route('/simulation', methods=['GET', 'HEAD'], include_in_schema=False)
def simulation_page():
    return _page(STATIC / 'simulation.html')


@app.api_route('/qr', methods=['GET', 'HEAD'], include_in_schema=False)
def qr_page():
    return _page(STATIC / 'qr.html')


@app.get("/view/{code}", include_in_schema=False)
def view(code: str) -> HTMLResponse:
    """Lightweight Studio passport; the sibling viewer stays independent."""
    return _page(STATIC / 'passport.html')


@app.api_route("/c/{padded}", methods=["GET", "HEAD"], include_in_schema=False)
def resolve(padded: str) -> RedirectResponse:
    try:
        code = passport_doc.resolve(padded)
    except passport_doc.PassportError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return RedirectResponse(url=f"/view/{code}", status_code=302)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "paths": RESOLVED, "auth": bool(os.environ.get("STUDIO_PASSWORD")),
            "extra_data": str(files.EXTRA_DATA) if files.EXTRA_DATA else None}


# ---------------------------------------------------------------- files ---
@app.get("/api/files")
def list_files() -> list[dict]:
    return files.catalogue()


@app.post("/api/files/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    try:
        entry = files.store_upload(file.filename or "mesh", data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return entry


# ----------------------------------------------------------------- jobs ---
def _job(job_id: str) -> Job:
    job = REGISTRY.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job")
    return job


@app.post("/api/jobs")
def create_job(request: settings.JobRequest) -> dict:
    entry = files.find(request.file_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown file {request.file_id!r}")
    params = request.model_dump()
    if entry["kind"] == "mesh_file":
        if params["unit"] not in meshio.UNITS:
            raise HTTPException(status_code=422, detail=(
                "a mesh file needs its unit stated (m, cm or mm) — units are never guessed"))
        if params["up_axis"] not in meshio.UP_AXES:
            raise HTTPException(status_code=422, detail="a mesh file needs its up axis (Y or Z)")
    if request.chart not in sizing_map.sizing.CHARTS:
        raise HTTPException(status_code=422, detail=f"unknown chart {request.chart!r}")
    if params["population"] not in (None, *settings.POPULATIONS):
        raise HTTPException(status_code=422, detail="population must be men, women or empty")
    job = REGISTRY.create(params, entry)
    return {"job_id": job.id, "entry": entry, "state": job.state}


_STAGES = {"load": pipeline.run_load, "measure": pipeline.run_measure}


@app.post("/api/jobs/{job_id}/run/{stage}")
def run_stage(job_id: str, stage: str, body: dict | None = None) -> dict:
    job = _job(job_id)
    with job.action_lock:
        return _run_job_stage(job, stage, body)


def _run_job_stage(job: Job, stage: str, body: dict | None) -> dict:
    job_id = job.id
    if stage in ('simulate', 'replay'):
        with job.action_lock:
            if job.busy:
                raise HTTPException(status_code=409, detail='a stage is already running on this job')
            try:
                # Legacy pacing/optional downstream controls are intentionally
                # retired: they cannot change a geometry-based cutting plan.
                params = {k:v for k,v in (body or {}).items() if k not in ('delay','embroidery','printing')}
                player = simulation.start(job, SimulationConfig(**params))
            except InputError as exc:
                raise HTTPException(status_code=422, detail={'message':str(exc),'issues':exc.issues})
            except (ValidationError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f'could not save simulation: {exc}')
            return {'job_id':job.id,'stage':'simulate','state':job.state,'run_id':player.run_id}
    if job.simulation and job.simulation.get()['status']=='playing':
        raise HTTPException(status_code=409, detail='pause the cutting simulation before changing its inputs')
    if stage == "size":
        req = settings.SizeRequest(**(body or {}))
        target = lambda j: sizing_map.resize(j, req.chart, req.population, req.clothed)
    elif stage in _STAGES:
        target = _STAGES[stage]
    else:
        raise HTTPException(status_code=404, detail=f"unknown stage {stage!r}")
    if stage == "measure" and job.mesh is None:
        raise HTTPException(status_code=409, detail="load the scan first")
    if stage == "size" and not job.measurements:
        raise HTTPException(status_code=409, detail="measure the scan first")
    if job.busy:
        raise HTTPException(status_code=409, detail="a stage is already running on this job")
    if stage in ('load', 'measure') and job.simulation:
        job.simulation.close()
        job.simulation = None
        job.replay = {}
        job.passport = {}
        job.emit('simulation_reset','simulation',reason='measurement inputs changed')
    if not REGISTRY.start(job, stage, target):
        raise HTTPException(status_code=409, detail="a stage is already running on this job")
    return {"job_id": job.id, "stage": stage, "state": job.state}


@app.get('/api/simulation/options')
def simulation_options():
    return {'defaults':SimulationConfig().model_dump(), 'schema':SimulationConfig.model_json_schema(),
            'required':{k:{'unit':v[0],'min':v[1],'max':v[2]} for k,v in REQUIRED.items()},
            'machines':machine_catalogue()}


@app.get('/api/jobs/{job_id}/simulation')
def get_simulation(job_id: str):
    job=_job(job_id)
    # Lock the publisher before reading the SSE cursor, avoiding a gap between
    # a snapshot and attaching a new event stream.
    with job.action_lock:
        player=job.simulation
    if player:
        with player.lock:
            return {'plan':player.plan,'state':player.get(),
                    'inputs':simulation.input_view(job),'last_event_id':len(job.events),
                    'example':job.entry.get('kind')=='simulation_example'}
    return {'plan':None,'state':None,'inputs':simulation.input_view(job),'last_event_id':len(job.events),
            'example':job.entry.get('kind')=='simulation_example'}


@app.post('/api/jobs/{job_id}/simulation/control')
def control_simulation(job_id: str, request: Control):
    job=_job(job_id)
    with job.action_lock:
        if not job.simulation or job.simulation.run_id!=request.run_id:
            raise HTTPException(status_code=409,detail='stale or missing simulation run')
        if job.busy:
            raise HTTPException(status_code=409,detail='a stage is changing the inputs')
        try:
            return job.simulation.control(request.action,request.value)
        except ValueError as exc:
            raise HTTPException(status_code=422,detail=str(exc))


@app.get('/api/jobs/{job_id}/simulation/download')
def download_simulation(job_id: str):
    job=_job(job_id)
    with job.action_lock:
        player=job.simulation
        if not player:raise HTTPException(status_code=404,detail='no simulation yet')
        data={'schema_version':player.plan['schema_version'],
              'plan':player.plan,'result':player.get()}
    return Response(json.dumps(data,ensure_ascii=False,allow_nan=False),media_type='application/json',
                    headers={'Content-Disposition':'attachment; filename="cutting-simulation.json"'})


@app.post('/api/simulation/example')
def simulation_example():
    """Explicit synthetic inputs, independent of a person's scan, for exploration."""
    config=json.loads((paths.STUDIO_ROOT/'examples'/'cutting-config.json').read_text(encoding='utf-8'))
    job=REGISTRY.create({}, {'id':'research-example','kind':'simulation_example','label':'Synthetic research example'})
    sizing_map.set_override(job, 'm', 'Synthetic research preset')
    job.simulation_document={'units':'mm','measurements':{},'meta':{}}
    return {'job_id':job.id,'config':config,'example':True}


@app.get("/api/jobs/{job_id}/events")
async def events(job_id: str, request: Request, after: int = Query(default=0, ge=0)):
    job = _job(job_id)
    try:
        last_id = max(0, int(request.headers.get("Last-Event-ID", str(after))))
    except ValueError:
        last_id = 0

    async def gen():
        async for event in job.stream(last_id, request.is_disconnected):
            if event is None:
                yield ": ping\n\n"
                continue
            yield f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/jobs/{job_id}/mesh")
def mesh(job_id: str) -> Response:
    job = _job(job_id)
    if job.mesh is None:
        raise HTTPException(status_code=409, detail="not loaded yet")
    data, decimated = meshio.pack_binary(job.mesh)
    return Response(content=data, media_type="application/octet-stream",
                    headers={"X-Decimated": "1" if decimated else "0"})


@app.get("/api/jobs/{job_id}/result")
def result(job_id: str) -> dict:
    job = _job(job_id)
    # Capture the cursor first; subsequent updates may be replayed, never missed.
    with job.cond:
        cursor = len(job.events)
    points, facing = pipeline.C.landmarks_json(job.landmarks)
    player = job.simulation
    return {
        "job_id": job.id, "state": job.state, "entry": job.entry, "params": job.params,
      "busy_stage": job.active_stage, "last_event_id": cursor,
        "simulation_state": player.get() if player else None,
        "mesh": job.mesh_info,
        "measurements": pipeline.measurement_rows(job) if job.measurements else [],
        "landmarks": points, "facing": facing,
        "prototypes": [{"key": k, **v.to_dict(), "label": v.label} for k, v in job.prototypes.items()],
        "curves": job.curves, "curve_notes": job.curve_notes,
        "size": job.size_view, "replay": job.replay, "passport": job.passport,
        "reports": job.reports,
        "document_path": str(job.document_path) if job.document_path else None,
    }


@app.get("/api/jobs/{job_id}/measurement.json")
def measurement_document(job_id: str) -> Response:
    job = _job(job_id)
    doc = pipeline.document_json(job)
    if doc is None:
        raise HTTPException(status_code=404, detail="no document yet")
    return Response(content=json.dumps(doc, indent=2, ensure_ascii=False),
                    media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="measurement-{job.id}.json"'})


@app.post("/api/jobs/{job_id}/size/override")
def override_size(job_id: str, request: settings.OverrideRequest) -> dict:
    job = _job(job_id)
    with job.action_lock:
        if job.busy:
            raise HTTPException(status_code=409, detail='wait for the current stage before changing size')
        try:
            return sizing_map.set_override(job, request.size, request.reason)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/jobs/{job_id}/reports")
def file_report(job_id: str, request: settings.ReportRequest) -> dict:
    job = _job(job_id)
    try:
        return pipeline.add_report(job, request.target, request.key, request.value,
                                   request.unit, request.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ------------------------------------------------------------ settings ---
@app.get("/api/schema/active")
def schema(lang: str = Query(default="en")) -> dict:
    if lang not in LANGS:
        raise HTTPException(status_code=422, detail=f"lang must be one of {LANGS}")
    return passport_doc.schema(lang)


@app.get("/api/settings/options")
def options() -> dict:
    return {**settings.options(), "default_config": passport_doc.default_config()}


# ----------------------------------------------------------- passport ---
@app.post("/api/jobs/{job_id}/passport")
def build_passport(job_id: str, request: settings.PassportRequest) -> dict:
    job = _job(job_id)
    with job.action_lock:
        if job.busy:
            raise HTTPException(status_code=409, detail='wait for the current measurement or sizing stage before generating the QR')
        try:
            return passport_doc.build(job, request.config, request.base_url)
        except passport_doc.PassportError as exc:
            raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/qr/{code}.png")
def qr_png(code: str, base_url: str = Query(...), scale: int = Query(default=8, ge=1, le=20)) -> Response:
    try:
        passport_doc.decode_checked(code)
        content = passport_doc.png(code, base_url, scale)
    except passport_doc.PassportError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return Response(content=content, media_type="image/png")


@app.get("/api/passports/{code}")
def get_passport(code: str, role: Role = Query(default=Role.PUBLIC),
                 explain: bool = Query(default=False)) -> dict:
    try:
        return passport_doc.passport_for(code, role, explain)
    except passport_doc.PassportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get('/api/passports/{code}/summary')
def get_passport_summary(code: str):
    try:
        version, config = passport_doc.decode_checked(code)
        data = passport_summary.read(code) or passport_summary.configuration_only(code, version, config)
    except passport_doc.PassportError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return Response(content=json.dumps(data, ensure_ascii=False, allow_nan=False), media_type='application/json',
                    headers={'Cache-Control': 'no-store'})


class RevalidatingStatic(StaticFiles):
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


if (DPP_VIEW / "assets").is_dir():
    app.mount("/view/assets", StaticFiles(directory=DPP_VIEW / "assets"), name="view-assets")
app.mount("/static", RevalidatingStatic(directory=STATIC), name="static")
