# Maß-DPP Studio

Three pages share one job through the Maß-DPP chain:

1. pick a scan file (with its licence badge, and its unit stated by you),
2. see it in 3D,
3. run `body-measure` and see the measurement rings, surface paths and landmarks on the body,
4. assign a size from a cited chart — or see why none was assigned,
5. generate a research polo pattern, nest it and simulate cutting and Pfaff sewing in 3D, a terminal, or both,
6. encode the garment configuration with `qr-configurator` and get the QR and the passport.

`/measure?job=…` contains steps 1–4, `/simulation?job=…` contains the manufacturing
simulation, and `/qr?job=…` contains product configuration, QR generation and
the original expandable document JSON. The top navigation keeps the same job;
leaving a page does not pause or restart its server clock. The public destination
at `/view/{code}` also has an expandable, public-only JSON view.

Flow time, electricity, electricity-related CO₂e, material/direct-labour/energy/
equipment costs and the captured size come from the shared engine. Research
presets and calculation boundaries are described in
[workflow and resource model](docs/workflow-resources.md).

The public [SimPy factory CLI](docs/factory-phase1.md) adds deterministic
multi-order cutting, sewing and batch transport with up to 1,000 identical
polos. It uses `requirements-factory.txt` and works without the private QR
submodule. Phase 1 exports research results and indexed replay files; it does
not change the web workflow. See the [measured benchmark](docs/factory-benchmark.md).

Measurement uses the repository's `body_measure` package. Size assignment and
QR encoding use the integrated `polo-line-sim` directory and the
`qr-configurator` submodule (`studio/paths.py`). The new cutting engine lives in
`studio/simulation/`; one immutable plan and server clock drive the 3D
viewer, browser terminal and attached CLI. The original `polo-line-sim`
reports and full-line CLI remain available as the earlier analytical model.

## Cutting studio

Open **Cutting & sewing / Zuschnitt & Nähen / 재단·봉제** in the top navigation.
Choose **Research example** to run immediately with explicitly synthetic
inputs (no scan or personal data). For your scan, run measurement first,
open **Pattern & machine inputs**, review the measured and prototype values,
and supply missing/rejected values with a manual value and source/reason.
Then choose **Generate & cut**.

- **3D / Terminal / Both** changes only the display, never the run.
- **Production line / Cutting table / Fabric top view** changes the camera.
  Select any equipment card to inspect the corresponding 3D machine.
- Pause, play, previous/next task, seek, speed (0.1–100×), and restart all
  control the same server clock. Seek pauses at the requested time.
- Reloading restores the current job in the same browser session. The
  `?job=...` URL opens that job in another tab while this server is alive.
- **Save simulation** downloads the versioned plan and current state.
  The terminal footer provides the exact CLI command for joining this job.

### PowerShell

From this `studio` directory, using the existing virtual environment:

```powershell
# Self-contained research example, using the same calculation engine as the web.
.venv\Scripts\python -m studio.simulate --measurements examples/cutting-measurements.json --config examples/cutting-config.json

# Immediate operation-by-operation output and reproducible artifacts.
.venv\Scripts\python -m studio.simulate --measurements examples/cutting-measurements.json --config examples/cutting-config.json --instant --no-color --jsonl runs/events.jsonl --out runs/cutting.json

# Join a web job; copy the actual job ID and server from the terminal footer.
.venv\Scripts\python -m studio.simulate --attach JOB_ID --server http://127.0.0.1:8010 --no-color
```

For your own body_measure output, replace `--measurements` with its JSON
path and provide a config containing design/machine changes and any
explicit manual supplements. Config keys and ranges are available at
`GET /api/simulation/options`. If the Studio uses BasicAuth, the attached
CLI reads its password from `STUDIO_PASSWORD`; no password is written into
the command URL, event log or simulation artifact. Ctrl+C detaches the CLI
without stopping a web job. An attached CLI exits when cutting completes.

### Construction and assumptions

This is **a geometry-based research draft**, not a fit-validated pattern,
cloth-physics solver or hardware connection. `body_measure`'s original
measurements and pattern-readiness verdict are never changed. This particular
construction uses 11 body inputs (6 core and 5 prototypes); the broader
14-input body readiness gate still describes its own unverified requirements.
Missing or unsuitable core inputs require explicit manual supplements.
Prototypes stay identified as unvalidated research inputs. Clothed core
measurements require manual body values. Wrist sleeve length is not consumed
for this short-sleeved garment.

