# FCC Active Antenna Towers

Download the FCC **Antenna Structure Registration (ASR)** database and build a
CSV of **active antenna structures** with location (lat/lon), tower type, and
tower heights.

## Files

| File | Purpose |
|---|---|
| `fcc_towers.py` | The program (Python 3, standard library only — no dependencies) |
| `active_antennas.csv` | Output: one row per active antenna coordinate (~164k rows) |
| `build_overlay.py` | Step 2: turns the CSV into an X-Plane 12 overlay scenery pack |
| `output/FCC_Towers/` | Step 2 output: the scenery pack (copy into `C:\X-Plane 12\Custom Scenery`) |
| `synthetic_antennas.csv` | Showroom input: a small grid of sample tower objects near Akron, CO |
| `output/FCC_TowerShowroom/` | Showroom scenery pack built from that grid (`make_showroom.py` generates the CSV) |
| `tools/gen_monopole.py` | Generates the grey monopole cell-tower objects (50/75/100/150 m) |
| `objects/` | The generated monopole meshes + texture; shipped in both packs (regenerate with `python tools/gen_monopole.py`) |
| `tmp/` | Cache for downloaded zips + DSF text staging (auto-deleted after a build) |
| `doc/pubacc_asr_intro.pdf`, `doc/patower-4.pdf`, `doc/asr_codes.pdf` | FCC reference documents (see below) |

## Quick start

```shell
python fcc_towers.py
```

This downloads `r_tower.zip` (FCC complete **registration** data, ~38 MB) to
`tmp\`, parses it, and writes `active_antennas.csv`. Everything after the first
download is a few seconds (the zip is cached in `tmp\`; use `--force` to
re-download).

Then build the X-Plane overlay pack (this is the normal full build — all states,
with the default 300 ft exclusion zones):

```shell
python build_overlay.py
```

It writes `output\FCC_Towers\`, which you copy into `C:\X-Plane 12\Custom
Scenery` (see the X-Plane overlay section below).

## Step 1: Download FCC Towers List

Run `python fcc_towers.py` (shown in Quick start above).

### fcc_towers.py Options

```shell
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

### "Active" filter

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

### Output columns

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

## Step 2: Generate X-Plane 12 overlay scenery

`build_overlay.py` turns `active_antennas.csv` into a normal X-Plane 12
scenery pack that draws a placeholder tower object at every antenna location.

**How it works:** antennas are grouped into X-Plane 1° sub-regions (files like
`+40-101.dsf`) inside 10° big-region folders, matching exactly what World
Editor emits. Region names are zero-padded to X-Plane's convention
(latitude 2 digits, longitude 3: `+20-090`, `+00+010`) — X-Plane matches
folder names as literal strings, so `+20-90` would never be found. Each region is written as a DSF *text* file (with
`PROPERTY sim/overlay 1` so it renders above the terrain as an overlay) and
converted to X-Plane 12's native binary (`XPLNEDSF` magic) with Laminar's
`DSFTool.exe --text2dsf`. No binary is written by hand.

**Placeholder objects:** the FCC `structure_type` selects a style *family*,
and the structure height (meters) selects the shortest object in that family
whose cap is ≥ the height:

- **big** — TOWER, LTOWER, GTOWER, MTOWER and the `N…N` multi-structure
  codes (e.g. `3TA2`, `2TOWER`, digits stripped first):

  | Height (m) | Object | Actual height |
  |---|---|---|
  | ≤ 10 | `comm_tower_10m_1` (airport scenery library) | ~10 m |
  | 11–15 | `comm_tower_15m_1` | ~15 m |
  | 16–40 | `comm_tower_25m_1` | ~25 m |
  | 41–50 | `radio_50` (900 us objects) | 50 m |
  | 51–100 | `radio_100` | 100 m |
  | 101–150 | `radio_140` | 150 m |
  | 151–200 | `radio_200` | 200 m |
  | 201–250 | `radio_250` | 250 m |
  | 251+ | `radio_300` | 300 m (cap — tallest stock radio mesh) |

- **small** — POLE, UPOLE, MAST: the same ramp plus finer buckets at the
  bottom (`antenna_5m_01` ≤ 5 m, `antenna_8m_01` ≤ 8 m,
  `comm_tower_12m_1` ≤ 12 m).
- **monopole** — MTOWER, MTA, POLE, UPOLE, MAST **above 40 m**: the generated
  grey monopole cell towers `monopole_50` / `monopole_75` / `monopole_100` /
  `monopole_150`, generated by `tools/gen_monopole.py`, shipped in the pack's
  `objects/` folder and EXPORTed via its `library.txt` as
  `fcc_towers/monopole_*.obj`. Stock scenery has no monopole-style object
  above 25 m, so these fill the gap; 93% of those FCC types are 40–75 m, and
  anything above 150 m clamps to the 150 m mesh. At ≤ 40 m the stock grey
  `comm_tower_*` meshes are still used (better size match).
- **suppressed (not drawn)** — building-attached and non-tower structures:
  B, BANT, BTWR, BMAST, BPOLE, BPIPE, TANK, TREE, SILO, PIPE, STACK, SIGN
  (≈5,140 of the 164,282 records: antennas *on* buildings, plus tanks,
  trees, silos, stacks and signs).

