"""Agreement statistics with mutually exclusive quality buckets.

Headline statistics use ONLY accepted values with exact definition
mappings (docs/measurement-audit.md); manual_review and approximate
mappings are reported separately. A value carries its full flag list too —
the bucket is a single representative label so per-group Ns sum to the
total instead of double-counting."""
from __future__ import annotations

import statistics

from ..result import MeasurementValue

BUCKET_PRIORITY = (
    "rejected", "manual_review", "gap_closed", "low_confidence",
    "arm_clipped", "fallback", "clean",
)

_LOW_CONFIDENCE_FLAGS = {
    "minimum_at_search_boundary", "maximum_at_search_boundary",
    "single_slice_arm_separation", "front_back_low_confidence",
    "axis_not_inside_any_loop", "orientation_unknown",
    "surface_path_detour", "waypoint_snapped_to_main_component",
}
_FALLBACK_FLAGS = {
    "lateral_axis_pca_fallback", "lateral_axis_default_no_torso",
    "armpit_not_detected_window_is_stature_relative",
}


def quality_bucket(value: MeasurementValue) -> str:
    """Single representative bucket (mutually exclusive, priority order)."""
    if value.selected_value_mm is None or value.disposition == "rejected":
        return "rejected"
    if value.disposition == "manual_review":
        return "manual_review"
    flags = set(value.quality)
    if flags & {"gap_closed_degraded", "gap_closed_manual_review"}:
        return "gap_closed"
    if flags & _LOW_CONFIDENCE_FLAGS:
        return "low_confidence"
    if "arm_clipped_at_merged_level" in flags:
        return "arm_clipped"
    if flags & _FALLBACK_FLAGS:
        return "fallback"
    return "clean"


def summarize(entries: list[dict]) -> dict:
    """entries: [{"delta": float|None, "bucket": str}, ...].

    Statistics are computed over ACCEPTED deltas only (bucket not in
    rejected/manual_review, delta present). sample_sd uses ddof=1 and is
    null below n=2."""
    accepted = [
        e["delta"] for e in entries
        if e["bucket"] not in ("rejected", "manual_review") and e["delta"] is not None
    ]
    abs_accepted = [abs(d) for d in accepted]
    return {
        "n_total": len(entries),
        "n_computed": sum(1 for e in entries if e["delta"] is not None),
        "n_accepted": len(accepted),
        "n_manual_review": sum(1 for e in entries if e["bucket"] == "manual_review"),
        "n_rejected": sum(1 for e in entries if e["bucket"] == "rejected"),
        "bias": statistics.mean(accepted) if accepted else None,
        "mae": statistics.mean(abs_accepted) if abs_accepted else None,
        "median_ae": statistics.median(abs_accepted) if abs_accepted else None,
        "sample_sd": statistics.stdev(accepted) if len(accepted) >= 2 else None,
        "max_ae": max(abs_accepted) if abs_accepted else None,
        "buckets": {
            bucket: sum(1 for e in entries if e["bucket"] == bucket)
            for bucket in BUCKET_PRIORITY
            if any(e["bucket"] == bucket for e in entries)
        },
    }


# Definition-mapping verdicts per dataset (docs/measurement-audit.md).
# Only "exact" rows may enter headline statistics.
TEXEL_MAPPING = {
    "waist_circumference": "exact",
    "across_back_shoulder_width": "exact",
    "upper_arm_girth": "approximate",  # pending the ISO 5.3.16 text check
    "chest_circumference": "approximate",
    "neck_circumference": "approximate",
    "back_length": "approximate",
    "sleeve_length": "approximate",  # performance verdict deferred (audit)
}
NOMO_MAPPING = {
    "neck_circumference": "approximate",
    "chest_circumference": "approximate",
    "upper_arm_girth": "approximate",
}
