# Datasets

전 파일은 `data/external/<name>/` 아래에만 두고, 디렉토리 전체가 gitignore 대상이다.
어떤 데이터셋 파일도, 파생 메시도 커밋하지 않는다 (decisions.md #8).

## 역할과 라이선스

| 데이터셋 | 역할 | 라이선스 | 접근 |
|---|---|---|---|
| Texel BodyScan | dataset_agreement 1차 (ISO 8559-1 치수 동봉) + Part 2(42명×5회) 반복성 프록시 + SMPL/STAR 피팅으로 fitted/estimated 경로 교차 | CC BY-NC 4.0 (비상업 연구) | 공개 다운로드, ~1.1GB |
| 3DPatBody | 대규모 N(299) 허리 둘레 편향 분포; 팔다리 희소 메시의 open_loop 처리 검증 | CC BY | 공개 저장소 |
| NOMO-3D-400 | 의류용 신체치수 보강 (항목·정의는 다운로드 후 확인). **부위 분할 메시** — 표면 경로가 부위를 건널 수 없다 (결정 #35) | 연구 무료, 수정·재배포·상업 금지 | 공개, ~690MB. 주의: NOMO-3D-4K/BODY-fit은 피팅 메시이지 원본 스캔이 아님 |
| HSRD-100 | LOD(5M/1M/100K/10K) 간 일관성 = 실데이터 해상도 강건성; **공개 자료용 유일 허용 데이터** | CC BY 4.0 (상업 가능) | 전체 246GB — 인물 2~3명 × LOD1/2만 선별 |
| CAPE | C3 합성 공장의 재료 — 착의 displacement(SMPL 토폴로지, 정점 대응). 신체는 T-pose로 배포되므로 **betas에서 A-pose로 재생성해 측정** (결정 #34) | 연구 라이선스, 개인·단일 사용자·양도 불가 | 등록 후 다운로드. 피험자별 Option 2만 받는다 — 하단 "Download links"는 POP/SCALE 패킹본이라 메시가 아니다 |
| SMPL (모델) | T-pose 레퍼런스 비교 트랙 + A-pose 강건성 트랙 (Slice 4) | 등록 필요, 재배포 불가 | smpl.is.tue.mpg.de 계정 → `models/smpl/` (gitignored) |

## 치수 정의 대조표 (dataset_agreement 전제 조건)

비교는 정의가 일치 확인된 항목만 수행한다. Texel Part 1 CSV 확인 완료(2026-08-17):
portal_mx CSV는 ISO 8559-1 조항 번호가 붙은 100+ 항목, **cm 단위, 자동 측정값**.

| spec 항목 | Texel ID (ISO 조항) | 정의 일치? | 비고 |
|---|---|---|---|
| waist_circumference | **m102** Minimum Waist Girth (조항 없음) | ✅ (spec=최소 둘레) | m16 Waist Girth(5.3.10, 자연 허리선)는 정의 상이 — Part 1에서 m102보다 평균 +20mm. m16은 aux로 기록 |
| chest_circumference | m5 Bust/Chest Girth (5.3.4) | ✅ (max girth 정의 일치) | Part 1 관측: +32.9/max 78mm (팔 클리핑 근사, 플래그 필수). m44 +21.4, m45 +22.5 — 후보 간 변별력 없음, 정의 기준으로 m5 유지 |
| neck_circumference | m11 Neck Base Girth (5.3.3) | ⚠️ v1 수평 근사 | Part 1 관측: vs m11 +8.8/max 58.9, vs m87 +26.7 — v1은 m11에 더 가까움. ISO 정의는 경사면, v2에서 틸트 |
| across_back_shoulder_width | m1 Across Back Shoulder Width (through the back neck point) (5.4.3) | ✅ 문구까지 동일 | m34 Back Shoulder Width(5.4.2)와 구분 |
| sleeve_length | m55 Back Neck Point to Wrist (5.4.17) | ✅ | m2 Outer Arm Length(5.7.8)와 구분 |
| back_length | m3 Back Neck Point to Waist (5.4.5) | ✅ | m31 …to Waist Level(5.4.13)과 구분 |

추가 사실 (Part 1 검사에서 확인):
- **GT는 자동 측정값** — 일치는 dataset_agreement이지 ISO 적합성이 아님
- **Part 2에는 메시가 아예 없음** (2026-08-17 확인): 42명 × 5회 폴더에 depth 프레임
  (16-bit PNG) + params.json + person.scan.xml만 존재. scan.ply를 얻으려면 RGB-D
  재구성(FreeFusion 상당)을 직접 구현해야 하므로 범위 밖.
  → **"Part 2 = 반복성 프록시" 계획은 메시 기준으로 불성립.** scan_repeatability는
  스캐너 도착 후로 사실상 전부 이연되며, 그 전까지는 numerical_robustness
  (노이즈·decimation·rigid 변환)와 HSRD LOD 일관성이 유일한 대체 근거
- portal_mx와 free_fusion의 GT가 서로 크게 다름 (Man0 waist 102.7 vs 94.7cm — 다른
  세션/장비). 비교는 반드시 **같은 파이프라인의 메시 ↔ 같은 파이프라인의 CSV**
- 메시 규약: portal_mx = mm, Y-up, 바닥 y=0, watertight (Part1/Man0에서 검증).
  free_fusion = m 단위, 축 규약 미검증 → 어댑터가 로드 거부 (추측 금지)
- 진단용 aux: m12 Stature, m43 Waist Height, m16

## NOMO는 분할 메시다 (2026-09-01, 30명 전수)

NOMO 스캔은 하나의 연결된 표면이 아니라 **부위별로 끊어진 표면들**이다.
30명 전수 조사:

| | 성분 수 | 주 성분 비율 | 용접으로 병합된 정점 |
|---|---|---|---|
| NOMO (n=30) | 5~13 (중앙값 8) | 0.491~0.570 (중앙값 **0.538**) | 중앙값 0 |
| Texel (n=10) | 1 | 1.000 | 중앙값 1 |

male_0000의 구성이 전형적이다 — 몸통+머리 54%, 왼다리 15%, 오른다리 15%,
오른팔 8.5%, 왼팔 7.8%, 그리고 발밑 y≈0의 조각 몇 개.

용접(결정 #21)이 아무것도 병합하지 못한다는 점이 중요하다. HSRD의 조각남은
텍스처 차트마다 정점을 복제한 로더 결함이었지만, NOMO는 **진짜로 분리된
표면**이다. 고칠 수 있는 결함이 아니라 데이터셋의 성질이다.

**따라서 부위를 건너는 표면 경로는 NOMO에서 원리상 불가능하다.**
`sleeve_length`(등목점→어깨→손목)는 몸통에서 팔로 건너야 하므로 30명 전원
`waypoint_off_main_surface`로 거부된다 — 손목은 주 성분에서 172~191mm 떨어져
있다. 이것은 파이프라인의 결함이 아니라 정확한 거부다.

몸통 안에 머무는 경로(`across_back_shoulder_width`, `back_length`)는 정상
동작한다. 둘레 측정은 평면 절단이라 연결성을 요구하지 않지만, 열린 루프가
많아 gap closure에 더 자주 의존한다.

## NOMO 첫 접촉 결과 (2026-08-17, male 10명)

- 정의 일치 GT: **NeckBase_Circ**(목밑둘레, spec 일치!) 평균 −1.5mm, **CHEST_Circ** 평균 +18.5mm
- **waist는 TC2에 최소둘레 정의가 없음** (MaxWAIST/TrouserWAIST뿐) → GT 아닌 aux
- **스캔에 구멍 많음**(open_loops_present) → gap-closure 3등급(accept ≤30mm AND ≤5% / manual_review ≤120mm AND ≤20% / reject→null, reject 후 다른 루프 재탐색 금지) 도입. **7/10에서 몸통 단면 선택과 인체 범위 내 측정값 산출을 복구했으며, 정확도는 별도로 검증되지 않았다.** 나머지 3건은 구멍이 커서 reject/저신뢰 — 후속 개선 항목
- OBJ 단위는 피험자별 Head_Top_Height(cm)와 대조해 검증 (추측 아님)

## T-pose 구현 간 비교 결과 (synthetic_agreement, 2026-08-17)

SMPL-Anthropometry(MIT)와 동일 vertex, **동일 랜드마크 높이**에서: 허리 −1.1mm(최대 5.9),
가슴 −0.8mm(최대 18.5) — 측정 프리미티브 사실상 일치. 목 +24.3mm(최대 95)는 레퍼런스가
body-part 면 세그멘테이션으로 목만 자르는 차이. 주의: estimated 랜드마크 경로는 T-pose
입력 계약 밖(팔 수평 → 겨드랑이 휴리스틱 무효) — 랜드마크 높이 주입 방식으로만 비교.

## 다운로드 절차

기록 위치이자 재현 절차. 각 데이터셋을 실제로 받을 때 URL·버전·해시를 여기에 추가한다.

1. **Texel BodyScan** (받음, 2026-08-17): https://github.com/m-krivov/Texel-BodyScan-Dataset
   README의 Yandex Disk 링크 (Part 1: disk.yandex.ru/d/5R57d5509rP7jQ 140MB 7z,
   Part 2: disk.yandex.ru/d/aXTJ1eoJYbJngA 935MB). Yandex 공개 API로 href 획득 후
   다운로드, 7z는 bsdtar(tar -xf)로 해제 → `data/external/texel/PartN/`
   저장소 코드 MIT, 데이터 CC BY-NC 4.0
2. **3DPatBody**: 공개 저장소에서 PLY+CSV/JSON → `data/external/patbody/`
3. **NOMO-3D-400**: 아카이브 → `data/external/nomo/` (재배포 금지 — 사본 이동 금지)
4. **HSRD-100**: 선별 인물의 LOD1(1M)·LOD2(100K)만 → `data/external/hsrd/`
   실측 확인된 규약 (HSR0015-Body-009): **Z-up, 미터, 바닥 z=0**, LOD 디렉터리별 OBJ 1개.
   메타데이터 키는 배포 JSON의 Title Case(`"Upper Body Clothing"`)이며 웹 API의
   snake_case가 아니다. **착의 스캔은 피험자보다 크다** — 부츠·모자가 키를 더하고
   빼는 요소는 없으므로(관측 +56mm) 단위 검증 허용범위는 한쪽으로 열어 둔다
   (`STATURE_TOLERANCE_LOW/HIGH = 0.95/1.20`).
   **정량 근거로는 사용 금지**: 동일인 body-under-clothing 참조가 없어 의류 오프셋을
   계산할 수 없다(`fit_references` 비어 있음). 공개 그림·실패/기권 데모 전용.
5. **SMPL**: 등록 후 neutral 모델 → `models/smpl/` (Slice 4에서만 필요)