The original symmetric block constructs the front/back neckline and
quadratic armscye curves, then solves each sleeve-cap half to match its body
armscye. Front/back width balance is distributed without altering paired
side-seam lengths. Armhole depth includes a documented 20 mm construction
allowance. Body length and short-sleeve length are garment design parameters,
not relabelled body measurements. Rib collar/cuff attachment uses the explicit
rib stretch ratio. Seam allowance is an outward polygon offset and shrinkage
compensation scales by `1 / (1 - shrink_pct / 100)`. All these construction
choices need sample fitting before production use.

Nine complete pieces are generated: front, back, two mirrored sleeves,
two plackets, collar and two cuffs. Piqué and rib have separate markers.
Bottom-left placement respects polygon clearance and grain (0°/180° only),
and opens a new bed window rather than bisecting a part. This heuristic
does not claim an optimal marker. Allocation is the sum of each used
window's width × used length; yield and waste come from actual cut polygons.

The schedule contains loading, feed, alignment, vacuum, marking, internal
cuts, external contours and pickup/sorting. Tool-up travel is separate from
cutting; internal cuts precede outer cuts. Time is path distance / configured
speed plus explicit handling/tool delays. There is no acceleration or
measured sensor feed. The editable 1600 × 2000 mm bed, 100 mm/s cutting
speed and handling times are **research assumptions, not S3 specifications**.
The proposal's 3-minute cutter estimate is not imposed on the result.

