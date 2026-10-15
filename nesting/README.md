# Shirt-pattern nesting study

Research code that reads a 1:1 pattern PDF of one shirt, nests the pieces on a
fabric roll of fixed width with the grain rule, and writes a marker with its
efficiency. It exists to design an algorithm that fits *this* problem exactly,
and to compare it against the open-source nesters Deepnest and SVGnest on the
same input.

Validation boundary: one pattern (six shapes, nine placements), one drafting
convention for the PDF, roll widths and gaps chosen by the user. It is not an
industrial marker-making CAD and makes no production-accuracy claim.

## What the problem is

| constraint | value in this study |
|---|---|
| fabric | roll of fixed width (default 1007 mm, the sheet width), unbounded length |
| objective | minimise marker length; efficiency = piece area / (width x length) |
| grain (FDL) | along or across the roll (vertical or horizontal), never tilted: rotations 0, 90, 180, 270 deg. Every marker carries a grain check; `--rotations 0,180` keeps every grain line along the roll |
| quantities | `1XSTOFF` = one copy, `2XSTOFF` = two copies, `SCHABLONE` never cut |
| mirrored copies | single-ply cutting: copy 2 of every 2x piece is mirrored (`--mirror pairs`; also `none`, `free`) |
| gap | 5 mm between cut lines and to the selvedges |

## Quick start (Windows, Python 3.12)

```powershell
cd C:\Users\harry\Documents\ITA\nesting
.\setup.ps1
.\.venv\Scripts\python -m nesting import examples\schnittteile-hemd.pdf -o out\pieces.json
.\.venv\Scripts\python -m nesting nest out\pieces.json --width 1007 --gap 5 -o out\hemd-1007
.\.venv\Scripts\python -m nesting nest out\pieces.json --engine sparrow --width 1007 --gap 5 -o out\sparrow-1007
.\.venv\Scripts\python -m pytest -q
```

`--engine sparrow` places the pieces with sparrow (MIT, built by `python -m bench.fetch_tools`) under the
same grain, mirror and gap rules and runs for the whole `--time-limit` (default 120 s). The study keeps
what sparrow does not know: allowed rotations from the grain lines, pre-mirrored left/right copies, the
gap and margin, and a final check on the true cut lines. A marker that breaks a rule, including a
tilted grain line, is refused.

`import` writes `pieces.json` (the piece contract, mm, y up, grain along +y)
and `pieces.svg` (1 unit = 1 mm, one polygon per copy, for Deepnest/SVGnest).
`nest` writes `marker.json`, `marker.svg`, `marker.png` and `report.md`.

## How the PDF is read

The sheet is vector graphics; roles are recognised by stroke colour:

| role | drawing |
|---|---|
| cut line with seam allowance (nested) | grey stroke rgb(0.353, 0.353, 0.353) |
| net line | white fill, dark stroke rgb(0.2, 0.2, 0.2) |
| grain line `FDL`, fold lines `UMBRUCH`, sleeve hem | blue-violet rgb(0.498, 0.459, 0.737); the straight line nearest the `FDL` label is the grain |
| notches (Knipsen) | red 10 mm lines |
| ignored | orange annotation circles, the red cross, the crossed-out `SCHABLONE` |

The 10x10 cm square on the sheet must measure 100 mm, which proves the sheet is
at 1:1. Labels (`1XSTOFF`, `2XSTOFF`, `UMBRUCH`, `+EINLAGE`, `FDL`) are
matched to the piece that contains them.

## How the nesting works

See [docs/nesting.md](docs/nesting.md) for the full description and the
benchmark table. In short:

1. Every piece is rotated so its grain runs along the roll and simplified to a
   collision polygon (0.25 mm tolerance).
2. Exact no-fit polygons are built from convex parts (ear-clipping triangles
   merged Hertel-Mehlhorn style; Minkowski sums of convex parts). The gap is one
   round buffer of the raw NFP, which is the same as inflating both pieces by
   half the gap. Orientation identities reduce the work to 8 base NFPs per pair
   of shapes.
