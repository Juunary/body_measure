# body-measure Development Report — The Full Journey Through Slices 0–5

Date: 2026-08-17 · Context: Maß-DPP / 3D body scanner pre-arrival software
Repository: `ITA/body-measure` · Final state: **46 tests passing, six measurements with a three-way validation system**

---

## 0. Why this project

The 3D body scanner (VITRONIC BodyLoop is the leading candidate) is still in
procurement, weeks to months away. The goal was to build the measurement
pipeline — "scanner mesh in, six shirt measurements out" — ahead of the
hardware, using public datasets as stand-ins for scanner output, with
validation completed before the device arrives.

**The most important decision was made at the planning stage — the boundary
of what validation may claim:**

> Before the scanner arrives, we validate the pipeline's **implementation
> correctness, reproducibility, and robustness**. Real measurement accuracy
> and repeatability are validated only after the hardware arrives.

ISO 20685-1 is an evaluation protocol that presupposes real subjects, manual
reference measurements by a trained measurer, and statistical analysis — so
no comparison against synthetic meshes or datasets may claim ISO conformity.
Every reported number carries one of six category labels
(analytic_correctness / synthetic_agreement / numerical_robustness /
dataset_agreement / scan_repeatability / measurement_accuracy). This framing
itself came out of a plan review that flagged an earlier, overreaching claim
("validate ISO conformity with synthetic meshes") and corrected it.

---

## Slice 0 — Fixed definitions, contracts, analytic primitives

**What was built**
- `measurement-spec.v1.yaml`: the six measurements pinned down not by name
  but by **definition** (ISO 8559-1 based), route waypoints, posture, and
  known deviations. The spec is the contract, not the code.
- The `NormalizedBodySurface` adapter contract: every input (dataset,
  generic file, the future scanner) is normalized to mm / Y-up / floor at
  zero before the measurement core ever sees it. **Units are never
  guessed** (adapter metadata → explicit CLI flag → hard failure).
- Plane slicing with torso-loop selection (axis containment → largest area →
  nearest-centroid fallback → null) and circumference measurement (raw
  contour and convex hull reported side by side, hull ≤ raw).
- Analytic ground-truth tests: cylinder vs 2πr (matching the inscribed
  polygon to machine precision), ellipse vs Ramanujan, and a
  **two-cylinder scene** proving the torso is selected by axis even when a
  larger foreign cylinder is present — a regression trap for the
  "largest loop" mistake.

**The twists**
- Discovered that trimesh's `Path3D.discrete` **returns an empty list for
  open cross-sections**. Our requirement was to *report* holes, not drop
  them — so slicing was rebuilt on raw `mesh_plane` segments chained by
  hand (grid-merged endpoints, walking degree ≤ 2 components). That
  decision later became the foundation for handling NOMO's hole-riddled
  scans in Slice 5.
- The star-prism test exposed a missing triangulation engine →
  `mapbox-earcut` added.

---

## Slice 1 — Texel BodyScan: first waist on real data

**What was built**
- Downloaded Texel BodyScan (Yandex Disk public API for the href; the
  archive turned out to be **7z**, not zip → extracted with Windows bsdtar).
- Mapped Part 1 (10 subjects): two capture pipelines, `portal_mx`
  (professional rig) and `free_fusion` (single Kinect), and — better than
  hoped — **portal_mx CSVs carry 100+ automatic measurements with ISO
  8559-1 clause numbers**. All six of our measurements matched directly
  (m5/m102/m11/m1/m55/m3).
- Verified mesh conventions: portal_mx is mm, Y-up, floor at zero,
  watertight (mesh height 1762.8 mm ≈ stature 176.4 cm). free_fusion is in
  metres with an unverified axis convention → **the adapter refuses to
  load it** (no guessing).
- Implemented the estimated waist landmark (minimum torso girth search) and
  measured all ten subjects.

