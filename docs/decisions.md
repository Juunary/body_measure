# Decisions

Format follows dpp-prototype: decided / what it rules out / revisit if.

## 1. Pre-scanner validation claims are bounded

**Decided:** Before the scanner arrives we validate implementation
correctness, reproducibility, and robustness only. Real measurement
accuracy and repeatability (manual-tape comparison, ISO 20685-1 protocol)
are validated after the hardware arrives. Reports must label every number
with its category: `analytic_correctness`, `synthetic_agreement`,
`numerical_robustness`, `dataset_agreement`, `scan_repeatability` (proxy),
`measurement_accuracy` (post-scanner only).

**Rules out:** Claiming ISO 20685-1 conformity from synthetic meshes or
dataset comparisons; using ISO allowable errors as per-body pass/fail
gates before the standard's protocol can actually be run.

**Revisit if:** The scanner arrives, or ITA provides access to subjects
plus a trained measurer.

## 2. Measurement definitions live in measurement-spec.v1.yaml, not in code

**Decided:** The six shirt measurements are fixed by definition (ISO
8559-1 naming), route waypoints, posture, and known deviations in the
spec file. Result JSON contains exactly these keys. `definition_verified`
stays false until each definition is checked against the ISO 8559-1 text
(ITA library task).

**Rules out:** Renaming or reinterpreting a measurement in code without a
spec version bump; comparing against reference values whose definition
does not match (`no_reference: true` items).

**Revisit if:** The ISO text check changes a definition, or ANTHROSCAN's
measurement list becomes the de-facto downstream contract.

## 3. Circumference reports both raw contour and taut-tape hull

**Decided:** Every circumference carries `raw_contour_mm` and
`taut_tape_hull_mm` (hull <= raw for a simple closed contour), plus a
provisional `selected_value_mm` with `selection_method: convex_hull`.

**Rules out:** Hard-coding either value as "the" tape measurement before
manual comparisons exist.

**Revisit if:** Post-scanner manual tape comparisons show, per
measurement, which value (or which mix) matches practice.

## 4. Torso-loop selection is axis-based with an honest failure mode

**Decided:** Priority: loops containing the body-axis point → largest
area among those → nearest centroid (low confidence, flagged) → null.
Landmarks and selections carry `confidence`, `method`, `quality_flags`.

**Rules out:** "Largest loop" as a criterion (the two-cylinder test
enforces this); forcing a number when no closed loop is trustworthy.

**Revisit if:** Real scans show systematic axis-estimation failures
(e.g., leaning subjects) — then the per-height torso axis replaces the
global centroid axis.

## 5. Units are never guessed

**Decided:** Vertex units come from adapter metadata or an explicit
`--input-unit`; otherwise loading fails. No bounding-box heuristics.

**Rules out:** Silent m/mm confusion producing 1000x errors that look
like algorithm bugs.

**Revisit if:** Never, ideally.

## 6. Slice loops are chained from mesh_plane segments, not Path3D.discrete

**Decided:** `slice_mesh` chains `trimesh.intersections.mesh_plane`
segments itself (grid-merge endpoints, walk degree<=2 components).
Reason: `Path3D.discrete` returns [] for open cross-sections, and open
sections must be reported (`open_loop`), not dropped. Non-manifold
junction components are skipped — better no number than a wrong one.

**Rules out:** Depending on trimesh path internals for correctness.

**Revisit if:** trimesh changes mesh_plane semantics, or junction-heavy
scan meshes need explicit handling beyond skipping.

## 7. SMPL beta monotonicity is not a test

**Decided:** SMPL shape betas are not semantically fixed independent
variables; sweeps are evaluated by correlation/MAE/bias against reference
measurements. Invariance tests (rigid transform, uniform scale, winding,
remeshing) plus targeted deformations (radial waist expansion) replace
beta monotonicity.

**Rules out:** "beta k up implies girth up" assertions.

**Revisit if:** —

## 8. Ground truth is mapped by definition, not by name (Texel waist = m102)

**Decided:** Our estimated waist (minimum torso girth) is compared against
Texel m102 "Minimum Waist Girth", not m16 "Waist Girth" (ISO 5.3.10,
natural waist level). First run on Part 1 made the difference measurable:
vs m102 mean −3.5 mm / max 38.6 mm; vs m16 mean −19.9 mm — a systematic
definition gap, not an algorithm error. m16 is kept as an aux diagnostic.
Regression bounds in validate/thresholds.py are internal targets derived
from this run.

**Rules out:** Comparing values whose definitions differ and calling the
gap an error; tuning the algorithm to chase m16 while the spec says
minimum girth.

**Revisit if:** The shirt pattern workflow needs the natural-waist girth
(m16 definition) — then the spec gains a second waist measurement with an
anatomical landmark strategy, as its own spec version bump.

## 9. Armpit search runs top-down; chest clips merged arms, always flagged

**Decided:** The armpit level is the HIGHEST slice with >= 3 closed loops —
searching bottom-up stops at the hanging wrists (hands separate from the
torso near hip height; observed on every Texel Part 1 body). Real subjects
stand with arms touching the torso, so the chest/bust level can sit above
the arm-merge height; there the merged cross-section is clipped to the
torso x-range taken at the armpit level and the largest central piece is
measured — a tape approximation carrying `arm_clipped_at_merged_level` in
quality flags, never silent. Effect on Part 1 vs m5: mean error went from
−72 mm (measuring the under-bust region) to +33 mm.

**Rules out:** Bottom-up "first 3 loops" armpit detection; publishing a
chest girth from a merged slice without the clip flag.

**Revisit if:** Scans arrive in a proper A-pose (arms separated to the
chest level) — then the plain torso-loop path covers chest and the clip
becomes a fallback; or if the scanner software provides segmentation.

## 10. Shoulder points are the highest surface above the armpit crease

**Decided:** With hanging arms, the lateral silhouette extreme above the
armpit is the ARM, not the shoulder — using it sent the shoulder-width
path around the arm mass (+454 mm mean on Part 1). The v1 acromion
approximation is the highest vertex in the vertical column above the
armpit crease (mean error dropped to +32 mm). Sleeve length keeps a known
systematic overshoot (+197 mm mean: edge-graph inflation + acromion
approximation + arm/torso contact detours); its regression bound guards
against getting worse, and the offset is an open improvement item (heat
method, arm-axis waypoints, elbow waypoint).

**Rules out:** Treating the sleeve regression bound as an accuracy claim;
lateral-extreme shoulder points.

**Revisit if:** A heat-method geodesic lands (recheck all three lengths),
or scanner software provides palpated-equivalent landmarks.

## 11. The lateral axis comes from arm-loop centroids, never world x

**Decided:** All side-dependent logic (chest arm-clip bounds, shoulder
creases, wrist side assignment) uses a body lateral axis estimated from
the line between the two arm-loop centroids at the armpit slice — stable
on the poses tested so far (Texel Part 1, generated SMPL bodies) — with
cross-section PCA as a flagged fallback (`lateral_axis_pca_fallback`,
propagated into every dependent measurement; unvalidated for asymmetric
or single-arm bodies). World x is never assumed — the robustness battery
showed yaw+translation shifting chest by +142 mm under the world-x
version, and a scanner will not guarantee subject alignment. PCA alone is
also insufficient: a torso slice can be deeper than wide (Texel Woman4),
sending the PCA major axis front-back.

**Rules out:** World-axis assumptions in measurement code; PCA-primary
lateral estimation.

**Revisit if:** Bodies with a single detectable arm appear (amputee scans
— currently falls back to PCA, unvalidated).

## 12. Armpit position is the highest separating slice; persistence sets confidence only

**Decided:** The armpit level is the highest slice with >= 3 closed loops.
Whether the slice below also separates only downgrades/upgrades
confidence (`single_slice_arm_separation` flag) — it never moves the
position, because a lower, thicker separation zone (forearm gaps) must
not outrank a one-slice-thin true armpit (Texel Woman4). Consequence:
1 mm vertex noise on real scans can still shift the armpit and with it
chest (+~250 mm) and shoulder width (+~200-500 mm) — an OPEN, documented
fragility. Waist/neck are noise-stable (<12 mm).

**Rules out:** Persistence-based position selection; pretending the noise
sensitivity away by loosening thresholds silently.

**Revisit if:** Slice-profile smoothing or scanner-provided landmarks
land; then re-run scripts/robustness_report.py and tighten.

## 13. SMPL v1.1.0 pickles are converted once to plain numpy

**Decided:** chumpy no longer installs on modern Python, so
scripts/convert_smpl_pkl.py unpickles the release files with a stub-class
Unpickler (any chumpy.* class -> stub, array taken from its 'x' attr) and
rewrites plain-numpy pickles that smplx loads directly. Originals kept as
*_chumpy.pkl. Sidecar JSONs record model version, seed, betas, pose for
every generated body.

**Rules out:** Installing chumpy; regenerating bodies without sidecar
provenance.

**Revisit if:** smplx changes its expected .pkl schema.

## 14. Stage 1 is a short-sleeve shirt; upper_arm_girth joins the spec

