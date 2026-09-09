"""A report is a person's note against one value; it travels with the
document and never changes the number."""
import json

import pytest

from studio import pipeline
from studio.curves import key_for_label


def test_labels_map_to_table_keys():
    assert key_for_label("Chest girth  1017 mm") == "chest_circumference"
    assert key_for_label("Hip girth  1033 mm") == "hip_girth"
    assert key_for_label("Across-back width  400 mm") == "across_back_shoulder_width"
    assert key_for_label(None) is None and key_for_label("nothing") is None


def test_a_report_lands_in_the_document_next_to_the_untouched_value(measured_job):
    before = measured_job.measurements["chest_circumference"].selected_value_mm
    report = pipeline.add_report(measured_job, "measurement", "chest_circumference",
                                 before, "mm", "loop clips the arm")
    assert report["id"] == 1 and report["scan"] == measured_job.entry["id"]
    doc = json.loads(measured_job.document_path.read_text(encoding="utf-8"))
    assert doc["meta"]["reports"][0]["text"] == "loop clips the arm"
    assert doc["measurements"]["chest_circumference"]["selected_value_mm"] == before
    assert measured_job.events[-1]["type"] == "line"
    assert any(e["type"] == "report" for e in measured_job.events)


def test_an_empty_report_is_refused(measured_job):
    with pytest.raises(ValueError):
        pipeline.add_report(measured_job, "measurement", "waist_circumference", 860.0, "mm", "   ")
    with pytest.raises(ValueError):
        pipeline.add_report(measured_job, "opinion", "waist_circumference", 860.0, "mm", "x")
