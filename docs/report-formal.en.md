# body-measure Validation Results — Formal Report

Six-measurement pipeline and four pre-arrival validation categories implemented. Metrological accuracy validation for production use is NOT yet performed.

Four pre-arrival validation categories are operational: analytic_correctness, synthetic_agreement, numerical_robustness, dataset_agreement. scan_repeatability and measurement_accuracy are post-scanner phases.

All dataset numbers are **agreement against dataset references** (the datasets' own automatic values), not accuracy against manual measurements. Texel references come from the BodyFit pipeline, NOMO references from TC2.

## Headline results — accepted values with exact mappings only

**Texel — pilot baseline (N=10, portal_mx)**

| Measurement | Mapping | N (total/computed/accepted/review/rejected) | Bias | MAE | Median AE | SD | Max AE |
|---|---|---|---|---|---|---|---|
| waist_circumference | exact | 10/10/10/0/0 | -3.6 | 9.4 | 5.9 | 14.4 | 38.6 |
| across_back_shoulder_width | exact | 10/9/5/4/1 | +58.4 | 58.4 | 53.7 | 29.2 | 86.3 |

## Reference comparisons — approximate mappings (definition deviations; not for performance verdicts)

| Measurement | Mapping | N (total/computed/accepted/review/rejected) | Bias | MAE | Median AE | SD | Max AE |
|---|---|---|---|---|---|---|---|
| chest_circumference | approximate | 10/10/10/0/0 | +26.8 | 28.1 | 25.7 | 23.6 | 78.1 |
| neck_circumference | approximate | 10/10/10/0/0 | +8.8 | 24.2 | 19.7 | 28.1 | 58.9 |
| sleeve_length | approximate | 10/9/5/4/1 | +197.8 | 197.8 | 211.3 | 48.4 | 239.6 |
| back_length | approximate | 10/9/5/4/1 | +14.2 | 31.0 | 33.3 | 32.8 | 42.5 |

**NOMO — pilot baseline (N=10, male)**

| Measurement | Mapping | N (total/computed/accepted/review/rejected) | Bias | MAE | Median AE | SD | Max AE |
|---|---|---|---|---|---|---|---|
| neck_circumference | approximate | 10/10/10/0/0 | +7.6 | 25.7 | 22.4 | 31.2 | 61.0 |
| chest_circumference | approximate | 10/10/10/0/0 | +14.0 | 48.2 | 37.0 | 66.2 | 170.9 |

## Quality bucket distribution (mutually exclusive; group Ns sum to total)

| Measurement | bucket distribution |
|---|---|
| chest_circumference | arm_clipped: 10 |
| waist_circumference | clean: 10 |
| neck_circumference | clean: 10 |
| across_back_shoulder_width | rejected: 1, manual_review: 4, clean: 5 |
| sleeve_length | rejected: 1, manual_review: 4, clean: 5 |
| back_length | rejected: 1, manual_review: 4, clean: 5 |

Sleeve segment audit (n=9): back_neck→shoulder ↔ m36 is a **mismatch** (m36 originates at the side neck point) and is excluded from numeric comparison. shoulder→wrist ↔ m2 (approximate; posture differs) mean +183.5 mm, combined ↔ m55 (approximate) mean +198.9 mm — **the overshoot localizes in the shoulder→wrist segment**; edge-graph inflation, wrist-point placement, and the posture deviation are the candidate causes.

## Current verdict per measurement

| Measurement | Verdict |
|---|---|
| waist_circumference | baseline established — good reference agreement (not production-approved) |
| chest_circumference | research stage — depends on the arm-clip approximation; approximate mapping |
| neck_circumference | research stage — horizontal v1 approximation; large outliers need analysis |
| across_back_shoulder_width | research stage — acromion-estimate error; manual_review under low orientation confidence |
| sleeve_length | performance verdict deferred (possible definition mismatch) — the offset localizes in the shoulder→wrist segment |
| back_length | research stage — path and orientation estimation need refinement |

## numerical_robustness (excerpt)

Across tested yaw angles [45, 90, 180, 270]°, the maximum |Δ| of the three circumferences was ≤ 2.3e-13 mm (numerical precision level). Known limitations: armpit-dependent measurements (chest/shoulder) are unstable under 1 mm noise on real scans; untested poses (asymmetric arms, missing limbs) are unvalidated.

Scan-hole handling: the torso candidate is identified first, then tiered (accept ≤30 mm AND ≤5% / manual_review ≤120 mm AND ≤20% / reject); a reject returns null and never re-shops among other loops. On NOMO this restored torso-section selection and human-range values for 7/10 subjects; accuracy is not separately validated.

Front/back orientation is estimated by toe_projection with a reported front_back_confidence. Missing feet set orientation_unknown and null the three back-neck-dependent measurements; low confidence demotes them to manual_review.

## synthetic_agreement — cross-implementation at identical landmark heights

| Measurement | bias (mm) | max |d| (mm) | n |
|---|---|---|---|
| chest_circumference | -0.8 | 18.5 | 9 |
| waist_circumference | -1.1 | 5.9 | 9 |
| neck_circumference | +24.3 | 95.0 | 9 |

## Items requiring institutional confirmation

- Texel BodyScan is CC BY-NC 4.0 — usage scope within an industry project involving ColorDigital must be confirmed. Currently local research validation only; no distribution.
- NOMO-3D-400 is research-only; no modification, redistribution, or inclusion in proprietary software — must not ship with code or packages.
- ISO 20685-1 text check (ITA library); per-measurement production tolerances to be agreed with ITA garment experts.

## DPP integration boundary

Body measurements and raw scans are NOT public DPP data; they live in the internal personal-data domain. The same boundary as dpp-prototype's design (body measurements are not passport fields; INTERNAL_PRIVATE tier) applies to this pipeline's outputs — only finished-garment dimensions and an opaque fit reference ever reach a passport.

## Run information

- generated (UTC): 2026-08-17T14:22:03+00:00
- git commit: f84161e34e4e (dirty)
- python 3.12.10; numpy 2.5.2, trimesh 5.0.0, shapely 2.1.2, scipy 1.18.0
- spec_version 2 (sha256 59eab70bbd5f348d); thresholds sha256 c26b0c82319bbc3c
- Texel Part 1 persons: 10