**Decided:** Handover confirmed the stage-1 product is a short-sleeve
shirt (long-sleeve extension undecided). A short sleeve ends on the upper
arm, so `upper_arm_girth` (right side, maximum girth between armpit and
the upper-arm span) is added as spec v3 — the same plane-slice primitive
as the torso girths, applied to the arm loop that arm_loops_at already
isolates. sleeve_length is KEPT but demoted: its regression bound only
guards against regressions, and the +198 mm decomposition drops in
priority. References: Texel m15_r (ISO 5.3.16), NOMO Bicep_Circ — both
judged approximate until the ISO text check.

The search window's upper clearance was removed (20 mm -> 0) after the
maximum landed on the window boundary for all ten Texel subjects; the
choice was then cross-checked on NOMO (bias -5.5, MAE 19.0), not tuned
further. Negative clearance (above the armpit) was measured to help
slightly on Texel and rejected as overfitting.

**Rules out:** Optimising sleeve_length before the definition audit
resolves; picking window parameters on a single dataset without a
second-dataset check.

**Revisit if:** Long-sleeve becomes confirmed (sleeve_length precision
returns to the critical path), or the ISO 5.3.16 text moves the mapping
to exact/mismatch.

## 15. Public artifacts use HSRD-100 only

**Decided:** Weekly reports, portfolio, and anything shown outside the
research context use HSRD-100 (CC BY 4.0) exclusively. Texel (CC BY-NC),
NOMO (no redistribution), SMPL (no redistribution) stay inside
`data/external/`, which is gitignored wholesale.

**Rules out:** Screenshots or derived meshes from NC-licensed data in
public material; committing any dataset file.

**Revisit if:** A dataset's license changes or ITA legal advises
otherwise.

## 16. A claim is derived from its reference, never typed by hand

**Decided:** `body_measure/validate/claims.py` holds the vocabulary of
pathways and reference kinds, and the claim category follows from the
PAIR. The same reference licenses different claims depending on what was
measured against it: a clothed scan against a body reference yields
`clothing_offset` (it characterises the garment), an inferred body against
that same reference yields `reference_surface_agreement` (it characterises
the inference). Undefined pairs raise rather than defaulting, and
`manual_reference` is registered as `available=False`, so
`measurement_accuracy` is unreachable in code until a tape and real
subjects exist.

**Rules out:** hand-labelling a comparison; an inferred-body agreement
being presented as accuracy; a provided registration being described as a
minimal scan.

**Revisit if:** a manual reference becomes obtainable (flip `available`),
or a new pathway/reference is added — deliberately, as a new entry.

## 17. What SIZER ships is audited before an adapter assumes it

**Decided:** `scripts/audit_sizer_manifest.py` runs before
`adapters/sizer.py` exists. The published description does not establish
that every clothed scan has an independent raw minimal scan in 1:1
correspondence, and "body under clothing" is not the same reference as "a
provided registration". The audit reports which subjects actually have a
`raw_minimal_scan` and **downgrades the permitted claim wording** to
"provided body-reference surface" when they do not. Unrecognised files
become `unclassified` and are reported, never guessed into a role.

The data model is `Subject ├─ BodyReference 0..N └─ ClothedObservation
1..N`, not one clothed plus one minimal surface per subject.

**Rules out:** an adapter built on an assumed pairing; a results sentence
that claims more than the data supports.

**Revisit if:** the real download shows a structure the role patterns miss
— extend `ROLE_PATTERNS`, do not loosen the classifier.

## 18. Train/test split is subject-disjoint and locked before any statistic

**Decided:** SIZER repeats a subject across garments and sizes, so a
scan-level random split puts one body shape on both sides. The split is
subject-disjoint, decided in the audit step, and hashed into
`reports/split-manifest.json`. Train-only subjects feed the C1b gap
atlas, the C2 priors and the C3 simulator calibration; test subjects
contribute to no prior, threshold or calibration.

**Rules out:** computing a clothing offset over all subjects and then
evaluating on those same subjects.

**Revisit if:** the split policy changes — the hash makes that visible.

## 19. The export path was proven before an architecture was chosen

**Decided:** `scripts/probe_export_path.py` runs a deliberately
export-hostile throwaway model (runtime kNN, the pattern DGCNN-class
encoders are built from) through torch.export → ONNX → ONNX Runtime CPU,
at 4k and 8k points, before any encoder is selected. Measured on this
machine (torch 2.13.0+cpu): export ok at both sizes, CPU parity 3e-8 to
6e-8 (float32 noise), dynamic batch ok, ONNX CPU p50 71 ms at 4k and
224 ms at 8k.

Three environment constraints were found and are recorded in
`requirements-inference.txt`:
- export with **batch >= 2** — torch.export specialises a dim it only ever
  sees as 1 and then refuses the dynamic constraint;
- `onnxscript` is required by `torch.onnx.export` and is not pulled in;
- **`PYTHONUTF8=1` on a cp949 console** — the exporter's progress output
  contains characters cp949 cannot encode and kills the run.

The probe's peak RSS (1.9 GB at 4k, 6.4 GB at 8k) is the cost of its
O(N^2) distance matrix and is **not** a budget for a real encoder — it is
the pattern a real encoder must avoid.

**Rules out:** discovering after a GPU training run that the model cannot
be exported for CPU inference; TorchScript as the primary path (deprecated
in torch 2.13).

**Revisit if:** the chosen encoder introduces control flow the probe did
not cover — rerun the probe with that model before training.

## 20. A clothed scan loses four of seven measurements — and the core has no human-range bound

**Decided:** The C1 skeleton runs on HSRD-100 (CC BY 4.0), the only
dataset usable while SIZER licence review is open. HSRD ships **no
same-subject body reference**, so `HsrdAdapter.fit_references` is empty
and `scripts/clothing_offset_report.py` emits `offset.status:
"unavailable"` with a reason instead of a number. The offset itself
belongs to SIZER.

What the skeleton did establish, on a jacket/jeans/boots scan:

| measurement | clothed result |
|---|---|
| neck girth | the only clean one — and the only LOD-stable one (max abs delta 2.8 mm) |
| chest girth | produced, arm-clipped, LOD delta 154 mm |
| waist girth | produced, `minimum_at_search_boundary`, LOD delta **808 mm** |
| upper-arm girth | rejected — `no_arm_loop_in_upper_arm_window` (a jacket merges arm into torso) |
| shoulder width, sleeve, back length | rejected — `disconnected_surface_path` (the clothed mesh is several shells) |

**The finding that matters most is a gap in the core:** at the coarse LOD
the pipeline returned a waist of **140.9 mm** and an upper-arm girth of
**174.7 mm** with disposition `accepted`. No human has those. The
measurement core has **no plausibility bound at all** — it flags low
confidence but never asks whether a body could have the number.

The report therefore carries a REPORT-level `implausible` field with a
generous adult range per measurement, so a future offset table cannot be
averaged over impossible values. The core was deliberately left unchanged:
choosing a hard range is a design decision with real cost (unusual bodies,
children, per-garment inflation) and belongs in its own decision, not in a
skeleton run.

**Rules out:** computing a clothing offset from HSRD; building the SIZER
offset table without a plausibility filter; assuming clothed scans degrade
gracefully — four of seven measurements do not degrade, they disappear.

**Revisit if:** a human-range gate is added to the core (then the report
filter becomes redundant), or `disconnected_surface_path` is addressed —
it alone costs all three length measurements on clothed scans.

## 21. `disconnected_surface_path` was a loader defect, not a hole in the body

**Decided:** weld duplicate-position vertices in `canonicalize` (on by
default, `weld=False` for fixed-topology callers), and make the remaining
surface-path failures distinguishable from one another.

The flag cost all three length measurements on every clothed scan, and the
name invited the wrong diagnosis — a jacket looked like it had torn the
surface. It had not. HSRD's OBJ splits a vertex once per texture chart, so
the same 3D point arrives under several indices: **1348 vertex-graph
components at lod2, the largest holding 1.94 % of vertices.** Measured
directly, 69 % of vertices had a cross-component neighbour at **0.0000 mm**
— coincident duplicates, not gaps. Merging by position gives one component
at lod2 and 99.98 % at lod1, with bounds and area unchanged.

It cannot be fixed in the adapter: trimesh keeps UV-split vertices apart
while texture data is attached. By the time a surface reaches
`canonicalize` the UVs are gone and position is all that is left to merge
on. Texel was already effectively connected, so this is a no-op there —
92 tests passed unchanged before the guards below were added.

**The fix alone would have made the pipeline worse.** A connected mesh
always yields *some* number, so three measurements went from `null` to a
`clean` bucket — and two of the new values are impossible (back length
944 mm, sleeve 1114 mm). A quiet wrong answer is worse than an honest
refusal, so two guards ship with the weld:

- `surface_path_detour` — path length over straight-line chord above 1.5.
  A path down the spine exceeds the chord by a little; one that goes
  *around* the torso because the landmarks are on opposite sides does not.
  Demoted to `manual_review`, never `accepted`.
- `waypoint_off_main_surface` / `waypoint_snapped_to_main_component` — a
  landmark whose nearest vertex sits on a fragment is pinned to the main
  component if that moves it under 15 mm, and refuses beyond.

