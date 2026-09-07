"""The end of the pipeline: turn measured body dimensions into a size.

What this module is: a chest-girth classifier. It takes ONE measured
body dimension — the primary measurement of the chosen chart, chest (or
bust) girth on every chart here — and returns the letter whose published
band contains it. That is a reference size by chest girth. It is not a
fit recommendation: height, waist, shoulder width and the ease a pattern
adds play no part in it, and EN 13402 itself names height and waist as
secondary dimensions this module does not read. Anything downstream that
calls the result a "recommended size" is overstating it.

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
           "chest girth in cm — XS-3XL via onlineconversion.com/clothing_en13402_standard.htm "
           "(re-read 2026-09-07); 4XL via en.wikipedia.org/wiki/EN_13402 'Letter codes' "
           "(read 2026-09-07), whose XS-3XL rows agree with the first page",
    checked="2026-09-07",
    dimension_kind="body",
    population="men",
    note="The European standard for the market this line produces for. S to "
         "XL each span two adjacent 4 cm size steps (8 cm); XXL is 118-129 "
         "as the source page prints it, 11 cm, so the two-step rule is not "
         "uniform. Men's upper-body garments are designated by chest girth "
         "as the primary dimension; height and waist are secondary "
         "dimensions the standard allows and this classifier does not use. "
         "XS (78-86) is not carried: no body on this line has needed it and "
         "adding bands on speculation is how a chart drifts. 3XL (129-141) "
         "is the first page's last row; 4XL (141-154, 13 cm) comes from a "
         "second summary page that also lists 5XL (154-166), not carried. "
         "Both pages are summaries, not the standard's text; the edition is "
         "unrecorded on either.",
    bands=(
        SizeBand("S", 86.0, 94.0),
        SizeBand("M", 94.0, 102.0),
        SizeBand("L", 102.0, 110.0),
        SizeBand("XL", 110.0, 118.0),
        SizeBand("XXL", 118.0, 129.0),
        # the page's last men's row; added 2026-09-07 (decision #50) after a
        # body at 143.9 cm was refused — which it still is, 3XL ends at 141
        SizeBand("3XL", 129.0, 141.0),
        # 4XL is not on the first page; the Wikipedia table carries it and
        # 5XL (154-166). 4XL was asked for and is added (decision #51);
        # 5XL is not, for want of a body that needs it
        SizeBand("4XL", 141.0, 154.0),
    ),
)

LACOSTE_MEN = SizeChart(
    key="lacoste",
    name="Lacoste numeric labels on EN 13402-3 bands (derived, unofficial)",
    source="Derived: the EN 13402-3 men's bands above, relabelled with "
           "Lacoste's numeric sizes (3=S, 4=M, 5=L, 6=XL, 7=XXL). Not the "
           "brand's own table. A span of 86-117 cm for S-XXL was noted from "
           "the brand's guide on 2026-08-28 and is recorded as noted; it "
           "could not be re-verified on 2026-09-07 (the site refused the "
           "fetch) and it does not match this table's 86-129, which is EN's.",
    checked="2026-08-28",
    dimension_kind="body",
    population="men",
    note="A label conversion, not a brand chart: every band edge here is "
         "EN 13402-3's, and only the label differs. It stops at 7 (XXL) "
         "because that is where the recorded label mapping stops; the EN "
         "chart's 3XL has no recorded Lacoste number and is not guessed. It "
         "exists so a size can "
         "be written the way this polo maker writes it. It cannot serve as "
         "a cross-check of the standard — it IS the standard, renamed — and "
         "agreement between the two says nothing. Replace the bands with "
         "the brand's published per-size cut points, with a citation, "
         "before reading it as Lacoste's.",
    bands=(
        SizeBand("3 (S)", 86.0, 94.0),
        SizeBand("4 (M)", 94.0, 102.0),
        SizeBand("5 (L)", 102.0, 110.0),
        SizeBand("6 (XL)", 110.0, 118.0),
        SizeBand("7 (XXL)", 118.0, 129.0),
    ),
)

EN_13402_3_WOMEN = SizeChart(
    key="en13402-women",
    name="EN 13402-3 letter codes, women",
    source="EN 13402-3 (European size designation), letter-code table for women, "
           "bust girth in cm — XS-3XL via onlineconversion.com/clothing_en13402_standard.htm "
           "(re-read 2026-09-07); 4XL via en.wikipedia.org/wiki/EN_13402 'Letter codes' "
           "(read 2026-09-07)",
    checked="2026-09-07",
    dimension_kind="body",
    population="women",
    note="Two irregularities are kept as the source page's letter table "
         "prints them rather than smoothed. L ends at 106 cm and XL begins "
         "at 107, leaving a 1 cm gap no letter covers; a bust in it is "
         "refused. And XL and XXL span 12 cm where the smaller letters span "
         "8. Neither is verified against the standard's text: the same page's "
         "detailed women's table runs 98-102 / 102-107 / 107-113 with no "
         "gap, so the page contradicts itself and the gap may be the page's, "
         "not EN's. A second summary page (Wikipedia, read 2026-09-07) prints "
         "L as 98-107 with no gap, so two of three tables say the gap is not "
         "there. Until the edition is read, the letter table is used as "
         "printed and the refusal stands; closing the gap by hand would be "
         "choosing between sources without the standard.",
    bands=(
        SizeBand("XS", 74.0, 82.0),
        SizeBand("S", 82.0, 90.0),
        SizeBand("M", 90.0, 98.0),
        SizeBand("L", 98.0, 106.0),
        SizeBand("XL", 107.0, 119.0),
        SizeBand("XXL", 119.0, 131.0),
        SizeBand("3XL", 131.0, 143.0),   # the page's last women's row (decision #50)
        SizeBand("4XL", 143.0, 155.0),   # second source (decision #51); it also lists 5XL 155-167
    ),
)

CHARTS = {chart.key: chart
          for chart in (EN_13402_3, EN_13402_3_WOMEN, LACOSTE_MEN)}
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
            "chart_note": self.chart.note,
            "chest_mm": self.chest_mm,
            "reason": self.reason,
            "flags": self.flags,
            "alternative": self.alternative,
        }


def _band_overlaps(chart: SizeChart, band: SizeBand, lo_cm: float, hi_cm: float) -> bool:
    """Whether the closed window [lo, hi] shares a point with `band`. The
    band's upper edge is exclusive except on the chart's last band, the
    same rule `assign` selects by, so a window that ends exactly on a
    shared edge reaches the band above it and not the band below."""
    last = band is chart.bands[-1]
    below_top = lo_cm <= band.chest_max_cm if last else lo_cm < band.chest_max_cm
    return below_top and hi_cm >= band.chest_min_cm


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
    # docs/measurement-audit.md maps chest_circumference to ISO 8559-1 m5
    # "Bust/Chest Girth" — one item for both populations — and rates the
    # mapping `approximate` because ISO fixes the height at the bust point
    # while this pipeline searches for the maximum girth. The height rule
    # matters more on a female body, where the bust point is a named
    # anatomical location rather than wherever the torso is widest.
    flags.append("chest_definition_approximate_iso_m5")
    # The gap is measured, not merely acknowledged (decision #36): across
    # Texel Part 1 the search peaks at 0.732 +/- 0.017 of stature while the
    # reference matches this pipeline's own profile at 0.708 +/- 0.014,
    # about 42 mm lower, reading +26.8 mm high on average. A band is 80 mm
    # wide, so a third of a band is spent before the body is considered,
    # and the label moved on 3 of those 10 subjects. A reader of this size
    # needs the direction, not just the word "approximate".
    flags.append("chest_reads_high_vs_iso_definition_mean_27mm_texel_n10")

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

    # The last band's top edge is inclusive so the chart's stated maximum
    # gets a size. That exception must still require the band's minimum:
    # without it any value below the last band fell through to it, which
    # only became visible once a chart with a gap existed — the women's
    # table put 106.5 cm in XXL.
    band = next((b for b in chart.bands
                 if b.chest_min_cm <= chest_cm < b.chest_max_cm
                 or (b is chart.bands[-1]
                     and b.chest_min_cm <= chest_cm <= b.chest_max_cm)), None)
    if band is None:
        # inside the chart's outer range but between two of its bands — the
        # women's table has a 1 cm gap where no letter applies
        return SizeAssignment(
            chart, None, chest_mm,
            reason=f"{chest_cm:.1f} cm falls in a gap between the chart's bands; "
                   "the published table covers no letter there",
            flags=flags + ["between_bands"])

    # The alternative is a band the measurement could actually be in: the
    # error window [chest - margin, chest + margin] has to overlap the
    # neighbour under the neighbour's own edge rule. Distance to this
    # band's edge is not enough — on the women's table 105.5 cm is 5 mm
    # from L's edge and 15 mm from XL's start, and naming XL there was
    # naming a band the window never reached (decision #49).
    alternative = None
    lo_cm = (chest_mm - BOUNDARY_MARGIN_MM) / 10.0
    hi_cm = (chest_mm + BOUNDARY_MARGIN_MM) / 10.0
    index = chart.bands.index(band)
    for neighbour in (index - 1, index + 1):
        if 0 <= neighbour < len(chart.bands) and _band_overlaps(
                chart, chart.bands[neighbour], lo_cm, hi_cm):
            alternative = chart.bands[neighbour].label
            flags.append("near_size_boundary")

    reason = f"chest {chest_cm:.1f} cm falls in {band.chest_min_cm:.0f}-{band.chest_max_cm:.0f} cm"
    if alternative:
        reason += (f"; within {BOUNDARY_MARGIN_MM:.0f} mm of the edge, so {alternative} "
                   "is equally defensible under this pipeline's own error")
    return SizeAssignment(chart, band.label, chest_mm, reason=reason,
                          flags=flags, alternative=alternative)