**The twist — the first definition collision**
The first run showed a systematic −19.9 mm bias against m16 "Waist Girth".
Digging in revealed that the item matching *our* definition (minimum girth)
is **m102 "Minimum Waist Girth"** — and against that, the mean error is
−3.5 mm. The 20 mm gap between m16 (natural waist level) and m102 was
proven numerically to be a **definition difference, not an algorithm
error**. From then on, "ground truth is mapped by definition, not by name"
became a project rule, enforced by a per-dataset definition table
(datasets.md).

One more: the two pipelines' ground truths disagree substantially with each
other (Man0 waist 102.7 vs 94.7 cm — different sessions/devices).
Comparisons are only ever made between a mesh and the CSV of the *same*
pipeline.

---

## Slice 2 — Chest, neck, and what arm interference actually looks like

**What was built**: chest (maximum girth) and neck (horizontal v1 slice)
estimation and measurement, validated on all ten Texel subjects.

**The twists — three reversals in a row**

1. **Chest failed on all ten subjects.** The armpit had been defined as
   "the lowest height where the slice splits into 3+ loops" — but with
   lowered arms, **the hands already separate from the torso near hip
   height**, so the wrists (0.55 h) were mistaken for the armpit and the
   chest search window became [waist, something below the waist] = empty.
   → Search flipped to **top-down** (the 3→1 merge transition). This was
   the real-data incarnation of the "arm interference" question Zhen had
   raised in the procurement mail thread.
2. **Still −72 mm too small.** Printing the girth profile showed Man0
   stands with arms touching the torso: the loops merge at y≈1216 mm while
   the true bust level (m42 = 1267 mm) sits *above* the merge. Above it the
   girth explodes to 1418 mm (arms included), so the search window had been
   capped below — and we were effectively measuring the under-bust (our
   1035.9 vs m18 Under Bust Girth 1029 — eerily exact). → Implemented a
   tape approximation that **clips the merged cross-section to the torso's
   width at the armpit level** (the straight cut edges standing in for the
   tape bridging the armpits), always flagged
   `arm_clipped_at_merged_level`. Mean error went from −72 to **+33 mm**;
   Woman4 came out 1114.1 vs GT 1114.
3. The neck surprise: the v1 horizontal slice turned out to sit closer to
   **m11 (neck base)** than to m87 (middle neck) — the opposite of the
   initial expectation (+8.8 vs +26.7 mean) — settled by evidence, not
   assumption.

---

## Slice 3 — Surface-path lengths and the shoulder trap

**What was built**: edge-graph shortest-path geodesics (explicitly labelled
`edge_graph_approximation`), back length (back neck point → waist along the
back), across-back shoulder width (forced through the back neck point),
sleeve length (segment sum), and facing detection (toes sit forward of the
body axis).

**The twist — the +454 mm disaster**
Shoulder points were first taken as "the lateral extremes of the silhouette
above the armpit" — and shoulder width came out +454 mm on average. With
hanging arms, that lateral extreme is not the shoulder but the **outer
surface of the arm**, and the geodesic wrapped around the whole arm mass.
→ Redefined the shoulder point as **the highest surface point in the
vertical column above the armpit crease** (an acromion approximation) —
mean error dropped to **+32 mm**.

Sleeve length remained at +197 mm systematic overshoot (edge-graph zigzag +
the acromion approximation + detours around arm/torso contact + ISO's
bent-elbow definition). Its regression bound only guards against getting
*worse*; the offset itself is **recorded openly as an improvement item**
(heat-method geodesics, arm-axis waypoints) — numbers are not made to look
better than they are.

---

## Slice 4 — The two SMPL tracks and the robustness battery

**What was built**
- SMPL v1.1.0 (neutral, 300 shape PCs). **chumpy no longer installs on
  modern Python at all** → a custom Unpickler maps every chumpy class to a
  stub (extracting the array from its `x` attribute) and rewrites the model
  pickles as plain numpy, once. smplx then loads them without chumpy.
- Generated 18 bodies (9 shapes × T/A-pose), each with a mandatory sidecar
  JSON (seed, betas, pose, model version).
