# FCC Active Antenna Towers

Download the FCC **Antenna Structure Registration (ASR)** database and build a
CSV of **active antenna structures** with location (lat/lon), tower type, and
tower heights.

## Files

| File | Purpose |
|---|---|
| `fcc_towers.py` | The program (Python 3, standard library only — no dependencies) |
| `active_antennas.csv` | Output: one row per active antenna coordinate (~164k rows) |
| `build_overlay.py` | Phase 2: turns the CSV into an X-Plane 12 overlay scenery pack |
| `output/FCC_Towers/` | Phase 2 output: the scenery pack (copy into `C:\X-Plane 12\Custom Scenery`) |
| `synthetic_antennas.csv` | Showroom input: a small grid of sample tower objects near Erie, CO |
| `output/FCC_TowerShowroom/` | Showroom scenery pack built from that grid (`make_showroom.py` generates the CSV) |
| `tmp/` | Cache for downloaded zips + DSF text staging (auto-deleted after a build) |
| `doc/pubacc_asr_intro.pdf`, `doc/patower-4.pdf`, `doc/asr_codes.pdf` | FCC reference documents (see below) |

## Quick start

```bat
python fcc_towers.py
```

This downloads `r_tower.zip` (FCC complete **registration** data, ~38 MB) to
`tmp\`, parses it, and writes `active_antennas.csv`. Everything after the first
download is a few seconds (the zip is cached in `tmp\`; use `--force` to
re-download).

Useful options:

```bat
:: Use the application-history archive (a_tower.zip, ~198 MB) instead
python fcc_towers.py --source application

:: Restrict to constructed structures only (status C), custom output file
python fcc_towers.py --status C --out active_constructed.csv

:: Use a zip you already have on disk (skips download entirely)
python fcc_towers.py --zip-path tmp\r_tower.zip

