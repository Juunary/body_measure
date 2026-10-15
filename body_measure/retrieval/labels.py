"""Size labels a record carries, one per chart, from the same
`sizing.assign` the pipeline uses. A neighbour's label therefore means
exactly what a direct assignment would have meant on that body, refusals
included: a refused chart stores None, and the vote counts it as
unlabelled weight rather than dropping it."""
from __future__ import annotations

from .. import sizing
from ..charts import ita_he_26

#: the charts every record is labelled against
LABEL_CHARTS: tuple[str, ...] = tuple(sizing.CHARTS)
#: label key of the shirt chart, which is a nearest-row mapping rather
#: than a band chart and so is not in sizing.CHARTS
ITA_KEY = "ita_he_26"


def label_record(measurements: dict, *, population: str | None,
                 pathway: str = "estimated",
                 charts: tuple[str, ...] = LABEL_CHARTS,
                 shirt_values: dict | None = None,
                 shirt_usable: dict | None = None) -> dict[str, str | None]:
    """Labels per band chart, plus the ITA_HE_26 shirt size when
    `shirt_values` (feature-keyed values, prototypes included) are given.
    The shirt chart is a men's chart; a women's body gets None there."""
    out: dict[str, str | None] = {}
    for key in charts:
        assignment = sizing.assign(measurements, chart=sizing.CHARTS[key],
                                   pathway=pathway, population=population)
        out[key] = assignment.label
    if shirt_values is not None:
        if population == "women" or pathway == "measured_clothed":
            out[ITA_KEY] = None
        else:
            shirt = ita_he_26.nearest_size(shirt_values, shirt_usable)
            out[ITA_KEY] = None if shirt.size is None else str(shirt.size)
    return out