**What this exposed:** the connectivity failure was masking a worse one.
With the surface walkable, the landmarks are visibly wrong on a clothed
body — lod1 puts the waist at y=759 mm, 45 % of stature, at thigh height;
lod2 puts the back-neck and back-waist points on opposite sides of the
torso. **Clothed-scan lengths now produce numbers and those numbers are
not usable.** Coverage went 3/7 to 6/7 *producing values*; it did not go
3/7 to 6/7 *working*.

**Rules out:** reporting clothed-scan length coverage as a capability;
tuning `MAX_PATH_CHORD_RATIO` until it happens to catch lod1's 944 mm back
length — one scan is not evidence for a threshold, and that failure is a
landmark error that a ratio test cannot see.

**Revisit if:** landmark estimation is made clothing-aware (the real next
problem), or a dataset appears whose legitimate paths exceed ratio 1.5.

## 22. A fallback loop may feed a girth, never a landmark — and #20 is answered

**Decided:** three trust rules in landmark estimation, and a resolution of
the open question from decision #20: **no absolute human-range gate goes
into the measurement core.**

The W1 diagnosis (HSRD, jacket/jeans/boots, vs a Texel baseline) reduced
every "clothed landmarks are wrong" symptom to one mechanism plus one
window effect:

1. **The 140.9 mm waist was a trust failure, not a range failure.** At one
   single height (lod2, y=1249) the torso loop fails axis containment and
   the nearest-centroid fallback picks a 140.9 mm jacket-fold loop —
   and `_extremum_level` took the argmin over the profile without regard
   to how each slice was selected, so one conf-0.4 guess beat 25 conf-0.9
   slices. `torso_girth_profile` now skips non-axis-containment slices
   outright. Skipped, not down-weighted: one untrusted slice in an argmin
   poisons the whole profile.
2. **`estimate_back_point_at` refuses fallback loops.** The most-backward
   point of a loop that is merely *near* the axis can face anywhere — on
   HSRD it landed 104 degrees off the back (backness −0.25). No back
   point beats a wrong one.
3. **Shoulders carry their doubt.** Shoulder landmarks inherit the armpit
   flags they stand on, and a vertical step over 5 % of stature between
   the two "shoulders" (200 mm on lod2 — a collar vs a sleeve; Texel
   subjects sit within 3 mm) flags `shoulder_vertical_asymmetry`, which
   demotes every dependent length to manual_review. Anchor-landmark flags
   now propagate into the lengths built on them (back_length inherits the
   waist boundary flag; sleeve inherits shoulder flags).

Effect on HSRD: waist LOD spread 808 mm → **0.36 mm**, back-length spread
350 mm → 7.7 mm, chest 154 mm → 42 mm; the asymmetric-shoulder sleeve
(1114 mm) is manual_review. Texel: worst change 0.005 mm (= rounding of
the recorded baseline), so the validated numbers stand.

**Why #20 closes without a core range gate:** both impossible values
traced to the same mechanical cause — an untrusted loop reaching an
argmin — which is now removed. A hard mm range would have *masked* that
defect as "rejected: out of range" instead of exposing it, and it costs
real coverage on unusual bodies and children. The report-level
`PLAUSIBLE_MM` net stays, and stays at the report level.

**What remains honestly unusable on clothed scans:** back_length ~944 mm
is now *flagged* (low_confidence via the inherited boundary flag) but the
number itself is a garment fact — a jacket hides the natural waist, so
the search ends at its window boundary near the jeans. That is not a
landmark bug; it is what "the waist of a dressed body" means, and it is
exactly the gap the SIZER offset (C1) exists to measure.

**Rules out:** down-weighting fallback slices instead of skipping them;
per-garment window tuning against one HSRD subject.

**Revisit if:** SIZER's clothed scans show axis-containment failing over
whole height bands (then profile coverage, not trust, becomes the
problem), or a legitimate body produces shoulder asymmetry above 5 %.

## 23. C2 optimisation fitting — first working version, and what its own gates found

**Decided:** `body_measure/inference/` (torch-isolated), a staged shell-fitting
optimiser, and an 8-case synthetic gate battery
(`scripts/c2_synthetic_battery.py`). Claim category `synthetic_recovery`,
derived from (`inferred_smpl_under_clothing`, `synthetic_latent`) — never
typed by hand.

Four debugging findings fixed the optimiser; a fifth surfaced a real
limit that stays, by design, unfixed at this layer.

**Face winding cannot be trusted, but it can be repaired.** A per-point
heuristic ("normal points away from the body axis") silently flipped
every inward-facing arm normal, so the identity shell — the floor of the
battery, offset zero, the shell IS the body — failed to fit itself.
Replaced with `trimesh.repair.fix_normals(multibody=True)`, which treats
winding as a mesh property to correct once rather than a per-point sign
to infer.

**Point-to-plane is precise near the solution and wrong far from it.**
With mismatched correspondences (a badly placed body), a finite-difference
check found the gradient pointing the wrong way on 5–7 of 10 betas.
Fixed by staging: two sign-free, normal-free chamfer-distance stages run
first to get the body onto the shell from anywhere, before the signed
gap-band objective — which only means anything once correspondences are
roughly right — takes over.

**Loss units matter as much as loss correctness.** The first version ran
data terms in m² with a beta prior weighted 0.02, and the prior won:
betas shrank toward zero, the torso came out ~60 mm thin, and the
residual looked fine throughout. Every term now runs in mm² with weights
readable as "cost per mm² of violation", and the docstring on `FitConfig`
records the failure mode so the next weight change doesn't reintroduce it.
This is the concrete case for why `fit_quality_score` is never called
confidence: the run with the lowest residual was the most wrong one.

**A flat gap band is a dead zone.** Once past the outside/band terms, a
body that reached the band's inner edge during the chamfer stage had no
further gradient and stopped there — visible as a corner-heavy, ~10 mm
undersized recovery. A weak pull toward the band's centre (`w_center`,
two orders of magnitude below the band term) gives the interior a slope.
This is exactly the job the gap atlas (C1b) is for: its per-part median
replaces this placeholder centre with a real prior once it exists.

**What the battery actually found, and did not paper over.** On six of
seven shells, `back_length` recovers 360–390 mm too long. The cause is
not the optimiser: the recovered body's waist search hits
`minimum_at_search_boundary` — the exact mechanism decision #22 built
guards for on clothed HSRD scans — because a body shaped under a coarse,
uncalibrated gap-band prior can have proportions whose true waist minimum
falls outside `WAIST_WINDOW`. **Every one of these deltas already carries
`recovered_bucket: low_confidence`**, propagated by decision #22's flag
inheritance, with zero C2-specific code. The identity shell (offset 0,
no prior to be wrong about) recovers back_length within 11 mm and stays
`clean`. This is the layered claim system working as designed — a defect
built for one failure mode caught an unrelated one — and it is left
exactly as it is: the fix belongs in C1b's real gap priors, not in a
narrower waist window bolted on to make one battery case look better.

**Recovery quality (identity shell, clean-measuring latent body):**
chest −16 mm, waist −18 mm, neck −5 mm, upper-arm −7 mm, shoulder width
0 mm, sleeve +19 mm, back length +10 mm; 0% collapse, 1.6% outside
violation. Multi-start beta spread on the two hardest cases: 0.6–0.8 (of
comparable size to true betas ~1–2.5) — real disagreement between starts
on where the body is, which is the diagnostic multi-start exists to
provide, not a defect to average away.

**A decimation case that was not decimating.** The voxel size chosen when
routing around the blocked native library (below) was 6 mm, against a
shell whose median edge is 18 mm: it merged almost nothing, 94 % of faces
survived, and the "coarse scanner" case silently tested nothing at all
for one battery run. Found only by exporting the meshes to look at them,
which is itself the lesson — a case that reports a number every run can
still be measuring nothing, and no assertion in the battery would have
caught it. Now 30 mm (13776 -> 5429 faces, 61 % removed), and the case
turns out to be one of the easier ones: chest -3 mm, upper-arm +2 mm,
back_length +115 mm against +360 mm for the other offset shells.

**A second, unrelated finding en route:** `trimesh.simplify_quadric_decimation`
imports the compiled `fast_simplification` extension, which Windows
Defender Application Control blocks on this machine — a system security
policy, not something to route around with elevated rights. The battery's
`decimated_shell` case was rewritten to quantise vertices to a voxel grid
and re-merge (numpy only, reuses the welding this project already relies
on for photogrammetry OBJs). `body_measure/validate/robustness.py`'s
`decimate()` has the same dependency and the same exposure — currently
invisible only because `test_robustness.py` is skipped without a
generated SMPL body — and is flagged as separate follow-up, out of scope
for this decision.

**Rules out:** measuring the fitted (scan-matching) pose instead of the
canonical pose; treating `fit_quality_score` as a per-case accept/reject
gate before it is calibrated against held-out error; narrowing
`WAIST_WINDOW` to fix one battery case's back-length delta.

**Revisit if:** C1b lands and `w_center`'s placeholder is replaced by the
real gap-atlas median; the robustness-battery decimation follow-up lands
and its result changes what `decimate()` should do here too; multi-start
spread is calibrated into an actual `fit_confidence`.

## 24. Scope: the garment is an upper garment, and the scan's lower half is not evidence

