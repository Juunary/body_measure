"""polo-line's frames are what the terminal prints — and what the studio
forwards. Every style name must be one the page has a class for."""
from polo_line import live, term

from studio import events as ev
from studio.jobs import Job
from studio.replay import run_replay


def test_frames_render_to_the_printed_line():
    term._COLOR = False
    first = next(e for e in live.frames(width=200) if e["type"] == "frame")
    line = term.render(first["segments"])
    assert line.startswith("      00:") and "█" in line


def test_replay_stage_forwards_every_station_and_ends_replayed():
    job = Job(id="r", params={"replay": {"delay": 0.0}}, entry={})
    run_replay(job)
    types = [e["type"] for e in job.events]
    assert types[0] == "stage" and job.events[0]["status"] == "start"
    assert types.count("station_start") == 9 and types.count("frame") == 54
    assert types[-1] == "stage" and job.events[-1]["status"] == "done"
    assert job.state == "replayed" and job.replay["totals"]["blocks"] == 9
    assert job.replay["document"]["customer_spec"]["size_source"] == "unknown"
    for event in job.events:
        for segments in ([event["segments"]] if "segments" in event else []):
            for _, styles in segments:
                assert set(styles) <= set(ev.STYLES)
