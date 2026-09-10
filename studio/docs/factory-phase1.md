# SimPy factory — phase 1

The public Python factory model repeats the existing research polo template
across orders, machines, workers and transport batches. It ends after collection
of the sewn research assembly. There is no factory web route, SSE stream, GUI,
QC, finishing, shipping, or QR update in this phase. The existing three-page
Studio and its `garment-simulation/3` artifacts continue to work as before.

## Run without the private QR repository

From the `body_measure` repository root, using Python 3.12:

```powershell
cd studio
py -3.12 -m venv .venv-factory
.venv-factory\Scripts\python -m pip install -r requirements-factory.txt
.venv-factory\Scripts\python -m studio.factory --scenario examples/factory-scenario.json --out runs/factory-example.json --jsonl runs/factory-events.jsonl --no-color
.venv-factory\Scripts\python -m studio.factory --replay runs/factory-example.json --at 120 --garment order-1:0001 --no-color
```

Linux/macOS use `.venv-factory/bin/python`. An existing Studio environment can install
`requirements-factory.txt` and use the same commands. SimPy is pinned to 4.1.2.
No `git submodule update` or QR credentials are needed for these commands.

The CLI calculates the schedule immediately; `--replay --at` evaluates a saved
process time. It does not sleep for manufacturing time or resume a SimPy process.
Output is plain text by default. Failures return exit code 2 with an explanation;
an invalid scenario never replaces an existing output artifact. JSONL contains
domain transitions with execution ID, content hash, sequence and process time.

## Scenario contract

`factory-scenario/1` accepts these fields. Extra fields, non-finite numbers,
invalid units, non-positive resource counts and non-integer counts are rejected.
Paths below are relative to the scenario file, not the current directory.

| Field | Meaning |
| --- | --- |
| `measurements` | Public body-measure document, or path to its JSON |
| `config` | Existing `SimulationConfig`, or path to its JSON; defaults allowed |
| `size` | Required fixed `label`, optional `source` (default `manual_research`) and `chart` |
| `orders` | Ordered list of unique `id`, positive integer `quantity`, optional `release_s` (default 0) |
| `factory` | Counts and transport settings listed below |

The total quantity must be at most 1,000 and the scope must be `through_sewing`.
All orders share the same dimensions, design and size. A supplied size that
conflicts with the document's assignment is rejected. Size is captured, not
classified again. Existing quality gates and explicitly documented size-based
research supplements still apply; original measurements and flags are preserved.

| Factory parameter | Default / limit |
| --- | --- |
| `zund`, `pfaff` | 1 each; 1–64 |
| `cutting_workers`, `sewing_workers`, `transport_workers` | 1 each; 1–64 |
| `carts` | 1; 1–64 |
| `batch_size` | 1; no greater than buffer capacity |
| `buffer_capacity` | 10; 1–1,000 |
| `transport_s` | Existing `config.machine.transfer_s`; positive, at most 86,400 s |

Transport time is per batch and includes loading, travel, unloading and return.
The whole batch arrives at service completion. It replaces the template's
`transfer_to_sewing`, so there is no duplicate transfer time. Batches never mix
orders. Full batches leave when resources are available; the last smaller batch
is released after all garments of that order have been cut. Completed cutting
output has unlimited storage in this first model. The sewing buffer counts
reserved/transit slots as well as physically arrived garments.

## Scheduling and accounting

Geometry, nesting, fine cutting operations and paired seam paths are compiled
once. Adjacent operations with the same station, fabric window and attendance
requirements become one SimPy interval. The default template has 188 operations,
12 coarse segments, two fabric windows and 18 seams. Different nesting may create
more segments; there is no assumed fixed segment count or shared nesting across
garments.

SimPy timeout callbacks enqueue completions and arrivals. A dispatcher drains
the complete timestamp before sorting ready requests by `(ready time, order
input index, garment number)`. It selects the lowest free instance IDs. This
also determines who receives an idle machine, without relying on process creation
order or the FIFO behavior of ordinary resource requests. Allocation is
non-preemptive.

A cutter stays assigned from the first load through the final piece pickup.
Automatic segments return their worker. The same cutter may then wait for a
cutting worker before its next attended segment. Sewing acquires one Pfaff and
one sewing worker together for the complete attended sewing stage. Transport
acquires its worker, cart and all required buffer slots atomically; sewing
start releases one buffer slot. These rules avoid circular holding dependencies.
Every run checks instance overlap, retained allocations, buffer bounds and
completion. An exhausted event queue with unfinished garments is an error,
including the pending work and buffer state in the diagnostic.

The factory ledger uses `factory-resources/1`:

- Working machine power, vacuum, fabric purchases, thread use and direct labour
  retain the template's operation-specific rates and timing.
- A held cutter waiting for a worker uses standby power, equipment occupancy
  cost and any still-enabled vacuum. Waiting workers incur no labour cost.
- Transport incurs one worker's direct labour per batch, split equally across
  the batch members. Manual carts have zero power and zero equipment fee.
- Unoccupied machines are powered off. Unexecuted equipment has no costs.
- Common power applies once to the union of working intervals, including
  automatic tasks and transport. No common power is charged when all tasks are
  waiting. At each time it is allocated equally among active garments; a batch
  contributes its garment count. Order and garment totals reconcile to the
  factory total.
