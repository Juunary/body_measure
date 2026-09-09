# Pfaff research sewing simulation

The default scope is now `through_sewing`: Zünd cutting, collection of all nine
parts, transfer, Pfaff setup, 18 seam passes, and assembly collection. Select
**Cut only** in Pattern & machine inputs, or set `scope: "through_cutting"` in
the JSON config, to retain the previous stopping point.

The model executes plackets, shoulders, front/back collar attachment, four
sleeve-cap halves, side seams, sleeve closures, cuffs and front/back hems.
Every seam contains paired paths in the original pattern coordinates. Rib
paths use the explicit design stretch ratio. Mismatched seam lengths stop plan
generation. The cuff pattern was corrected to match the actual sleeve opening
length (the former rectangle was twice the required length).

Pfaff performs an idealized lockstitch research assembly. This does not validate
stitch suitability for knitted fabric. Overlock, coverstitch, buttonholes,
finishing and QC remain unexecuted; the result is not a finished garment.

## Automatic input completion after sizing

An assigned body-size chart band enables missing-value completion. Existing
measured and prototype values remain in use; manual inputs take precedence.
Chest defaults to the chart band midpoint. Other missing dimensions use the
versioned `polo-size-fallback/1` research block, including a zero front/back
width difference. These research assumptions are not dimensions published by
the chart. Each effective input retains its original value and quality flags
and records `size_chart` or `size_preset` with an `auto_basis` description.
Without a recognized assigned size, missing values still need manual completion.
Wrong units and finite out-of-range values remain errors. CLI documents use the
same `meta.size` assignment written by body_measure.

## Timing and playback

Each seam runs alignment, presser down, stitching, thread trim and presser up.
Stitches are `ceil(seam_length / requested_stitch_length)`. The actual spacing
is `seam_length / stitches`; stitching time is `stitches * 60 / stitches_per_min`.
Handling times and stitch settings are editable research presets, not Pfaff
manufacturer specifications. No live equipment connection is made.

The same Python schedule and random-access snapshot run in Studio and CLI.
SSE transmits progress and cumulative metrics, while paired geometry is fetched
once. A part is marked sewn only after every required pass involving it has
finished thread trimming. Assembly completion requires the final collection.
Cutting counters retain their values after parts enter sewing. Seeking backward
recomputes seams, parts, stitch count and machine states from the schedule.

The 3D view animates a fixed needle, presser, handwheel and both seam edges
feeding under the needle. Blue lines show target seams and orange lines show
stitched portions. Remaining parts sit in a stack. Completed parts appear in a
schematic flat assembly layout. This is feed kinematics and a process display;
folding, drape, fabric tension and collision physics are not simulated.

## Run from PowerShell

From `ITA/studio`:

```powershell
.\.venv\Scripts\python -m studio.simulate --measurements examples/cutting-measurements.json --config examples/cutting-config.json --instant --no-color --out runs/sewing-example.json
.\.venv\Scripts\python -m studio.simulate --attach JOB_ID --server http://127.0.0.1:8010
```

Existing configs without a scope use the new sewing default. New exports use
`garment-simulation/2` and include `sewing_seams`, all operations and sewing
totals. Passport manufacturing data records the actual scope, separate cutting
and sewing completion flags, and `finished_garment: false`.

Default synthetic example: 18 seams, 4,484.873 mm sewn, 1,504 stitches,
234.792 s cutting and 281.400 s sewing including handling. These values are
calculated results, not timing constraints.