Blank/unknown types default to the big family (a tower beats nothing).
The radio-tower set is **meter-scaled** — verified by measuring the OBJ
geometry (r50 = 50 m, r100 = 100 m, r140 = 150 m, r300 = 300 m);
`r350`…`r650` all export the same 300 m mesh, so nothing stock exists
above 300 m. The smallest stock radio tower is 50 m, so short structures
use the `comm_tower_*` / `antenna_*` families from
`airport scenery/library.txt` (variants `_1`/`_2`/`_3` are different
styles).
DSFTool's text format does not preserve a per-object scale, so size variety
comes from object choice, not scaling.

A CSV row may also carry an optional `object_path` column with an exact
X-Plane resource path, which always wins over type/height selection —
the hook for custom/public-domain models (`make_showroom.py` uses it).
Swap the objects in the `BIG_TOWERS` / `SMALL_MASTS` tables (or force one
family with `--object big|small`) once better models are available.
The grey monopole meshes can be regenerated with
`python tools/gen_monopole.py` (`--heights 50 75 100 150 --out objects`).

### Scenery Build Options

```shell
python build_overlay.py                :: full pack: ~1,096 regions, 155,041 towers, ~16 MB
python build_overlay.py --state TX --max-objects 300   :: quick test subset
python build_overlay.py --min-height 100               :: only tall structures
python build_overlay.py --dry-run                      :: report the plan only
python build_overlay.py -h                             :: all options
```

