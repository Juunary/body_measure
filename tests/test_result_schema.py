"""Result contract: exactly the spec's six measurements, JSON round-trip,
honest nulls for unimplemented values."""
import json

from body_measure.result import SCHEMA_VERSION, empty_result
from body_measure.spec import load_spec

EXPECTED = {
    "chest_circumference",
    "waist_circumference",
    "neck_circumference",
    "across_back_shoulder_width",
    "sleeve_length",
    "back_length",
}


def test_the_spec_defines_exactly_the_six_shirt_measurements():
    assert set(load_spec().names) == EXPECTED


def test_result_contains_exactly_the_spec_measurements_and_round_trips():
    spec = load_spec()
    result = empty_result(spec, source_type="mesh_file", source_id="x.ply", pathway="estimated")
    payload = json.loads(result.to_json())
    assert set(payload["measurements"]) == EXPECTED
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["units"] == "mm"
    assert payload["pathway"] == "estimated"


def test_unimplemented_measurements_report_null_not_a_number():
    spec = load_spec()
    result = empty_result(spec, source_type="mesh_file", source_id="x.ply", pathway="estimated")
    payload = json.loads(result.to_json())
    for value in payload["measurements"].values():
        assert value["selected_value_mm"] is None
        assert "not_implemented" in value["quality"]


def test_every_unverified_definition_is_marked_as_such():
    # definition_verified flips only after the ISO 8559-1 library check
    spec = load_spec()
    for m in spec.measurements.values():
        assert m.definition_verified is False


def test_surface_path_measurements_declare_their_forced_route():
    spec = load_spec()
    shoulder = spec.measurements["across_back_shoulder_width"]
    assert "back_neck_point" in shoulder.route
    sleeve = spec.measurements["sleeve_length"]
    assert sleeve.route.index("shoulder_point_right") < sleeve.route.index("elbow_point_right")
