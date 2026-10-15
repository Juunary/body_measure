"""From a query body to its nearest reference bodies, and from them to an
estimate: per-key values with a spread, and a size vote per chart.

What this is and is not. When the query vector came from the geometry
pipeline (an unclothed scan, or a body C2 recovered from a clothed one),
that vector is already the body's measurement and stays the authority.
Retrieval adds four things the single number cannot give:

  * whether the body lies inside what the store knows at all (abstention),
  * how much bodies that look like it vary on each key (spread),
  * which size bodies like it were given, as a probability (votes),
  * the ITA_HE_26 shirt size of bodies like it.

The result carries the `retrieved_neighbours` pathway (validate.claims),
so nothing downstream can present it as a measurement.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from .. import sizing
from .calibration import Calibration
from .features import STATURE_KEY, vectorise
from .index import MIN_SHARED_KEYS, BruteForceIndex

PATHWAY = "retrieved_neighbours"
PRIMARY_KEY = "chest_circumference"
#: label key for a neighbour the chart refused; it keeps its weight so a
#: neighbourhood half outside the chart says so instead of renormalising
UNLABELLED = "neighbour_refused"
#: a vote below this share for the winning label is a refusal, not a size
MIN_SHARE = 0.5
#: a runner-up with at least this share is named as the alternative
ALTERNATIVE_SHARE = 0.2
#: a chest spread above this among the neighbours is wider than half a
#: band, and is flagged (EN 13402 men's bands are 80 mm)
CHEST_SPREAD_FLAG_MM = 40.0
MAD_TO_SD = 1.4826


@dataclass
class Neighbour:
    record_id: str
    distance: float
    weight: float
    n_shared: int
    source_type: str
    licence_class: str
    population: str | None
    size_labels: dict


@dataclass
class RetrievalEstimate:
    db_name: str
    k: int
    abstained: bool
    abstain_reason: str | None
    query_pathway: str
    nearest_distance: float | None
    threshold: float
    sigma: float
    neighbours: list[Neighbour] = field(default_factory=list)
    #: weighted median over neighbours with a usable value, per key
    values: dict[str, float | None] = field(default_factory=dict)
    #: 1.4826 x MAD over the same neighbours; None below two values
    spread: dict[str, float | None] = field(default_factory=dict)
    #: chart key -> label -> weight share (shares sum to 1 per chart)
    size_votes: dict[str, dict[str, float]] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    reason: str = ""
    pathway: str = PATHWAY

    @property
    def neighbour_ids(self) -> list[str]:
        return [n.record_id for n in self.neighbours]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["neighbour_ids"] = self.neighbour_ids
        return data

    def to_size_assignment(self, chart: sizing.SizeChart, *,
                           population: str | None = None,
                           chest_mm: float | None = None) -> sizing.SizeAssignment:
        """The vote for `chart` as a SizeAssignment, so every consumer of
        `sizing.assign` can read it. Abstention and a population mismatch
        refuse exactly as `assign` would."""
        if self.abstained:
            return sizing.SizeAssignment(
                chart, None, chest_mm,
                reason=f"retrieval abstained: {self.abstain_reason}",
                flags=["retrieval_pathway", "retrieval_abstained"] + list(self.flags))
        if population is not None and population != chart.population:
            return sizing.SizeAssignment(
                chart, None, chest_mm,
                reason=f"the chart is for {chart.population} and the subject is {population}",
                flags=["retrieval_pathway", "population_mismatch"])
        votes = self.size_votes.get(chart.key)
        if not votes:
            return sizing.SizeAssignment(
                chart, None, chest_mm,
                reason=f"no neighbour carries a {chart.key} label",
                flags=["retrieval_pathway"])
        out = sizing.assign_from_votes(chart, votes, k=len(self.neighbours),
                                       chest_mm=chest_mm, min_share=MIN_SHARE,
                                       alternative_share=ALTERNATIVE_SHARE)
        out.flags.extend(f for f in self.flags if f not in out.flags)
        if population is None:
            out.flags.append(f"population_unverified_chart_is_for_{chart.population}")
        return out


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values, kind="stable")
    v, w = values[order], weights[order]
    if w.sum() <= 0:
        return float(np.median(v))
    cum = np.cumsum(w) / w.sum()
    return float(v[np.searchsorted(cum, 0.5)])


def _abstain(db_name, cal, query_pathway, reason, *, nearest=None, flags=()) -> RetrievalEstimate:
    return RetrievalEstimate(
        db_name=db_name, k=cal.k, abstained=True, abstain_reason=reason,
        query_pathway=query_pathway, nearest_distance=nearest,
        threshold=cal.threshold, sigma=cal.sigma, flags=list(flags),
        reason=f"abstained: {reason}")


def estimate(store, index: BruteForceIndex, cal: Calibration, values: dict,
             usable: dict | None = None, *, population: str | None = None,
             query_pathway: str = "estimated", k: int | None = None,
             exclude_ids=(), extra_flags=()) -> RetrievalEstimate:
    """Retrieve the k nearest reference bodies of one query and summarise
    them. `values` / `usable` are keyed like FEATURE_KEYS (stature in mm
    under `stature_mm`); `exclude_ids` removes records from the search,
    which is how leave-one-subject-out evaluation queries a store that
    contains the subject."""
    k = int(k or cal.k)
    flags = list(extra_flags)
    space = store.space
    z, mask = vectorise(space, values, usable)
    mask = mask & space.index_mask()
    min_shared = min(MIN_SHARED_KEYS, len(space.index_keys))

    if not mask[space.index_of(PRIMARY_KEY)]:
        return _abstain(store.db_name, cal, query_pathway,
                        "the chest, which every chart reads, is not usable on the query",
                        flags=flags)
    if int(mask.sum()) < min_shared:
        return _abstain(store.db_name, cal, query_pathway,
                        f"only {int(mask.sum())} usable index keys; at least {min_shared} "
                        "are compared", flags=flags)

    exclude = set(exclude_ids)
    if population is not None:
        # a body of the other population is not a reference for this one;
        # population-free records (neutral SMPL) stay comparable
        exclude |= {r.record_id for r in store.records
                    if r.population is not None and r.population != population}
    positions, dist, n_shared = index.query(z, mask, k, exclude=exclude)
    if positions.size == 0:
        return _abstain(store.db_name, cal, query_pathway,
                        "no reference body shares enough keys with the query", flags=flags)
    nearest = float(dist[0])
    if nearest > cal.threshold:
        return _abstain(
            store.db_name, cal, query_pathway,
            f"nearest reference is {nearest:.2f} away, beyond the {cal.coverage:.0%} "
            f"calibration distance {cal.threshold:.2f}: the body is outside what the store knows",
            nearest=nearest, flags=flags + ["out_of_reference_manifold"])

    weights = np.exp(-(dist ** 2) / (2.0 * cal.sigma ** 2))
    if weights.sum() <= 0:
        weights = np.ones_like(dist)
    recs = [store.records[int(p)] for p in positions]
    neighbours = [Neighbour(r.record_id, float(d), float(w), int(n), r.source_type,
                            r.licence_class.value, r.population, dict(r.size_labels))
                  for r, d, w, n in zip(recs, dist, weights, n_shared)]

    est_values: dict[str, float | None] = {}
    est_spread: dict[str, float | None] = {}
    for key in space.keys:
        vals, ws = [], []
        for r, w in zip(recs, weights):
            if r.usable(key):
                vals.append(r.stature_mm if key == STATURE_KEY else r.values[key])
                ws.append(w)
        if not vals:
            est_values[key], est_spread[key] = None, None
            continue
        v, wv = np.array(vals, dtype=float), np.array(ws, dtype=float)
        med = weighted_median(v, wv)
        est_values[key] = round(med, 2)
        est_spread[key] = (round(MAD_TO_SD * float(np.median(np.abs(v - med))), 2)
                           if v.size >= 2 else None)
    chest_spread = est_spread.get(PRIMARY_KEY)
    if chest_spread is not None and chest_spread > CHEST_SPREAD_FLAG_MM:
        flags.append("retrieval_chest_spread_exceeds_half_band")

    votes: dict[str, dict[str, float]] = {}
    charts = sorted({c for r in recs for c in r.size_labels})
    total = float(weights.sum())
    for chart_key in charts:
        tally: dict[str, float] = {}
        for r, w in zip(recs, weights):
            if chart_key not in r.size_labels:
                continue
            label = r.size_labels[chart_key] or UNLABELLED
            tally[label] = tally.get(label, 0.0) + float(w)
        denom = sum(tally.values()) or total
        votes[chart_key] = {lab: round(v / denom, 4)
                            for lab, v in sorted(tally.items(), key=lambda kv: -kv[1])}

    if any(r.licence_class.value == "local_only_licensed" for r in recs):
        flags.append("neighbours_include_local_only_records")
    reason = (f"{len(recs)} nearest reference bodies, nearest {nearest:.2f} "
              f"(threshold {cal.threshold:.2f}); an estimate from similar bodies, not a "
              "measurement of this one")
    return RetrievalEstimate(
        db_name=store.db_name, k=k, abstained=False, abstain_reason=None,
        query_pathway=query_pathway, nearest_distance=nearest,
        threshold=cal.threshold, sigma=cal.sigma, neighbours=neighbours,
        values=est_values, spread=est_spread, size_votes=votes, flags=flags, reason=reason)


def query_from_measurements(measurements: dict, prototypes: dict | None,
                            stature_mm: float | None) -> tuple[dict, dict]:
    """(values, usable) for `estimate`, from what the pipeline returned on
    the query body — the same trust rule a stored record uses."""
    from .features import PROTOTYPE_KEYS, SPEC_KEYS
    from .record import UNTRUSTED_BUCKETS, prototype_bucket
    from ..validate.stats import quality_bucket

    values, usable = {}, {}
    for key in SPEC_KEYS:
        mv = measurements.get(key)
        values[key] = None if mv is None else mv.selected_value_mm
        usable[key] = mv is not None and quality_bucket(mv) not in UNTRUSTED_BUCKETS
    for key in PROTOTYPE_KEYS:
        pv = (prototypes or {}).get(key)
        values[key] = None if pv is None else pv.value
        usable[key] = prototype_bucket(pv) not in UNTRUSTED_BUCKETS
    values[STATURE_KEY] = stature_mm
    usable[STATURE_KEY] = stature_mm is not None
    return values, usable
