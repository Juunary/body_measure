# Three-page workflow and resource model

The legacy root redirects to `/measure`, retaining its query. `/measure`,
`/simulation` and `/qr` each have their own HTML and ES-module entry point.
`workflow.js` shares job discovery, navigation, language and SSE connection.
Only the measurement page loads the body viewer; only simulation loads the
cutting/sewing viewer. Both QR pages load no Three.js.

The job ID in the URL wins over the session's last job. A page restores the
job and its `busy_stage`/`last_event_id`, then connects to `/events?after=…`.
Native reconnects use `Last-Event-ID`; duplicate event IDs and simulation
sequence numbers are discarded. History-cache restoration reloads current
server state. Navigation never sends a run or playback control request.
Expired jobs offer measurement/example entry paths. Live jobs remain ephemeral
across server restarts; SQLite public QR captures remain durable.

## Calculation boundary

`garment-simulation/3` contains an immutable `resource_ledger`,
`resource_model` (`research-resources/1`), resource settings and captured size.
Every operation has machine, vacuum and common electricity, directly attended
time, equipment occupancy, thread consumption and any purchases at its end.
`snapshot(plan,t)` integrates this ledger to `t`; the same calculation at the
last operation is `plan.totals.resources`. UI speed/pause and computer wall
time never enter the arithmetic. No future operation is counted.

- Flow time: material-load start to the selected scope's last collection, s.
- Electricity: sum of each power × elapsed operation seconds / 3600, kWh.
- CO₂e: electricity × configured gCO₂e/kWh. Electricity only, not product LCA.
- Fabric: each loaded window's full width × used length, m², including waste;
  charge the entire window at load completion. Body and rib use separate rates.
- Thread: sewn length in metres × 3, plus 0.1 m at each completed thread trim
  under the initial preset. Both values are editable.
- Labour: attended operation seconds / 3600 × hourly rate. Loading, alignment,
  vacuum controls, pickup, transfer, sewing setup, seam alignment, presser
  controls, stitching and thread trimming are attended. Automatic feed,
  marking, cuts, travel and cutter tool controls are not.
- Equipment: each machine's own stage occupancy × its hourly rate. Unexecuted
  downstream equipment has no occupancy, electricity or cost.
- Total cost: fabric + thread + direct labour + electricity + equipment, EUR.

Zünd uses active power during feed/mark/cut/travel/tool operations and standby
power during handling. Vacuum adds load from the start of vacuum-on through
completion of vacuum-off. Pfaff uses active power for stitching and standby
power throughout its other operations. Machines are powered only within their
own stage. Common load spans the selected process scope.

## Initial research assumptions

| Parameter | Default |
| --- | --- |
| Zünd active / standby | 1.0 / 0.1 kW |
| Vacuum / common load | 0.8 / 0.3 kW |
| Pfaff active / standby | 0.55 / 0.04 kW |
| Electricity rate / emissions factor | 0.25 EUR/kWh / 380 gCO₂e/kWh |
| Direct labour | 22 EUR/h |
| Zünd / Pfaff equipment use | 6 / 1 EUR/h |
| Body / rib fabric | 5 / 8 EUR/m² |
| Thread | 0.01 EUR/m |
| Thread multiplier / trim tail | 3 / 0.1 m |

These are editable assumptions, not manufacturer specifications, verified
tariffs or actual machine telemetry. Resource setting names carry their units;
the schema rejects invalid/extra unit fields, unsupported currency, negative
or non-finite values. The UI labels every unit. Configuration changes apply to
a new run, while an existing run retains its original assumptions. Historical
plans without a ledger return unknown resources, never a new estimated history.

## Size and QR records

Size is captured from the measurement job's assignment or manual override.
The engine does not create a second size classification. The synthetic example
explicitly uses a manual research size M. A later size change leaves the old
run identifiable and blocks linking it to a differently sized QR until rerun.

The QR still directly encodes product configuration, including size. Changing
resource metrics does not change its encoding or appearance. Engine results
are a code-linked SQLite snapshot, captured when QR generation is requested.
The public summary includes accumulated and planned resources, run size and
public research rates. It excludes raw dimensions, coordinates and paths.

Studio retains the expandable document JSON; public `/view/{code}` exposes
only expandable public summary JSON. Studio document generation removes the
sibling builder's demo production dates/events, fabricated garment dimensions,
repair/warranty/recycling claims and fixed material description. The sibling
Vue project and its independent API are unchanged. Legacy stored public v1
records stay unchanged; new metrics display as not provided until regeneration
from a new run. Finishing/QC remain unexecuted and the product is not certified
as manufactured or finished.

## Verification

Run `.venv\Scripts\python -m pytest tests` from `studio`. The resource tests
cover event boundaries, calculations, parameter isolation, geometry sensitivity,
cutting-only scope, playback determinism, old records and standalone CLI parity.
Workflow tests cover separated routes, query preservation and SSE cursors.

Run `node tests/passport-browser.cjs` with Playwright installed (or set
`PLAYWRIGHT_MODULE` to the package path). It uses an isolated server/database,
tests both JSON viewers and QR persistence, navigation/reload/multiple tabs,
size mismatch and regeneration, resource settings, a real synthetic mesh's
measurement and size flow, 360px/desktop in all languages, and no 3D loads on
QR pages. Screenshots are under `runs/passport-browser-*`.
