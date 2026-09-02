# body-measure 검증 결과 공식 보고서

6종 측정 파이프라인과 4종 선행 검증 체계 구현 완료. 실물 제작 적용을 위한 계측 정확도 검증은 미완료.

작동 중인 선행 검증 4종: analytic_correctness, synthetic_agreement, numerical_robustness, dataset_agreement. scan_repeatability와 measurement_accuracy는 스캐너 도착 후의 후속 단계이다.

모든 데이터셋 수치는 **dataset reference**(데이터셋 자체 자동 측정값) 대비 **일치도(agreement)**이며, 수동 측정 정답 대비 정확도가 아니다. Texel 참조값은 BodyFit 자동 측정, NOMO 참조값은 TC2 자동 측정이다.

## 헤드라인 결과 — accepted + exact 매핑만

**Texel — pilot baseline (N=10, portal_mx)**

| 측정 | 매핑 | N 전체/산출/accepted/review/reject | N 통계 | Bias | MAE | Median AE | SD | Max AE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| waist_circumference | exact | 10/10/10/0/0 | 10 | -3.6 | 9.4 | 5.9 | 14.4 | 38.6 |
| across_back_shoulder_width | exact | 10/10/9/1/0 | 9 | +0.7 | 13.4 | 11.7 | 15.8 | 23.7 |

## 참고 비교 — approximate 매핑 (정의 편차 있음, 성능 판정에 사용 금지)

| 측정 | 매핑 | N 전체/산출/accepted/review/reject | N 통계 | Bias | MAE | Median AE | SD | Max AE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| chest_circumference | approximate | 10/10/10/0/0 | 10 | +26.8 | 28.1 | 25.7 | 23.6 | 78.1 |
| neck_circumference | approximate | 10/10/10/0/0 | 10 | +8.8 | 24.2 | 19.7 | 28.1 | 58.9 |
| upper_arm_girth | approximate | 10/10/10/0/0 | 10 | -3.3 | 11.3 | 12.4 | 12.8 | 20.9 |
| sleeve_length | approximate | 10/10/9/1/0 | 9 | +178.8 | 178.8 | 176.9 | 36.1 | 253.5 |
| back_length | approximate | 10/10/10/0/0 | 10 | +3.7 | 21.9 | 14.5 | 31.5 | 69.1 |

**NOMO — pilot baseline (N=10, male)**

| 측정 | 매핑 | N 전체/산출/accepted/review/reject | N 통계 | Bias | MAE | Median AE | SD | Max AE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| neck_circumference | approximate | 10/10/10/0/0 | 10 | +7.6 | 25.7 | 22.4 | 31.2 | 61.0 |
| chest_circumference | approximate | 10/10/10/0/0 | 10 | +12.8 | 45.3 | 31.6 | 63.0 | 162.6 |
| upper_arm_girth | approximate | 10/10/10/0/0 | 10 | -5.5 | 19.0 | 10.1 | 33.5 | 93.1 |

Bias, MAE, Median AE, SD 및 Max AE는 `accepted` 표본만을 대상으로 계산하였다 (`N 통계` 열). `manual_review`와 `reject` 표본은 헤드라인 통계에서 제외하였다. SD는 signed delta의 표본표준편차(`ddof=1`)이다. 소매 구간 감사의 N=9 통계는 산출 가능한 `accepted + manual_review` 전체를 사용했으므로 헤드라인 결과와 모집단이 다르다.

## Quality bucket 분포 (상호 배타, 그룹 N 합 = 전체 N)

| 측정 | bucket 분포 |
|---|---|
| chest_circumference | arm_clipped: 10 |
| waist_circumference | clean: 10 |
| neck_circumference | clean: 10 |
| upper_arm_girth | clean: 10 |
| across_back_shoulder_width | manual_review: 1, clean: 9 |
| sleeve_length | manual_review: 1, clean: 9 |
| back_length | clean: 10 |

소매길이 구간 감사 (n=10): back_neck→shoulder ↔ m36은 **mismatch**(m36 기점은 side neck point)로 수치 비교 제외. shoulder→wrist ↔ m2(approximate, 자세 상이) 평균 +156.7 mm, 전체 ↔ m55(approximate) 평균 +173.3 mm — **과대 편차는 shoulder→wrist 구간에 국소화**되어 있으며, edge-graph 근사·손목점 배치·자세 편차가 후보 원인이다.

## 측정별 현재 판정

| 측정 | 판정 |
|---|---|
| waist_circumference | 기준선 확보 — 현재 6종 중 참조값 대비 가장 낮은 MAE. 실사용 허용오차 미합의로 제작 적용 판정은 보류 |
| chest_circumference | 연구 단계 — 팔 클리핑 근사 의존, approximate 매핑 |
| neck_circumference | 연구 단계 — 수평 v1 근사, 일부 큰 편차 원인 분석 필요 |
| across_back_shoulder_width | 정의 매핑 exact — accepted 산출률 50%, 편차 및 방향 신뢰도 개선 필요 |
| sleeve_length | 정의 불일치 가능성으로 성능 판정 보류 — 편차는 shoulder→wrist 구간에 국소화됨 |
| back_length | 연구 단계 — 경로·방향 추정 개선 필요 |

## numerical_robustness (발췌)

