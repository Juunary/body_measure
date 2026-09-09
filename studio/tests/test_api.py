"""The HTTP surface, through ASGI: job creation rules, the QR roundtrip,
the passport tiers and the resolver."""
import pytest
from fastapi.testclient import TestClient

from studio import passport_doc
from studio.server import app

client = TestClient(app)


def test_health_and_schema():
    assert client.get("/healthz").json()["ok"] is True
    schema = client.get("/api/schema/active?lang=en").json()
    assert schema["x-studio-locked"] == ["size"]
    assert client.get("/api/schema/active?lang=xx").status_code == 422


def test_a_mesh_file_needs_its_unit():
    entry = next((e for e in client.get("/api/files").json() if e["kind"] == "mesh_file"), None)
    if entry is None:
        pytest.skip("no mesh_file entry on this machine")
    r = client.post("/api/jobs", json={"file_id": entry["id"]})
    assert r.status_code == 422 and "never guessed" in r.json()["detail"]
    r = client.post("/api/jobs", json={"file_id": entry["id"], "unit": "m", "up_axis": "Y"})
    assert r.status_code == 200 and r.json()["job_id"]


def test_unknown_file_and_stage():
    assert client.post("/api/jobs", json={"file_id": "nope"}).status_code == 404
    entry = client.get("/api/files").json()[0]
    job = client.post("/api/jobs", json={"file_id": entry["id"], "unit": "m", "up_axis": "Y"}).json()["job_id"]
    assert client.post(f"/api/jobs/{job}/run/nothing").status_code == 404
    assert client.post(f"/api/jobs/{job}/run/measure").status_code == 409     # not loaded


def test_qr_roundtrip_and_passport_tiers(measured_job):
    job = measured_job
    config = passport_doc.default_config()
    r = client.post(f"/api/jobs/{job.id}/passport", json={"config": config, "base_url": "http://testserver"})
    assert r.status_code == 200, r.text
    body = r.json()
    code = body["code"]
    assert body["decoded"]["size"] == body["size_option"]
    assert body["passport"]["customer_spec"]["size_source"] == "3d_scan"
    assert not any("chest" in k or "_mm" in k for k in body["passport"]["customer_spec"])

    png = client.get(f"/api/qr/{code}.png", params={"base_url": "http://testserver"})
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"

    public = client.get(f"/api/passports/{code}", params={"role": "public", "explain": "true"}).json()
    assert "customer_spec" not in public["passport"] and "customer_spec" in public["withheld"]
    authority = client.get(f"/api/passports/{code}", params={"role": "authority"}).json()
    assert authority["passport"]["customer_spec"]["size_chart_id"] == "en13402"

    r = client.get(f"/c/xxxxxxxx{code}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == f"/view/{code}"
    assert client.get("/c/xxxx").status_code == 404

    # the event stream replays the buffer first; the live tail never ends,
    # so the generator is read directly and left after the buffered part
    import asyncio

    async def first_events(n):
        out = []
        async def never_disconnected():
            return False
        async for event in job.stream(0, never_disconnected):
            out.append(event)
            if len(out) == n:
                break
        return out
    events = asyncio.run(first_events(3))
    assert [e["id"] for e in events] == [1, 2, 3]
    assert events[0]["type"] == "stage" and events[0]["name"] == "load"
