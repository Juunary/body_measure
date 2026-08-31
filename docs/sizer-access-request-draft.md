# SIZER 데이터 접근 요청 — 이메일 초안

## 수신처 — 저장소에 적힌 주소는 죽었다

`gtiwari@mpi-inf.mpg.de`는 **반송된다** (2026-08-31 확인). 저자가 MPI-INF를
떠났기 때문이다: Garvita Tiwari는 Real Virtual Humans 페이지에 `Alumni_PhD`로
표시돼 있고, 그룹 자체가 **튀빙겐 대학**으로 옮겼다. 저장소 README의 주소는
갱신되지 않았다.

| 역할 | 주소 | 비고 |
|---|---|---|
| **To** — 제1저자 | `garvita.tiwari@uni-tuebingen.de` | 현 소속. 다만 졸업생이라 응답 보장 없음 |
| **Cc** — 교신/그룹장 | `gerard.pons-moll@uni-tuebingen.de` | SIZER 시니어 저자이자 그룹장. **가장 안정적** |
| Cc — 행정 | `violaine.le-guily@graphics.uni-tuebingen.de` | 위 둘 모두 무응답일 때만 |

제2저자 Bharat Lal Bhatnagar도 졸업 후 Meta Reality Labs로 옮겼으므로
MPI 주소로 보내지 않는다.

**제1저자가 졸업생이므로 Pons-Moll을 반드시 참조에 넣는다.** 그가 그룹장이자
데이터셋의 시니어 저자이고, 라이선스·산업 맥락 질문(아래 4번)에 답할 권한이
있는 쪽도 그다.

발신: **Waldemar Lang이 발신자이거나 참조** — `weights-permission.md` 규칙.
개인 앞으로 온 회신은 ITA를 구속하지도 보호하지도 않는다.

절차 (`github.com/garvita-tiwari/sizer_dataset`):
1. 저장소에 링크된 Google Form 작성 — **먼저**
2. 위 주소로 비밀번호 요청
3. MPI Nextcloud에서 다운로드

---

## 이 메일이 반드시 받아와야 하는 것

비밀번호만 받고 끝내면 안 된다. LICENSE-G0가 요구하는 것과 결정 #17이
요구하는 것이 함께 걸려 있다:

| 받아올 것 | 왜 |
|---|---|
| **약관 원문** | 저장소 페이지에 라이선스 조항이 없고 인용 요구만 있다. LICENSE-G0 항목 1은 원문 verbatim 확보를 요구한다 (`sizer-terms.txt` + `provenance.md` 해시) |
| **최소 착의 스캔의 1:1 대응 여부** | 결정 #17 — 대응이 확인되지 않으면 claim 문구가 `provided body-reference surface`로 강등된다 |
| **원본 스캔 vs registration 구분** | 같은 이유. SMPL/SMPL+D/SMPL+G registration은 원본 스캔이 아니다 |
| **상업적 경로** | `scope.md` — 산업 파트너가 있는 프로젝트는 "비상업"을 무조건 체크할 수 없다. 누락에 의한 허가는 필요한 순간에 무효가 된다 |

---

Subject: SIZER dataset access request — RWTH Aachen ITA

Dear Dr. Tiwari, dear Prof. Pons-Moll,

I am writing from the Institut für Textiltechnik (ITA) at RWTH Aachen
University, where we are developing a body-measurement pipeline for
made-to-measure garments as part of a Digital Product Passport project. We
have completed the access form on the SIZER GitHub page and would like to
request the download password.

(The address given on the repository page, gtiwari@mpi-inf.mpg.de, no
longer accepts mail — you may want to update the README. I am writing to
the Tübingen addresses instead.)

Our intended use is non-commercial research: estimating body dimensions
from 3D scans of dressed subjects, for which SIZER's paired clothed and
minimally-clothed scans are the reference we need.

Before we download, could I ask four questions so that we describe the data
correctly in our own reporting?

1. **Licence terms.** The repository page states the citation requirement
   but does not link licence conditions. Could you point us to the terms
   text that applies to the dataset, or send it? We keep a verbatim copy of
   every dataset licence on file before any data is used.

2. **Body reference pairing.** Does every clothed scan have a corresponding
   minimally-clothed scan of the same subject? Our pipeline reports a
   weaker claim when the body reference is a registration rather than an
   independent scan, so this distinction changes what we are allowed to
   state about our results.

3. **Raw scans versus registrations.** The page lists raw scans alongside
   SMPL, SMPL+D and SMPL+G registrations. Are the raw scans available for
   all subjects, or for a subset?

4. **Industry context.** Our project runs at a university institute with
   industry partners, and results may inform a future commercial product.
   No SIZER data or derivative would be redistributed, and no model trained
   on it would be published or shared without your prior written
   permission. We would rather state this now than discover later that our
   use was outside the intended scope. If a different arrangement is needed
   for that context, we would be grateful to know whom to contact.

Thank you very much for making the dataset available.

Best regards,
Junewoo Kang
Institut für Textiltechnik (ITA), RWTH Aachen University

---

## 회신 도착 후 (자동으로 이어지는 작업)

1. 회신 **원문**을 `docs/licenses/sizer-terms.txt`에 붙여넣고
   `provenance.md`에 SHA-256 기록 → LICENSE-G0 항목 1 ☑
2. `data/external/sizer/`로 다운로드 (gitignored)
3. `scripts/audit_sizer_manifest.py --root data/external/sizer` 실행 —
   **어댑터를 쓰기 전에**. 출력 `reports/sizer-manifest.json`이
   `raw_minimal_scan` 존재 여부로 C1의 claim 문구를 정한다 (결정 #17)
4. subject-disjoint split을 감사 단계에서 잠그고
   `reports/split-manifest.json`에 해시 (결정 #18)