Equipment follows **Table 3 (Seite 37 / PDF page 41)** and the process diagram
on **Seite 38 / PDF page 42** of `Anlage_zum_Antrag_ITA.pdf`. Zünd S3 runs;
the ITA laser cutter is shown as an alternative. Pfaff, Veit SF 27, camera
QC, ZSK, Epson and Kornit are recognisable downstream/optional models.
Overlock, coverstitch, rib supply and button/buttonhole equipment are marked
as polo additions not named in Table 3. They do not execute in this version.
The S3 rotary-tool and vacuum depiction follows the
[manufacturer's S3 description](https://www.zund.com/en/cutting-systems/digital-cutting-systems/s3-cutter).

### API, persistence and passports

| Interface | Behavior |
| --- | --- |
| `GET /api/simulation/options` | Defaults, JSON Schema, input ranges and machine catalogue |
| `POST /api/jobs/{id}/run/simulate` | Validate inputs/geometry, save an immutable plan, start its clock |
| `POST /api/jobs/{id}/run/replay` | Compatibility alias; legacy delay/embroidery/printing fields are retired |
| `GET /api/jobs/{id}/simulation` | Plan, current snapshot, input provenance, SSE cursor |
| `POST /api/jobs/{id}/simulation/control` | `{run_id, action, value?}`; play/pause/seek/speed/restart/next/previous |
| `GET /api/jobs/{id}/events` | Shared SSE; `simulation_ready` and `simulation_state` events |
| `GET /api/jobs/{id}/simulation/download` | Download plan and current result |
| `POST /api/simulation/example` | Create a separate explicitly synthetic example job |

Geometry is sent with the plan, not with each 10 Hz clock event. Snapshots
carry a run ID, increasing sequence, playback revision, process time,
current operation/window/tool/head, part states and cumulative metrics.
Seeking rebuilds state from the immutable schedule. Old or duplicate
snapshots are discarded; stale control requests return 409.

Plans and result checkpoints are written under
`runs/<job>/simulation/` (or `STUDIO_STATE_DIR`). The live clock, like the
existing Studio jobs, is in memory and is not resumed after a server restart.
The registry retains at most eight jobs; evicting a job closes its clock.
Re-measuring invalidates that job's old simulation; changing draft settings
and starting creates a new run. Saved body provenance and geometry stay in
the internal artifact, never in the QR payload.

Passport manufacturing data explicitly states `is_simulation: true`, the
selected scope, `pattern_status: research_draft_unverified`, cutting/sewing
completion and `finished_garment: false`. It contains no body dimensions or
pattern geometry. Finishing and QC remain unexecuted.

## Run

```powershell
git clone https://github.com/Juunary/body_measure.git
cd body_measure
# Requires access to the private Juunary/ita-qr-configurator repository.
git submodule update --init --recursive
cd studio
.\setup.ps1     # once: venv, requirements, three.js vendored from the DPP viewer
.\run.ps1       # http://127.0.0.1:8010
```

Tests: `.venv\Scripts\python -m pytest` (the pipeline tests skip when
`body-measure/data/generated` is absent — data is never committed).

## What the page will not do

- measure a scan that is not a standing A pose: front and back must be resolvable from the feet and both arms must slice apart from the torso; otherwise the measure stage says why and stops (HSRD-100's fashion scan, or a T pose, is refused here);
- guess a unit: a plain OBJ/PLY/STL needs its unit and up axis stated;
- assign a size to a clothed scan, or to a chest outside the chart's range — the reason is shown and the QR is blocked until the size is overridden, and the override is recorded in the passport (`size_source: manual_override`, with the measured label beside it);
- put a body dimension into the passport: the customer block is polo-line's `CustomerSize.to_dpp()`, which carries the size and the chart it came from and nothing in millimetres;
- claim per-measurement progress: `body-measure` has no progress hooks, so the terminal shows the call boundaries and then the table.

Camera scanning of the QR is deliberately not here yet.

## Cutting and Pfaff sewing

Stage five now runs the shared geometry simulation through Pfaff research
assembly by default. The web offers 3D, terminal or both, a sewing close-up,
editable stitch settings, and an optional cutting-only scope. See
[sewing simulation](docs/sewing-simulation.md) for the process, CLI and limits.
Restart the running Uvicorn server after backend changes, then refresh the page.

## QR product passport

The QR destination is a lightweight, mobile product page in German, English
or Korean. It shows QR product declarations and a saved snapshot of research
cutting/sewing progress, with copy link, public JSON download and print.
It loads no 3D or simulator bundle. Generate the QR again to capture later
progress; opening the page does not update its record. Existing QR codes
without a snapshot show configuration only.

Public snapshots persist in `runs/passport-summaries.sqlite3` (under
`STUDIO_STATE_DIR` when configured). The same configuration code replaces its
older snapshot atomically. Body measurements, scan files and pattern geometry
are excluded. See [passport page](docs/passport-page.md) for API and validation.

## Licence badges

Only HSRD-100 (CC BY 4.0) is cleared for public material. Texel is
CC BY-NC; synthetic SMPL bodies, NOMO and CAPE are internal. The badge is
on every entry so a screenshot of the page cannot be taken innocently.
Uploads are the uploader's responsibility.

## Layout

```
studio/            paths, events, jobs (threads + SSE), files (catalogue), meshio,
                   pipeline (measure), curves, sizing_map, replay, passport_doc, settings, server
static/            index.html, app.js, viewer.js (three.js), terminal.js, settings.js, i18n.js, style.css
tests/
runs/              per-job measurement.json and qr.png (gitignored)
uploads/           user files (gitignored)
```

## A link instead of localhost

**Now: a Cloudflare quick tunnel from this machine.** One command, a
random `https://….trycloudflare.com` link that lives as long as the
window does, and a password in front of everything but the health check:

```powershell
.	unnel.ps1 -Password "choose-one"        # add -Lang KR for the Korean page
```

The scans stay on this machine; the page shows them to whoever has the
link and the password. That password matters: the synthetic SMPL bodies
and anything uploaded are not public material (body-measure decision
#15), so the link must never be an open one. `STUDIO_PASSWORD` turns the
same protection on for any other way of running the server.

**Later: a permanent link on Fly.io.** The image was built, run with a
password, and measured a scan placed on its `/data/scans` volume:

- `studio/Dockerfile` — built from the `body_measure` repository root;
  no dataset is in git, so none is in the image.
- `studio/fly.toml` — app `ita-mass-dpp-studio`, Frankfurt, one machine
  with a volume at `/data` for uploads, results and *deployed scans*
  (`/data/scans`, a mesh plus an optional sidecar `name.json` with
  `units`, `up_axis`, `pose`, `population`, `clothed`, `licence`).
- `.github/workflows/studio.yml` — runs polo-line-sim and Studio tests on
  pushes and pull requests. Deployment remains a deliberate manual step.

First-time steps, from the repository root:

```powershell
flyctl apps create ita-mass-dpp-studio
flyctl volumes create studio_data --region fra --size 3 -a ita-mass-dpp-studio
flyctl secrets set STUDIO_PASSWORD=choose-one -a ita-mass-dpp-studio
flyctl tokens create deploy -a ita-mass-dpp-studio   # -> GitHub secret FLY_API_TOKEN
```

The app name is the link every QR encodes, so rename it before the first
printed label, not after.
