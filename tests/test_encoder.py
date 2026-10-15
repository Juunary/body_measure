"""The point encoder: shapes, losses, and the export path to a torch-free
query. Untrained weights are enough: what is pinned is that the graph
exports with a dynamic batch, ONNX agrees with eager, and the query side
refuses a store whose feature space the model was not trained in."""
import json

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("onnxruntime")
pytest.importorskip("onnxscript")

from body_measure.inference.encoder import PointEncoder, losses  # noqa: E402
from body_measure.retrieval.features import FEATURE_KEYS, raw_vector, fit_standardiser  # noqa: E402


def _space():
    rows = [raw_vector({k: 100.0 + i * 10 for k in FEATURE_KEYS}) for i in range(6)]
    return fit_standardiser(rows)


def test_shapes_and_unit_embedding():
    model = PointEncoder(n_meas=len(FEATURE_KEYS)).eval()
    emb, betas, meas = model(torch.rand(3, 512, 3))
    assert emb.shape == (3, 64) and betas.shape == (3, 10) and meas.shape == (3, len(FEATURE_KEYS))
    assert torch.allclose(emb.norm(dim=1), torch.ones(3), atol=1e-5)


def test_losses_are_finite_and_respect_the_mask():
    model = PointEncoder(n_meas=4)
    emb, b_hat, m_hat = model(torch.rand(6, 256, 3))
    meas = torch.randn(6, 4)
    mask = torch.ones(6, 4, dtype=torch.bool)
    mask[:, 3] = False
    out = losses(emb, b_hat, m_hat, torch.randn(6, 10), meas, mask)
    assert all(torch.isfinite(v) for v in out.values())
    # a masked key's target cannot move the measurement loss
    meas2 = meas.clone()
    meas2[:, 3] = 1e6
    out2 = losses(emb, b_hat, m_hat, torch.randn(6, 10), meas2, mask)
    assert float(out2["meas"]) == pytest.approx(float(out["meas"]))


def test_export_matches_eager_and_the_query_refuses_a_foreign_space(tmp_path):
    from body_measure.inference.export_encoder import export_onnx
    from body_measure.retrieval.onnx_query import OnnxEncoder

    space = _space()
    model = PointEncoder(n_meas=space.dim)
    ckpt = tmp_path / "enc.pt"
    torch.save({"state_dict": model.state_dict(), "n_meas": space.dim,
                "feature_space": space.to_dict(),
                "training_manifest": {"store": "t", "licence_classes": ["synthetic_smpl"]}}, ckpt)
    report = export_onnx(ckpt, tmp_path / "enc.onnx", n_points=512)
    assert report["parity_ok"], report
    assert report["dynamic_batch_ok"]

    enc = OnnxEncoder(tmp_path / "enc.onnx")
    out = enc(np.random.default_rng(0).random((512, 3), dtype=np.float32))
    assert set(out.values) == set(FEATURE_KEYS)
    enc.check_space(space)
    other = fit_standardiser([raw_vector({k: 5.0 * i for k in FEATURE_KEYS}) for i in range(6)])
    with pytest.raises(ValueError, match="feature space"):
        enc.check_space(other)
    meta = json.loads((tmp_path / "enc.json").read_text(encoding="utf-8"))
    assert meta["licence_classes"] == ["synthetic_smpl"]


def test_points_are_area_uniform_metres_and_centred():
    import trimesh

    from body_measure.retrieval.points import sample_surface

    box = trimesh.creation.box(extents=(400.0, 1800.0, 200.0))
    box.apply_translation((50.0, 900.0, 30.0))
    pts = sample_surface(box, n=4000, seed=1)
    assert pts.shape == (4000, 3) and pts.dtype == np.float32
    assert abs(pts[:, 0].mean()) < 1e-4 and abs(pts[:, 2].mean()) < 1e-4
    assert pts[:, 1].min() >= -1e-6 and pts[:, 1].max() <= 1.8 + 1e-6
