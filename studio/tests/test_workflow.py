import asyncio
from types import SimpleNamespace
from fastapi.testclient import TestClient
from studio import server
from studio.jobs import Job


def test_page_routes_and_legacy_query_preservation():
    client=TestClient(server.app)
    r=client.get('/?job=abc&lang=de',follow_redirects=False)
    assert r.status_code==302 and r.headers['location']=='/measure?job=abc&lang=de'
    measure=client.get('/measure').text
    simulation=client.get('/simulation').text
    qr=client.get('/qr').text
    assert 'id="viewer"' in measure and 'id="cutting-canvas"' not in measure and 'id="qr-card"' not in measure
    assert 'id="cutting-canvas"' in simulation and 'id="viewer"' not in simulation
    assert 'id="qr-card"' in qr and '<canvas' not in qr and 'three' not in qr
    assert '/static/app.js?v=' in measure
    assert '/static/simulation-page.js?v=' in simulation
    assert '/static/qr-page.js?v=' in qr


def test_workflow_snapshot_busy_stage_and_cursor(monkeypatch):
    job=Job('snapshot',{},{});job.active_stage='measure'
    job.emit('stage','measure',name='measure',status='start')
    monkeypatch.setattr(server,'_job',lambda _:job)
    data=TestClient(server.app).get('/api/jobs/snapshot/result').json()
    assert data['busy_stage']=='measure' and data['last_event_id']==1
    assert data['simulation_state'] is None
    job.simulation=SimpleNamespace(get=lambda: {'status':'paused','run_id':'shared-run'})
    assert server.result(job.id)['simulation_state']['run_id']=='shared-run'


def test_initial_sse_cursor_and_reconnect_header(monkeypatch):
    job=Job('events',{},{});monkeypatch.setattr(server,'_job',lambda _:job)
    for i in range(4):job.emit('line','measure',segments=[[str(i),[]]])
    async def run(headers,after):
        async def connected():return False
        request=SimpleNamespace(headers=headers,is_disconnected=connected)
        response=await server.events(job.id,request,after)
        iterator=response.body_iterator
        first=await anext(iterator)
        await iterator.aclose()
        return first
    assert asyncio.run(run({},3)).startswith('id: 4\n')
    assert asyncio.run(run({'Last-Event-ID':'2'},0)).startswith('id: 3\n')
