"""From a measured body to the one size field the QR code can hold.

Two rules are kept from the projects that own them:

* body-measure assigns a size from a cited chart or refuses with a reason
  (decision #27). The refusal is shown, not hidden, and a refused size
  blocks the QR until the user overrides — visibly.
* polo-line's passport block carries the size together with the chart it
  came from and never the chest girth. `customer_spec` here is that
  block, built by polo-line's own `CustomerSize.to_dpp()`.

The QR schema has eight size options. A chart label is mapped to one only
by exact, case-insensitive match; `4 (M)` from the Lacoste chart is *not
representable* rather than parsed, because the schema has no place to say
which chart the letter meant.
"""
from __future__ import annotations

from . import events as ev
from . import paths  # noqa: F401
from .jobs import Job
from app.schemas import ACTIVE_VERSION, SCHEMAS
from body_measure import sizing
from polo_line import passport

PHASE = ev.PHASE_SIZE

SIZE_OPTIONS = tuple(next(f for f in SCHEMAS[ACTIVE_VERSION].fields if f.key == "size").options)
OK, REFUSED, NOT_REPRESENTABLE = "ok", "refused", "not_representable"


def to_qr_option(label: str | None) -> str | None:
    if label is None:
        return None
    candidate = label.strip().lower()
    return candidate if candidate in SIZE_OPTIONS else None


def chart_for_population(chart_key: str, population: str | None) -> str:
    """The chart of the same standard for this population, if the chosen
    one is for the other. EN 13402-3 publishes a men's and a women's
    table; picking the standard and then the subject should not end in a
    refusal that only says to pick the other table. A chart with no
    sibling (Lacoste) is returned unchanged and sizing refuses as before."""
    chart = sizing.CHARTS[chart_key]
    if not population or chart.population in (None, population):
        return chart_key
    family = chart_key.split("-")[0]
    for key, other in sizing.CHARTS.items():
        if key.split("-")[0] == family and other.population == population:
            return key
    return chart_key


def chart_options() -> list[dict]:
    out = []
    for key, chart in sizing.CHARTS.items():
        out.append({
            "key": key, "name": chart.name, "population": chart.population,
            "dimension_kind": chart.dimension_kind, "source": chart.source,
            "checked": chart.checked, "range_cm": list(chart.range_cm),
            "labels": [band.label for band in chart.bands],
            "primary_measurement": chart.primary_measurement,
            "representable": [to_qr_option(band.label) is not None for band in chart.bands],
        })
    return out


def assign_size(job: Job, chart_key: str | None, population: str | None,
                clothed: bool, *, spec=None) -> sizing.SizeAssignment:
    chart_key = chart_key or sizing.DEFAULT_CHART
    if chart_key not in sizing.CHARTS:
        raise ValueError(f"unknown size chart {chart_key!r}; known: {', '.join(sizing.CHARTS)}")
    matched = chart_for_population(chart_key, population)
    if matched != chart_key:
        job.line(PHASE, ev.note(
            f"chart {chart_key} is for {sizing.CHARTS[chart_key].population}; the subject is "
            f"{population}, so the same standard's {matched} chart is used"))
        chart_key = matched
    assignment = sizing.assign(
        job.measurements, chart=sizing.CHARTS[chart_key],
        pathway="measured_clothed" if clothed else "estimated",
        population=population or None)
    job.sizing = assignment
    job.params.update({"chart": chart_key, "population": population, "clothed": clothed})

    option = to_qr_option(assignment.label)
    if assignment.label is None:
        status, why = REFUSED, assignment.reason
    elif option is None:
        status, why = NOT_REPRESENTABLE, (
            f"chart label {assignment.label!r} is not a size option of QR schema "
            f"v{ACTIVE_VERSION} ({', '.join(SIZE_OPTIONS)})")
    else:
        status, why = OK, ""
    job.size_view = {
        **assignment.to_dict(),
        "qr_option": option, "qr_status": status, "qr_reason": why,
        "size_source": "3d_scan" if assignment.label else "unknown",
        "override": None,
    }
    _describe(job)
    job.emit("size", PHASE, **job.size_view)
    return assignment


