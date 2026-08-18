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