:: python fcc_towers.py -h  for the full list
```

## Where the data comes from

FCC ULS public access files (pipe-delimited text inside a zip), per the FCC
documents included in this folder:

- `pubacc_asr_intro.pdf` — "ULS Database Public Access Files" (file layout,
  naming convention, join keys)
- `patower-4.pdf` — field-by-field definitions of the RA/CO/... records
- `asr_codes.pdf` — code meanings (status, purpose, archive flag, ...)

Two relevant archives:

| Archive | Content | Records |
|---|---|---|
| `r_tower.zip` (default) | **Registrations** = currently registered (active) antenna structures | ~197k |
| `a_tower.zip` | **Applications** = full application history (granted, dismissed, withdrawn, ...) | ~1.5M |

For an "active antennas" list, registrations are the canonical source, so the
program defaults to `r_tower.zip`. The application archive is available via
`--source application` if you need the application history.

Inside each zip the program uses two files:

- **`RA.dat`** — one record per application/registration (49 pipe-delimited
  fields): status, purpose, city/state, heights (in **meters**), structure
  type, FAA study number, ...
- **`CO.dat`** — one record per structure coordinate (18 fields): lat/lon in
  deg-min-sec plus total-seconds fields. Array structures have several records
  (one per array element), distinguished by the `array_position`/`array_total`
  columns.

Records are joined on the **File Number** field.

## "Active" filter

FCC codes (see `asr_codes.pdf`):

- Archive Flag: `C` = current version, `A` = archive (superseded)
- Status: `C` = Constructed, `G` = Granted, `D` = Dismissed, `W` = Withdrawn,
  `I` = Dismantled, `A` = Canceled, `T` = Terminated, `P` = Pending, ...

Defaults:

- registrations: `Archive = C` **and** `Status in {C, G}`
  (≈160k structures → 164k rows including array elements)
- applications: `Status = G` (Granted)

Override with `--status C` (or `--status C,G,D,...`) and
`--include-archived`.

## Output columns

`active_antennas.csv` columns:

- Identifiers: `file_number`, `registration_number`, `usi`
- Location: `state`, `city`, `latitude`, `longitude` (decimal degrees, NAD83 —
  within a few meters of WGS84), `coordinate_type` (T tower / A array),
  `array_position`, `array_total`
- Structure: `structure_type` (TOWER, LTOWER lattice, MTOWER monopole,
  GTOWER guyed, POLE, MAST, ...)
- Heights (meters as recorded **and** feet = m × 3.28084):
  `height_structure_*` (structure height), `ground_elevation_*` (ground
  elevation), `overall_height_ag_*` (structure + ground, above ground),
  `overall_height_amsl_*` (above mean sea level)
- Metadata: `status`, `purpose`, `faa_study_number`, `date_action`

Rows for active registrations that have no coordinate record are still written
with blank lat/lon (3 in the current data set) so nothing is silently dropped.

## X-Plane 12 overlay scenery (Phase 2)

`build_overlay.py` turns `active_antennas.csv` into a normal X-Plane 12
scenery pack that draws a placeholder tower object at every antenna location.

**How it works:** antennas are grouped into X-Plane 1° sub-regions (files like
`+40-101.dsf`) inside 10° big-region folders, matching exactly what World
Editor emits. Each region is written as a DSF *text* file (with
`PROPERTY sim/overlay 1` so it renders above the terrain as an overlay) and
converted to X-Plane 12's native binary (`XPLNEDSF` magic) with Laminar's
`DSFTool.exe --text2dsf`. No binary is written by hand.

**Placeholder objects:** the FCC structure height (meters) selects the object
— shortest object whose cap is ≥ the height:

| Height (m) | Object | Actual height |
|---|---|---|
| ≤ 10 | `comm_tower_10m_1` (airport scenery library) | ~10 m |
| 11–15 | `comm_tower_15m_1` | ~15 m |
| 16–25 | `comm_tower_25m_1` | ~25 m |
| 26–50 | `radio_50` (900 us objects) | 50 m |
| 51–100 | `radio_100` | 100 m |
| 101–150 | `radio_140` | 150 m |
| 151–200 | `radio_200` | 200 m |
| 201–250 | `radio_250` | 250 m |
| 251–300 | `radio_300` | 300 m |
| 301+ | `radio_350` | 300 m (cap) |

The radio-tower set is **meter-scaled** — verified by measuring the OBJ
geometry (r50 = 50 m, r100 = 100 m, r140 = 150 m, r200 = 200 m, r350 = 300 m).
The smallest stock radio tower is 50 m, so towers ≤ 25 m use the
`comm_tower_10m/15m/25m` family from `airport scenery/library.txt` (variants
`_1`/`_2`/`_3` are different styles) for a much better size match.
DSFTool's text format does not preserve a per-object scale, so size variety
comes from object choice, not scaling.
A CSV row may also carry an optional `object_path` column with an exact
X-Plane resource path, which bypasses the height mapping — the hook for
custom/public-domain models (`make_showroom.py` uses it). Swap the
`TOWER_OBJECTS` table (or extend `--object`) once such models are available.

### Build

```bat
python build_overlay.py                :: full pack: ~1,104 regions, 164,241 towers, ~7 MB, ~7 s
python build_overlay.py --state TX --max-objects 300   :: quick test subset
python build_overlay.py --min-height 100               :: only tall structures
python build_overlay.py --dry-run                      :: report the plan only
python build_overlay.py -h                             :: all options
```

Requires `DSFTool.exe` (part of the X-Plane SDK,
<https://developer.x-plane.com>) on your PATH, or pass `--dsftool <path>`.

### Install + test

```bat
xcopy /e /i output\FCC_Towers "C:\X-Plane 12\Custom Scenery\FCC_Towers"
```

(Reverting the object table is a one-line-per-bucket edit to `TOWER_OBJECTS`
in `build_overlay.py` plus a ~7 s rebuild, if it ever becomes necessary.)

X-Plane auto-detects the `Earth nav data` folder (same layout as a World
Editor export) and lists the pack in
`C:\X-Plane 12\Custom Scenery\scenery_packs.ini`.

**Pack order matters:** the `FCC_Towers` entry must sit **above (before) the
simHeaven entries** in `scenery_packs.ini`. If it is listed below them,
X-Plane silently fails to load our region files wherever simHeaven also ships
an overlay for that region (e.g. `+40-105`, Denver metro) — nothing is logged,
the towers just don't appear. Moving the entry above simHeaven fixed it.

Then fly to one of these tall, identifiable test towers:

| Tower | Location | Lat / Lon | Region |
|---|---|---|---|
| 610 m GTOWER | HITCHCOCK, TX | 29.30008, -95.11131 | +29-96 |
| 610 m TOWER | ERA, TX | 33.48486, -97.41244 | +33-97 |
| 609 m TOWER | STOWELL, TX | 29.69792, -94.40258 | +29-94 |

The `radio_*` placeholders are confirmed rendering in X-Plane 12.4 (e.g. the
610 m towers at Hitchcock, TX and the Denver metro). The `comm_tower_*` family
from `airport scenery/library.txt` is now used for the ≤ 25 m buckets (see
above) and is placed through the same `OBJECT_DEF` mechanism as the radio
towers; `antenna_5m_*` / `antenna_8m_*` are also available via the
`object_path` column.

### Data quirks handled

- 3 rows with (0,0)-area coordinates (data errors from CO/AURORA and
  KS/WELLINGTON registrations) are skipped rather than placed in the Gulf
  of Guinea.
- Alaska (1,284 points at lat 50–70) and other outlying territories are
  legitimate and included.

## Notes / known quirks

- The FCC CDN (Akamai) rejects requests with custom or browser-like
  User-Agent headers (HTTP 403). `fcc_towers.py` therefore uses Python's
  default UA, which is accepted. If you change the download code, keep that in
  mind (plain `curl` also works).
- Source data has gaps: a few thousand records lack structure type, and 3
  active registrations have no coordinates at all.
- A few coordinates fall outside the 48 states (Alaska, Hawaii, Puerto Rico,
  USVI, American Samoa) — that's expected for a national database.
- The same physical tower can appear in more than one registration (e.g.
  replacement structures); deduplication is left as a future step.
