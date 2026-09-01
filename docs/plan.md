# 작업 계획 v4 (2026-08-31)

v3까지의 계획은 `.claude/plans/`에만 있어 버전 관리되지 않았다. 그래서
`scope.md`의 "SIZER download imminent (2026-08-21)"가 열흘 동안 현실과 어긋난
채 보고서에 유령 항목으로 떴다. 계획 문서는 이제 저장소 안에 있고, 상태가
바뀌면 커밋으로 남는다.

**2026-08-31 확인 결과: SIZER는 막힌 것이 아니라 연락처가 낡은 상태다.**
`github.com/garvita-tiwari/sizer_dataset`의 절차는 Google Form 작성 후 비밀번호
요청이지만, README에 적힌 `gtiwari@mpi-inf.mpg.de`는 **반송된다** — 저자가
MPI-INF를 떠났고 Real Virtual Humans 그룹이 튀빙겐 대학으로 옮겼기 때문이다.
현행 수신처와 요청서는 `docs/sizer-access-request-draft.md`에 있다.

---

## 1. 짝 데이터셋 — SIZER가 1순위인 이유

C1 계열이 필요로 하는 것은 **같은 사람의 착의 표면과 신체 표면 한 쌍**이다.
후보는 둘이고, 같은 물건이 아니다.

| | SIZER | CAPE |
|---|---|---|
| 피험자 | **100명** | 15명 (남 10 / 여 5) — `subj_genders.pkl`만 17명으로 적지만 03212·03213은 아무것도 실려 있지 않다 (결정 #34) |
| 스캔 | 약 2,000 | 611시퀀스 · 148,508프레임 (프레임 상관 심함) |
| 의류 | **10종 × 여러 사이즈** | 의상 조합 15종 |
| 신체 표면 | **원본 스캔 + 최소 착의 신체 스캔** | registration (canonical T-pose) |
| 착의 표면 | 원본 스캔 + SMPL/SMPL+D/SMPL+G | SMPL 토폴로지 registration |
| 부가 | 의류 분할(상의/하의/신체), 스타일·사이즈·성별 라벨 | 피험자별 SMPL betas (2023-07) |

**결정적 차이는 원본 스캔의 유무다.** 결정 #17은 "제공된 registration"과
"body under clothing"이 같은 reference가 아니며, 원본 미니멀 스캔이 확인되지
않으면 claim 문구를 `provided body-reference surface`로 강등하도록 정해뒀다.
SIZER 페이지는 최소 착의 신체 스캔을 명시하므로, 사실이면 강등이 불필요하다.
CAPE만으로 C1을 하면 강등은 불가피하다.

규모도 7배 차이다. subject-cluster bootstrap CI의 폭이 여기서 갈린다.

### 그래도 CAPE는 필요하다
CAPE는 C1의 대체재가 아니라 **C3(합성 데이터 공장)의 재료**다. displacement
분포로 착의 셸을 생성해 C2 합성 배터리를 넓힌다. 라이선스가 이미 정리돼
있어(§5) 지금 받을 수 있고, SIZER 회신을 기다리지 않는다.

---

## 1a. CAPE — 무엇을 받고 무엇을 받지 않는가

전체 49GB를 받지 않는다. Option 2(피험자별)로 필요한 것만 받는다.

### 받을 것

| 순서 | 대상 | 이유 |
|---|---|---|
| 1 | `cape_release.zip` | 피험자 개요 이미지 + 시퀀스 목록. **먼저 받아야** 어느 피험자를 받을지 정할 수 있다 |
| 2 | `cape_utils` (GitHub) | 파싱 스크립트. `cape_release/` 아래 배치 |
| 3 | **SMPL betas** (2023-07 배포) | 작고, C1.5 표현 상한선에 직접 쓰인다 |
| 4 | 피험자 **00215** | `poloshort` 보유 — 이 프로젝트의 제품과 직접 겹치는 유일한 피험자 |
| 5 | 피험자 **00096** | 반팔 2종 (`shortshort` 13시퀀스, `shortlong` 6시퀀스) + 긴팔 대조군 4종. 머리 길이 변화는 이 배포분에 **없다**(아래) |
| 6 | 필요 시 00032, 03375 | 반팔(`shortlong`, `shortshort`) 추가 |

의상 이름은 `<상의><하의>` 규칙이지만, **첫 토큰이 소매 길이를 말해주지
않는다.** `short`/`long`은 그렇지만 `polo`·`jersey`·`shirt`는 옷 종류이지
소매가 아니다. 실측으로 확인한 소매 경계는 아래와 같다 (2026-09-01, T-pose에서
팔을 따라 바깥으로 걸으며 displacement가 음수로 떨어지는 지점, 반신폭 대비):

| 의상 | 소매 끝 | 판정 |
|---|---|---|
| `poloshort` (00215) | ~0.39 | 반팔 |
| `shortlong` (00215) | ~0.39 | 반팔 |
| `shortshort` (00096) | ~0.47 | 반팔 |
| `jerseyshort` (00096) | 0.71까지 양수 | **긴팔** |
| `shirtlong` (00096) | 0.79까지 양수 | 긴팔 |
| `longshort` (00215·00096) | 0.71~0.79까지 양수 | 긴팔 |

따라서 **반팔은 `polo*`와 `short*`뿐이다.** `jersey*`를 반팔로 분류하면 안 된다.

### 머리카락은 이 데이터에 없다
배포 페이지는 00096·03284에 머리 길이 변화가 있다고 적지만, 그것은 원본
스캔의 이야기다. 우리가 받은 것은 **SMPL 토폴로지 registration**이고 SMPL에는
머리카락 지오메트리가 없다. 실제로 머리 밴드의 displacement는 여섯 의상 모두
−0.5~+0.3 mm로 사실상 0이다. 결정 #32의 머리카락 실패(Woman4의 어깨점이 탐색
천장에 박힌 것)를 재현할 자료는 여기 **없다** — raw scan을 따로 요청해야 한다.

