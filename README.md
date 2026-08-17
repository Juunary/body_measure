# body-measure

3D 신체 메시에서 셔츠 치수 6종을 추출하는 측정 파이프라인.
Maß-DPP 프로젝트의 3D 바디스캐너 도착 전 선행 개발 — 입력은 어댑터로 추상화되어
있어 장비 도착 시 어댑터만 추가하면 된다.

**검증 범위의 경계선:** 스캐너 도착 전에는 측정 파이프라인의 구현 정확성·재현
가능성·강건성을 검증하고, 장비 도착 후 실제 계측 정확도와 반복성을 검증한다.
어떤 수치도 ISO 20685-1 적합성 주장으로 읽혀서는 안 된다 (docs/decisions.md #1).

## 측정 항목

[measurement-spec.v1.yaml](measurement-spec.v1.yaml)이 계약이다 — 이름이 아니라
정의(ISO 8559-1 기반), 경유점, 자세, 알려진 편차까지 고정한다:
chest / waist / neck circumference, across-back shoulder width,
sleeve length, back length.

## 설치 (Windows)

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest tests -q   # 데이터셋 없이 green이어야 정상
```

SMPL 트랙(Slice 4)만 `requirements-smpl.txt`(torch CPU)가 추가로 필요하다.
측정 코어는 torch를 import하지 않는다.

## 사용

```powershell
# 단위는 절대 추측하지 않는다 — 명시 필수
.venv\Scripts\python -m body_measure measure body.ply --input-unit m --up-axis Z --waist-height 800 --out result.json
```

결과 JSON은 spec의 6개 키를 정확히 포함하며, 미구현/실패 항목은 숫자 대신
null + quality 플래그로 보고된다. 둘레는 `raw_contour_mm`(교차 폴리라인)과
`taut_tape_hull_mm`(convex hull, hull ≤ raw)을 모두 담는다.

## 구조

- `body_measure/adapters/` — 입력 정규화 (`NormalizedBodySurface`), 단위 강제,
  데이터셋별 ground-truth 계약 (`provides` frozenset)
- `body_measure/measure/` — 평면 슬라이싱, 몸통 루프 선택, 둘레/표면 경로
- `body_measure/landmarks/` — fitted-vertex 경로 vs 추정(topology-agnostic) 경로
- `body_measure/validate/` — 카테고리 구분 검증 하네스 (Slice 5)
- `docs/decisions.md` — 결정 기록 / `docs/datasets.md` — 데이터셋·라이선스

## 데이터

`data/external/`과 `models/`는 통째로 gitignore — 어떤 데이터셋 파일도 커밋하지
않는다. 공개 자료(보고서·포트폴리오)에는 CC BY인 HSRD-100만 사용한다.
상세는 [docs/datasets.md](docs/datasets.md).