시험한 yaw 각도 [45, 90, 180, 270]°에서 둘레 3종의 최대 |Δ| ≤ 3.4e-13 mm (수치 정밀도 수준). 알려진 한계: 실스캔 1 mm 노이즈에서 겨드랑이 의존 측정(가슴·어깨) 불안정, 시험하지 않은 자세(비대칭 팔, 편측 결손)는 미검증.

스캔 구멍 처리: 몸통 후보를 먼저 식별한 뒤 3등급(accept ≤30 mm AND ≤5% / manual_review ≤120 mm AND ≤20% / reject)으로 판정하며, reject 시 다른 루프를 재탐색하지 않고 null을 반환한다. NOMO에서는 7/10 피험자에서 몸통 단면 선택과 인체 범위 내 측정값 산출을 복구했으며, 정확도는 별도로 검증되지 않았다.

전후 방향은 toe_extent_about_leg으로 추정한다. 발은 발목 위 다리를 기준으로 뒤꿈치보다 발가락 쪽으로 3~6배 멀리 뻗으며, 이 비대칭이 방향의 부호를 준다. front_back_confidence는 단일 표본의 크기가 아니라 양발이 서로 일치하는 정도에서 나온다. 발 스캔이 없으면 orientation_unknown으로 등목점 의존 측정 3종을 null 처리하고, 저신뢰면 manual_review로 강등한다. 이전 toe_projection 방식은 신장 3% 단면의 중심을 썼으나 그 높이에는 발가락이 없어 방향이 180° 반대였다 (결정 #31); 그 이전에 보고된 길이 수치는 모두 대체되었다.

## synthetic_agreement — 동일 랜드마크 높이의 구현 간 비교

| 측정 | Bias (mm) | Max AE (mm) | N |
|---|---:|---:|---:|
| chest_circumference | -0.8 | 18.5 | 9 |
| waist_circumference | -1.1 | 5.9 | 9 |
| neck_circumference | +24.3 | 95.0 | 9 |

## 기관 확인 필요 사항

- Texel BodyScan은 CC BY-NC 4.0 — ColorDigital이 참여하는 산업 프로젝트 문맥에서의 사용 범위를 기관에 확인 필요. 현재는 로컬 연구 검증 전용, 배포 금지.
- NOMO-3D-400은 과학 연구 전용, 수정·재배포·독점 프로그램 포함 금지 — 코드·배포 패키지에 포함 불가.
- ISO 20685-1 원문 대조(ITA 도서관), 치수별 실제 제작 허용오차 합의(ITA 의류 전문가).

## DPP 연동 경계

신체 치수와 원본 스캔은 DPP 공개 데이터가 아니라 내부 개인정보 영역이다. dpp-prototype의 설계 원칙(신체 치수는 패스포트 필드가 아님, INTERNAL_PRIVATE 계층)과 동일한 경계를 이 파이프라인의 산출물에도 적용한다 — 패스포트로 전달되는 것은 완성 의류 치수와 불투명한 fit 참조뿐이다.

## 실행 정보

- generated (UTC): 2026-09-02T12:59:59+00:00
- git commit: 4ed9160ea0c194adc12d80f1c844d58e39a07ea8 — working tree: clean
- platform: Windows-11-10.0.26200-SP0
- python 3.12.10; numpy 2.5.2, trimesh 5.0.0, shapely 2.1.2, scipy 1.18.0
- spec_version 5; spec SHA-256: 30f3ec8f5fd3a07c89cc81f681f3da23df46de4cec64b4e4d80f9d9196b16d50
- thresholds SHA-256: 420470aec4ce0a66d62e72f470b2806f4020822962e5d504efb9ad0f79e11de9
- pytest: 195 passed in 128.77s
- random seed (SMPL generation): 20260817
- commands: python -m pytest tests; python scripts/build_validation_results.py; python scripts/render_formal_report.py
- report paths: reports/validation-results.json; docs/report-formal.ko.md; docs/report-formal.en.md
- Texel Part 1: 10 persons (extracted in place; original archive hash: part1.7z: 5f1e43f9ff68031c316751dc849c75a15f8d66e0b450502d689d2bca2a303c36)
- NOMO archive SHA-256: nomo400.zip: a4f99a47225f1cca00f7c53c2680de3e6e7beb762ef27db1d8ba71f4741de2e3

## 참고문헌

- ISO 8559-1:2017, Size designation of clothes — Part 1: Anthropometric definitions for body measurement.
- ISO 20685-1:2018, 3-D scanning methodologies for internationally compatible anthropometric databases — Part 1: Evaluation protocol for body dimensions extracted from 3-D body scans.
- Texel BodyScan Dataset and Texel BodyFit automatic measurements (CC BY-NC 4.0).
- Yan, S., Wirta, J., Kämäräinen, J.-K.: Anthropometric clothing measurements from 3D body scans. Machine Vision and Applications 31, 7 (2020). NOMO-3D-400 dataset: doi:10.5281/zenodo.3735905.
- Bojanić, D.: SMPL-Anthropometry (MIT license). https://github.com/DavidBoja/SMPL-Anthropometry
- Loper, M., Mahmood, N., Romero, J., Pons-Moll, G., Black, M. J.: SMPL: A Skinned Multi-Person Linear Model. ACM Transactions on Graphics 34(6), 248:1–248:16 (2015).
