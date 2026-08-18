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
| waist_circumference | 최소 몸통 둘레 수평 슬라이스 / standing / 표면 둘레 | (조항 없음) | m102 "Minimum Waist Girth" | 없음 (Max/Trouser만) | **exact** | 명칭·정의 동일. m16(5.3.10 자연 허리선)은 정의 상이 → aux |
| chest_circumference | 최대 가슴 높이 수평 둘레 / standing / 팔 병합 시 클리핑 | 5.3.4 | m5 "Bust/Chest Girth" | CHEST_Circ | **approximate** | ISO는 bust point 높이 기준, 우리는 최대 둘레 탐색 — 높이 결정 방식 상이. 클리핑은 구현 근사(별도 플래그) |
| neck_circumference | 어깨 위 최소 둘레 **수평** 슬라이스 | 5.3.3 | m11 "Neck Base Girth" | NeckBase_Circ | **approximate** | ISO 목밑둘레는 경사면(경추점 경유), v1은 수평 근사 |
| across_back_shoulder_width | 좌견봉→등목점→우견봉 표면 경로 | 5.4.3 | m1 "Across Back Shoulder Width (through the back neck point)" | Across_Back(?) | **exact** (Texel) / unverified (NOMO) | 정의 문구 일치. 견봉을 '겨드랑이 기둥 최고점'으로 놓는 것은 구현 근사(플래그) |
| sleeve_length | 등목점→어깨점→손목 표면 경로 / **팔 내림·팔꿈치 경유 생략** | 5.4.17 | m55 "Back Neck Point to Wrist (L/R)" | 없음 | **approximate — 성능 판정 보류** | 시작·종료 일치. ISO/참조는 팔꿈치 굽힘 자세 + 팔꿈치 경유 추정 — 자세·경로 편차 미정량. 구간 분해 감사(하단) 전까지 '사용 불가' 판정 유보 |
| back_length | 등목점→허리 높이, 등 표면 경로 | 5.4.5 | m3 "Back Neck Point to Waist" | 없음 | **approximate** | 시작·종료 일치. 참조의 경로(척주 추종 vs 지오데식) 미확인 |

## 소매길이 구간 분해용 매핑

| 구간 | 후보 참조 | ISO 조항 | 판정 | 근거 |
|---|---|---|---|---|
| back_neck → shoulder | m36 "Shoulder Length" | 5.4.1 | **mismatch — delta 계산 금지** | Shoulder Length는 통상 **side neck point**→shoulder point. 우리 구간은 back neck point 기점 — 기점 상이 |
| shoulder → wrist | m2 "Outer Arm Length" | 5.7.8 | **approximate** | 종점·경유(견봉→손목) 유사하나 ISO는 팔꿈치 굽힘 자세. 참고 비교만 |
| 전체 (back_neck→shoulder→wrist) | m55 | 5.4.17 | approximate | 위와 동일 사유 |

## 헤드라인 편입 규칙 적용 결과

- **헤드라인(accepted + exact)**: waist_circumference(m102), across_back_shoulder_width(m1, Texel)
- **참고 비교(approximate)**: chest(m5), neck(m11/NeckBase_Circ), back_length(m3), sleeve(m55), shoulder→wrist(m2)
- **비교 금지(mismatch)**: back_neck→shoulder ↔ m36
- **unverified**: NOMO Across_Back, NOMO CHEST_Circ의 세부 정의 (벤더 문서 확보 시 갱신)

## 갱신 이력

- 2026-08-17 최초 작성 (ISO 원문 미대조 상태의 명칭 기반 판정)
