"""Integrated projects must resolve to the right trees, and the wrong
modules must never be loaded — both collisions are real."""
import sys
from pathlib import Path

from studio import paths


def test_polo_line_is_the_original_with_a_passport_module():
    import polo_line.passport  # noqa: F401
    assert paths.POLO in Path(sys.modules["polo_line"].__file__).parents


def test_app_is_qr_configurator_and_only_its_pure_modules():
    import app.codec, app.qrfixed, app.passport  # noqa: F401,E401
    assert paths.QRBACK in Path(sys.modules["app"].__file__).parents
    from studio import server  # noqa: F401
    for forbidden in ("app.main", "app.simbridge", "app.mfgstore"):
        assert forbidden not in sys.modules, forbidden


def test_verify_reports_all_three():
    resolved = paths.verify()
    assert set(resolved) == {"polo_line", "body_measure", "app"}
