# Nesting algorithm notes and benchmark

Research notes for the shirt-pattern nesting study. Numbers below come from
`marker.json` files produced by `python -m nesting nest`; nothing is retyped
from memory. One pattern, one roll width: they say nothing about other
garments or about production markers.

## Problem statement

Nine placements of six shapes (RUECKEN 1x, VORDERTEIL 2x, AERMEL 2x, PASSE 2x,
OBERKRAGEN 1x, UNTERKRAGEN 1x; SCHABLONE excluded) on a roll 1007 mm wide,
5 mm gap and selvedge margin, every grain line along or across the roll
(rotations 0/90/180/270 deg, never tilted), copy 2 of each 2x shape mirrored.
Total cut-line area 1.3031 m2, so the perfect-packing lower bound is 1317 mm
(efficiency 100 % inside the margins); the naive vertical stack is 4926 mm.

## Grain rule

The study began with grain lines parallel *or* perpendicular to the roll
(rotations 0/90/180/270). A grain audit of every benchmark marker
(`out/compare/grain_audit.py`) showed what that rule permits: every nester cut
2 - 9 of the nine pieces cross-grain, usually including the back, a front or a
sleeve, and sometimes only one piece of a left/right pair. Warp and weft differ
in strength, stretch and shrinkage, so such a shirt would hang and shrink
unevenly. Since 2026-10-01 the rule is 0/180: every grain line along the roll.
Under it the audit finds no cross-grain or tilted piece (0.0000 deg off) and
correct left/right mirroring in every marker. Pieces still point both up and
down the roll (a two-way marker); a napped or one-way fabric would need
rotation 0 only, which has not been run.

Later on 2026-10-01 the user set the rule that applies now: a grain line is
acceptable when it runs along or across the roll (vertical or horizontal), and
never when it is tilted. The default rotations are 0/90/180/270 again, so a
marker may cut pieces cross-grain as described above. `nesting.grain` checks
every marker of both engines: it counts the pieces along and across, refuses
any tilted grain line or rotation outside the rule, and confirms one plain and
one mirrored copy per left/right pair. `--rotations 0,180` keeps every grain
line along the roll.

## Coordinates and the placement transform

- Sheet: PDF points become mm with `1 pt = 25.4 / 72 mm`, y flipped so y is up;
  the 10x10 cm square is checked to measure 100 +- 0.2 mm.
- Piece local frame: rotated so the grain line runs along +y, bounding-box
  minimum at the origin. Body pieces keep their sheet orientation; collars and
  yoke are turned 90 deg.
- Roll frame: x across the width, y along the length, y = 0 at the roll start.
- Placement: `p_roll = R(theta) * M * p_local + t`, M = mirror (x -> -x) or
  identity, rotation about the local origin, *no* re-centring. This is what makes
  `NFP(T A, T B) = T NFP(A, B)` exact for every orientation T, and it is the
  composition every output contour is rebuilt with (a test checks it).

## No-fit polygons

1. Collision polygon = cut line simplified with 0.25 mm tolerance
   (Douglas-Peucker, topology preserving), CCW.
2. Convex decomposition: ear-clipping triangulation (`mapbox-earcut`), then
   Hertel-Mehlhorn merging: a diagonal shared by two convex parts is removed when
   both endpoints stay convex; one pass suffices because an essential diagonal
   stays essential. Parts <= 2r + 1 for r reflex vertices (measured 12 - 41
   parts on these pieces).
3. Raw NFP `A (+) (-B)` = union of the convex hulls of the pairwise vertex sums
   of all part pairs (exact for convex parts), snapped to a 0.01 mm grid before
   the union for robustness.
4. Gap: one round buffer of the raw NFP with radius
   `gap + 2 x tolerance + 0.05 - 0.02`. Inflating both pieces by half the gap
   is the same set, because `(A (+) D_r) (+) -(B (+) D_r) = (A (+) -B) (+) D_2r`.
   The extra `2 x tolerance` pays back the simplification on both pieces, so the
   true contours are never closer than the gap (measured 5.0 - 6.0 mm), and the
   0.02 mm erosion keeps exact-fit corridors from collapsing to zero area.
