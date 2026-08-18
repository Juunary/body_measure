# body-measure 검증 결과 공식 보고서

6종 측정 파이프라인과 4종 선행 검증 체계 구현 완료. 실물 제작 적용을 위한 계측 정확도 검증은 미완료.

작동 중인 선행 검증 4종: analytic_correctness, synthetic_agreement, numerical_robustness, dataset_agreement. scan_repeatability와 measurement_accuracy는 스캐너 도착 후의 후속 단계이다.

모든 데이터셋 수치는 **dataset reference**(데이터셋 자체 자동 측정값) 대비 **일치도(agreement)**이며, 수동 측정 정답 대비 정확도가 아니다. Texel 참조값은 BodyFit 자동 측정, NOMO 참조값은 TC2 자동 측정이다.

## 헤드라인 결과 — accepted + exact 매핑만

**Texel — pilot baseline (N=10, portal_mx)**

| 측정 | 매핑 | N (전체/산출/accepted/review/reject) | Bias | MAE | Median AE | SD | Max AE |
|---|---|---|---|---|---|---|---|
| waist_circumference | exact | 10/10/10/0/0 | -3.6 | 9.4 | 5.9 | 14.4 | 38.6 |
| across_back_shoulder_width | exact | 10/9/5/4/1 | +58.4 | 58.4 | 53.7 | 29.2 | 86.3 |

## 참고 비교 — approximate 매핑 (정의 편차 있음, 성능 판정에 사용 금지)

| 측정 | 매핑 | N (전체/산출/accepted/review/reject) | Bias | MAE | Median AE | SD | Max AE |
|---|---|---|---|---|---|---|---|
| chest_circumference | approximate | 10/10/10/0/0 | +26.8 | 28.1 | 25.7 | 23.6 | 78.1 |
| neck_circumference | approximate | 10/10/10/0/0 | +8.8 | 24.2 | 19.7 | 28.1 | 58.9 |
| sleeve_length | approximate | 10/9/5/4/1 | +197.8 | 197.8 | 211.3 | 48.4 | 239.6 |
| back_length | approximate | 10/9/5/4/1 | +14.2 | 31.0 | 33.3 | 32.8 | 42.5 |

**NOMO — pilot baseline (N=10, male)**

| 측정 | 매핑 | N (전체/산출/accepted/review/reject) | Bias | MAE | Median AE | SD | Max AE |
|---|---|---|---|---|---|---|---|
| neck_circumference | approximate | 10/10/10/0/0 | +7.6 | 25.7 | 22.4 | 31.2 | 61.0 |
| chest_circumference | approximate | 10/10/10/0/0 | +14.0 | 48.2 | 37.0 | 66.2 | 170.9 |

## Quality bucket 분포 (상호 배타, 그룹 N 합 = 전체 N)

| 측정 | bucket 분포 |
|---|---|
| chest_circumference | arm_clipped: 10 |
| waist_circumference | clean: 10 |
| neck_circumference | clean: 10 |
| across_back_shoulder_width | rejected: 1, manual_review: 4, clean: 5 |
| sleeve_length | rejected: 1, manual_review: 4, clean: 5 |
| back_length | rejected: 1, manual_review: 4, clean: 5 |

소매길이 구간 감사 (n=9): back_neck→shoulder ↔ m36은 **mismatch**(m36 기점은 side neck point)로 수치 비교 제외. shoulder→wrist ↔ m2(approximate, 자세 상이) 평균 +183.5 mm, 전체 ↔ m55(approximate) 평균 +198.9 mm — **과대 편차는 shoulder→wrist 구간에 국소화**되어 있으며, edge-graph 근사·손목점 배치·자세 편차가 후보 원인이다.

## 측정별 현재 판정

| 측정 | 판정 |
|---|---|
| waist_circumference | 기준선 확보 — 참조값 일치도 양호 (실사용 승인 전) |
| chest_circumference | 연구 단계 — 팔 클리핑 근사 의존, approximate 매핑 |
| neck_circumference | 연구 단계 — 수평 v1 근사, 일부 큰 편차 원인 분석 필요 |
| across_back_shoulder_width | 연구 단계 — 견봉 추정 오차, 방향 저신뢰 시 manual_review |
| sleeve_length | 정의 불일치 가능성으로 성능 판정 보류 — 편차는 shoulder→wrist 구간에 국소화됨 |
| back_length | 연구 단계 — 경로·방향 추정 개선 필요 |

## numerical_robustness (발췌)

시험한 yaw 각도 [45, 90, 180, 270]°에서 둘레 3종의 최대 |Δ| ≤ 2.3e-13 mm (수치 정밀도 수준). 알려진 한계: 실스캔 1 mm 노이즈에서 겨드랑이 의존 측정(가슴·어깨) 불안정, 시험하지 않은 자세(비대칭 팔, 편측 결손)는 미검증.

스캔 구멍 처리: 몸통 후보를 먼저 식별한 뒤 3등급(accept ≤30 mm AND ≤5% / manual_review ≤120 mm AND ≤20% / reject)으로 판정하며, reject 시 다른 루프를 재탐색하지 않고 null을 반환한다. NOMO에서는 7/10 피험자에서 몸통 단면 선택과 인체 범위 내 측정값 산출을 복구했으며, 정확도는 별도로 검증되지 않았다.

전후 방향은 toe_projection으로 추정하며 front_back_confidence를 보고한다. 발 스캔이 없으면 orientation_unknown으로 등목점 의존 측정 3종을 null 처리하고, 저신뢰면 manual_review로 강등한다.

## synthetic_agreement — 동일 랜드마크 높이의 구현 간 비교

| 측정 | bias (mm) | max |d| (mm) | n |
|---|---|---|---|
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

- generated (UTC): 2026-08-17T14:22:03+00:00
- git commit: f84161e34e4e (dirty)
- python 3.12.10; numpy 2.5.2, trimesh 5.0.0, shapely 2.1.2, scipy 1.18.0
- spec_version 2 (sha256 59eab70bbd5f348d); thresholds sha256 c26b0c82319bbc3c
- Texel Part 1 persons: 10