def _describe(job: Job) -> None:
    view = job.size_view
    if view["size"]:
        job.line(PHASE, ev.seg("      ", ("size ", "grey"), (str(view["size"]), "bold", "green"),
                               (f"  {view['chart_name']}", "grey"),
                               (f"  (or {view['alternative']})" if view.get("alternative") else "", "yellow")))
    else:
        job.line(PHASE, ev.seg("      ", ("size ", "grey"), ("not assigned", "bold", "yellow"),
                               (f" — {view['reason']}", "grey")))
    for flag in view.get("flags") or []:
        job.line(PHASE, ev.note(flag))
    if view["qr_status"] == NOT_REPRESENTABLE:
        job.line(PHASE, ev.warn_line(view["qr_reason"]))
    if view["qr_status"] in (REFUSED, NOT_REPRESENTABLE):
        job.line(PHASE, ev.warn_line("the QR needs a size — override it in settings to continue, "
                                     "and the passport will say the size was overridden"))


def load_customer_size(job: Job) -> passport.CustomerSize:
    """polo-line's own reader on the document the studio wrote, so
    `source_document` is a real path and the block is the tested one."""
    if job.document_path is None:
        job.customer_size = passport.UNKNOWN
    else:
        job.customer_size = passport.load(job.document_path)
        # the passport names the document, not this machine's directory tree
        job.customer_size.source_document = f"studio/runs/{job.id}/measurement.json"
    return job.customer_size


def resize(job: Job, chart_key: str | None, population: str | None, clothed: bool) -> None:
    """Stage `size`: re-run sizing on the stored measurements and rewrite
    the document's size block."""
    if not job.measurements:
        raise RuntimeError("measure the scan first")
    from .pipeline import write_document
    job.stage(PHASE, "sizing", "start", f"chart {chart_key}")
    job.line(PHASE, ev.stage_line(1, 1, "sizing", f"chart {chart_key} · population {population or 'unstated'}"
                                  f" · {'clothed' if clothed else 'unclothed'}"), "head")
    assign_size(job, chart_key, population, clothed)
    write_document(job)
    load_customer_size(job)
    job.stage(PHASE, "sizing", "done")


def set_override(job: Job, option: str | None, reason: str = "") -> dict:
    """A manual size for the QR. Recorded, never silent."""
    if option is not None and option not in SIZE_OPTIONS:
        raise ValueError(f"size must be one of {', '.join(SIZE_OPTIONS)}")
    if not job.size_view:
        job.size_view = {"size": None, "qr_option": None, "qr_status": REFUSED,
                         "qr_reason": "no measurement yet", "size_source": "unknown",
                         "flags": [], "reason": "no measurement yet"}
    job.size_view["override"] = None if option is None else {
        "size": option, "reason": reason or job.size_view.get("qr_reason") or "user override"}
    job.emit("size", PHASE, **job.size_view)
    return job.size_view


def effective_qr_option(job: Job) -> tuple[str | None, str]:
    """(size option for the code, size_source)."""
    view = job.size_view or {}
    if view.get("override"):
        return view["override"]["size"], "manual_override"
    if view.get("qr_status") == OK:
        return view["qr_option"], "3d_scan"
    return None, view.get("size_source", "unknown")


def customer_spec(job: Job, fit: str) -> dict:
    """The passport's customer block: polo-line's block plus the fit and
    fabric the line writes, plus the override record when there is one."""
    size = job.customer_size or passport.UNKNOWN
    block = {**size.to_dpp(), "fit": fit, "fabric": "organic pique 220g"}
    override = (job.size_view or {}).get("override")
    if override:
        block.update({
            "size": override["size"].upper(),
            "size_source": "manual_override",
            "size_measured": size.label,
            "size_override_reason": override["reason"],
        })
    return block