5. Cache: `NFP(A@(0,0), B@(m, d))` for m in {0, 1} and d in the rotation set is
   computed once per shape pair; every other orientation pair is a rotation or
   mirror of one of these, and `NFP(B, A) = -NFP(A, B)`. About 120 base NFPs
   are computed for this pattern, roughly 10 s.
6. Compound items (a pre-nested pair) need no new NFPs: the exclusion region of
   a union is the union of translated component regions.

## Placement decoder

Free region for the next item = inner-fit rectangle (translations that keep the
true contour inside the margins) minus the union of the translated exclusion
regions of every placed component. The candidate set is every vertex of every
ring of that region; the lexicographic minimum of (resulting marker length,
item top, x) is always attained at a vertex, so the decoder is optimal for its
rule. Rules: `bottom-left` (length, top, x), `left-bottom` (length, x, top),
`compact` (length, bounding-box area of everything placed, x).

## Search

- Items: each single copy (mirrored per the rule). `--pairs` adds one pre-nested
  pair per 2x shape (copy 2 against copy 1 at the exclusion-boundary vertex with
  the best bounding-box fill, over all rotations) as an *extra* candidate for the
  beam. It is off by default: once the beam picks a pair, no local-search move
  can split it, and under the 0/180 rule that froze the search (see the
  comparison below).
- Beam search over (item, rotation): children are shortlisted by an admissible
  completion bound `L + remaining area / usable width`, and the best `2 x beam`
  are ranked by a greedy roll-out (largest remaining item first, best rotation),
  which yields a complete marker each time; every roll-out is a candidate result.
- Local search: iterated local search with restarts. A first-improvement hill
  climb over swaps, rotation changes and re-insertions (neighbours in a seeded
  order) runs to a local optimum; the run's best sequence is then perturbed by
  two random moves and climbed again, accepting equal-or-better results. The
  climb ranks layouts by marker length and, on equal length, by the sum of item
  tops, which gives it a direction on the long plateaus of equal length. A run
  that finds no better layout within `--restart-patience` decodes (2500) ends,
  and the next run starts from the beam sequence with its own random order. Runs
  settle into different rotation combinations and the best run is kept.
  `--iterations` bounds the total number of decodes.
- Decoding: every placed prefix is cached, so a neighbour that keeps the start of
  a sequence is decoded from there; this roughly doubles the decodes per second.
- Compaction: re-place items from the top down when that lowers their key.
- Verification on the original contours: pairwise distance >= gap - 0.05 mm,
  containment in the roll frame, each copy exactly once.

## Results on this pattern (width 1007 mm, gap 5 mm, pairs mirrored)

Filled from `out/*/marker.json`.

| run | rotations | length mm | efficiency | beam -> local search -> compaction (mm) | min distance mm | runtime | budget |
|---|---|---|---|---|---|---|---|
| `out/hemd-1007` | 0/90/180/270 (default: along or across) | 1633 | 79.2 % | 1633 -> 1633 -> 1633 | 5.35 | 14 s | beam 16, window 4, 1500 decodes, seed 0 |
| `out/hemd-1007-along` | 0/180 (every grain line along) | 1554 | 83.3 % | 1744 -> 1554 -> 1554 | 5.33 | 9 s | beam 16, window 4, 1500 decodes, seed 0 |

Lower bound 1317 mm (100 % inside the margins); naive vertical stack 4926 mm. Single copies, no pre-nested
pairs (the default since 2026-10-01; with pairs the same runs gave 1768 and 1629 mm).

With 1500 decodes the four-rotation search ends above the 0/180 result although its rotations include 0 and
180: the larger space is the harder search. On this pattern the cross-grain freedom is worth little anyway:
sparrow gained 4 mm with it on the 1007 mm roll (1547 against 1551 mm).

Budget sensitivity of the earlier pair-based search (four rotations, seed 0, placement rule bottom-left):
with only 40 - 160 local-search decodes the result moved between 1655 and 1687 mm depending on beam width;
1500 decodes reached 1629 mm and the compaction pass took the last 16 mm. The three placement rules
(bottom-left, left-bottom, compact) ended within 3 mm of each other at beam 16, so the default is the simplest.
Runtime is dominated by the one-time NFP construction (about 120 base NFPs, 10 - 15 s). Once the no-fit
polygons are cached, one full decode of the nine placements costs about 5 ms, and the prefix cache brings the
local search to roughly 400 decodes per second.

