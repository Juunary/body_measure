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