- The robustness battery: yaw+translation / uniform scale / vertex
  permutation & winding flip / 1 mm Gaussian noise / 50%+25% decimation /
  subdivision / **targeted radial waist expansion** (the replacement for
  beta-monotonicity testing, which the plan review had rejected — SMPL
  betas are not semantically fixed variables).

**The twists — two real bugs caught, two design lessons learned**

1. **The SMPL thigh gap.** The neutral template stands with a visible gap
   between the thighs, so the waist search found a single-thigh girth
   (627 mm) as the minimum. Texel subjects' thighs touch, which had masked
   the bug entirely. → Added **crotch-level detection** (the lowest height
   whose slice has a loop enclosing the body axis) as the waist window's
   floor.
2. **The world-x assumption.** The yaw-rotation test blew the chest up by
   +142 mm. Arm clipping, shoulder creases, and wrist side assignment were
   all pinned to world x — and a real scanner will never guarantee subject
   alignment, so this was a production bug waiting to happen. The first fix
   (cross-section PCA major axis) broke again on Woman4, because **a torso
   slice can be deeper than it is wide**, sending PCA front-back. Final
   design: **the lateral axis is the line between the two arm-loop
   centroids** (arms hang beside the torso by construction — yaw-invariant
   and always right), with PCA only as a fallback. After the fix: full yaw
   invariance, *and* Texel accuracy improved as a side effect (chest +26.8,
   shoulder +26.9 mean).
