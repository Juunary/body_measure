"""What a deployment adds: a password in front of the page, and a data
directory a volume can hold."""
import base64
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio.server import BasicAuth


def _app():
    app = FastAPI()

    @app.get("/healthz")
    def health():
        return {"ok": True}

    @app.get("/secret")
    def secret():
        return {"data": 1}

    app.add_middleware(BasicAuth, password="pw")
    return TestClient(app)


def test_the_health_check_is_open_and_everything_else_needs_the_password():
    client = _app()
    assert client.get("/healthz").status_code == 200
    r = client.get("/secret")
    assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Basic")
    token = base64.b64encode(b"anyone:pw").decode()
    assert client.get("/secret", headers={"Authorization": f"Basic {token}"}).status_code == 200
    wrong = base64.b64encode(b"anyone:no").decode()
    assert client.get("/secret", headers={"Authorization": f"Basic {wrong}"}).status_code == 401
    assert client.get("/secret", headers={"Authorization": "Bearer x"}).status_code == 401


def test_a_deployed_scan_directory_is_listed_with_its_sidecar(tmp_path, monkeypatch):
    from studio import files
    (tmp_path / "demo.obj").write_text("v 0 0 0\n", encoding="utf-8")
    # written as PowerShell writes it: with a byte-order mark
    (tmp_path / "demo.json").write_text("﻿" + json.dumps({
        "units": "mm", "up_axis": "Z", "pose": "a", "population": "women", "clothed": False,
        "licence": "public · CC BY 4.0 · demo", "public": True}), encoding="utf-8")
    (tmp_path / "bare.ply").write_bytes(b"ply\n")
    monkeypatch.setattr(files, "EXTRA_DATA", tmp_path)
    entries = {e["id"]: e for e in files.catalogue() if e["group"] == "Deployed"}
    demo = entries["deployed:demo.obj"]
    assert demo["defaults"]["unit"] == "mm" and demo["defaults"]["up_axis"] == "Z"
    assert demo["pose"] == "a" and demo["licence"]["public"] is True
    bare = entries["deployed:bare.ply"]
    assert bare["defaults"]["unit"] is None and bare["licence"]["public"] is False   # never guessed