- Fabric is charged at each load completion, including waste. Thread tails are
  charged only on completed trims. In-progress stitching includes continuous
  thread length and integer completed stitches.

Garment Flow time spans first load to final assembly collection and includes
intermediate waits. Lead time additionally includes waiting since order release.
Order Flow time spans its first load to last collection. Factory makespan is
first load to last collection, while `completion_time_s` is the absolute process
time since scenario time zero. Throughput uses completed assemblies / makespan.
Utilization is working time / makespan; occupied waiting and idle time are
reported separately. Queue averages use the same observation horizon. Transient
zero-duration states within one timestamp are excluded from queue peaks.

For one garment without waiting, time, paths, pieces, stitches, fabric, thread
and direct labour match the original engine. The old engine charged Pfaff
standby electricity and equipment occupancy during transport. The factory
removes those two charges and their derived electricity cost and CO2e. This is
an explicit model difference, not an empirical correction. Common power is equal
in this uninterrupted one-garment case. See the measured difference table in
[factory-benchmark.md](factory-benchmark.md).

## Saved files and Python API

```python
from studio.factory import simulate, Replay, save, load

run = simulate(scenario_dict)  # paths must already be resolved to JSON objects
save("run.json", run)
player = Replay(load("run.json"))
state = player.snapshot(120.0, garment_id="order-1:0001")
```

`factory-simulation/1` contains the normalized scenario, one legacy template,
template indexes, garment IDs/timestamps, coarse working/waiting intervals,
instance assignments, domain events, accounting indexes, replay checkpoints and
final factory/order/garment results. Inputs contain internal measurement
provenance: this is a local research artifact, not the public passport schema.
Convenience measurement/config filenames are resolved before persistence.

The file has a random execution ID, UTC creation time and a deterministic SHA-256
content hash. Metadata and display speed do not change the content hash. Geometry
libraries and SimPy versions are recorded in the benchmark environment; changes
to calculation code or dependencies can change results. Loading verifies the
format version and hash. Saves use a temporary file in the destination directory
and atomic replacement. Legacy garment artifacts are not migrated to factory
records.

Template operation ends and continuous/discrete quantities have prefix indexes.
Factory queries sum completed segment prefixes plus partial values in active
machine/cart lanes. Working intervals retain shared-template references, so fine
operations are not expanded for each garment. Public replay returns counts,
active instances, current accumulated quantities and optional detail for one
garment; final planned quantities remain under `run.result`.

Every 256 domain events, a checkpoint stores lightweight garment lifecycle and
resource states. Forward queries apply deltas; random seeks restore a checkpoint
and apply at most 255 events. Duplicate sequence numbers are ignored; gaps are
rejected. Checkpoints restore playback state, not a running SimPy environment.

## Verification and review gate

```powershell
python -m pytest factory_tests -q
python -m studio.factory.benchmark --out runs/factory-benchmark.json --report runs/factory-benchmark.md
# With the full Studio dependencies and QR checkout:
python -m pytest tests -q
```

Factory tests run without the private QR repository, including an isolated
subprocess that denies imports of QR, polo, web and legacy path bootstrap modules.
Golden files cover one garment, two orders, limited workers, multiple machines,
batch transport and the final partial batch. Additional tests compare indexed
results with a slow operation-by-operation reference, validate all one-garment
operation boundaries and midpoints, check conservation and parameter isolation,
and exercise checkpoint replay, corruption, rejected measurements and CLI errors.
Golden files are checked-in references; tests never update them automatically.

The benchmark records build/save/reload time, event and segment counts, artifact
size, OS peak process resident memory, and 1,000 random summary-plus-selected-
garment queries after 50 warmups. Its gate is p95 below 50 ms and at most 255
events replayed after a checkpoint. The report also exposes maximum latency;
this is not a hard realtime guarantee or a browser/SSE performance test.

Phase 1 ends here for review. API/SSE/terminal comparison tables, schematic 3D
and passport integration remain separate later decisions. Later QR integration
must show run ID, order ID and capture time on the public page/JSON/download,
with the latest selected order replacing the same configuration code's snapshot.

### Verification recorded on 2026-09-10

- 49 factory tests passed in both the existing environment and a newly created
  environment installed solely from `requirements-factory.txt`, including the
  subprocess checkout with no private modules and import denial checks.
- 99 existing Studio tests passed (cutting, sewing, resources, workflow, QR and
  passport regression coverage).
- 57 selected public measurement tests passed (`test_sizing`,
  `test_result_schema`, `test_pose_gate`).
- From `polo-line-sim`, `python -m unittest` passed 38 legacy polo process
  tests. `python -m pytest test_polo_line.py -q -p no:cacheprovider` passed
  the full set of 43 tests: the same 38 plus five module-level pytest
  functions covering measurement-document and passport size handling.
- All single-garment operation boundaries and midpoints matched the original
  engine. Shifted multi-garment boundaries were checked immediately before,
  at and after the boundary, including floating-point translation effects.
- The final 1,000-garment benchmark passed after installation in the fresh
  public environment; exact measurements and dependency versions are in
  `factory-benchmark.json` and `factory-benchmark.md`.

CI configuration now runs factory tests and the benchmark without checking out
QR. These changes were verified locally; no remote workflow run is claimed here.