3. **Three rounds on armpit persistence.** A "must persist for two
   consecutive slices" rule was added against noise — and broke Woman4,
   whose true arm gap is exactly one slice thick; the persistent rule let a
   lower, thicker forearm-gap zone outrank her real armpit. Final design:
   **position is always the highest separating slice; persistence only
   sets confidence**. The consequence — chest/shoulder still jump under
   1 mm noise on real scans — is documented openly as a known limitation
   (decisions.md #12) rather than hidden behind looser thresholds
   (waist/neck stay noise-stable under 12 mm).
4. **The waist-expansion test was wrong, not the code.** Expanding the
   waist band by +10 mm "should" grow the girth by ~+63 mm, but only
   +16 mm appeared — because a *minimum-girth* definition legitimately
   relocates its minimum outside the expanded band. Re-specifying the check
   as "girth at the fixed original height" produced +50 to +58 mm. The test
   had to be corrected to match the definition, a small mirror of the whole
   project's theme.

**T-pose cross-implementation comparison (synthetic_agreement)**
- Against SMPL-Anthropometry (MIT, DavidBoja) on identical vertices. First
  attempt: chest +2000 mm — our estimated landmarks assume lowered arms,
  and on a T-pose they measured the **wingspan**. Not a bug: out-of-contract
  input. → Redesigned the comparison to inject the *reference's* landmark
  vertex heights and measure at identical heights, isolating the pure
  measurement primitive.
- Final result: **waist −1.1 mm (max 5.9), chest −0.8 mm (max 18.5)** — the
  two implementations effectively agree. Neck +24.3 mm is explained by the
  reference slicing only neck-segment faces (body-part segmentation) while
  our plane cuts the whole mesh.

---

## Slice 5 — Dataset expansion and the validation harness

**What the dataset survey overturned**
- **3DPatBody**: earlier research said CC BY, but the paper itself says
  **CC BY-NC-ND**, and its waist is defined at the **umbilicus** —
  mismatching our minimum-girth definition. Its value collapsed; only the
  5 MB sample was fetched, full download deferred.
- **HSRD-100**: turned out to be **clothed fashion scans** (jacket, jeans,
  "looking at mobile phone" pose). Useless as body-measurement ground truth
  → repurposed strictly for LOD-consistency checks (same geometry at
  different resolutions). One pose's LOD1/LOD2 downloaded; the script is a
  follow-up item.
- **Texel Part 2**: planned as the repeatability proxy (42 subjects × 5
  recordings) — but it contains **no meshes at all**, only depth frames.
  Repeatability validation is therefore honestly deferred to the
  post-scanner phase, and the plan was amended to say so.
- **NOMO-3D-400**: 658 MB from Zenodo. Its TC2 measurement
  **NeckBase_Circ matches our neck-base definition exactly** — a valuable
  ground truth. TC2 has no minimum-girth waist (only Max/Trouser variants),
  so waist gets no GT there. OBJ units are **verified** per subject against
  their own TC2 stature — never guessed.

**The twist — scans full of holes**
NOMO's first run produced wrist-sized waists (163–229 mm) on half the
subjects. The scans are full of holes: when a torso slice crosses one, the
torso polyline comes out *open*, and the "closed loops only" rule handed
the selection to a closed **arm** loop instead. → Open loops whose endpoint
gap is ≤ 20% of their length are now admissible candidates, measured with
the closing chord (= the tape crossing the hole) and always flagged
`gap_closed_open_loop`. Seven of ten subjects normalized; the remaining
three (large holes) stay broken *with honest flags* as a follow-up item.

**The harness**: one command — `python -m body_measure validate` —
generates all four category-labelled reports (Texel & NOMO
dataset_agreement / numerical_robustness / synthetic_agreement) into
`reports/`.

---

## Final numbers

**dataset_agreement — Texel Part 1 (portal_mx, 10 subjects, definition-matched GT)**

| Measurement | Mean | Max |d| | Notes |
|---|---|---|---|
| waist (m102) | −3.6 mm | 38.6 | |
| chest (m5) | +26.8 mm | 78.1 | arm-clip tape approximation, flagged |
| neck (m11) | +8.8 mm | 58.9 | horizontal v1 |
| shoulder width (m1) | +26.9 mm | 86.3 | acromion approximation |
| sleeve (m55) | +193.6 mm | 241.7 | **open improvement item** |
| back length (m3) | +26.2 mm | 86.8 | |

**dataset_agreement — NOMO, 10 males**: neck (NeckBase) −1.5 mm, chest +18.5 mm

**synthetic_agreement — T-pose, identical landmark heights**: waist −1.1 / 5.9,
chest −0.8 / 18.5, neck +24.3 / 95

**numerical_robustness**: yaw+translation, vertex permutation, and winding
flip fully invariant; uniform scale linear; real-scan decimation at 50/25%
within ±0.4 mm on circumferences; targeted waist expansion behaves as the
definition predicts. Open limitations: armpit-dependent measurements
(chest/shoulder) unstable under 1 mm noise on real scans; SMPL low-poly
(7k faces) decimation breaks the thigh-gap/crotch logic.

---

## Principles that kept working

1. **The definition is the contract** — same-named values are never
   compared unless the definitions match (m16 vs m102, umbilicus waists,
   Adam's-apple necks). The spec and the mapping tables enforce it.
2. **Never guess** — units, axes, and alignment are verified, declared, or
   the load fails. The free_fusion refusal and NOMO's stature cross-check
   are products of this rule.
3. **Never force a number** — low confidence yields null plus a flag. Every
   approximation (arm clip, gap closure, acromion, edge-graph) propagates
   its quality flag downstream.
4. **Validation redesigns the system** — the robustness battery caught the
   world-x bug and the thigh-gap bug; real data exposed the armpit search
   direction, the merge-above-armpit problem, and the hole problem. All six
   major reversals were signalled by a test or a report first.
5. **Claims stay bounded** — no number is ever reported without its
   category label.

## What remains

- Sleeve-length systematic overshoot: heat-method geodesics, arm-axis and
  elbow waypoints
- Armpit noise fragility: profile smoothing, or scanner-provided landmarks
- HSRD LOD1/LOD2 consistency script (data already downloaded)
- The three large-hole NOMO subjects; ISO 20685-1 text check (ITA library);
  inclined neck plane v2
- Post-scanner: manual-tape comparison, true repeatability, agreement with
  VITRONIC's own measurements, the actual ISO 20685-1 protocol