Requires `DSFTool.exe` (part of the X-Plane SDK,
<https://developer.x-plane.com>) on your PATH, or pass `--dsftool <path>`.

### Exclusion zones (suppress other packs' towers at the same site)

By default the build emits a `sim/exclude_obj` **and** `sim/exclude_fac`
rectangle around every drawn tower. X-Plane uses these to **cull objects and
facades from lower-priority scenery** — packs that come **after** `FCC_Towers`
in `scenery_packs.ini` (e.g. SimHeaven / X-World Pro), and X-Plane's own
autogen primitives. The declaring DSF is exempt, so **our own towers always
draw** while a co-located impostor from a lower-priority pack is suppressed.
This is what removes the "double tower" you would otherwise see where another
pack (or autogen) also places a radio tower at the same site (verified at
Hitchcock, TX, the Northglenn array, and Simpsonville, KY).

**Both properties are required.** At Simpsonville, KY an autogen impostor
rendered next to our tower with only `sim/exclude_obj` (and even SimHeaven's
own 1°×1° full-cell exclusions did not remove it); adding `sim/exclude_fac`
removed it. `fac` = facades — X-Plane's class of building/autogen scenery
(sibling to `sim/require_facade` in the DSF spec).

#### Exclusion Zone Options

```shell
python build_overlay.py --exclude-radius-ft 500   :: half-size of each zone (default 300 ft)
python build_overlay.py --no-exclude              :: emit no exclusion zones at all
python build_overlay.py --exclude-min-height 100  :: only zone towers >= this height (m); default 0
```

Two honest trade-offs:

- **Far-range under-cull.** A lower-priority impostor more than the radius
  (default 300 ft / ~90 m) away from the FCC position is *not* culled and will
  still double-draw at distance. If a specific site misplaces its impostor
  that far out, raise `--exclude-radius-ft` and rebuild.
- **Over-removal.** The zone culls *any* lower-priority object or facade
  inside it, not just towers — so legitimate base detail (houses, equipment)
  from another pack near a tower may also be suppressed. That is accepted: for
  a pilot, the tower's position, height and silhouette matter far more than
  the scenery at its base.

The zones add most of the pack's size (~7 MB without them). The exclusion
mechanism is pack-independent: it works for whatever is installed below us, so
it does not depend on buying a particular scenery product.

### Install + test

```shell
xcopy /e /i output\FCC_Towers "C:\X-Plane 12\Custom Scenery\FCC_Towers"
```

(Reverting object choices is a one-line-per-bucket edit to the `BIG_TOWERS`
/ `SMALL_MASTS` tables in `build_overlay.py` plus a ~7 s rebuild, if it
ever becomes necessary.)

X-Plane auto-detects the `Earth nav data` folder (same layout as a World
Editor export) and lists the pack in
`C:\X-Plane 12\Custom Scenery\scenery_packs.ini`.

**Pack order matters:** the `FCC_Towers` entry must sit **above (before) the
simHeaven (or similar) entries** in `scenery_packs.ini`. If it is listed below them,
X-Plane silently fails to load our region files wherever simHeaven also ships
an overlay for that region (e.g. `+40-105`, Denver metro) — nothing is logged,
the towers just don't appear.

Then fly to one of these tall, identifiable test towers:

| Tower | Location | Lat / Lon | Region |
|---|---|---|---|
| 610 m GTOWER | HITCHCOCK, TX | 29.30008, -95.11131 | +29-96 |
| 610 m TOWER | ERA, TX | 33.48486, -97.41244 | +33-97 |
| 609 m TOWER | STOWELL, TX | 29.69792, -94.40258 | +29-94 |

The `radio_*` placeholders are confirmed rendering in X-Plane 12.4 (e.g. the
610 m towers at Hitchcock, TX and the Denver metro). The `comm_tower_*` family
from `airport scenery/library.txt` is now used for the ≤ 40 m buckets (see
above) and is placed through the same `OBJECT_DEF` mechanism as the radio
towers; `antenna_5m_*` / `antenna_8m_*` are also available via the
`object_path` column.

### One tower per registration (dedup)

FCC co-located array sites list **two rows per registration** — one
`coordinate_type = T` (true/exact) and one `A` (approximate), e.g. the
Northglenn 4TA1-4TA4 array is 8 rows that are really 4 towers. `build_overlay.py`
places **exactly one object per registration**, at its **`T` coordinate**
(the most accurate position), and drops the `A` row. If a registration ever
lacks a `T` row, its first row is used. This removes the phantom duplicate
silhouettes the raw rows would otherwise produce. (~4,090 of the 164,282 rows
are dropped this way; 97.5% of registrations have a single row and are
unaffected.)

### Data quirks handled

- 3 rows with (0,0)-area coordinates (data errors from CO/AURORA and
  KS/WELLINGTON registrations) are skipped rather than placed in the Gulf
  of Guinea.
- Alaska (1,284 points at lat 50–70) and other outlying territories are
  legitimate and included.

## Showroom (object test gallery)

`make_showroom.py` + `build_overlay.py` build `output/FCC_TowerShowroom`: a
fixed grid of **every stock antenna object** the sim can offer **plus the
generated grey monopole set**, at their true heights, standing on a
solid-white plinth near Akron, CO. The point is a
permanent place to judge placeholder styles and heights in flight — and
later, candidate custom/public-domain models — without hunting real
towers. It is placed through the same `object_path` column as custom
models, so it is independent of the type/height selection rules.

**Layout** — SE corner at 40.1932349, −103.2108206; rows run north at
125 m spacing, columns run west at 125 m (ragged on the west; a road just
east of the first column lines up with every row's start). The white plinth
extends 125 m beyond the grid on all sides:

| Row (S→N) | Contents |
|---|---|
| 1 | `antenna_5m` styles 01…09 (5 m) |
| 2 | `antenna_8m` styles 01…06 (8 m) |
| 3 | `comm_tower` 10 m styles 1…3 |
| 4 | `comm_tower` 12/15/25 m styles (12–25 m) |
| 5 | radio towers r50 r100 r140 r200 r250 r300 (50–300 m) |
| 6 | `antenna_100m` dish style (100 m) |
| 7 | generated grey monopole 50/75/100/150 (the pack's own `fcc_towers/monopole_*.obj`) |

The stock smokestack is intentionally absent: it is a DSF-700 object and
X-Plane 12 does not render it. The `5×5`/`10×10` radio series export
the same physical files, so they would look identical. Full rationale is in
the `make_showroom.py` header.

**Build:**

```shell
python make_showroom.py                     :: regenerate synthetic_antennas.csv
python build_overlay.py --csv synthetic_antennas.csv ^
    --out output\FCC_TowerShowroom --plinth-z 1
```

(`--plinth-z 1` merely switches the draped white plinth on; the polygon
drapes onto the terrain mesh.)

**Install:**

```shell
xcopy /e /i output\FCC_TowerShowroom "C:\X-Plane 12\Custom Scenery\FCC_TowerShowroom"
```

**Uninstall:**

```shell
rd /s /q "C:\X-Plane 12\Custom Scenery\FCC_TowerShowroom"
```

Then remove the `FCC_TowerShowroom` line from
`C:\X-Plane 12\Custom Scenery\scenery_packs.ini` (with X-Plane closed).

**Viewing:** depart **KAKO (Akron/Colorado-Yampa)** and fly **north** about
8 nm (15 km). The white plinth rectangle appears over the fields north of
the airport; the object grid stands on it (row 1 at the south end, row 5's
300 m radio tower is the landmark). Fly low — a few hundred feet AGL —
to judge the small rows (1–4).

As with `FCC_Towers`: if the objects do not appear, make sure the
`FCC_TowerShowroom` entry sits **above (before) the simHeaven (or similar) entries** in
`scenery_packs.ini` (same overlay conflict, silent failure).

## Notes / known quirks

- The FCC CDN (Akamai) rejects requests with custom or browser-like
  User-Agent headers (HTTP 403). `fcc_towers.py` therefore uses Python's
  default UA, which is accepted. If you change the download code, keep that in
  mind (plain `curl` also works).
- Source data has gaps: a few thousand records lack structure type, and 3
  active registrations have no coordinates at all.
- A few coordinates fall outside the 48 states (Alaska, Hawaii, Puerto Rico,
  USVI, American Samoa) — that's expected for a national database.
- **Within**-registration array-element duplicates are now handled (one tower
  per registration, preferring the `T` coordinate — see above). The same
  **physical** tower appearing under more than one *registration number* (e.g.
  a replacement structure) is a separate case and is *not* deduped; that remains
  a possible future refinement.
