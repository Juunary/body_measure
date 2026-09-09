"""The measurement phase on a synthetic body: stage order, curves for the
rings, a size, and a document polo-line can read."""
import json

def test_stages_come_in_the_cli_order(measured_job):
    starts = [e["name"] for e in measured_job.events
              if e["type"] == "stage" and e["status"] == "start" and e["phase"] == "measure"]
    assert starts == ["load", "canonicalize", "pose", "landmarks_measurements", "prototypes",
                      "curves", "sizing", "document"]
    assert measured_job.state == "measured"


def test_there_is_a_ring_for_each_torso_girth_and_the_upper_arm(measured_job):
    labels = [c["label"] or "" for c in measured_job.curves]
    for name in ("Neck girth", "Chest girth", "Waist girth", "Upper arm girth"):
        assert any(label.startswith(name) for label in labels), labels
    for curve in measured_job.curves:
        assert curve["kind"] in ("loop", "path") and len(curve["points"]) >= 2


def test_the_document_is_one_polo_line_reads(measured_job):
    from polo_line import passport
    doc = json.loads(measured_job.document_path.read_text(encoding="utf-8"))
    assert doc["schema_version"] == 1 and set(doc["measurements"]) >= {"chest_circumference"}
    assert "size" in doc["meta"]
    size = passport.load(measured_job.document_path)
    assert size.known and size.chart == "en13402"
    assert measured_job.customer_size.source_document.startswith("studio/runs/")


def test_mesh_buffer_has_the_header_it_promises(measured_job):
    import struct
    from studio import meshio
    data, decimated = meshio.pack_binary(measured_job.mesh)
    assert data[:4] == meshio.MAGIC and decimated is False
    n_v, n_f, flags = struct.unpack("<III", data[4:16])
    assert n_v == len(measured_job.mesh.vertices) and n_f == len(measured_job.mesh.faces)
    assert len(data) == 16 + n_v * 12 + n_f * 12
