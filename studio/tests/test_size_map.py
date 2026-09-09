"""A chart label reaches the QR only by exact match, and the passport's
customer block never carries a body dimension."""
from studio import sizing_map
from studio.jobs import Job


def test_letters_map_and_numbers_do_not():
    assert sizing_map.to_qr_option("S") == "s"
    assert sizing_map.to_qr_option("XXL") == "xxl"
    assert sizing_map.to_qr_option(" m ") == "m"
    assert sizing_map.to_qr_option("4 (M)") is None
    assert sizing_map.to_qr_option(None) is None


def test_every_en13402_label_is_representable_and_lacoste_is_not():
    charts = {c["key"]: c for c in sizing_map.chart_options()}
    assert all(charts["en13402"]["representable"])
    assert all(charts["en13402-women"]["representable"])
    assert not any(charts["lacoste"]["representable"])


def _job_with_size(label, alternative=None):
    from polo_line.passport import CustomerSize
    job = Job(id="t", params={}, entry={})
    job.customer_size = CustomerSize(label=label, chart="en13402", chart_name="EN", chart_source="src",
                                     chart_checked="2026-08-28", chest_mm=941.0, alternative=alternative,
                                     flags=["near_size_boundary"], source_document="studio/runs/t/measurement.json")
    job.size_view = {"size": label, "qr_option": sizing_map.to_qr_option(label),
                     "qr_status": "ok", "qr_reason": "", "size_source": "3d_scan", "override": None}
    return job


def test_customer_spec_carries_provenance_and_no_body_dimension():
    job = _job_with_size("M", "L")
    block = sizing_map.customer_spec(job, "regular")
    assert block["size"] == "M" and block["size_source"] == "3d_scan"
    assert block["size_chart_id"] == "en13402" and block["size_alternative"] == "L"
    assert block["fit"] == "regular"
    assert not any("chest" in key or "_mm" in key for key in block), block


def test_an_override_is_recorded_next_to_the_measured_size():
    job = _job_with_size("M")
    sizing_map.set_override(job, "xl", "demo")
    option, source = sizing_map.effective_qr_option(job)
    assert (option, source) == ("xl", "manual_override")
    block = sizing_map.customer_spec(job, "slim")
    assert block["size"] == "XL" and block["size_source"] == "manual_override"
    assert block["size_measured"] == "M" and block["size_override_reason"] == "demo"
    assert block["size_chart_id"] == "en13402"       # provenance stays
    sizing_map.set_override(job, None)
    assert sizing_map.effective_qr_option(job) == ("m", "3d_scan")


def test_the_standard_follows_the_population():
    assert sizing_map.chart_for_population("en13402", "women") == "en13402-women"
    assert sizing_map.chart_for_population("en13402-women", "men") == "en13402"
    assert sizing_map.chart_for_population("en13402", "men") == "en13402"
    assert sizing_map.chart_for_population("en13402", None) == "en13402"
    assert sizing_map.chart_for_population("lacoste", "women") == "lacoste"   # no sibling: refuses downstream