3. Items are single copies. `--pairs` also offers one pre-nested mirrored pair
   per 2x shape; it is off by default because the local search cannot split a
   pair once the beam has chosen it.
4. A beam search over placement order and rotation ranks partial layouts by a
   greedy roll-out (an actual complete marker), then an iterated local search
   with restarts over the sequence and a top-down compaction pass polish the
   best layout. On this pattern with the default 1500 decodes: 1633 mm, 79.2 %
   efficiency with grain along or across the roll, 1554 mm, 83.3 % with every
   grain line along it (`--rotations 0,180`). sparrow reaches 1547 mm, 83.7 %
   in 120 s under the default rule (see `docs/nesting.md`).
5. The result is verified on the original contours: pairwise distance >= gap,
   all pieces inside the roll, every copy exactly once.

Results are deterministic for a given seed unless `--time-limit` stops the
search early (the report says so when that happens).

## Comparison with open-source nesters

`bench/` runs SVGnest, Deepnest and sparrow on the same pre-mirrored polygons
and checks every result with one evaluator on the true cut lines. There are two
roll setups, each with tables, convergence curves and the best markers: the
pattern PDF's 1007 mm plot width in [docs/benchmark.md](docs/benchmark.md), and
the full 1600 mm working width of the Bullmer PremiumCut 1620 CV that cuts ITA's
markers in [docs/benchmark-bullmer1600.md](docs/benchmark-bullmer1600.md). Both
reports mark which markers fit the cutter's 2000 mm cutting zone. Both run the study's
grain rule (along or across the roll); earlier run sets are archived in `out/bench/archive/`.

```powershell
.\.venv\Scripts\python -m pip install -r bench\requirements.txt
.\.venv\Scripts\python -m bench.fetch_tools
.\.venv\Scripts\python -m bench.compare run
.\.venv\Scripts\python -m bench.compare report
.\.venv\Scripts\python -m bench.compare run --spec bullmer1600
.\.venv\Scripts\python -m bench.compare report --spec bullmer1600
```

GFPack++ (learned packer, ICCV 2025) is compared against the stored sparrow records in
[docs/benchmark-gfpack.md](docs/benchmark-gfpack.md): released checkpoint, a no-model control, and a LoRA
adaptation to shirt markers. It runs on CPU in WSL (`bench/gfpack_infer.py`, `gfpack_run.py`,
`gfpack_teacher.py`, `gfpack_lora.py`, `gfpack_report.py`); sparrow is not re-run.

## Layout

```
nesting/
  nesting/pattern_pdf.py   PDF -> pieces (the only PyMuPDF user besides the PNG preview)
  nesting/grading.py       scales pieces per axis for size studies (examples/hemd-pieces.json is the size-52 fixture)
  nesting/pieces.py        piece / placement contract and the mirror -> rotate -> translate transform
  nesting/polygons.py      simplification, convex decomposition, NFP, exclusion cache
  nesting/placer.py        bottom-left-fill decoder, compaction, independent verification
  nesting/search.py        items, beam search with roll-outs, local search, result document
  nesting/marker.py        SVG / PNG / report writers
  nesting/grain.py         grain check of a finished marker (along / across / tilted)
  nesting/sparrow.py       sparrow as placement engine behind the same constraints
  examples/                the input sheet (test fixture)
  bench/                   comparison with SVGnest, Deepnest and sparrow (fetch, run, evaluate, report)
  tests/                   pytest
  docs/nesting.md          algorithm notes
  docs/benchmark.md        open-source comparison on the 1007 mm roll, generated from the run records
  docs/benchmark-bullmer1600.md   the same comparison on the Bullmer's 1600 mm working width
```

PyMuPDF is AGPL-licensed; it is used only in the offline import and the PNG
preview and can be swapped for pdfplumber if the importer ever ships inside a
served application.