### 받지 말 것 — 이름이 함정이다

페이지 하단 "Download links" 목록(`00215_poloshort (4.3G)` 등)은 **POP/SCALE
패킹 포맷**이다. 그 절의 제목이 "NEW in October 2021: Packed CAPE data in
POP / SCALE-compatible format"이고, 내용물은 positional map과 표면에서 샘플링한
**포인트 클라우드**이지 메시가 아니다. `00215_poloshort`라는 이름이 이 프로젝트에
딱 맞아 보이지만, 우리가 필요한 것은 측정 가능한 표면이므로 쓸 수 없다.

받아야 할 것은 "Download by subject" 절의 **피험자 버튼**이다.

ICON 평가용 test set도 받지 않는다 — 다른 논문의 벤치마크 분할이다.

### 프레임은 거의 다 버린다 — 다만 이유가 바뀌었다

148,508프레임은 필요 없다. 배포 페이지는 "모든 시퀀스가 A-pose로 시작한다"고
적지만, **실측 결과 그 말은 느슨하다** (2026-09-01, 결정 #34): 00215 poloshort
12개 시퀀스의 첫 프레임에서 몸통 관절이 평균 |ω| 0.144~0.223 rad, 최대
0.72~1.33 rad로 이 프로젝트의 A-pose 외전각(0.87 rad)을 넘고 시퀀스마다 다르다.

따라서 **포즈가 잡힌 프레임을 직접 측정하지 않는다.** 대신 각 프레임의
`v_cano`에서 displacement를 뽑아 이 프로젝트의 canonical A-pose 신체에
전이한다. 그것이 C3의 설계이며, 결과물은 합성 셸이지 착의 관측이 아니다.

서브샘플링 규칙은 C0a 감사 단계에서 확정한다 (결정 #18).

`seq_with_remove_frames_<subj>.txt`에 등록 품질 불량으로 **수동 제거된 프레임
구간**이 적혀 있다. 시퀀스가 연속이 아니므로 프레임 인덱스로 이웃을 가정하면 안
된다.

### 미리 알아둘 방법론적 걸림돌

**신체 기준면과 착의 관측의 포즈가 다르다.** `minimal_body_shape`는 canonical
T-pose이고 `sequences`는 포즈가 잡혀 있다. 포즈가 다른 두 표면의 둘레를 그냥
빼면 그것은 의류 오프셋이 아니라 포즈 차이다. 파싱 스크립트의
`--option canonical`이 옷을 T-pose로 옮겨주지만, 그것은 **관측된 T-pose가 아니라
변환된 관측**이므로 claim 문구에 반영해야 한다.

이 문제는 SIZER에는 없다 — 같은 자세로 착의·비착의를 각각 스캔하기 때문이다.
C1을 SIZER로 하려는 또 하나의 이유다.

---

## 2. 작업 순서

```
G0-1 SIZER 요청 발송 ──(회신 대기)──┐
                                     ├─→ C0a 감사 → C0b → C1 → C1.5 → C1b
CAPE 다운로드 ───────────────────────┘                              └→ C3
P1 sleeve_length ──── 데이터 불필요, 지금 시작
P3 대외 자료 갱신 ─── 데이터 불필요, 지금 시작
```

SIZER 회신은 며칠 걸릴 수 있다. **그 사이에 P1·P3를 진행한다.**

### C0a — 감사가 어댑터보다 먼저 (결정 #17 유지)
`scripts/audit_sizer_manifest.py --root data/external/sizer`를
`adapters/sizer.py`보다 **먼저** 돌린다. §1의 표는 배포 페이지 설명이지
확인된 파일 구조가 아니다. 인식되지 않는 파일은 `unclassified`로 보고하며
역할을 추측하지 않는다. 출력이 C1의 claim 문구를 정한다.

### C0a — subject-disjoint split (결정 #18 유지)
SIZER는 한 피험자를 여러 의상·사이즈로 반복한다. 스캔 단위 무작위 분할은 같은
체형을 양쪽에 넣는다. 분할은 피험자 단위로 감사 단계에서 결정하고
`reports/split-manifest.json`에 해시한다.

CAPE를 쓸 때는 더 심하다 — 한 시퀀스의 연속 프레임은 거의 같은 관측이다.
시퀀스당 프레임 서브샘플링 규칙을 감사 단계에서 함께 정한다.

### C0b~C1b — v3 그대로
어댑터(`provides = frozenset()`, `fit_references`는 감사가 확인한 것만),
의류 분류·사이즈별 오프셋 표(subject-weighted bias / MAE / P90 / coverage,
N_subjects·N_scans 병기, subject-cluster bootstrap CI), 표현 상한선 분해,
gap atlas(train subject만) → C2의 `L_gap_band` 교체.

---

## 3. 지금 바로 할 수 있는 것

비착의 스캔 40명(Texel 10 + NOMO 30) 기준 현재 품질:

| 측정 | 사용 가능 | 비고 |
|---|---|---|
| `upper_arm_girth` | 40/40 | |
| `neck_circumference` | 38/40 | |
| `back_length` | 36/40 | 결정 #31 이후 |
| `waist_circumference` | 34/40 | |
| `across_back_shoulder_width` | 34/40 | 결정 #32 이후 |
| `chest_circumference` | 23/40 | clean 0 — 전원 근사 등급 |
| `sleeve_length` | 9/40 | NOMO 30/30 거부 |

### P1 — `sleeve_length` (가장 큰 구멍)
NOMO 30/30 거부는 손목 검출(`estimate_wrist_points`)로 좁혀진다. Texel은 값이
나오지만 편향 **+173mm**이고, 결정 #32의 어깨 수정에도 거의 움직이지 않았다.
어깨가 아니라 손목점 또는 경로 정의(팔꿈치 경유점 생략) 쪽 문제다. 폴로
패턴의 필수 치수라 방치할 수 없다.

### P3 — 대외 자료 갱신
결정 #31(전후 반전) 이전에 보고된 **모든 길이 수치가 대체**됐다. 갱신 대상:
KW35 주간 발표자료, `reports/clothing_offset_hsrd.json`,
`docs/slice-report-2026-08-17.en.md`의 어깨·소매 델타 표.
(`dataset_agreement_texel.md`와 `size_report.json`은 재생성 완료.)

### P4 — `chest_circumference`
40명 전원이 `arm_clipped` 또는 `low_confidence`로 `clean`이 하나도 없다. 팔
클리핑은 문서화된 체계적 근사이므로 사용은 허용되지만, 폴로의 가장 중요한
치수가 가장 낮은 등급이라는 사실은 남는다.

---

## 4. `measurement_accuracy`는 SIZER로도 열리지 않는다

결정 #1대로 설계상 도달 불가다 — ISO 20685-1이 실제 피험자와 **훈련된
측정자의 줄자 실측**을 요구하는데 Texel·NOMO·HSRD·SIZER·CAPE 어느 것도 그걸
주지 않는다. 짝 데이터셋이 열어주는 것은 `clothing_offset`이지
`measurement_accuracy`가 아니다.

유일한 실질 후보는 **Size Korea**(국가기술표준원): 직접측정 136항목 ×
14,016명 + 3D 156항목 × 848명. 확인할 단 하나의 질문 — **3D 848명이
직접측정 14,016명의 부분집합인가.** 그렇다면 같은 사람의 줄자 값과 메시를
짝지을 수 있고, 이 프로젝트에서 처음으로 도달 가능해진다.

AI-Hub 「한국인 신체 3D 스캐닝」(530명, 동일 피험자 치수 동반)도 후보지만
**내국인 한정 + 안심구역 반출 통제**가 걸려 있다. 국적이 아니라 반출 문제이고
연구 수행지가 RWTH Aachen ITA이므로, 약관 원문 확보 전에는 진행하지 않는다.
`.env`의 AI-Hub 키는 그때까지 사용하지 않는다.

---

## 5. 라이선스 상태

| 항목 | 상태 |
|---|---|
| 1. SIZER 약관 원문 | ☐ 미확보. 2026-08-31 15:50 개인 Gmail에서 튀빙겐 3인에게 **비밀번호만** 요청 발송, 2026-09-01 현재 회신 없음. 약관·대응관계·산업맥락 질문이 빠졌고 Waldemar가 수신처에 없다 → 기관 주소 후속 메일 필요 (`sizer-access-request-draft.md`) |
| 2. CAPE 약관 원문 | ☑ 확보 (`cape-terms.txt`, provenance에 해시). 데이터 **수령 완료** 2026-09-01: `cape_release`, `minimal_body_params`, 피험자 00215·00096 |
| 3. SMPL 모델 라이선스 | ☑ |
| 4·5·7·8 | ☑ |
| 6. 가중치 승인 증빙 | ☑* 승인됨, 회신 **원문** 붙여넣기 미완 |
| 9. 윤리·동의 범위 | ☐ ITA의 2차 이용 입장 필요. CAPE raw scan 동의서도 여기 |

**CAPE 일반 배포분은 지금 받을 수 있다.** SIZER는 항목 1이 열려 있으므로
약관 원문 확보 전에는 C0a를 시작하지 않는다.

### CAPE raw scan (선택, 항목 9 연결)
4명 피험자 20시퀀스의 raw scan은 동의서를 **기관 이메일**로
`cape@tue.mpg.de`에 보내야 하고, 텍스처(정점 색) 필요 여부를 명시해야 한다.
SIZER가 원본 스캔을 주면 우선순위가 낮아진다.

### 확인이 필요한 불일치
`weights-permission.md`는 CAPE 상업 문의처를 `ps-license@tue.mpg.de`로 적으며
"`ps-licensing`이 아니라 라이선스 페이지에 인쇄된 주소"라고 주석했다. 그런데
**CAPE 다운로드 페이지는 `ps-licensing@tue.mpg.de`로 적는다.** 두 페이지가
다르다. 상업 문의를 실제로 보내기 전에 라이선스 페이지 원문을 다시 확인해야
한다 — 현재 문서의 단정은 근거가 한쪽뿐이다.

---

## 6. 변하지 않는 지배 원칙

v3에서 그대로 승계한다:

- NN/최적화는 신체를 복원하고, 치수는 기존 검증된 기하 파이프라인이 산출
- 추정은 측정이 아님 — claim category는 `(pathway, reference_kind)`에서 유도,
  손으로 타이핑 금지
- 복원 불가는 null 기권. 조용한 오답은 정직한 거부보다 나쁘다
- 측정 코어 torch-free, torch는 `body_measure/inference/`에 격리
- subject-disjoint split, train-only 통계, 감사 단계에서 잠금
- 공개 자료는 **HSRD-100만** (`public-material.md`) — 승인 범위에 공개 자료
  확장은 포함되지 않았다
- 라이선스 제한 데이터·가중치는 git 미포함
