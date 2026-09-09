# Studio QR product passport

The existing `/c/{padded}` QR redirects to `/view/{code}`. Only Studio's view
uses `static/passport.html`, `passport.css`, `passport.js` and
`passport-polo.webp`. The sibling DPP Vue viewer and QR codec/profile are
unchanged. The page never imports Three.js, WebGL, sewing or cutting viewers.

The product summary precedes material, care, process and identity sections.
At 760px and below these use a single column. The language follows
`studio.settings.lang`; the page's language buttons preserve all other Studio
settings. An optional `?lang=ko`, `de`, or `en` sets the initial page language.

## Public contract and persistence

`GET /api/passports/{code}/summary` validates the QR and returns
`studio-passport-summary/2` with `Cache-Control: no-store` (stored v1 summaries
remain readable without inventing the new metrics):

- `product`: QR-derived colour, size, fit, fibre composition, recycled content
  and wash setting, with display labels. The Studio garment is a polo.
- `recorded` / `generated_at`: whether a QR-generation snapshot exists and
  its UTC timestamp, displayed in the reader's local time zone.
- `process`: research scope, capture status, ordered stage statuses and
  accumulated public metrics. `null` if there is no saved record.
- `finished_garment`: always false. Finishing and QC are never executed here.

The metrics include cut/sewn length in mm, planned nesting yield in percent,
collected/total pieces, accumulated stitches, completed/total seams, elapsed
process time and planned total time in seconds. The page converts lengths to
metres. Pattern and body dimensions, coordinates, identifiers for internal jobs,
raw measurements, paths and override reasons are excluded by an explicit
allowlist. The downloaded JSON is exactly this public response.

Version 2 adds `process.resources`, `planned_resources`, `run_size` and
`estimation`. These contain the same engine-generated flow time, energy,
electricity-related CO₂e, cost breakdown and public research preset shown in
Studio and its terminal. Public JSON is also available in a collapsed viewer.
See [workflow and resource model](workflow-resources.md) for formulas and rates.

`POST /api/jobs/{id}/passport` captures the current authoritative player state
and commits one public JSON record in SQLite before reporting success. Job
actions cannot replace its input/player halfway through capture. A changing
measurement/sizing stage returns 409; an active simulation can be captured.
Unresolvable size and persistence errors are reported instead of publishing
a successful QR record.

SQLite lives at `runs/passport-summaries.sqlite3`, or
`$STUDIO_STATE_DIR/runs/passport-summaries.sqlite3`. A transaction replaces the
payload for the same code; a delayed older capture cannot replace a newer
one. Connections are closed after each operation. Keep this file on the
persistent volume along with the other Studio state.

Opening a QR reads the saved capture. Continuing or rewinding a simulation
does not change it. Regenerate the QR to capture the new position. After a
restart the jobs are still ephemeral, but the public snapshots remain.
Legacy valid codes with no row return QR declarations and no process record;
they never synthesize sample production events. The legacy role-filtered
document endpoint remains available for compatibility and is not fetched by
this page.

## Validation

From `studio`:

```powershell
.venv\Scripts\python -m pytest tests
# Requires a Playwright module and installed Edge; set PLAYWRIGHT_MODULE to
# the installed package's absolute path if it is outside Node's module path.
node tests/passport-browser.cjs
```

The browser check launches an isolated server on 8011 and an isolated state
directory under `runs/passport-browser-*`. It checks the old padded URL, QR
generation, unrun/in-progress/completed states, frozen captures, regeneration,
server restart, all three languages at 360px and 1366px, keyboard activation
and focus, copy, public JSON download, print styles, loading/error/retry,
invalid codes and absence of 3D dependencies. Screenshots and print output
are saved under that test directory. Headless print verifies the button
dispatch and generates a PDF using print CSS; it does not drive an OS print
dialog. The Python tests additionally cover cutting-only scope, excluded
sewing, both QR schema versions, privacy and concurrent atomic replacement.

## Representative image

`static/passport-polo.webp` is an AI-generated form example, explicitly
labelled as such in all three languages. The image is neutral; the encoded
colour is stated separately with a swatch. It is not production evidence.

Created with the built-in ImageGen tool, then encoded as WebP at quality 86
without changing its 1254×1254 dimensions. The original generated PNG is
retained by the image tool. Prompt:

> Use case: product-mockup. Create one representative catalogue flat lay image
> for a textile research Digital Product Passport website. A single unbranded
> pale warm-grey short-sleeve pique polo shirt, ribbed collar and short 2-button
> placket, matching sleeve rib cuffs, complete garment visible centered with
> generous breathing space. Front view lying flat, subtle realistic textile
> grain and soft folds, diffuse studio daylight from upper left, gentle contact
> shadow. Warm ivory background #f3f1eb, minimalist precise editorial textile
> catalogue aesthetic. Square composition. No mannequin, person, logos,
> labels, writing, badges, accessories, graphics or interface. This is a
> generic shape illustration, not a manufactured garment photograph. Save
> suitable as a website product asset.
