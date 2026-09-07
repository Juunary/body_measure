# body-measure Validation Results — Formal Report

Six-measurement pipeline and four pre-arrival validation categories implemented. Metrological accuracy validation for production use is NOT yet performed.

Four pre-arrival validation categories are operational: analytic_correctness, synthetic_agreement, numerical_robustness, dataset_agreement. scan_repeatability and measurement_accuracy are post-scanner phases.

All dataset numbers are **agreement against dataset references** (the datasets' own automatic values), not accuracy against manual measurements. Texel references come from the BodyFit pipeline, NOMO references from TC2.

## Headline results — accepted values with exact mappings only

**Texel — pilot baseline (N=10, portal_mx)**

| Measurement | Mapping | N total/computed/accepted/review/rejected | N stats | Bias | MAE | Median AE | SD | Max AE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| waist_circumference | exact | 10/10/10/0/0 | 10 | -12.2 | 13.5 | 6.4 | 18.6 | 49.8 |
| across_back_shoulder_width | exact | 10/10/9/1/0 | 9 | +0.8 | 13.1 | 13.6 | 15.5 | 24.8 |

## Reference comparisons — approximate mappings (definition deviations; not for performance verdicts)

| Measurement | Mapping | N total/computed/accepted/review/rejected | N stats | Bias | MAE | Median AE | SD | Max AE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| chest_circumference | approximate | 10/10/10/0/0 | 10 | +26.9 | 28.2 | 25.9 | 23.6 | 78.1 |
| neck_circumference | approximate | 10/10/10/0/0 | 10 | +8.8 | 24.2 | 19.7 | 28.1 | 58.9 |
| upper_arm_girth | approximate | 10/10/10/0/0 | 10 | -16.1 | 17.4 | 16.8 | 14.1 | 33.9 |
| sleeve_length | approximate | 10/10/9/1/0 | 9 | +170.8 | 170.8 | 168.9 | 22.3 | 206.2 |
| back_length | approximate | 10/10/10/0/0 | 10 | -2.7 | 16.4 | 14.3 | 20.8 | 37.3 |

**NOMO — pilot baseline (N=10, male)**

| Measurement | Mapping | N total/computed/accepted/review/rejected | N stats | Bias | MAE | Median AE | SD | Max AE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| neck_circumference | approximate | 10/10/10/0/0 | 10 | +7.6 | 25.7 | 22.4 | 31.2 | 61.0 |
| chest_circumference | approximate | 10/10/10/0/0 | 10 | +20.8 | 37.0 | 30.9 | 38.1 | 80.7 |
| upper_arm_girth | approximate | 10/10/10/0/0 | 10 | -13.6 | 17.9 | 8.2 | 32.6 | 102.5 |

Bias, MAE, Median AE, SD, and Max AE are computed over the `accepted` sample only (column `N stats`); `manual_review` and `reject` samples are excluded from headline statistics. SD is the sample standard deviation of the signed deltas (`ddof=1`). The sleeve segment audit's N=9 statistics use all computable `accepted + manual_review` values and therefore describe a different population than the headline results.

## Quality bucket distribution (mutually exclusive; group Ns sum to total)

| Measurement | bucket distribution |
|---|---|
| chest_circumference | low_confidence: 1, arm_clipped: 9 |
| waist_circumference | clean: 10 |
| neck_circumference | clean: 10 |
| upper_arm_girth | clean: 10 |
| across_back_shoulder_width | manual_review: 1, clean: 9 |
| sleeve_length | manual_review: 1, clean: 9 |
| back_length | clean: 10 |

Sleeve segment audit (n=10): back_neck→shoulder ↔ m36 is a **mismatch** (m36 originates at the side neck point) and is excluded from numeric comparison. shoulder→wrist ↔ m2 (approximate; posture differs) mean +156.7 mm, combined ↔ m55 (approximate) mean +165.1 mm — **the overshoot localizes in the shoulder→wrist segment**; edge-graph inflation, wrist-point placement, and the posture deviation are the candidate causes.

## Current verdict per measurement

| Measurement | Verdict |
|---|---|
| waist_circumference | baseline established — lowest MAE against references among the six; production verdict deferred until tolerances are agreed |
| chest_circumference | research stage — depends on the arm-clip approximation; approximate mapping |
| neck_circumference | research stage — horizontal v1 approximation; large outliers need analysis |
| across_back_shoulder_width | definition mapping exact — accepted coverage 50%; deviation and orientation confidence need improvement |
| sleeve_length | performance verdict deferred (possible definition mismatch) — the offset localizes in the shoulder→wrist segment |
| back_length | research stage — path and orientation estimation need refinement |

## numerical_robustness (excerpt)

Across tested yaw angles [45, 90, 180, 270]°, the maximum |Δ| of the three circumferences was ≤ 3.4e-13 mm (numerical precision level). Known limitations: armpit-dependent measurements (chest/shoulder) are unstable under 1 mm noise on real scans; untested poses (asymmetric arms, missing limbs) are unvalidated.

Scan-hole handling: the torso candidate is identified first, then tiered (accept ≤30 mm AND ≤5% / manual_review ≤120 mm AND ≤20% / reject); a reject returns null and never re-shops among other loops. On NOMO this restored torso-section selection and human-range values for 7/10 subjects; accuracy is not separately validated.

Front/back orientation is estimated by toe_extent_about_leg: about the leg above it, a foot reaches three to six times further toward the toes than the heel, and that asymmetry gives the sign. front_back_confidence comes from the two feet corroborating each other rather than from the magnitude of any single sample. Missing feet set orientation_unknown and null the three back-neck-dependent measurements; low confidence demotes them to manual_review. The earlier toe_projection method read the centroid of a cut at 3 % of stature, where the toes are no longer present, and was 180 degrees out (decision #31); length values reported before that fix are superseded.

## synthetic_agreement — cross-implementation at identical landmark heights

| Measurement | Bias (mm) | Max AE (mm) | N |
|---|---:|---:|---:|
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

- generated (UTC): 2026-09-07T12:10:28+00:00
- git commit: 64ec5e8a10efe7ce8147292549a6b045892fe03b — working tree: clean
- platform: Windows-11-10.0.26200-SP0
- python 3.12.10; numpy 2.5.2, trimesh 5.0.0, shapely 2.1.2, scipy 1.18.0
- spec_version 8; spec SHA-256: 26f7c13b1e7c9eb3dfa5babad233908d830e2785d6cf33ba8b29a36eff69842d
- thresholds SHA-256: 97263bc8f00acd1f3b9873491ed82df364d06c4640dc54c9eca018ae6ede6d56
- pytest: 257 passed in 536.07s (0:08:56)
- random seed (SMPL generation): 20260817
- commands: python -m pytest tests; python scripts/build_validation_results.py; python scripts/render_formal_report.py
- report paths: reports/validation-results.json; docs/report-formal.ko.md; docs/report-formal.en.md
- Texel Part 1: 10 persons (extracted in place; original archive hash: part1.7z: 5f1e43f9ff68031c316751dc849c75a15f8d66e0b450502d689d2bca2a303c36)
- NOMO archive SHA-256: nomo400.zip: a4f99a47225f1cca00f7c53c2680de3e6e7beb762ef27db1d8ba71f4741de2e3

## References

- ISO 8559-1:2017, Size designation of clothes — Part 1: Anthropometric definitions for body measurement.
- ISO 20685-1:2018, 3-D scanning methodologies for internationally compatible anthropometric databases — Part 1: Evaluation protocol for body dimensions extracted from 3-D body scans.
- Texel BodyScan Dataset and Texel BodyFit automatic measurements (CC BY-NC 4.0).
- Yan, S., Wirta, J., Kämäräinen, J.-K.: Anthropometric clothing measurements from 3D body scans. Machine Vision and Applications 31, 7 (2020). NOMO-3D-400 dataset: doi:10.5281/zenodo.3735905.
- Bojanić, D.: SMPL-Anthropometry (MIT license). https://github.com/DavidBoja/SMPL-Anthropometry
- Loper, M., Mahmood, N., Romero, J., Pons-Moll, G., Black, M. J.: SMPL: A Skinned Multi-Person Linear Model. ACM Transactions on Graphics 34(6), 248:1–248:16 (2015).
