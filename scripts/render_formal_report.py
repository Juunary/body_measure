"""Render the formal reports (ko + en) from reports/validation-results.json.
Both languages come from the SAME structured data — never hand-edit the
outputs, regenerate them.

Run:  .venv\\Scripts\\python scripts\\render_formal_report.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS = PROJECT_ROOT / "reports" / "validation-results.json"

VERDICTS = {
    "waist_circumference": {
        "ko": "기준선 확보 — 현재 6종 중 참조값 대비 가장 낮은 MAE. 실사용 허용오차 미합의로 제작 적용 판정은 보류",
        "en": "baseline established — lowest MAE against references among the six; production verdict deferred until tolerances are agreed",
    },
    "chest_circumference": {
        "ko": "연구 단계 — 팔 클리핑 근사 의존, approximate 매핑",
        "en": "research stage — depends on the arm-clip approximation; approximate mapping",
    },
    "neck_circumference": {
        "ko": "연구 단계 — 수평 v1 근사, 일부 큰 편차 원인 분석 필요",
        "en": "research stage — horizontal v1 approximation; large outliers need analysis",
    },
    "across_back_shoulder_width": {
        "ko": "정의 매핑 exact — accepted 산출률 50%, 편차 및 방향 신뢰도 개선 필요",
        "en": "definition mapping exact — accepted coverage 50%; deviation and orientation confidence need improvement",
    },
    "sleeve_length": {
        "ko": "정의 불일치 가능성으로 성능 판정 보류 — 편차는 shoulder→wrist 구간에 국소화됨",
        "en": "performance verdict deferred (possible definition mismatch) — the offset localizes in the shoulder→wrist segment",
    },
    "back_length": {
        "ko": "연구 단계 — 경로·방향 추정 개선 필요",
        "en": "research stage — path and orientation estimation need refinement",
    },
}


def fmt(v, digits=1):
    if v is None:
        return "—"
    return f"{v:+.{digits}f}" if isinstance(v, float) else str(v)


def measurement_table(measures: dict, lang: str, only_mapping=None, exclude_mapping=None):
    header = {
        "ko": "| 측정 | 매핑 | N 전체/산출/accepted/review/reject | N 통계 | Bias | MAE | Median AE | SD | Max AE |",
        "en": "| Measurement | Mapping | N total/computed/accepted/review/rejected | N stats | Bias | MAE | Median AE | SD | Max AE |",
    }[lang]
    lines = [header, "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, m in measures.items():
        if only_mapping and m["mapping"] not in only_mapping:
            continue
        if exclude_mapping and m["mapping"] in exclude_mapping:
            continue
        s = m["summary"]

        def plain(v):
            return "—" if v is None else f"{v:.1f}"

        lines.append(
            f"| {name} | {m['mapping']} | "
            f"{s['n_total']}/{s['n_computed']}/{s['n_accepted']}/{s['n_manual_review']}/{s['n_rejected']} | "
            f"{s['n_accepted']} | "
            f"{fmt(s['bias'])} | {plain(s['mae'])} | {plain(s['median_ae'])} | "
            f"{plain(s['sample_sd'])} | {plain(s['max_ae'])} |"
        )
    return "\n".join(lines) if len(lines) > 2 else ""


POPULATION_NOTE = {
    "ko": ("Bias, MAE, Median AE, SD 및 Max AE는 `accepted` 표본만을 대상으로 계산하였다"
           " (`N 통계` 열). `manual_review`와 `reject` 표본은 헤드라인 통계에서 제외하였다."
           " SD는 signed delta의 표본표준편차(`ddof=1`)이다. 소매 구간 감사의 N=9 통계는"
           " 산출 가능한 `accepted + manual_review` 전체를 사용했으므로 헤드라인 결과와"
           " 모집단이 다르다."),
    "en": ("Bias, MAE, Median AE, SD, and Max AE are computed over the `accepted` sample"
           " only (column `N stats`); `manual_review` and `reject` samples are excluded"
           " from headline statistics. SD is the sample standard deviation of the signed"
           " deltas (`ddof=1`). The sleeve segment audit's N=9 statistics use all"
           " computable `accepted + manual_review` values and therefore describe a"
           " different population than the headline results."),
}


def bucket_table(measures: dict, lang: str):
    title = {"ko": "| 측정 | bucket 분포 |", "en": "| Measurement | bucket distribution |"}[lang]
    lines = [title, "|---|---|"]
    for name, m in measures.items():
        buckets = ", ".join(f"{k}: {v}" for k, v in m["summary"]["buckets"].items())
        lines.append(f"| {name} | {buckets} |")
    return "\n".join(lines)


def sleeve_audit_block(audit: dict, lang: str):
    rows = audit["rows"]
    sw = [r["shoulder_to_wrist_minus_m2"] for r in rows if r["shoulder_to_wrist_minus_m2"] is not None]
    cb = [r["combined_minus_m55"] for r in rows if r["combined_minus_m55"] is not None]
    sw_mean = statistics.mean(sw) if sw else None
    cb_mean = statistics.mean(cb) if cb else None
    head = {
        "ko": ("소매길이 구간 감사 (n=%d): back_neck→shoulder ↔ m36은 **mismatch**"
               "(m36 기점은 side neck point)로 수치 비교 제외. shoulder→wrist ↔ m2"
               "(approximate, 자세 상이) 평균 %s mm, 전체 ↔ m55(approximate) 평균 %s mm"
               " — **과대 편차는 shoulder→wrist 구간에 국소화**되어 있으며, edge-graph"
               " 근사·손목점 배치·자세 편차가 후보 원인이다."),
        "en": ("Sleeve segment audit (n=%d): back_neck→shoulder ↔ m36 is a **mismatch**"
               " (m36 originates at the side neck point) and is excluded from numeric"
               " comparison. shoulder→wrist ↔ m2 (approximate; posture differs) mean %s mm,"
               " combined ↔ m55 (approximate) mean %s mm — **the overshoot localizes in"
               " the shoulder→wrist segment**; edge-graph inflation, wrist-point placement,"
               " and the posture deviation are the candidate causes."),
    }[lang]
    return head % (len(rows), fmt(sw_mean), fmt(cb_mean))


def render(lang: str, data: dict) -> str:
    p = data["provenance"]
    texel = data["categories"]["dataset_agreement"]["texel"]
    nomo = data["categories"]["dataset_agreement"]["nomo"]
    yaw = data["categories"]["numerical_robustness"]["yaw_sweep"]
    tpose = data["categories"]["synthetic_agreement"]

    T = {
        "ko": {
            "title": "# body-measure 검증 결과 공식 보고서",
            "scope": data["scope_statement"]["ko"],
            "cats": ("작동 중인 선행 검증 4종: analytic_correctness, synthetic_agreement, "
                     "numerical_robustness, dataset_agreement. scan_repeatability와 "
                     "measurement_accuracy는 스캐너 도착 후의 후속 단계이다."),
            "ref_note": ("모든 데이터셋 수치는 **dataset reference**(데이터셋 자체 자동 측정값) "
                         "대비 **일치도(agreement)**이며, 수동 측정 정답 대비 정확도가 아니다. "
                         "Texel 참조값은 BodyFit 자동 측정, NOMO 참조값은 TC2 자동 측정이다."),
            "headline": "## 헤드라인 결과 — accepted + exact 매핑만",
            "secondary": "## 참고 비교 — approximate 매핑 (정의 편차 있음, 성능 판정에 사용 금지)",
            "buckets": "## Quality bucket 분포 (상호 배타, 그룹 N 합 = 전체 N)",
            "verdicts": "## 측정별 현재 판정",
            "robust": "## numerical_robustness (발췌)",
            "yaw": ("시험한 yaw 각도 {angles}°에서 둘레 3종의 최대 |Δ| ≤ {maxd:.1e} mm "
                    "(수치 정밀도 수준). 알려진 한계: 실스캔 1 mm 노이즈에서 겨드랑이 의존 "
                    "측정(가슴·어깨) 불안정, 시험하지 않은 자세(비대칭 팔, 편측 결손)는 미검증."),
            "tpose": "## synthetic_agreement — 동일 랜드마크 높이의 구현 간 비교",
            "gap": ("스캔 구멍 처리: 몸통 후보를 먼저 식별한 뒤 3등급(accept ≤30 mm AND ≤5% / "
                    "manual_review ≤120 mm AND ≤20% / reject)으로 판정하며, reject 시 다른 "
                    "루프를 재탐색하지 않고 null을 반환한다. NOMO에서는 7/10 피험자에서 몸통 "
                    "단면 선택과 인체 범위 내 측정값 산출을 복구했으며, 정확도는 별도로 "
                    "검증되지 않았다."),
            "orient": ("전후 방향은 toe_projection으로 추정하며 front_back_confidence를 "
                       "보고한다. 발 스캔이 없으면 orientation_unknown으로 등목점 의존 측정 "
                       "3종을 null 처리하고, 저신뢰면 manual_review로 강등한다."),
            "inst": ("## 기관 확인 필요 사항\n\n"
                     "- Texel BodyScan은 CC BY-NC 4.0 — ColorDigital이 참여하는 산업 프로젝트 "
                     "문맥에서의 사용 범위를 기관에 확인 필요. 현재는 로컬 연구 검증 전용, 배포 금지.\n"
                     "- NOMO-3D-400은 과학 연구 전용, 수정·재배포·독점 프로그램 포함 금지 — "
                     "코드·배포 패키지에 포함 불가.\n"
                     "- ISO 20685-1 원문 대조(ITA 도서관), 치수별 실제 제작 허용오차 합의(ITA 의류 전문가)."),
            "dpp": ("## DPP 연동 경계\n\n신체 치수와 원본 스캔은 DPP 공개 데이터가 아니라 내부 "
                    "개인정보 영역이다. dpp-prototype의 설계 원칙(신체 치수는 패스포트 필드가 "
                    "아님, INTERNAL_PRIVATE 계층)과 동일한 경계를 이 파이프라인의 산출물에도 "
                    "적용한다 — 패스포트로 전달되는 것은 완성 의류 치수와 불투명한 fit 참조뿐이다."),
            "prov": "## 실행 정보",
        },
        "en": {
            "title": "# body-measure Validation Results — Formal Report",
            "scope": data["scope_statement"]["en"],
            "cats": ("Four pre-arrival validation categories are operational: "
                     "analytic_correctness, synthetic_agreement, numerical_robustness, "
                     "dataset_agreement. scan_repeatability and measurement_accuracy are "
                     "post-scanner phases."),
            "ref_note": ("All dataset numbers are **agreement against dataset references** "
                         "(the datasets' own automatic values), not accuracy against manual "
                         "measurements. Texel references come from the BodyFit pipeline, "
                         "NOMO references from TC2."),
            "headline": "## Headline results — accepted values with exact mappings only",
            "secondary": "## Reference comparisons — approximate mappings (definition deviations; not for performance verdicts)",
            "buckets": "## Quality bucket distribution (mutually exclusive; group Ns sum to total)",
            "verdicts": "## Current verdict per measurement",
            "robust": "## numerical_robustness (excerpt)",
            "yaw": ("Across tested yaw angles {angles}°, the maximum |Δ| of the three "
                    "circumferences was ≤ {maxd:.1e} mm (numerical precision level). Known "
                    "limitations: armpit-dependent measurements (chest/shoulder) are unstable "
                    "under 1 mm noise on real scans; untested poses (asymmetric arms, "
                    "missing limbs) are unvalidated."),
            "tpose": "## synthetic_agreement — cross-implementation at identical landmark heights",
            "gap": ("Scan-hole handling: the torso candidate is identified first, then tiered "
                    "(accept ≤30 mm AND ≤5% / manual_review ≤120 mm AND ≤20% / reject); a "
                    "reject returns null and never re-shops among other loops. On NOMO this "
                    "restored torso-section selection and human-range values for 7/10 "
                    "subjects; accuracy is not separately validated."),
            "orient": ("Front/back orientation is estimated by toe_projection with a reported "
                       "front_back_confidence. Missing feet set orientation_unknown and null "
                       "the three back-neck-dependent measurements; low confidence demotes "
                       "them to manual_review."),
            "inst": ("## Items requiring institutional confirmation\n\n"
                     "- Texel BodyScan is CC BY-NC 4.0 — usage scope within an industry "
                     "project involving ColorDigital must be confirmed. Currently local "
                     "research validation only; no distribution.\n"
                     "- NOMO-3D-400 is research-only; no modification, redistribution, or "
                     "inclusion in proprietary software — must not ship with code or packages.\n"
                     "- ISO 20685-1 text check (ITA library); per-measurement production "
                     "tolerances to be agreed with ITA garment experts."),
            "dpp": ("## DPP integration boundary\n\nBody measurements and raw scans are NOT "
                    "public DPP data; they live in the internal personal-data domain. The "
                    "same boundary as dpp-prototype's design (body measurements are not "
                    "passport fields; INTERNAL_PRIVATE tier) applies to this pipeline's "
                    "outputs — only finished-garment dimensions and an opaque fit reference "
                    "ever reach a passport."),
            "prov": "## Run information",
        },
    }[lang]

    parts = [T["title"], "", T["scope"], "", T["cats"], "", T["ref_note"], ""]

    if texel:
        parts += [T["headline"], "",
                  f"**Texel — {texel['label']}**", "",
                  measurement_table(texel["measurements"], lang, only_mapping={"exact"}), "",
                  T["secondary"], "",
                  measurement_table(texel["measurements"], lang, exclude_mapping={"exact"}), ""]
        if nomo:
            parts += [f"**NOMO — {nomo['label']}**", "",
                      measurement_table(nomo["measurements"], lang, exclude_mapping=set()), ""]
        parts += [POPULATION_NOTE[lang], "",
                  T["buckets"], "", bucket_table(texel["measurements"], lang), "",
                  sleeve_audit_block(texel["sleeve_segment_audit"], lang), ""]

    parts += [T["verdicts"], "",
              {"ko": "| 측정 | 판정 |", "en": "| Measurement | Verdict |"}[lang], "|---|---|"]
    for name, verdict in VERDICTS.items():
        parts.append(f"| {name} | {verdict[lang]} |")
    parts.append("")

    if yaw:
        parts += [T["robust"], "",
                  T["yaw"].format(angles=yaw["angles_deg"],
                                  maxd=max(yaw["max_abs_delta_mm"].values())), ""]
    parts += [T["gap"], "", T["orient"], ""]

    if tpose.get("available"):
        rows = [{"ko": "| 측정 | Bias (mm) | Max AE (mm) | N |",
                 "en": "| Measurement | Bias (mm) | Max AE (mm) | N |"}[lang],
                "|---|---:|---:|---:|"]
        for name, s in tpose["summaries"].items():
            rows.append(f"| {name} | {s['bias']:+.1f} | {s['max_ae']:.1f} | {s['n']} |")
        parts += [T["tpose"], "", "\n".join(rows), ""]

    parts += [T["inst"], "", T["dpp"], "", T["prov"], ""]
    tree = {"ko": "clean", "en": "clean"}[lang] if not p["git_dirty"] else "DIRTY"
    parts += [
        f"- generated (UTC): {p['generated_utc']}",
        f"- git commit: {p['git_commit']} — working tree: {tree}",
        f"- platform: {p.get('platform', '—')}",
        f"- python {p['python']}; " + ", ".join(f"{k} {v}" for k, v in p["packages"].items()),
        f"- spec_version {p['spec_version']}; spec SHA-256: {p['spec_sha256']}",
        f"- thresholds SHA-256: {p['thresholds_sha256']}",
        f"- pytest: {p.get('pytest_summary', '—')}",
        f"- random seed (SMPL generation): {p.get('random_seed', '—')}",
        "- commands: " + "; ".join(p.get("validation_commands", [])),
        "- report paths: " + "; ".join(p.get("report_paths", [])),
        f"- Texel Part 1: {p['texel_part1_persons']} persons (extracted in place; original archive hash: {p.get('texel_archive_sha256', 'unavailable')})",
        f"- NOMO archive SHA-256: {p.get('nomo_archive_sha256', 'unavailable')}",
        "",
        {"ko": "## 참고문헌", "en": "## References"}[lang],
        "",
        "- ISO 8559-1:2017, Size designation of clothes — Part 1: Anthropometric definitions for body measurement.",
        "- ISO 20685-1:2018, 3-D scanning methodologies for internationally compatible anthropometric databases — Part 1: Evaluation protocol for body dimensions extracted from 3-D body scans.",
        "- Texel BodyScan Dataset and Texel BodyFit automatic measurements (CC BY-NC 4.0).",
        "- Yan, S., Wirta, J., Kämäräinen, J.-K.: Anthropometric clothing measurements from 3D body scans. Machine Vision and Applications 31, 7 (2020). NOMO-3D-400 dataset: doi:10.5281/zenodo.3735905.",
        "- Bojanić, D.: SMPL-Anthropometry (MIT license). https://github.com/DavidBoja/SMPL-Anthropometry",
        "- Loper, M., Mahmood, N., Romero, J., Pons-Moll, G., Black, M. J.: SMPL: A Skinned Multi-Person Linear Model. ACM Transactions on Graphics 34(6), 248:1–248:16 (2015).",
        "",
    ]
    return "\n".join(parts)


def main() -> int:
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    for lang, name in (("ko", "report-formal.ko.md"), ("en", "report-formal.en.md")):
        out = PROJECT_ROOT / "docs" / name
        out.write_text(render(lang, data), encoding="utf-8-sig")
        print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
