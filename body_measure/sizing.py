"""The end of the pipeline: turn measured body dimensions into a size.

A size chart maps BODY girths to a label. It does not describe the
garment — a size-M polo is wider than a 94-102 cm chest, by whatever ease
the pattern adds — so nothing here may be read as a finished-garment
dimension. That distinction is the same one the clothed-scan work stream
exists to keep straight, and it is the reason a size is refused outright
on a `measured_clothed` result: the chest girth of a dressed subject is
the jacket's, and a size assigned from it would be the jacket's size.

Charts carry their source and the date it was checked. A chart without a
citable source does not belong here — an invented band looks exactly like
a standard one once it is in a table, and the difference only surfaces
when someone is asked where the number came from.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: A chest measurement this close to a band edge would land in the
#: neighbouring size under a measurement error the pipeline routinely has.
#: On a clothed scan the girth error is tens of millimetres, so a
#: boundary case is reported rather than silently resolved.
BOUNDARY_MARGIN_MM = 10.0


@dataclass(frozen=True)
class SizeBand:
    label: str
    chest_min_cm: float
    chest_max_cm: float          # exclusive, except on the last band


@dataclass(frozen=True)
class SizeChart:
    key: str
    name: str
    source: str
    checked: str
    #: what the chart's numbers describe — always body here, and stated so
    #: that a garment chart added later cannot be mixed in silently
    dimension_kind: str
    #: who the chart is for. EN 13402 designates the same letter by BUST
    #: girth for women and CHEST girth for men, so applying a men's band to
    #: a female body is not a rounding error — it is the wrong dimension.
    population: str
    note: str
    bands: tuple[SizeBand, ...]
    primary_measurement: str = "chest_circumference"

    @property
    def range_cm(self) -> tuple[float, float]:
        return self.bands[0].chest_min_cm, self.bands[-1].chest_max_cm


EN_13402_3 = SizeChart(
    key="en13402",
    name="EN 13402-3 letter codes, men",
    source="EN 13402-3 (European size designation), letter-code table for men, "
           "chest girth in cm — via onlineconversion.com/clothing_en13402_standard.htm",
    checked="2026-08-28",
    dimension_kind="body",
    population="men",
    note="The European standard for the market this line produces for. Each "
         "letter spans two adjacent 4 cm size steps, so the bands are 8 cm "
         "wide. Men's upper-body garments are designated by chest girth "
         "alone; height and waist are optional secondary indicators.",
    bands=(
        SizeBand("S", 86.0, 94.0),
        SizeBand("M", 94.0, 102.0),
        SizeBand("L", 102.0, 110.0),
        SizeBand("XL", 110.0, 118.0),
        SizeBand("XXL", 118.0, 129.0),
    ),
)

LACOSTE_MEN = SizeChart(
    key="lacoste",
    name="Lacoste men, numeric sizes 3-7",
    source="Lacoste men's size guide (numeric 3=S, 4=M, 5=L, 6=XL, 7=XXL); "
           "published body chest range for S-XXL is 86-117 cm",
    checked="2026-08-28",
    dimension_kind="body",
    population="men",
    note="A polo maker's own chart, kept as a cross-check rather than an "
         "authority. Its S-XXL span (86-117 cm) agrees with EN 13402-3 to "
         "within a centimetre, which is the useful fact: a brand chart and "
         "the standard do not disagree enough to change a size here. Bands "
         "below are the standard's, relabelled to Lacoste's numbers — the "
         "brand publishes the span, not the per-size cut points.",
    bands=(
        SizeBand("3 (S)", 86.0, 94.0),
        SizeBand("4 (M)", 94.0, 102.0),
        SizeBand("5 (L)", 102.0, 110.0),
        SizeBand("6 (XL)", 110.0, 118.0),
        SizeBand("7 (XXL)", 118.0, 129.0),
    ),
)

CHARTS = {chart.key: chart for chart in (EN_13402_3, LACOSTE_MEN)}
DEFAULT_CHART = EN_13402_3.key


@dataclass
class SizeAssignment:
    chart: SizeChart
    label: str | None
    chest_mm: float | None
    reason: str = ""
    flags: list[str] = field(default_factory=list)
    #: the neighbouring label a boundary case could equally have taken
    alternative: str | None = None

    @property
    def assigned(self) -> bool:
        return self.label is not None

    def to_dict(self) -> dict:
        return {
            "size": self.label,
            "chart": self.chart.key,
            "chart_name": self.chart.name,
            "chart_source": self.chart.source,
            "chart_checked": self.chart.checked,
            "dimension_kind": self.chart.dimension_kind,
            "chart_population": self.chart.population,
            "primary_measurement": self.chart.primary_measurement,
            "chest_mm": self.chest_mm,
            "reason": self.reason,
            "flags": self.flags,
            "alternative": self.alternative,
        }


def assign(measurements, *, chart: SizeChart = EN_13402_3,
           pathway: str = "estimated", population: str | None = None) -> SizeAssignment:
    """Assign a size from measured body dimensions, or refuse and say why.

    `measurements` is what run_estimated_measurements returned. `pathway`
    is the result's own pathway — a clothed measurement is refused rather
    than converted, because the girth belongs to the garment. `population`
    is who the subject is, when that is known; a mesh does not say, so it
    defaults to unknown and the mismatch is flagged rather than assumed
    away.
    """
    from .validate.stats import quality_bucket

    if pathway == "measured_clothed":
        return SizeAssignment(
            chart, None, None,
            reason="the scan is clothed, so the chest girth is the garment's, "
                   "not the body's; a size from it would be the garment's size",
            flags=["clothed_pathway"])

    value = measurements.get(chart.primary_measurement)
    if value is None or value.selected_value_mm is None:
        return SizeAssignment(
            chart, None, None,
            reason=f"{chart.primary_measurement} has no value on this scan",
            flags=list(value.quality) if value is not None else [])

    bucket = quality_bucket(value)
    chest_mm = float(value.selected_value_mm)
    flags = [f for f in value.quality if f != "ok"]
    if bucket in ("rejected", "manual_review"):
        return SizeAssignment(
            chart, None, chest_mm,
            reason=f"{chart.primary_measurement} is {bucket}; a size may not rest "
                   "on a measurement the pipeline itself will not accept",
            flags=flags)
    if bucket != "clean":
        flags.append(f"primary_measurement_{bucket}")

    if population is None:
        flags.append(f"population_unverified_chart_is_for_{chart.population}")
    elif population != chart.population:
        return SizeAssignment(
            chart, None, chest_mm,
            reason=f"the chart is for {chart.population} and the subject is "
                   f"{population}; EN 13402 designates the same letter by bust "
                   "girth for women and chest girth for men, so the band would "
                   "be read off the wrong dimension",
            flags=flags + ["population_mismatch"])

    chest_cm = chest_mm / 10.0
    low, high = chart.range_cm
    if not (low <= chest_cm <= high):
        return SizeAssignment(
            chart, None, chest_mm,
            reason=f"chest {chest_cm:.1f} cm is outside the chart's "
                   f"{low:.0f}-{high:.0f} cm range; extending a chart past its "
                   "published bands would be inventing sizes",
            flags=flags)

    band = next(b for b in chart.bands
                if b.chest_min_cm <= chest_cm < b.chest_max_cm
                or b is chart.bands[-1] and chest_cm <= b.chest_max_cm)

    alternative = None
    for edge, neighbour in ((band.chest_min_cm, -1), (band.chest_max_cm, +1)):
        if abs(chest_mm - edge * 10.0) <= BOUNDARY_MARGIN_MM:
            index = chart.bands.index(band) + neighbour
            if 0 <= index < len(chart.bands):
                alternative = chart.bands[index].label
                flags.append("near_size_boundary")

    reason = f"chest {chest_cm:.1f} cm falls in {band.chest_min_cm:.0f}-{band.chest_max_cm:.0f} cm"
    if alternative:
        reason += (f"; within {BOUNDARY_MARGIN_MM:.0f} mm of the edge, so {alternative} "
                   "is equally defensible under this pipeline's own error")
    return SizeAssignment(chart, band.label, chest_mm, reason=reason,
                          flags=flags, alternative=alternative)
