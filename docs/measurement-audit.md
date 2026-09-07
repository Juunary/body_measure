# Measurement Definition Audit

목적: 내부 spec ↔ 데이터셋 참조값의 정의 매핑을 판정하고, **exact만 헤드라인
통계에 편입**한다. approximate는 편차 주석과 함께 참고 비교, mismatch는 수치 비교
금지, unverified는 판정 보류.

판정 근거: Texel CSV의 측정 명칭 + ISO 8559-1 조항 번호 표기. **ISO 8559-1 원문
대조는 미완료**(ITA 도서관 태스크) — 원문 확인 전 판정은 명칭·통칭 정의 기반이며,
원문 확인 시 갱신한다. NOMO TC2 명칭은 벤더 문서 미확보로 대부분 unverified.

## 본 측정 6종

| 내부 키 | 내부 정의 (시작·경유·종료 / 자세 / 방식) | ISO 조항 | Texel ID | NOMO | 판정 | 비고 |
|---|---|---|---|---|---|---|
| waist_circumference | **자연 허리 둘레** — 둘레 최소점과 요추 오목점의 중간 높이에서 수평 슬라이스 / standing / 표면 둘레 (spec v7, 결정 #47) | **5.3.10 Waist girth** | **m16 "Waist Girth"** (m102 "Minimum Waist Girth" 는 v1 정의의 참조로 aux 에 유지) | 없음 (Max/Trouser만) | **approximate** | **2026-09-07 재판정 (결정 #53).** v1 은 `exact` 였고 옳았다 — 그때 우리 정의는 "최소 몸통 둘레"였고 m102 는 "Minimum Waist Girth", 같은 단어였다. v7 이 정의를 자연 허리로 바꾸고 참조를 m16 으로 옮겼는데 판정만 남아 있었다. 지금은 문구 동일성이 없다: 우리는 늑골·장골능이 아니라 **둘레 최소점과 등 오목점**으로 띠를 잡고(스펙 known_deviations 에 선언됨), ISO 5.3.10 원문도 Texel 의 m16 배치 방법도 읽지 않았다. 편차: 평균 −12.2 / sd 17.6 / 최악 −49.8 mm (n=10), 허리 높이는 m43 대비 평균 +13.1 mm |
| chest_circumference | 최대 가슴 높이 수평 둘레 / standing / 팔 병합 시 클리핑 | **5.3.4 또는 5.3.6 — 미해결** | m5 "Bust/Chest Girth" | CHEST_Circ | **approximate** | ISO는 bust point 높이 기준, 우리는 최대 둘레 탐색 — 높이 결정 방식 상이. 클리핑은 구현 근사(별도 플래그). **2026-09-07: 목차 확인 결과 ISO는 가슴 둘레를 네 항목으로 나눈다 — 5.3.4 Bust girth, 5.3.5 Bust girth contoured, **5.3.6 Chest girth (at axilla)**, 5.3.7 Upper chest girth. 이 표는 5.3.4만 보고 판정했는데 5.3.6은 겨드랑이 높이에 고정된 둘레라 "높이 결정 방식 상이"라는 근거가 5.3.6에는 다르게 적용된다. 어느 쪽이 우리 정의에 대응하는지 원문 없이는 못 정한다 (결정 #52)** |
| neck_circumference | 어깨 위 최소 둘레 **수평** 슬라이스 | 5.3.3 | m11 "Neck Base Girth" | NeckBase_Circ | **approximate** | ISO 목밑둘레는 경사면(경추점 경유), v1은 수평 근사 |
| across_back_shoulder_width | 좌견봉→등목점→우견봉 표면 경로 | 5.4.3 | m1 "Across Back Shoulder Width (through the back neck point)" | Across_Back(?) | **exact** (Texel) / unverified (NOMO) | 정의 문구 일치. 견봉을 '겨드랑이 기둥 최고점'으로 놓는 것은 구현 근사(플래그) |
| upper_arm_girth (v3 신규) | 위팔 최대 둘레 수평 슬라이스, 오른팔 | 5.3.16 | m15_r "Upper Arm Girth (R)" | Bicep_Circ | **approximate** (양쪽) | 1단계 반팔 확정으로 추가. ISO가 '최대'인지 특정 높이인지 원문 미확인; TC2 Bicep_Circ 정의도 미확보. 첫 결과: Texel bias −3.3 / MAE 11.3 / max 20.9, NOMO bias −5.5 / MAE 19.0 (max 93.1은 구멍 많은 male_0007) |
| sleeve_length | 등목점→어깨점→손목 표면 경로 / **팔 내림·팔꿈치 경유 생략** | 5.4.17 | m55 "Back Neck Point to Wrist (L/R)" | 없음 | **approximate — 성능 판정 보류** | 시작·종료 일치. ISO/참조는 팔꿈치 굽힘 자세 + 팔꿈치 경유 추정 — 자세·경로 편차 미정량. 구간 분해 감사(하단) 전까지 '사용 불가' 판정 유보 |
| back_length | 등목점→허리 높이, **시상면 절단** (결정 #48) | **5.4.5 또는 5.4.13 — 미해결** | m3 "Back Neck Point to Waist" | 없음 | **approximate** | 시작·종료 일치. 경로 질문에 첫 증거: 지오데식(엣지 그래프) → 척주 추종(시상면)으로 바꾸자 bias +17.6 → −2.7 mm, max 55.9 → 37.3 (Texel n=10). 참조가 척주를 따른다는 쪽을 지지하나, 원문 미확인이라 approximate 유지. **2026-09-07: ISO는 5.4.5 "Back neck point to waist"와 5.4.13 "Back neck point to waist level"을 별도 항목으로 둔다. 우리 구현은 waist level 까지 내려가므로 5.4.13 일 수 있다 (결정 #52)** |

## 소매길이 구간 분해용 매핑

| 구간 | 후보 참조 | ISO 조항 | 판정 | 근거 |
|---|---|---|---|---|
| back_neck → shoulder | m36 "Shoulder Length" | 5.4.1 | **mismatch — delta 계산 금지** | Shoulder Length는 통상 **side neck point**→shoulder point. 우리 구간은 back neck point 기점 — 기점 상이 |
| shoulder → wrist | m2 "Outer Arm Length" | 5.7.8 | **approximate** | 종점·경유(견봉→손목) 유사하나 ISO는 팔꿈치 굽힘 자세. 참고 비교만 |
| 전체 (back_neck→shoulder→wrist) | m55 | 5.4.17 | approximate | 위와 동일 사유 |

## 헤드라인 편입 규칙 적용 결과

- **헤드라인(accepted + exact)**: across_back_shoulder_width(m1, Texel) — **한 종뿐이다.**
  waist_circumference 는 2026-09-07 에 approximate 로 내려갔다 (결정 #53). 헤드라인이 한 줄이라는 것은
  이 파이프라인이 "같은 정의끼리 비교했다"고 말할 수 있는 측정이 하나라는 뜻이고, 줄이는 쪽이 정확하다.
  across_back 은 오히려 근거가 강해졌다 — ISO 프리뷰 목차가 5.4.3 의 제목을
  "Across back shoulder width (through the back neck point)" 로 확인해줬고, 이는 Texel m1 의 명칭과
  글자 그대로 같다 (결정 #52).
- **참고 비교(approximate)**: **waist(m16)**, chest(m5), neck(m11/NeckBase_Circ), back_length(m3), sleeve(m55), shoulder→wrist(m2)
- **비교 금지(mismatch)**: back_neck→shoulder ↔ m36
- **unverified**: NOMO Across_Back, NOMO CHEST_Circ의 세부 정의 (벤더 문서 확보 시 갱신)

## ISO 8559-1:2017 조항 지도 (2026-09-07)

출처: ISO 가 배포하는 **공식 무료 프리뷰 15쪽** (표지·저작권·전체 목차·Scope·
3.1.1~3.1.13). 원문 전체가 아니므로 **조항 번호와 제목만** 확인된 것이고,
5장 측정 정의 본문은 여전히 미확보다 — `definition_verified` 는 전부 false 로
남는다. 조항 번호는 "표준에 이 이름의 항목이 있다"는 사실이지 그 항목이
무엇인지가 아니다 (결정 #52).

| 우리 키 | ISO 조항 | 상태 |
|---|---|---|
| chest_circumference | 5.3.4 Bust girth / **5.3.6 Chest girth (at axilla)** | 후보 둘, 미해결 |
| waist_circumference | 5.3.10 Waist girth | 확정 |
| neck_circumference | 5.3.3 Neck base girth | 확정 |
| upper_arm_girth | 5.3.16 Upper-arm girth | 확정 |
| across_back_shoulder_width | 5.4.3 Across back shoulder width (through the back neck point) | 확정 — Texel m1 문구와 동일 |
| back_length | 5.4.5 Back neck point to waist / **5.4.13 Back neck point to waist level** | 후보 둘, 미해결 |
| sleeve_length | 5.4.17 Back neck point to wrist length | 확정 |
| hip_girth (proto) | 5.3.13 Hip girth / 5.3.14 Maximum hip girth (seat measure girth) | 5.3.14 로 추정 — 결정 #47 이 둔부 최대점을 쓰므로 |
| armhole_depth (proto) | 5.4.6 Scye depth length | 확정 |
| shoulder_slope (proto) | 5.6.2 Shoulder slope | 확정 |
| front_back_width (proto) | 5.2.4 Armscye front to back width | 추정, 미확인 |
| sleeve_opening_girth (proto) | **없음** | 설계 파라미터 — 표준은 몸을 재지 옷을 재지 않는다 |
| centre_front_length (미구현) | 5.4.8 Front neck point to waist | 확정 |
| armhole_girth (미구현) | 5.3.15 Armscye girth | 확정 |
| across_front (미구현) | 5.4.7 Across front width | 확정 |

**미구현 3종의 `unsourced` 판정은 철회한다.** "제조사 POM 시트만 이름을 부르고
그건 완제품 치수라 몸 치수의 근거가 못 된다"는 이유였는데, ISO 8559-1 이 셋 다
몸 치수로 정의하고 있다. 결정 #30 이 기다리던 M. Müller & Sohn / Aldrich 대조도
필요 없었다.

### 랜드마크 정의 (프리뷰에서 원문 확보, 3.1.1~3.1.13)

| ISO | 정의 (원문 요지) | 우리 구현 |
|---|---|---|
| 3.1.1 shoulder point | acromial process 의 **최외측점**을 피부로 수직 투영. ISO 7250-1 의 acromion 과 동일 | `estimate_shoulder_points` 는 겨드랑이 주름으로 높이를 고정하고 **최고점**을 찾는다 — **다른 극값** (결정 #52) |
| 3.1.6 back neck point | 제7경추 극돌기, **정중시상면**에서 후방으로 피부에 투영. ISO 7250-1 의 cervicale 과 동일 | 결정 #48 이 정중면 교차점으로 바꾼 것과 **일치**. 그 전(루프 최후방점)은 정의상 틀렸다 |
| 3.1.7 side neck point | neck base line 과 승모근 전연의 교차점 | 없음 — m36 mismatch 의 원인 |
| 3.1.8 front neck point | 좌우 쇄골 내측상연을 잇는 선과 전정중선의 교차점 | 없음 — `centre_front_length` 의 시작점 |
| 3.1.10 elbow point | 척골 주두의 최돌출점 | 없음 — `sleeve_length` 가 생략한 경유점 |
| 3.1.11 bust point | 브라 착용 상태에서 가슴의 **최전방점** | `estimate_bust_level` 이 토르소 최대 깊이를 쓰는 것과 방향 일치 |
| 3.1.12 centre chest point | 제3·4 흉골절 접합부, 정중시상면. mesosternale 과 동일 | 없음 |
| 3.1.13 armpit front fold point | 겨드랑이 앞주름점, 자를 겨드랑이에 대어 결정 | `armpit_level` 은 슬라이스 분리 높이 — 다른 방법 |

프리뷰는 3.1.13 에서 잘린다. 3.1.14 이후, 3.2 (선·평면), 5장 전체, Annex B
(자세), Annex C (랜드마크↔측정 매핑표)는 미확보.

## 갱신 이력

- 2026-09-07 waist_circumference 를 exact → approximate 로 재판정 (결정 #53). 헤드라인은
  across_back_shoulder_width 한 종만 남는다
- 2026-09-07 ISO 8559-1:2017 공식 프리뷰로 조항 지도를 작성 (결정 #52). 미구현
  3종의 `unsourced` 철회, 프로토타입 4종에 조항 부여, chest 와 back_length 는
  후보 조항이 둘씩이라 미해결로 표시. `back_neck_point` 는 ISO 정의와 일치가
  확인되고 `shoulder_point` 는 극값의 종류가 다름이 드러났다. waist 행이 코드와
  반대인 것도 여기서 발견 — 표시만 하고 판정은 두었다
- 2026-09-07 back_length 경로를 시상면 절단으로 (결정 #48). 스펙의 `no_reference: true`
  가 이 표와 모순되어 있었고 — 결정 #32 가 across_back_shoulder_width 에서 찾은 것과
  같은 종류의 낡은 플래그 — audit 우선 규칙대로 `false` 로 정정
- 2026-08-17 최초 작성 (ISO 원문 미대조 상태의 명칭 기반 판정)
