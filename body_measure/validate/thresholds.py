"""Validation targets, strictly separated by what they may claim.

DATASET_AGREEMENT_TARGETS are INTERNAL regression bounds, derived from the
first observed run on Texel Part 1 (portal_mx, 10 bodies) and set slightly
above it — they exist so a code change that degrades agreement fails a
test. They are NOT accuracy claims and NOT ISO 20685-1 conformity gates.

ISO_20685_REFERENCE_VALUES stays empty until the values are checked
against the actual standard text (ITA library task). Even then they are
informational: the ISO protocol needs real subjects and a trained
measurer, which this project cannot run before the scanner arrives.
"""

# spec measurement name -> internal regression bounds (mm), vs the
# definition-matched dataset ground truth (see adapters/texel.py GT_IDS).
# First runs on Texel Part 1 (portal_mx, 10 bodies):
#   waist vs m102: mean -3.5, max |d| 38.6
#   chest vs m5:   mean +32.9, max |d| 78.0  (arm-clipped tape approximation)
#   neck  vs m11:  mean +8.8,  max |d| 58.9  (horizontal v1 slice)
#   shoulder vs m1: mean +31.7, max |d| 91.3 (acromion approximation)
#   sleeve vs m55:  mean +197.1, max |d| 241.7 — KNOWN systematic overshoot
#     (edge-graph inflation + acromion approximation + arm/torso contact
#     detours); the bound only guards against getting WORSE, the offset
#     itself is an open improvement item (heat method, arm-axis waypoints)
#   back_length vs m3: mean +26.2, max |d| 86.8
DATASET_AGREEMENT_TARGETS: dict[str, dict[str, float]] = {
    "waist_circumference": {"per_body_mm": 45.0, "mean_bias_mm": 10.0},
    "chest_circumference": {"per_body_mm": 85.0, "mean_bias_mm": 45.0},
    "neck_circumference": {"per_body_mm": 65.0, "mean_bias_mm": 25.0},
    "across_back_shoulder_width": {"per_body_mm": 100.0, "mean_bias_mm": 45.0},
    "sleeve_length": {"per_body_mm": 260.0, "mean_bias_mm": 230.0},
    "back_length": {"per_body_mm": 95.0, "mean_bias_mm": 40.0},
}

# waist-height sanity vs Texel m43 (first run: mean +24.4, max |d| 65.4)
WAIST_HEIGHT_TARGET_MM = 75.0

# VERIFY against ISO 20685-1 before recording anything here; until then
# no code may import this for pass/fail decisions.
ISO_20685_REFERENCE_VALUES: dict[str, float] = {}