**Decided:** the subject may wear anything below the waist, so the lower
body is excluded from the fit and may not anchor an upper-body landmark.
Recorded in the spec as `priority` (spec v4) and in the fitter as
`part_weights`.

The scope statement is about the **input**, not just the output. None of
the seven measurements was ever a leg measurement, so "we don't need
lower-body numbers" changes nothing. What changes things is that the
lower half of a clothed scan is a skirt, or baggy trousers, or a coat
hanging to the knee — and two parts of the pipeline were quietly leaning
on it.

**`priority` on each measurement (spec v4).** `core` for the six the
shirt needs; `deferred` for `sleeve_length`, the only measurement whose
route reaches past the elbow (it ends at the wrist). Priority is scope,
not difficulty: sleeve_length works, it is simply outside a short-sleeve
product. Extending to long sleeve means flipping one line back — the
definition and implementation stay.

**The waist floor is anchored on the armpit.** The waist search ran from
0.45 H, which is thigh height, and was floored by the crotch — a landmark
a skirt does not have. The floor is now the strictest of three: the
stature bound, the crotch when one exists, and armpit − 0.28 H. Each
guards something different and none subsumes the others.

Only the floor moved. Lowering the *ceiling* to an armpit-relative height
was tried and rejected on evidence: NOMO male_0007's true minimum sits at
0.657 H, an armpit-relative ceiling cut it off, and the returned girth
was 28.6 mm larger — by the spec's own definition ("minimum torso
girth"), the wrong answer. On 15 real scans the floor change moves 13 by
0.00 mm and two by ≤0.21 mm; the one real move (NOMO male_0001, +12.3 mm)
is boundary-flagged both before and after, so nothing changes silently.
The validated Texel pathway moves 0.005 mm — the rounding of the recorded
baseline.

**Legs are excluded from the fit, not down-weighted.** SMPL's betas are
global: every millimetre of trouser the optimiser chases is spent from
the same budget the torso needs. Measured on the uniform-15 mm shell, leg
weight 1.0 gives back_length +360 mm and waist −32 mm; 0.25 gives
+362/−34, no help whatever; 0.0 gives +105/−11. A knob with no useful
middle is not a knob — it is a scope decision, and it is stored as one.

**Excluding a body part means excluding the shell that covers it.** The
first implementation dropped leg *vertices* and left the chamfer's
shell-to-body direction asking whether every piece of shell — trousers
included — had body near it. With no legs to answer, the torso was
dragged down onto them: a uniform shrink, worst exactly where it should
have been exact (identity shell chest −16 mm before, −37 mm after). The
shell-to-body direction is now masked to the fitted body's own height
range. The body-to-shell direction needs no mask, since each body vertex
finds its own nearest shell point regardless.

**And a metric that charged for the exclusion.** `coverage_fraction`
divided by the whole body, so removing 20 % of vertices scored as 20 %
missing coverage and tripped `low_shell_coverage` on a good fit. It is a
fraction of the *included* vertices.

**Result across the eight-shell battery** (all core measurements, worst
absolute error over cases): back_length 386 mm → 47 mm, and the identity
shell recovers it exactly. chest 82 → 56, waist 34 → 48, neck 24 → 25,
upper-arm 14 → 26, shoulder width 27 → 25. Coverage 1.00, collapse 0 %,
outside violation 2 %. The one measurement that got clearly worse is
`sleeve_length` (±104 mm) — the deferred one, whose endpoint is the
wrist, on the part of the arm this decision declares out of scope. That
it degraded exactly where scope was withdrawn is the expected shape of
the result, not a surprise.

**Rules out:** using the crotch as the only waist floor; down-weighting
rather than excluding the lower body; masking body vertices without
masking the shell they were answering for.

**Revisit if:** the product extends to long sleeve (flip `sleeve_length`
back to `core` and restore full-arm evaluation), or trousers enter scope
(legs return to `part_weights` and the crotch floor regains its value).

## 25. A chest profile may be measured one way, not two

**Decided:** the arm-merge height is decided once per profile and the
chest samples are all produced by the same method. Clipping is refused
outright when the armpit that defines its bounds is not trustworthy.

`measure_chest_circumference` chose per height between measuring the
torso loop directly (arms are their own loops) and clipping the merged
loop at the armpit's lateral extent (arms are not), then took the maximum
over the mixture. The two branches measure different things, so the
maximum was answering *which method returned the larger number*. This is
decision #22's defect in a second place: an extremum taken over samples
that are not comparable.

**What made it visible.** HSRD's chest read 1366 mm `clean` at lod1 and
1293 mm `arm_clipped` at lod2 — 72 mm apart on the same scan. The chest
*level* was identical (0.718 H in both) and a direct slice at that height
gives 1367.3 mm on lod2 against 1365.6 on lod1. The geometry agreed to
2 mm; only the branch disagreed.

**The branch test is sound on skin and not on cloth.** Writing out the
per-height sequence of "are the arms separate?", all ten Texel subjects
flip exactly once — separate below the merge, joined above, which is the
physical story the function was written for. HSRD flips **eight times at
both LODs**: a jacket sleeve touches and leaves the torso as the
triangulation happens to fall. So the fix is not to pick a better
threshold but to stop treating a noisy sequence as if each sample were an
independent decision.

The merge index is now the split that best matches "separate below,
merged above" — exactly the flip point when the sequence is already
monotone, so **all ten Texel subjects and every one of their seven
measurements move 0.0000 mm with no flag change**, and the least-wrong
single split when it is not. A sequence that flips more than once carries
`arm_merge_height_unstable`, which buckets as low confidence. HSRD is now
low confidence at both LODs, which is what it should always have been.

**Untrusted clip bounds are refused, not used.** The clip window comes
from the torso loop at the armpit. HSRD lod2's armpit is confidence 0.4
(`single_slice_arm_separation`) and produced a 289 mm window against
lod1's 420 mm — a 131 mm error inherited by every clipped sample. Below
confidence 0.5 the clip branch is disabled and the flag says so.

**Effect on HSRD:** chest LOD spread 72.5 mm → 40.5 mm, and both LODs now
report low confidence instead of one of them reading clean. The remaining
40 mm is real disagreement between a clipped and an unclipped reading of
a jacket, correctly labelled as unreliable rather than resolved by
accident.

