import sys
from pathlib import Path

import pytest

STUDIO = Path(__file__).resolve().parents[1]
if str(STUDIO) not in sys.path:
    sys.path.insert(0, str(STUDIO))

from studio import paths  # noqa: E402,F401  (sys.path bootstrap for the siblings)

# Not a package on purpose: qr-configurator/backend is on sys.path and owns
# the name `tests`, so nothing here is imported as `tests.something`.
SMPL_BODY = paths.BODY / "data" / "generated" / "smpl_neutral0_apose.obj"


@pytest.fixture(autouse=True)
def isolated_passport_database(tmp_path, monkeypatch):
    from studio import passport_summary
    monkeypatch.setattr(passport_summary, 'DB_PATH', tmp_path / 'passports.sqlite3')


@pytest.fixture(scope="session")
def measured_job():
    """One synthetic body, loaded and measured once for the whole session."""
    if not SMPL_BODY.is_file():
        pytest.skip("generated SMPL body absent")
    from studio import files, pipeline
    from studio.jobs import REGISTRY

    entry = files.find("generated:smpl_neutral0_apose")
    assert entry is not None
    job = REGISTRY.create({"unit": "m", "up_axis": "Y", "clothed": False, "population": "men",
                           "chart": "en13402", "replay": {"delay": 0.0}}, entry)
    pipeline.run_load(job)
    pipeline.run_measure(job)
    return job