## sparrow as the placement engine

`python -m nesting nest pieces.json --engine sparrow` (`nesting/sparrow.py`) hands the placement to
sparrow v0.2.0 and keeps the study's constraints around it: the allowed rotations of the grain rule
for every copy, copy 2 of a 2x piece mirrored before nesting (sparrow cannot mirror), the gap as
sparrow's minimum separation (also to the roll edges), and a final check on the true cut lines - gap,
roll edges, every copy once, and the grain check - before any file is written. Each copy is packed as
its cut line simplified by 0.25 mm and grown back by 0.26 mm, so the packed polygon contains the true
line. sparrow runs for the whole `--time-limit`, so its result depends on the machine.

| run | rotations | length mm | efficiency | grain (along / across / tilted) | min distance mm | budget |
|---|---|---|---|---|---|---|
| `out/sparrow-1007` | 0/90/180/270 | 1547 | 83.7 % | 5 / 4 / 0 | 5.30 | 120 s, seed 0 |
| `out/sparrow-1600` (Bullmer width) | 0/90/180/270 | 977 | 83.4 % | 3 / 6 / 0 | 5.53 | 120 s, seed 0 |

## Comparison with open-source nesters

The comparison with SVGnest, Deepnest and sparrow is automated in `bench/` and
reported in [benchmark.md](benchmark.md): same pre-mirrored polygons for every
tool, one evaluator on the true cut lines, both grain rules, 30 s and 120 s
budgets, three runs each. `out/pieces.svg` from `python -m nesting import`
stays available for trying other nesters by hand; it holds both copies of each
2x piece unmirrored.

The same comparison on the full 1600 mm working width of the Bullmer PremiumCut
1620 CV is in [benchmark-bullmer1600.md](benchmark-bullmer1600.md).

What the comparison shows (all numbers are in the two reports, which run the
study's grain rule, every grain line along or across the roll; earlier run sets
are archived in `out/bench/archive/`: both rules in `two-rules-20261001/`, 0/180
only in `rule-0180-20261001/`):

- sparrow v0.2.0 is the strongest nester under the grain rule: 120 s medians of
  1547 mm on the 1007 mm roll and 977 mm on the 1600 mm roll, reached within
  30 s. This study is second, 2.5 % and 4.0 % longer (1585 and 1016 mm), ahead
  of Deepnest (1704, 1085 mm) and SVGnest (1759, 1127 mm). Every marker fits
  one 2000 mm cutting zone.
- Grain: the grain audit (`out/compare/grain_audit.py`, `nesting.grain`) finds
  no tilted grain line, no rotation outside the rule and correct left/right
  mirroring in all 44 markers, including all 20 of sparrow's. The rule lets
  pieces turn across the roll, and every tool uses that: 1 - 9 of the nine
  pieces are cross-grain per marker (sparrow: 3 - 4 on the 1007 mm roll, 6 - 9
  on the 1600 mm roll, including the back).
- With every grain line along the roll (0/180, archived run set of the same
  day) sparrow needs 1552 and 1032 mm and this study 1554 and 1032 mm: the
  study draws level there, but it does not use the cross-grain freedom as well
  as sparrow does.
- The bottom-left decoder is not what separated the two. Given the rotation
  sparrow chose for each copy and sparrow's order along the roll, the study's
  decoder rebuilt 1548.1 mm against sparrow's 1547.0 mm (1007 mm roll) and
  975.2 mm against 976.6 mm (1600 mm roll) in the earlier four-rotation runs,
  both valid in the evaluator.
- What separated them was the search: pre-nested pairs that no local-search
  move can split (the beam result of 1768.4 mm on 1007 mm never improved), and,
  with four rotations, rotation combinations that differ from the good one in
  several pieces at once. Since 2026-10-01 the study nests single copies and
  restarts its local search, which closed the 0/180 gap. Structured rotation
  kicks were tried at equal decode budgets and did worse than plain restarts.
- sparrow is MIT-licensed and already takes this study's instance, so it could
  run behind the study's own constraint layer (grain rule, mirrored pairs, gap,
  PDF import, verification).
