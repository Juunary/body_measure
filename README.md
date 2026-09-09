# body-measure

This repository also contains **Maß-DPP Studio**, the browser workflow that
connects measurement and size assignment to polo cutting, Pfaff sewing, and a
QR product passport. The measurement package remains usable on its own.

## Maß-DPP Studio

Clone the QR dependency, install the Studio environment, and start the local
server from the repository root:

```powershell
# qr-configurator is a private dependency; authenticate to GitHub first.
git submodule update --init --recursive
cd studio
.\setup.ps1
.\run.ps1 KR
```

Open <http://127.0.0.1:8010/>. The workflow is split across `/measure`,
`/simulation`, and `/qr`; all three pages share the same job ID. See
[`studio/README.md`](studio/README.md) for the simulation, CLI, passport, and
research-boundary documentation.

Repository CI can run the complete Studio suite when the private
`QR_CONFIGURATOR_TOKEN` secret has read access to `Juunary/ita-qr-configurator`.
Without that secret it runs the public polo process tests and reports the
Studio suite as skipped.

A measurement pipeline that extracts seven shirt measurements from a 3D
body mesh. Built for the Maß-DPP project (ITA, RWTH Aachen) ahead of the
3D body scanner's arrival — inputs are abstracted behind adapters, so the
scanner becomes one more adapter when it lands.

**Where the validation boundary sits.** Before the scanner, this project
validates the pipeline's implementation correctness, reproducibility and
robustness. Measurement accuracy and repeatability against real subjects
are validated only after the scanner arrives, with a trained measurer.
No number here may be read as an ISO 20685-1 conformance claim
(`docs/decisions.md` #1). The claim a result is allowed to make is derived
in code from what it was compared against, never typed by hand
(`body_measure/validate/claims.py`).

## Measurements

[measurement-spec.v1.yaml](measurement-spec.v1.yaml) is the contract. It
pins each measurement by its **definition** (ISO 8559-1), its route
waypoints, the posture, and the known deviations — never by name alone:

| Measurement | Kind |
|---|---|
| chest circumference | girth |
| waist circumference | girth |
| neck circumference | girth |
| upper-arm girth | girth (added for the short-sleeve stage-1 garment) |
| across-back shoulder width | surface path |
| sleeve length | surface path |
| back length | surface path |

Reference values are mapped by definition too. Agreement with a dataset's
own automatic values is `dataset_agreement`; it is not accuracy.

## Setup (Windows)

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest tests -q   # green without any dataset present
```

The measurement core never imports torch. The SMPL track needs
`requirements-smpl.txt` (torch CPU). The clothed-scan inference work
stream (C2/C4) will live under `body_measure/inference/` with its own
`requirements-inference.txt`, keeping torch out of the core.

On Windows, set `PYTHONUTF8=1` for scripts that print non-ASCII.

## Usage

```powershell
# Units are never guessed — the input unit is mandatory
.venv\Scripts\python -m body_measure measure body.ply --input-unit m --up-axis Z --estimate --out result.json
```

`--estimate` first checks that the scan is a standing A pose — front and back resolvable from the feet, both arms clear of the torso — and refuses with the reasons if it is not (decision #45); `--skip-pose-gate` measures anyway and records that.

The result JSON contains exactly the seven spec keys. Anything that could
not be measured is reported as `null` plus quality flags, never as a
substitute number. Girths carry both `raw_contour_mm` (the intersection
polyline) and `taut_tape_hull_mm` (convex hull, hull ≤ raw).

## What the pipeline refuses to do

These are enforced in code, not in documentation:

- **Measure a scan that is not a standing A pose.** Front and back must be resolvable from the feet and both arms must slice apart from the torso; otherwise `--estimate` stops with the reasons and writes every measurement as `pose_rejected` (decision #45).

- **Guess a unit.** An adapter must know its unit or be told one.
- **Fill a hole.** A slice whose gap exceeds the accept band returns
  `null`; the closure tiers are AND-bounded (`validate/thresholds.py`).
- **Trust a fallback.** A torso loop chosen by nearest-centroid fallback
  may feed a flagged girth but never anchors a landmark
  (`docs/decisions.md` #22).
- **Call a detour a length.** A surface path more than 1.5× its chord is
  walking *around* the body, not along it, and is demoted to manual
  review (#21).
- **Overclaim.** The claim category comes from the (pathway, reference)
  pair. `measurement_accuracy` is unreachable until a manual reference
  exists.

## Layout

- `body_measure/adapters/` — input normalisation to `NormalizedBodySurface`,
  unit enforcement, per-dataset capability contracts (`provides` for
  reference values, `fit_references` for body surfaces — kept orthogonal)
- `body_measure/canonicalize.py` — canonical frame (Y-up, floor at 0) and
  duplicate-vertex welding, which photogrammetry OBJs require
- `body_measure/measure/` — plane slicing, torso-loop selection,
  circumference, surface paths on the edge graph
- `body_measure/landmarks/` — estimated (topology-agnostic) landmarks
- `body_measure/validate/` — claim taxonomy, statistics, robustness battery
- `scripts/` — dataset reports, the SIZER manifest audit, the export probe
- `docs/decisions.md` — every decision in *decided / rules out / revisit if*
  form; `docs/plan.md` — the current work plan and what blocks what;
  `docs/datasets.md` — provenance and download procedures;
  `docs/reference-garment-sizing-and-pom.md` — EU size standards and
  factory measurement points, and what of that touches this pipeline;
  `docs/licenses/` — the LICENSE-G0 gate

## Clothed-scan work stream

Measuring a dressed subject is a separate pathway (`measured_clothed`) and,
further on, body recovery under clothing (`inferred_smpl_under_clothing`).
The plan runs in slices — clothing offset (C1), representation ceiling
(C1.5), gap atlas (C1b), optimisation fitting (C2), synthetic data (C3),
neural regression (C4) — each gated on the one before. The offset report
skeleton already runs on HSRD-100 and emits no offset, because HSRD ships
no same-subject body reference; the numbers come from SIZER.

## Data and licences

`data/external/`, `models/`, checkpoints and every weight file are
gitignored. No dataset file is ever committed. Public material — weekly
decks, reports, anything leaving the project — uses **HSRD-100 (CC BY
4.0) only**. The clothed-scan work stream does not start a slice before
the checklist in [docs/licenses/README.md](docs/licenses/README.md) is
satisfied. Details and download procedures: [docs/datasets.md](docs/datasets.md).
