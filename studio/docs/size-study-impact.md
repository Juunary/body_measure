# Herrenhemd ITA_HE_26: what the size chart changes, in production and in the DPP

Status: research note, 2026-10-07. Only size 52 (L) is measured. Every other size is an estimate.
"Modelled" means the size study computes it. "Hypothesis" means it follows from the chart but is not
computed and not measured.

## A. What the chart changes

| Chart row (ITA_HE_26) | Drives | Modelled in the size study |
|---|---|---|
| Kragenweite | collar length, collar steps 5, 8, 9, 10, 29, 31, 32 | piece length and step needle time |
| 1/2 Saumweite | back and front width, hem steps 27, 28 | piece width and step 28 needle time |
| Länge HM | back and front length, plackets, side seams, steps 18, 19, 20 | piece length and step needle time |
| Ärmellänge | sleeve length | piece length |
| Ärmellänge ab HM | underarm seam, steps 19, 20 | step needle time |
| 1/2 Oberarmweite | sleeve width, armholes, steps 24, 25 | piece width and step needle time |
| 1/2 Ä-Saumweite | sleeve hem, step 23 | step needle time |
| RT Breite an Passe | yoke length, step 14 | piece length and step needle time |
| Schulterbreite an VT | yoke to front seam, step 15 | step needle time |
| 1/2 Oberweite | garment chest | step 35 (final pressing) and the polo drafter only, not the shirt piece widths |
| 1/2 Taillenweite, Taillenlänge, RT Breite an nat. Schulter | waist, back length, shoulder | polo drafter only, no shirt piece uses them yet |
| Breite Knopfleiste | placket width | constant 3.5 cm, no change |

Row 1/2 Ä-Saumweite shows 12.0 at sizes 48, 50 and 54. It is a typo, confirmed by the user. 19.0 is used.

Shape of the changes (modelled, sizes 40 to 58, relative to 52):

| Quantity | 40 | 52 | 58 | Shape |
|---|---|---|---|---|
| net piece area | 1.031 m² | 1.303 m² | 1.371 m² | stepped, close to quadratic in length |
| marker length | 1374 mm | 1554 mm | 1741 mm | stepped and noisy (packing) |
| sewing time | 1759 s | 1811 s | 1828 s | affine, fixed plus needle part |
| energy | 0.742 kWh | 0.780 kWh | 0.790 kWh | follows time, cutting part moves separately |

## B. What changes in the garment production process

Modelled:

1. **Cutting and fabric.** Marker length grows 27 % from 40 to 58. Fabric per shirt and fabric cost grow with it.
   Marker efficiency varies 75 to 83 % per size. Cutting length and vacuum time follow, so cutting energy moves
   with the pattern, not with sewing time.
2. **Sewing.** Needle time scales with sewn length. The fixed handling part does not. The sewing chapter differs by
   about 4 % between 40 and 58.
3. **Final pressing (step 35).** Scales with garment area, 119 s at 40 to 158 s at 58.
4. **Thread.** Follows sewn length, 17.6 m at 40 to 19.4 m at 58.
5. **Energy, power, CO2e, cost.** Computed from kW times time per operation. Mean power stays near 1.27 to
   1.30 kW because the vacuum and overhead terms dominate.

Hypotheses, not modelled:

6. **Spreading.** Lay-up time and ply count scale with marker length. Mixing sizes in one marker is the main
   lever against the 75 to 83 % efficiency swing.
7. **Fusing (steps 1, 3, 4).** Interlining area scales with collar and placket size. These steps have no measured
   time, so they are not scheduled.
8. **Handling.** Very small and very large pieces may take longer to align. The U-shape is possible. Only
   measuring sizes 40 and 58 can show it.
9. **Buttons.** Count and spacing stay fixed in the simulator. A longer Länge HM may need a different placket
   layout, which the model does not do.
10. **Quality control.** Scan time is fixed. The tolerance per size is not modelled.
11. **Scheduling.** Per-size time differences are small compared with the shop-floor noise, so they matter for
    batching and cost reporting, not for line balancing.

## C. How the results reach the DPP (proposal)

What the passport already carries (code: `passport_doc.py`, `passport_summary.py`, polo-line `passport.py`):

- a size block with label, chart name, chart source and an alternative label for boundary cases;
- no body dimensions, by design (privacy boundary);
- process resources: flow time, energy, CO2e, cost with breakdown, labour time, thread, fabric area by material,
  both planned and actual, plus the run size (label, source, chart);
- a guard that stops the QR if the simulation size differs from the assigned size.

What the size study would change:

| Passport item | Effect of ITA_HE_26 sizes |
|---|---|
| size label | the QR schema holds eight labels (xs to 4xl). Sizes 40/42 both map to XS, 44/46 to S, 48/50 to M, 52/54 to L, 56/58 to XL. The numeric size is lost unless the chart key and numeric size are added to the size block. |
| chart | add `ITA_HE_26` as a named chart; today an unknown chart gives no size defaults. |
| process resources | per-unit time, energy, CO2e and thread differ by size. The simulation must be run with the garment's size, and the existing size guard already enforces it. |
| fabric | the passport reports polo window area. For the shirt it should report the marker-based fabric (length times roll width), and no rib. |
| estimation flag | the numbers are graded from size 52. They must stay flagged as estimates with the model version, until sizes 40 and 58 are measured. |
| garment dimensions | chart rows are product specifications, not body data. They may be listed in the passport if wanted, without any body measurement. |

Size-level differences are 1 to 5 % in time and energy. They sit inside the model's uncertainty, so the passport
should show the size and the estimate basis, and should not claim precision at that level.

## D. Limits of this study

- Pressing steps 6, 7, 13, 16, 17, 21, 22, 26, 27 and 30, hand work (11, 12) and the button chapter keep their
  measured time at every size, so they do not react to the chart.
- Sewn lengths per step are estimates from the pattern and the chart, not measured. The needle speed 600 stitches/min
  is the simulator default.
- Pieces are scaled with their seam allowance. Real grading does not.
- Cutting and vacuum energy come from the polo pattern, not the shirt.