**Also found and left alone:** the clip branch can return values no body
has — 33.4 mm at one HSRD height, `None` at another. They never won the
maximum, so they never surfaced. They are still possible, and the
report-level plausibility net (#20) remains the only thing that would
catch one.

**Rules out:** tuning the `n_closed >= 3` threshold; taking an extremum
over a profile whose samples come from different methods; using clip
bounds from a landmark too uncertain to place.

**Revisit if:** a garment class makes the merge genuinely non-monotone
(a cape, arms folded), in which case the single-split model is wrong
rather than merely noisy — the flag would be firing for a real reason and
the profile would need segmenting instead.

## 26. Sweep: every extremum in the core, checked for untrusted inputs

**Decided:** `torso_girth_profile` admits only `accepted` slices, not
merely non-`rejected` ones. The rest of the sweep found no further live
instance, and what it did find is recorded here so the next reader does
not repeat it.

Decisions #21, #22, #24 and #25 were all the same defect wearing
different clothes: a sample the pipeline had already judged unreliable
was allowed into an `argmin`/`argmax`/`max`, and the extremum silently
promoted it over trustworthy neighbours. This is the sweep of every
remaining extremum in the measurement core.

**Found and fixed — the gap-closure tier was only half-enforced.**
`torso_girth_profile` skipped `disposition == "rejected"` and let
`manual_review` through. A manual_review slice is one the gap-closure
tier already judged too bridged to stand on its own, and an extremum
makes exactly that judgement on its behalf.

Measured across NOMO's first 40 subjects: 16 have at least one open slice
in the waist profile, and in 6 an open slice wins the argmin. Five of
those six are harmless — `gap_ratio` 0.0, meaning the loop is open by
index but has no geometric gap, which is why the tier accepted them.
The sixth is not: NOMO male_0001's winner had **15.5 % of its loop
replaced by a closing chord** and disposition `manual_review`, giving a
**675 mm waist on a 1725 mm subject** at the search boundary.

Requiring `accepted` costs that subject one sample of 52 and moves its
waist to 961 mm at 0.674 H, where every other subject's sits. **Texel
moves 0 subjects, HSRD moves 0, no profile is emptied** — the filter
distinguishes bridged loops from technically-open ones exactly as the
tier intended.

**Checked and clear — the armpit-extent sites.** Four places take the
lateral `min`/`max` of the torso loop at the armpit: shoulder seeding,
the chest clip bounds, wrist arm-separation, and the upper-arm window.
None checks the loop's selection tier, so a nearest-centroid fallback
would silently define a body's width. Probed across Texel, NOMO and
HSRD: **every case returns `axis_containment` at confidence 0.9.** The
hazard is real but unrealised, and adding a guard now would be untested
code defending against something no data produces. Left alone
deliberately, and written down so it is a known gap rather than an
oversight.

This also corrects an attribution in #25. HSRD lod2's 289 mm clip window
against lod1's 420 mm was blamed there on loop quality; both loops are in
fact `axis_containment` at 0.9. The difference comes from the armpit
*level* differing by 11 mm between LODs and the jacket's torso genuinely
having different extents there. The confidence guard shipped in #25 is
still the right one — it keys on the armpit landmark's confidence, which
is what was actually low — but the reason given was wrong.

**Checked and clear — the rest.** `estimate_back_point_at` and
`torso_girth_profile` already gate on tier (#22).
`measure_chest_circumference` now decides one method per profile (#25).
`select_torso_loop`'s own `max(area)` and `min(distance)` operate within
a single tier by construction. `surface_path`'s `argmax(component sizes)`
compares like with like. The fitter's `min`/`argmin` calls are distance
lookups, not quality judgements.

**Rules out:** treating "not rejected" as "trustworthy" anywhere a tier
exists; adding tier guards to the armpit-extent sites without data that
exercises them.

**Revisit if:** any dataset produces a nearest-centroid selection at the
armpit level — the four sites above become live and need the same gate
`torso_girth_profile` has.

## 27. A size is assigned from a cited chart, or not at all

**Decided:** `body_measure/sizing.py` maps a measured body to a
ready-to-wear size (`--size-chart en13402|lacoste`). Charts carry their
source and the date it was checked; a chart without one does not go in.

**Why the source matters more than the numbers.** An invented band looks
exactly like a standard one once it is in a table, and the difference
only surfaces when someone is asked where the number came from — by which
time garments have been cut. So a chart is a record with provenance, not
a constant.

The bands are **EN 13402-3**'s men's letter codes: S 86-94, M 94-102,
L 102-110, XL 110-118, XXL 118-129 cm chest girth. That is the European
standard for the market this line produces for, and each letter spans two
adjacent 4 cm size steps. A Lacoste chart is kept beside it as a
cross-check rather than an authority; the useful fact is that its
published S-XXL body span (86-117 cm) agrees with the standard to within
a centimetre, so a brand and the standard do not disagree enough to
change a size. Where Lacoste publishes only the span and not the per-size
cut points, the note says so rather than inventing them.

**Four refusals, each for a different reason.**

- **Clothed.** A dressed subject's chest girth is the garment's, so a size
  from it is the garment's size. `--clothed` records the
  `measured_clothed` pathway and the assignment refuses. A mesh file does
  not announce that its subject was dressed, so the caller says.
- **Outside the chart.** HSRD's jacket reads 132.6 cm, past XXL.
  Extending a chart beyond its published bands is inventing sizes.
- **A measurement the pipeline itself will not accept.** `rejected` or
  `manual_review` chest, no size. Anything short of `clean` still assigns
  but carries the bucket as a flag.
- **The wrong population.** EN 13402 designates the same letter by *bust*
  girth for women and *chest* girth for men, so a men's band on a female
  body reads the wrong dimension — not a size out, a category error. A
  mesh does not say who it is, so an unstated population is flagged rather
  than assumed, and a stated mismatch refuses.

**Band edges are reported, not resolved.** A chest within 10 mm of an edge
names the neighbouring size too. This pipeline's girth error is tens of
millimetres on a clothed scan and single millimetres at best, so a 4 mm
difference deciding S against M is a decision the measurement cannot
support. Naming both is the honest output.

**Rules out:** extrapolating a chart past its bands; assigning from a
clothed girth; a chart whose provenance is not in the file; silently
picking a side at a band edge.

**Revisit if:** a women's chart is added (it needs bust girth, which is
not the same measurement as chest and is not in the spec), or the line
moves to true made-to-measure, where a size label stops being the output
and the girths themselves are the pattern input.

## 28. Whether the line can run on size labels is a coverage question

**Decided:** `scripts/size_report.py` reports what a single assignment
cannot — coverage, refusal reasons, boundary rate, and how much a size
label leaves undetermined. Over 40 unclothed subjects (10 Texel, 30 NOMO)
with EN 13402-3:

| | |
|---|---|
| coverage | **31 / 40 (78 %)** |
| on a band boundary | **8 of 31 (26 %)** |
| refused | 5 women against a men's chart, 2 `manual_review` chest, 1 no value, 1 chest 134.4 cm past XXL |

**The boundary rate is the number that matters.** A quarter of the
subjects that do get a size sit within 10 mm of a band edge, which is
inside this pipeline's own girth error. For those the label is a coin
toss, and a coin toss on a garment is a return. That is a property of
8 cm-wide bands meeting millimetre-scale bodies, not a defect to fix.

**What a size label does not say.** Among subjects sharing one label, the
other measurements still span: waist 168 mm within L and 184 mm within
XL, neck up to 115 mm, upper arm up to 83 mm. A chest band fixes one
girth and leaves the rest free, so a polo cut to the label fits the middle
of each range and compromises at both ends. That is the made-to-measure
argument stated in this project's own numbers rather than asserted.

**A defect found in this report, of the kind it exists to catch.** The
spreads were first computed over every value regardless of its bucket,
and they were dominated by our own failures rather than by human
variation — XL back length read 441 mm before filtering and 33 mm after,
size-M waist 137 mm before and 23 mm after. Ranges are now taken over
accepted buckets only, with excluded subjects marked. This is decisions
#22 and #26 a third time: an untrusted sample reaching a statistic.
`arm_clipped` is kept because it is a documented systematic
approximation; `manual_review` and `rejected` are not.

**Rules out:** quoting a within-size spread without saying which buckets
it was taken over; treating the boundary rate as a bug rather than a
property of banded sizing.

**Revisit if:** the scanner arrives and the girth error is measured
against a tape — the 10 mm boundary margin is currently an estimate of our
error, and a measured one would move the boundary rate up or down.

## 29. The women's chart needed no new measurement — the audit already said so

**Decided:** `EN_13402_3_WOMEN` sizes female bodies from the same
`chest_circumference` the men's chart uses, against the standard's
women's bands. Coverage over the 40-subject set goes 78 % → 90 %.

**The measurement question answered itself from the audit.** The plan was
to add a `bust_girth` measurement first, since EN 13402 designates women's
tops by bust girth and men's by chest girth. But
`docs/measurement-audit.md` already maps `chest_circumference` to ISO
8559-1 **m5 "Bust/Chest Girth"** — ISO carries one item for both — and the
code's own docstring was already written as "the true chest/bust level".
Adding a second measurement would have created two names for one geometric
operation, which is the name-based thinking this project's founding rule
forbids. What differs between the populations is the *bands*, not the
dimension.

The audit's `approximate` rating comes along: ISO fixes the height at the
bust point while this pipeline searches for the maximum girth. That matters
more on a female body, where the bust point is a named anatomical location
rather than wherever the torso happens to be widest, so every assignment
now carries `chest_definition_approximate_iso_m5` rather than leaving the
caveat in a document nobody reads at assignment time.

**Two irregularities in the published women's table are recorded, not
smoothed.** L ends at 106 cm and XL begins at 107, leaving a centimetre no
letter covers; XL and XXL span 12 cm where the smaller letters span 8, so
the two-adjacent-steps rule the men's table follows does not hold across
this one. A bust in the gap is refused with `between_bands`. Closing the
gap would make the table tidier and no longer the published table.

**The gap exposed a latent bug.** The band search made the last band's top
edge inclusive so a chart's stated maximum gets a size, but the exception
did not also require that band's *minimum* — so any value matching no band
fell through to the last one. With contiguous men's bands nothing ever
fell through and the bug was invisible; the women's 1 cm gap put 106.5 cm
in XXL. A chart with a hole in it turned out to be a test the code had
never been given.

**Reports size per population.** The men's M and the women's M are
different bands read off the same ISO item, so `size_report.py` counts them
in separate distributions and the within-size spread table names the one
chart it covers. Summing them into one column would invent a size that
neither chart defines.

**Rules out:** a separate `bust_girth` measurement while ISO keeps one item;
editing a published table to make it regular; one size distribution across
two populations.

**Revisit if:** the ISO 8559-1 text is obtained and m5's height rule is
checked — the `approximate` rating and the flag it produces both rest on
the audit's reading, and `definition_verified` is still false.

## 30. The pattern gate reports what is missing, and refuses to say "ready"

**Decided:** `body_measure/pattern_readiness.py` checks a measured body
against what a polo draft consumes (`--pattern polo`). Its best possible
verdict is `complete_unverified`. **`ready` is not among the verdicts**,
and a test pins that the module offers no such string.

The reason is the same one that makes `measurement_accuracy` unreachable
in `claims.py`: no value here has been compared against a trained
measurer's tape. A gate that could return "ready" would be claiming
exactly the thing this project has spent every slice refusing to claim.

**Why the gate comes before the drafting code.** A size band is 80 mm
wide, so a chest can be tens of millimetres out and still land on the
right letter. A pattern draws a line at the number. The accuracy a draft
needs is roughly four times tighter than the accuracy a size label needs,
and we have not established the looser one. Writing a drafting routine
first would produce precise lines through numbers of unknown accuracy.

**What it found on a clean unclothed scan (Texel Man0): 4 of 15.**

| | count | why |
|---|---|---|
| draftable | 4 | chest, waist, neck, upper arm |
| blocked on quality | 3 | across-back, back length, sleeve — `manual_review` |
| present but unvalidated | 5 | the garment prototypes |
| not implemented | 3 | centre-front length, armhole girth, across front |

A prototype having a number does not make it draftable. It has no
definition audit and no reference, and presence is not permission to cut
cloth — so the gate reports the value and withholds the licence.

**The requirement list is itself a claim.** Twelve entries come from
polo-line-sim's measurement list, which already records that the Maß-DPP
plan lists no body measurements and that its own list is derived from
pattern practice and ISO 8559-1. Three more were identified while reading
that list against what a draft needs and are marked `unsourced`, because
they have not been checked against a named drafting system (M. Müller &
Sohn, Aldrich's menswear block). A gate that hid the provenance of its own
requirements would be the failure it exists to catch.

**Rules out:** writing pattern-drafting code before the measurements it
would consume are complete and validated; treating a prototype's presence
as fitness to draft from; a requirement list without provenance.

**Revisit if:** the three unimplemented dimensions are added (the gate
then measures quality rather than absence), or the scanner and ISO
20685-1 validation arrive — at which point a `ready` verdict becomes
definable for the first time, gated on a measured tolerance rather than
on a bucket.

---

## 31. Front and back were swapped, and confidence was measuring the wrong thing

**Date:** 2026-08-31 · **Status:** accepted · **Supersedes part of #1's
`toe_projection` method note**

Three measurements — `across_back_shoulder_width`, `back_length`,
`sleeve_length` — were landing in `manual_review` on clean Texel data.
They moved together on all ten subjects, which pointed at one shared
cause rather than three. The cause was `estimate_facing`, and it was
worse than a gating problem: **the estimate was 180 degrees out.**

The method took one horizontal cut at 3 % of stature and used the
centroid of the foot slice, on the reasoning that the toes extend forward
of the body axis. Toes are about 25 mm tall. At 3 % of stature — roughly
50 mm — they are already gone, and the cut holds heel and Achilles, which
sit *behind* the axis. On the generated SMPL body, whose frame defines the
front as +Z, the offset is +Z at 0.5–2 % of stature and reverses to −Z
from 3 % up:

```
 0.5%  (  -1.5, +91.4) mm   +Z  front
 2.0%  (  +2.9, +12.1) mm   +Z  front
 3.0%  (  +1.2,  -7.7) mm   -Z  back    <- the height the method sampled
 8.0%  (  -1.0, -34.9) mm   -Z  back
```

The magnitude grows the further past the crossover you cut, so the
method was *more* confident the *more* certainly it was backwards. That
is why the five Texel subjects it marked `clean` (offset 40–59 mm) were
the most firmly inverted, while the five it flagged merely sat near the
crossover. The confidence number ranked subjects by how wrong they were.

So `back_length` was measuring the front torso, `across_back_shoulder_width`
the front, and `sleeve_length` starting from the front neck point — on
every scan this project has measured.

**Decision.** Orientation comes from the asymmetry of each foot about the
leg above it (`toe_extent_about_leg`). The foot's long axis is heel-to-toe
and the leg meets it far nearer the heel, so about that point the toe end
reaches further — by a factor of 3–6 on the scans here. That is anatomy,
and unlike a horizontal cut it does not depend on choosing a height.
Confidence comes from **corroboration**: the two feet agreeing with each
other, and each outline being lopsided enough to name an end. A single
sample's magnitude is no longer allowed to stand in for certainty.

**Evidence.**

| check | old | new |
|---|---|---|
| SMPL frame (front = +Z, ground truth) | (+0.16, −0.99) wrong | (−0.00, +1.00) correct |
| Texel: agreement among the 10 subjects | scattered | within 9.7° |
| Texel `back_length` MAE vs dataset reference | 39.2 mm (n=9) | **21.9 mm (n=10)** |
| Texel `sleeve_length` MAE | 198.9 mm | 172.8 mm |
| Texel `across_back_shoulder_width` MAE | 34.5 mm | 44.8 mm |
| the three measurements' buckets, Texel | clean 5 / review 4 / rejected 1 | **clean 10** |
| the three, NOMO (n=30) | review 12–13 each | review 0 |

Three further cues on the Texel women, projected on the new front
direction, all agree with it: the bust reaches forward (1.01–1.35×), the
buttocks reach backward (hip forward/backward 0.66–0.96), and the
forefoot reaches forward (1.05–1.60×).

**`across_back_shoulder_width` got worse, and that is left standing.**
Its error went from scattered (−5 to +86 mm) to systematically short
(−16 to −61 mm on 9 of 10). A consistent sign is a definition or
landmark offset that can be found; a scattered one is noise. The likely
reading is that the shoulder points sit too medially once the path
actually runs across the back — which is a separate defect that the old
inversion was masking, not a reason to keep measuring the wrong side.

**Rules out:** deriving front/back confidence from the magnitude of one
sample; sampling anatomy at a height without checking that the feature
being relied on is still present there.

**Revisit if:** a scan arrives with the feet cropped or the subject
seated, where no foot cue exists — orientation then has to come from the
source (`provided_facing`) or the measurements refuse, as they already do.

**Note on the record.** Every length measurement this project has
reported before this commit was taken with the inverted orientation. The
KW35 deck, `reports/dataset_agreement_texel.md`, and the clothing-offset
figures all predate the fix and are superseded.

---

## 32. A shoulder search with room to slide will slide

**Date:** 2026-08-31 · **Status:** accepted · **Follows #31**

Correcting the front/back inversion left `across_back_shoulder_width`
systematically short: −16 to −61 mm on 9 of 10 Texel subjects, MAE
44.8 mm. A consistent sign is a landmark offset, and it was.

`estimate_shoulder_points` took the highest surface point in a ±25 mm
lateral column above the armpit crease. Profiling the shoulder ridge
shows why that cannot work. Walking outward from the midline, the top
surface is the **head** until it falls off a cliff — 197 mm on Man1 —
and from there the ridge declines *monotonically* out to the arm. There
is no acromion break to find. So an argmax over height inside a lateral
window returns the window's medial edge, always. It did: on 19 of 20
Texel shoulders the chosen point sat within 4 mm of the medial edge,
costing 25 mm a side and 50 mm on the width — which is the deficit that
was measured.

**Decision.** The lateral station is taken from the armpit crease and
not searched: the shoulder point is the top of the surface in a ±6 mm
slab at the crease's own lateral coordinate. Four constructions were
scored against Texel's reference before choosing:

| construction | MAE | note |
|---|---|---|
| ±25 mm column argmax (old) | 44.8 mm | short on 9 of 10 |
| **slab at the crease** | **20.5 mm** | errors −24…+21, balanced |
| slab 10 mm outboard | 30.0 mm | overshoots |
| walk out to a 25 mm ridge drop | 117.4 mm | walks onto the arm |

Over the nine subjects the pipeline accepts, MAE is 13.6 mm.

The tenth, Woman4, now reports itself. Her left shoulder lands 0.6 mm
below the vertical search ceiling — the window's lid, not her body —
while the right sits 102 mm below it. That 102 mm step clears the
existing `shoulder_vertical_asymmetry` threshold, so she becomes
`manual_review` instead of silently contributing +84 mm. A new
`shoulder_at_search_ceiling` flag catches the case asymmetry cannot: both
shoulders pinned to the lid at once.

**A stale spec flag was found and corrected.** `measurement-spec.v1.yaml`
carried `no_reference: true` for this measurement — "레퍼런스의 shoulder
breadth는 직선거리, 비교 금지" — written 2026-08-17 in the first commit.
`docs/measurement-audit.md`, written the next day, maps it to Texel m1
"Across Back Shoulder Width (**through the back neck point**)" and rules
it **exact**, which is why it is a headline measurement in
`validate/stats.py`. The audit is the definition-based verdict and wins;
the YAML flag had simply outlived it. Nothing reads the field in logic
today, which is how it survived. `sleeve_length` carries the same flag
and has NOT been changed — the audit rates it `approximate`
(reference-only), which is a weaker claim, and it deserves its own look.

**Rules out:** giving an extremum a search window along an axis the
surface varies monotonically in; treating a definition note in the spec
as authoritative over the audit.

**Revisit if:** a real acromion becomes available — a palpated landmark
from a trained measurer, or a scanner that marks it — at which point
"above the armpit crease" stops being the approximation and becomes
something to check against.

---

## 33. The plan lives in the repository

**Date:** 2026-08-31 · **Status:** accepted

`docs/licenses/scope.md` recorded SIZER as "registration approved,
download imminent" on 2026-08-21. On 2026-08-31 that line was still there
and still wrong: SIZER had never been requested. Ten days of status
reports carried it as a pending arrival, and a work plan branch — C0b,
C1, C1.5, C1b — sat marked "waiting for data" that nothing was going to
deliver.

The cause is structural rather than careless. The plan existed only
outside version control, so it was never reviewed alongside the code it
governed and no commit ever had to justify it.
Dataset *status* was written into the licence documents, which are about
permissions and are not read when deciding what to work on next.

**Decision.** The work plan is `docs/plan.md`, committed. A dataset's
status line names what has actually happened and when it was last
checked, not what is expected. "Imminent" is not a status.

Two corrections follow immediately:

- SIZER is **not blocked** — the access route is a Google Form plus a
  password request to `gtiwari@mpi-inf.mpg.de`. Its page describes 100
  subjects, ~2,000 scans, 10 garment classes across sizes, and raw scans
  alongside minimally-clothed body scans. If the pairing holds, decision
  #17's claim downgrade is not needed. `docs/sizer-access-request-draft.md`
  asks for the terms, the pairing and the industry-context position in one
  mail, because the repository page carries no licence text at all.
- CAPE is licence-cleared and simply undownloaded. It is the C3 synthetic
  factory's material, **not** a substitute for SIZER in C1: its clothed
  surfaces are SMPL-topology registrations, its body reference is a
  canonical T-pose registration, and it has 15 subjects to SIZER's 100.
  Building C1 on it would force the downgrade that SIZER may avoid.

**Rules out:** a plan that only exists in tooling state; a dataset status
written as an expectation; treating CAPE and SIZER as interchangeable
because both are clothed-body datasets from Max Planck institutes.

**Revisit if:** SIZER's terms turn out to forbid the industry context the
project runs in — CAPE then becomes the fallback, with the downgraded
claim wording stated up front rather than discovered later.

---

## 34. CAPE is measured from its betas, not from the body it ships

**Date:** 2026-09-01 · **Status:** accepted

CAPE's `minimal_body_shape` is a **canonical T pose**. This pipeline's
measurement core assumes hanging arms — `body_lateral_axis` says so
outright, "arms hang beside the torso by construction" — so a T pose is
outside what it was built for. Measuring `00215_minimal.ply` directly:

| measurement | T pose, as shipped | A pose, rebuilt from betas |
|---|---|---|
| chest_circumference | **3808 mm** `accepted` | 1080 mm `arm_clipped` |
| across_back_shoulder_width | 652 mm | 439 mm `clean` |
| back_length | 470 mm | 456 mm `clean` |
| neck_circumference | 446 mm | 417 mm `clean` |
| sleeve_length | null, rejected | 974 mm `clean` |
| waist_circumference | 887 mm | 882 mm `clean` |

3808 mm is a horizontal loop around the torso *and both outstretched
arms*, and the core returned it as `accepted`. Only `low_confidence`
flags were raised — nothing said "this is not a body girth". That is
decision #20 (no human-range gate in the core) with a second concrete
instance, and it is worse than the first: 140.9 mm was implausibly small,
where 3808 mm is implausibly large and the core has no opinion either way.

Note that `waist_circumference` barely moves (887 → 882). The
measurements that do not involve the arms are unaffected by the pose,
which is what makes the failure selective rather than obvious.

**Decision.** CAPE bodies are rebuilt in this project's own A-pose
canonical from the betas CAPE publishes (`<subj>_param.pkl`, added
2023-07), using `inference/smpl_body.py`. The shipped T-pose mesh is
inventory, not a measurement input. The gender comes from
`misc/subj_genders.pkl`, not from a guess.

**Clothing displacement is usable, and was checked rather than assumed.**
`v_cano` in each frame and `minimal_body_shape` are both SMPL topology
with 6890 vertices, so they correspond per vertex. For 00215 poloshort
the outward offset reads as a polo should:

| height band | median outward offset |
|---|---|
| 0.55–0.70 (torso) | **+15.4 mm** (p90 34.8) |
| 0.40–0.55 (hem, shorts waist) | +12.7 mm |
| 0.20–0.40 (shorts) | +10.5 mm |
| 0.70–0.85 (**arms**, n=3508) | **+0.9 mm** — bare, i.e. short sleeves |
| 0.85–1.00 (head) | +0.3 mm |
| 0.00–0.20 (lower legs) | −1.8 mm |

**"All sequences start with an A pose" is loose, and posed frames are not
measured.** At the first frame of the twelve 00215 poloshort sequences the
body joints carry mean |ω| 0.144–0.223 rad with a maximum of 0.72–1.33 rad
— above this project's A-pose abduction of 0.87 rad, and varying by
sequence. The route is displacement transfer onto the project's own
canonical, which is C3's design; the result is a synthetic shell and is
never reported as a clothed observation.

**One inventory file disagrees with the rest.** `subj_genders.pkl` lists
**17** subjects, while `minimal_body_shape`, `minimal_body_params` and
`seq_lists` each hold the same **15**. The two extras, `03212` and
`03213`, have a gender and nothing else — no body, no betas, no
sequences. The 15 that do ship are 10 male and 5 female, which is what
the download page states, so the page is right and the gender table is
the odd one out. Reading the subject list off `subj_genders.pkl` — the
obvious file for it — would have produced two phantom subjects. This is
what decision #17's audit exists to catch, and it came out of
cross-checking rather than trusting any single file.

**Sleeve length is a lateral question, and reading it as a height band
was wrong.** The polo signature above put the arm band at +0.9 mm and that
was read as "bare, therefore short sleeves". In a T pose the whole arm
sits at roughly shoulder height, so a height band mixes shoulder with
wrist and cannot see a cuff: 00096's *long*-sleeved outfits give the same
1.5–2.9 mm. Walking outward along the arm instead does separate them, at
the station where the offset turns negative (fraction of half-span):

| outfit | sleeve ends | |
|---|---|---|
| `poloshort`, `shortlong` (00215) | ~0.39 | short |
| `shortshort` (00096) | ~0.47 | short |
| `jerseyshort` (00096) | positive to 0.71 | **long** |
| `shirtlong` (00096) | positive to 0.79 | long |
| `longshort` (00215, 00096) | positive to 0.71–0.79 | long |

So the first token of an outfit name is the garment, not the sleeve:
`short`/`long` say sleeve length but `polo`, `jersey` and `shirt` do not.
`jersey*` must not be filed as short-sleeved. The conclusion for
`poloshort` happened to be right; the reasoning was not, and the same
reasoning applied to `jerseyshort` would have mislabelled it.

**The hair variation is not in this distribution.** The download page
notes that 00096 and 03284 vary in hair length, and that was taken as
material for reproducing decision #32's failure, where hair pinned
Woman4's shoulder point to the search ceiling. It is not: what ships is
SMPL-topology registration, SMPL carries no hair geometry, and the head
band's displacement is −0.5 to +0.3 mm across all six of 00096's outfits.
Reproducing that failure needs the raw scans, requested separately.

**One file in 00096 is not data.** `shirtshort_chicken_wings.000108.npz`
appears as `...npz5JRYHz-numpy.npy` — a temporary file that was packaged
by accident. The audit classifies it `unclassified` rather than guessing.

**Rules out:** measuring a CAPE mesh in the pose it ships in; taking a
subject list from any single file in the distribution; presenting a
displacement-transferred shell as an observed clothed scan; reading a
garment boundary off an axis the garment does not vary along.

**Revisit if:** the core gains a human-range gate (decision #20), which
would turn the 3808 mm into a refusal instead of a number nobody checked.

---

## 35. A short sleeve's length is chosen, not measured

**Date:** 2026-09-01 · **Status:** accepted

`sleeve_length` was reported as the pipeline's worst dimension — usable on
9 of 40 subjects, with a +173 mm bias on the ones that produce a value —
and picked as the next thing to fix. It was the wrong target, on three
counts, and the investigation is worth keeping because each count was
already written down somewhere nobody read.

**1. The 30 NOMO refusals are correct.** NOMO ships **segmented** meshes:
across all 30 subjects the mesh has 5–13 connected components with the
largest holding only 0.491–0.570 of the vertices (median 0.538). A typical
subject is torso+head 54 %, each leg 15 %, each arm ~8 %, plus fragments
under the feet. Welding (decision #21) merges a median of **zero**
vertices, because unlike HSRD's texture-chart duplicates these are
genuinely separate surfaces. The wrist therefore sits 172–191 mm from the
main component, and a path from the neck to it cannot exist. Texel, by
contrast, is one component at 1.000 on all ten. So the honest figure is
not 9/40: it is **9 of 10 on the dataset that can carry the measurement,
and structurally impossible on the other 30.**

**2. The +173 mm was already known and already forbidden to compare.**
The spec records `elbow_waypoint_omitted_in_v1_systematic_overshoot_observed`
with "+197 mm 평균" against Part 1, and carries `no_reference: true` for
this measurement because the reference's arm length is a different
definition. Re-deriving a documented deviation is not progress.

**3. A polo does not consume this measurement.** The spec defines
`sleeve_length` as back neck point to **wrist** and marks it
`priority: deferred` — scope, not difficulty, recorded when the product
was scoped to short sleeves on 2026-08-25. Meanwhile
`garment_prototypes.py` already says the right thing: "A short sleeve ends
part-way down the upper arm. Where exactly is a garment design choice, so
this is a parameter, not a definition."

**The actual defect was in the gate.** `POLO_REQUIREMENTS` listed
`sleeve_length` as drafting "short sleeve length", so the readiness gate
demanded a measurement to the wrist in order to draft a sleeve that stops
above the elbow — and reported `NOT_READY` partly for that reason. It is
the same shape of error as the stale `no_reference` flag in decision #32:
two files disagreeing, with the wrong one driving behaviour.

**Decision.** `sleeve_length` is removed from `POLO_REQUIREMENTS`. The arm
is drafted from `upper_arm_girth` (spec, clean on all 40) and
`sleeve_opening_girth` (prototype); the length itself is
`SLEEVE_END_FRACTION`, a parameter the gate names as a choice rather than
pretending to measure. The measurement, its implementation and its tests
all stay — extending to long sleeves needs only the spec's `priority`
flipped back to `core`.

**The invariant is now enforced rather than remembered.**
`test_the_gate_never_requires_a_measurement_the_spec_defers` asserts that
every spec-provisioned requirement in the gate is `priority: core`. The
gate can no longer demand something the product was scoped out of.

**Rules out:** choosing work from a coverage number without checking what
the measurement is for; a garment requirement list that disagrees with the
spec's scope; treating a refusal forced by a dataset's topology as a
pipeline defect.

**Revisit if:** the product extends to long sleeves — flip `priority` to
`core`, restore the requirement, and the elbow waypoint (the known cause
of the overshoot) becomes worth implementing.

---

## 36. The chest is measured correctly, and it is the wrong dimension

**Date:** 2026-09-01 · **Status:** accepted

`chest_circumference` looked like the pipeline's weakest measurement:
`clean` on 0 of 40 subjects, and a +26.8 mm mean bias against Texel's
reference. Both readings were misleading, and what is underneath is worse
than either.

**`clean` on 0 of 40 is by design.** With arms hanging naturally the bust
sits *above* the height where the arm loops merge into the torso loop, so
the girth there is taken with the arms clipped at the torso's lateral
extent — a documented tape approximation that is always flagged and is in
`DRAFTABLE_BUCKETS` for exactly that reason. All ten Texel subjects are
`arm_clipped`; the degraded NOMO buckets are the segmentation of decision
#35, not a chest problem.

**The +26.8 mm is not error.** Two candidate causes were tested and both
ruled out:

- *Extremum-over-samples inflation* (the family in #22, #26, #31, #32).
  The peak is never at the search boundary on any subject, and only 2–4
  of ~28 samples sit within 5 mm of it, spanning 10–30 mm of height. The
  profile is peaked, not flat, so the max is not floating on noise.
- *The clip window keeping arm.* The window is the torso's lateral extent
  at the armpit, applied 34–105 mm higher up. Measured against the true
  torso width just below the merge it is off by −3 to +5 mm, and its error
  does not correlate with the bias at all — Man4 is +78 mm biased with a
  +1 mm window error.

What remains is the height, and it is consistent. Across the ten
subjects the search peaks at **0.732 ± 0.017** of stature while the
reference matches this pipeline's own profile at **0.708 ± 0.014** — about
42 mm lower, and a plausible bust-point height. The audit already rated
the m5 mapping `approximate` for precisely this reason: ISO fixes the
height, this pipeline searches for the maximum, and a maximum cannot be
smaller than a fixed-height girth.

**The defect is downstream, in sizing.** EN 13402-3's bands are defined
on chest girth as ISO measures it, and this pipeline feeds them a maximum
girth taken 42 mm higher. A band is 80 mm wide, so a third of it is spent
before the body is considered. Assigning sizes from both values over the
ten Texel subjects:

| | |
|---|---|
| label changes | **3 of 10** (Man4 M→S, Woman0 M→S, Woman3 XL→gap) |
| boundary flag differs | 2 more |
| unaffected | 5 |

Half the subjects are affected by a definition mismatch that was recorded
as a one-word caveat.

**Decision.** The size assignment now carries the gap **signed and
measured** —
`chest_reads_high_vs_iso_definition_mean_27mm_texel_n10` — alongside the
existing `chest_definition_approximate_iso_m5`. "Approximate" does not
tell a reader whether the label is likely one size high or one size low;
this does, and it travels into the DPP passport with the label.

**No correction factor is applied.** Subtracting 27 mm would fit the
pipeline to ten subjects of one dataset and would make the number agree
without making it right. The measurement stays what it is; what changes
is that its consumer is told which way it leans.

**Rules out:** reading a quality bucket as an accuracy claim; calibrating
a definition mismatch away with an offset; describing a known, signed,
measured deviation as "approximate".

**Revisit if:** a chest level is defined anatomically rather than by
search — a bust-point landmark, which differs between populations and is
the real fix. At that point this flag is replaced by a definition, and
`definition_verified` in the spec can finally become true.

---

## 37. The bust point is found, and it reports rather than corrects

**Date:** 2026-09-01 · **Status:** accepted · **Follows #36**

Decision #36 established that `chest_circumference` reads ~27 mm high not
through error but through definition: ISO fixes bust/chest girth at a
height and this pipeline searches for the maximum, which cannot be
smaller. The fix named there was a bust-point landmark. This is it, and
what it does is narrower than "fix the chest".

**Four constructions were scored before choosing**, against the height at
which the reference matches this pipeline's own girth profile
(0.708 ± 0.014 of stature, n=10 Texel):

| construction | lands at | girth bias | MAE | wrong labels |
|---|---|---|---|---|
| maximum girth (current) | 0.732 ± 0.017 | +26.8 mm | 28.1 | 3/10 |
| **maximum torso depth** | **0.710 ± 0.023** | **+4.4 mm** | 28.9 | 2/10 |
| forward protrusion | 0.698 ± 0.035 | −12.9 mm | 42.0 | — |
| depth × girth | — | +23.0 mm | 25.2 | 2/10 |

Depth is what a bust point is — the sagittal thickness peaks where the
bust does — and it lands on the target in the mean, removing six-sevenths
of the bias.

**It does not replace the chest definition.** Its spread is wider
(sd 22.4 → 36.8 mm), so it trades a systematic error for a random one,
and the label test that would decide between them is 2 wrong against 3 on
ten subjects — one of which, Woman3, is wrong for all three because her
reference falls in the women's chart's own 106–107 cm gap. Two errors
against three on nine subjects of one dataset proves nothing. Switching
the definition of the pipeline's most important measurement on that
evidence would be fitting to Texel's extraction algorithm, not moving
toward ISO.

**What it does instead is let each scan state its own gap.** The chest now
carries `chest_max_exceeds_bust_level_girth_by_<n>mm`, computed from that
body rather than from a constant averaged over ten of somebody else's.
Over Texel the per-scan gaps run 0–33 mm — note that these are *smaller*
than the +26.8 mm disagreement with the reference, so our own two
definitions do not account for the whole of it. The flag says what this
pipeline's maximum exceeds this pipeline's bust level by; it does not
claim to measure the distance to ISO.

**Corroboration, not a single reading.** On Texel Man0 the depth peak
sits 150 mm below the girth peak while the other nine sit within 60 mm.
One of the two found something that is not the chest and there is no
telling which, so beyond `MAX_BUST_CHEST_SEPARATION_FRACTION` (0.05 of
stature) the landmark is flagged `bust_level_disagrees_with_chest_level`,
its confidence drops to 0.3, and **no gap is claimed at all**. Man0 was
reporting a 118 mm "definition gap" before that guard; it was a landmark
failure wearing a definition's clothes.

The landmark also refuses outright when the orientation is unresolved:
depth is measured along the facing, and along a wrong axis "depth" is a
mixture of depth and width.

**Rules out:** replacing a definition because a candidate wins on bias
while losing on spread; reporting a gap between two landmarks that
disagree about where the chest is; measuring depth without a resolved
front.

**Revisit if:** a dataset with a stated bust-point height arrives, or
SIZER's reference makes n large enough for the label test to mean
something. The choice then rests on evidence rather than on n=10.

---

## 38. The passport records the garment, not the body

**Date:** 2026-09-02 · **Status:** accepted

`polo-line-sim`'s passport carried the customer's chest girth:
`passport.py` wrote `"chest_mm": self.chest_mm` into the `customer_spec`
block of every Digital Product Passport it produced.

`docs/licenses/ethics.md` had already ruled that out, and not as a
footnote:

> Body measurements are **excluded from the Digital Product Passport by
> design.** The passport carries garment data; it does not carry the
> customer's body. This was decided during DPP data-model work and is the
> main privacy boundary of the system — it means the passport cannot leak
> body dimensions regardless of who reads it.

Two documents in the same project disagreed, and the one that shipped a
number won by default. This is the third instance of that shape in a
fortnight — decision #32 found the spec's `no_reference` flag contradicting
the audit, decision #35 found the polo gate demanding a measurement the
spec had deferred — and in all three the stale or narrower statement was
the one driving behaviour.

**Decision.** `chest_mm` is removed from the passport block. Everything
that describes the *label* stays: `size`, the chart and its source and
check date, `size_alternative`, `size_note`, `measurement_flags`. The
value is still read from the measurement document and kept on
`CustomerSize`, because the boundary case is decided from it — but it is
decided in `to_dpp()`, and only the decision travels.

**This costs nothing the passport was for.** After a return the question
is whether the label was right, which needs the label, the chart it came
from, and whether the body sat near a band edge. All three remain. A
millimetre figure would answer a different question — what the customer's
body is — which is the question the passport exists not to answer.

**Rules out:** putting a body dimension in the passport because a
downstream reader might find it convenient; letting a privacy boundary
recorded in prose be overridden by a field that ships.

**Revisit if:** ITA's DPP data model changes its position, in which case
`ethics.md` changes first and this follows.
