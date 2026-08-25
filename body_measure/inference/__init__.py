"""Body recovery under clothing — the only package that imports torch.

Everything here produces a *body* (SMPL betas, a pose) and hands a
canonical-pose mesh to the measurement core. Nothing here measures. That
split is the project's founding rule for this work stream: the geometry
pipeline that was validated on unclothed scans is the only thing that
turns a surface into a number, so an inferred body is measured exactly
like a scanned one and the comparison is apples to apples.

Import discipline: `body_measure.measure`, `.landmarks`, `.validate` and
`.adapters` never import from this package. `tests/test_inference_isolation.py`
enforces it.
"""
