# Windows 3D polo simulator

The desktop application imports a `body_measure` JSON result and simulates one
research garment through cutting, sewing by the measured men's-shirt work
steps, buttonholes and buttons, and deterministic vision QC. It stops at
`ready_for_qr`; it never creates a DPP label or QR.

The immutable plan uses schema `polo-plan/2`; `polo-plan/1` projects saved
before the work-step table no longer open. Saved projects use
`polo-simulation/1`, include their source document, configuration, plan and
paused playback position, and are protected by a SHA-256 content hash. Opening
a project always restores it paused at the saved position.

## Development run

```powershell
cd C:\Users\harry\Documents\ITA\body-measure\studio
.\.venv-desktop\Scripts\python -m studio.desktop.app
```

The window uses pywebview with the EdgeChromium renderer and a JavaScript-to-
Python bridge. There is no FastAPI/Uvicorn process, no public port and no QR
repository dependency. The UI polls the authoritative Python clock at 10 Hz.

## Windows bundle and installer

```powershell
.\build-desktop.ps1
```

The script builds `dist/PoloSimulator/` with PyInstaller, downloads and verifies
Microsoft's signed WebView2 Evergreen x64 standalone installer, and creates
`installer/output/PoloSimulatorSetup.exe` with Inno Setup 6 or 7. Use
`-SkipInstaller` when only the inspectable onedir bundle is required.

The installer is per-user, creates Start Menu and optional desktop shortcuts,
installs WebView2 only when it is absent, and registers normal Windows removal.
Once installed, the simulator runs without an internet connection or a system
Python installation.

## Desktop 1.1 interaction

`연구 예제로 시작` loads and generates the synthetic example in one click.
The five chapter cards (cutting, sewing, buttons, QC, ready for QR) seek to the start of each process and pause there.
Use `재생` to continue, `현재 작업` for a closer view, or `전체 공정` to see
the line. Dragging the 3D view turns off automatic follow; enable the checkbox
to resume it. Space toggles playback, arrows seek five simulated seconds,
and Home returns to the beginning when focus is outside a form control.

The actual seam contours feed through each sewing station. A separate,
dimensioned polo on the assembly table shows the completed parts. Transfers,
button placement and the QC scan follow the authoritative playback
position and restore when seeking backwards. The cost tab breaks down
fabric, thread, labour, electricity and equipment charges.

## Packaged verification

```powershell
.\dist\PoloSimulator\PoloSimulator.exe --smoke-test "$env:TEMP\polo-engine-check.json"
.\dist\PoloSimulator\PoloSimulator.exe --ui-smoke-test "$env:TEMP\polo-ui-check.json"
```

The first check generates all processes, verifies the QR-ready result,
rewinds and saves/reopens a project under a Korean path. The second also
starts a hidden WebView2 window and verifies WebGL, all five chapters,
3D/terminal synchronization, button rewind, 0.1× speed and three languages.
It writes a JSON result and exits. These checks require no external Python.

## Sewing work steps

Sewing time comes from the measured table *Arbeitsschritte Herrenhemd*
(35 steps, 42:35), kept in full in `studio/desktop/shirt_steps.py`. The
intermediate and final ironing steps 6, 7, 13, 16, 17, 21, 22, 26, 27, 30 and 35
(12:24) are skipped for now. That leaves 18 timed steps totalling
**30:11 (1811 s)**, which is exactly the length of the sewing chapter; the
transfer from the cutter ends the cutting chapter. Steps 1-4 (fusing, cutting the
top collar) and 33-34 (buttonholes, buttons) have no measured time; the button
chapter keeps its own research timings.

| No | Step | Station | Time | Polo seams closed |
|---|---|---|---|---|
| 5 | Ober-/Unterkragen verstürzen | Lockstitch | 0:22 | – |
| 8 | Kragensteg absteppen 0,4 cm | Lockstitch | 0:21 | – |
| 9 | Naht 1,5 mm absteppen | Lockstitch | 0:18 | – |
| 10 | Kragenseiten und Steg verstürzen | Lockstitch | 1:19 | – |
| 11 | Kragenecken zurückschneiden, wenden | Hand (scissors) | 0:47 | – |
| 12 | Ecken ausformen | Hand (awl) | 0:54 | – |
| 14 | Passe an Rückenteil | Lockstitch | 1:45 | – |
| 15 | Passe an Vorderteile | Lockstitch | 3:10 | shoulders |
| 18 | Knopfleiste absteppen | Lockstitch | 1:33 | plackets |
| 19 | Seiten- und Unterärmelnähte schließen | Lockstitch | 3:04 | sides, underarms |
| 20 | Seiten- und Unterärmelnähte versäubern | Overlock | 1:20 | – |
| 23 | Ärmelsäume absteppen | Lockstitch | 1:06 | cuffs |
| 24 | Ärmel einsetzen, Armloch nähen | Lockstitch | 6:01 | four armhole halves |
| 25 | Armloch versäubern | Overlock | 1:20 | – |
| 28 | Saum absteppen | Lockstitch | 1:08 | hems |
| 29 | Kragen auf Rumpf steppen | Lockstitch | 2:40 | collar front/back |
| 31 | Oberkragen am Ansatz aufsteppen | Lockstitch | 1:37 | – |
| 32 | Kragenkanten absteppen | Lockstitch | 1:26 | – |

The pattern is still the research polo, so each of its 18 seams is closed by
exactly one step, and a step's measured time is split across its seams by
length. Stitch counts use the step's stitch length (3 mm where the table gives
none). Steps without a matching polo seam run as timed operations; they add no
sewn length or thread. The station draws active power for each whole step, which
overstates sewing energy. Steam finishing is not simulated.

## Model boundary

Button and QC timings, energy and costs are editable research assumptions.
QC always passes and supplies display readouts only. There is no
cloth physics, camera inference, defect/rework model, live machinery or claim
that a garment was manufactured or validated.
