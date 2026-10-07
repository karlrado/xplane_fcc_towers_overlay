# Design and operation notes

This document explains how `fcc_towers.py` works and why: where the data
comes from, how each tower is turned into an X-Plane object, how the
exclusion zones and deduplication behave, and the DSFTool plumbing.
`README.md` is the short user guide; this is the deep end.

## Where the data comes from

FCC ULS public access files (pipe-delimited text inside a zip), per the FCC
documents in `doc/`:

- `doc/pubacc_asr_intro.pdf` — "ULS Database Public Access Files" (file
  layout, naming convention, join keys)
- `doc/patower-4.pdf` — field-by-field definitions of the RA/CO/... records
- `doc/asr_codes.pdf` — code meanings (status, purpose, archive flag, ...)

Two relevant archives:

| Archive | Content | Records |
|---|---|---|
| `r_tower.zip` (default) | **Registrations** = currently registered (active) antenna structures | ~197k |
| `a_tower.zip` | **Applications** = full application history (granted, dismissed, withdrawn, ...) | ~1.5M |

For an "active antennas" list, registrations are the canonical source, so
the program defaults to `r_tower.zip`. The application archive is available
via `--source application` if you need the application history.

The FCC refreshes these public access files **weekly**, so the contents
(which towers are active, their coordinates and heights) drift over time.
Rebuilding periodically picks up the changes; the downloaded zip is cached
in `tmp\` and `--no-download` reuses it when you don't want the data to
change (e.g. while testing).

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

FCC codes (see `doc/asr_codes.pdf`):

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
- Optional: `object_path` — an exact X-Plane resource path that always wins
  over type/height selection (used by the showroom grid and the additional
  sites)

Rows for active registrations that have no coordinate record are still written
with blank lat/lon (3 in the current data set) so nothing is silently dropped.

## How the pack is built

`build` turns `active_antennas.csv` into a normal X-Plane 12 scenery pack:

- Antennas are grouped into X-Plane 1° sub-regions (files like `+40-101.dsf`)
  inside 10° big-region folders, matching exactly what World Editor emits.
  Region names are zero-padded to X-Plane's convention (latitude 2 digits,
  longitude 3: `+20-090`, `+00+010`) — X-Plane matches folder names as
  literal strings, so `+20-90` would never be found.
- Each region is written as a DSF *text* file (with `PROPERTY sim/overlay 1`
  so it renders above the terrain as an overlay) and converted to X-Plane
  12's native binary (`XPLNEDSF` magic) with Laminar's DSFTool `--text2dsf`.
  No binary is written by hand. Conversions run in parallel (`--workers`).
- Text staging lives under `tmp/` and is deleted after the build unless
  `--keep-text` is given; `--text-only` stops before conversion entirely;
  `--dry-run` reports the region/object plan without writing anything.

The result is a normal scenery pack:

```
<out>/
    Earth nav data/
        +40-110/+40-101.dsf
        +29-90/+29-96.dsf
        ...
    objects/            generated monopole meshes + library.txt
```

Copy the `<out>` folder into `C:\X-Plane 12\Custom Scenery` and it loads
as an overlay.

## Which object each tower gets

The FCC `structure_type` selects a style *family*, and the structure height
(meters) selects the shortest object in that family whose cap is ≥ the
height:

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
  `comm_tower_*` meshes are still used (better size match). The meshes can be
  regenerated with `python tools/gen_monopole.py` (`--heights 50 75 100 150
  --out objects`).
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
`airport scenery/library.txt`.

DSFTool's text format does not preserve a per-object *scale*, so size variety
comes from object choice, not scaling.

### Visual variant rotation

The stock library ships several visual styles for some heights
(`comm_tower_10m_1/2/3`, `comm_tower_12m_1/2`, `comm_tower_15m_1/2`,
`comm_tower_25m_1/2/3`, `antenna_5m_01..09`, `antenna_8m_01..06`). Instead of
always drawing style `_1`, `pick_variant()` rotates through the set
deterministically: the SHA-256 digest of the tower's FCC registration number
(or its rounded coordinates when absent) selects the variant. The same tower
therefore always gets the same style (stable across weekly FCC refreshes and
across Python processes — the built-in `hash()` is salted per process and
would not be), while different towers spread across the available styles.
The radio-tower set and the generated monopoles have no variant sets and are
used as-is. `OBJECT_VARIANTS` / `pick_variant` live in the object-selection
section of `fcc_towers.py`.

### `--radio-only`

Pilot-oriented mode: draw only the tall red/white lattice radio towers
(`feat_RadioTower`), skipping grey monopole and comm-tower-style objects.
Explicit `object_path` rows (additional sites) still draw. Useful when the
short cell-style towers are not wanted (e.g. to save draw calls).

### Swapping in custom models

A CSV row may carry an `object_path` column with an exact X-Plane resource
path, which always wins over type/height selection — the hook for
custom/public-domain models (the showroom and additional sites use it). The
stock tables can also be swapped in `BIG_TOWERS` / `SMALL_MASTS` (or one
family forced with `--object big|small`) once better models are available.

## Exclusion zones (suppress other packs' towers at the same site)

By default the build emits a `sim/exclude_obj` **and** `sim/exclude_fac`
rectangle around every drawn tower. X-Plane uses these to **cull objects and
facades from lower-priority scenery** — packs that come **after** `FCC_Towers`
in `scenery_packs.ini` (e.g. SimHeaven / X-World Pro), and X-Plane's own
autogen primitives. The declaring DSF is exempt, so **our own towers always
draw** while a co-located impostor from a lower-priority pack is suppressed.
This is what removes the "double tower" you would otherwise see where another
pack (or autogen) also places a radio tower at the same site (verified at
Hitchcock TX, the Northglenn array, and Simpsonville KY).

**Both properties are required.** At Simpsonville, KY an autogen impostor
rendered next to our tower with only `sim/exclude_obj` (and even
SimHeaven's own 1°×1° full-cell exclusions did not remove it); adding
`sim/exclude_fac` removed it. `fac` = facades — X-Plane's class of
building/autogen scenery (sibling to `sim/require_facade` in the DSF spec).
The DSF spec never says what "facade" covers for towers; the pairing
`exclude_obj` + `exclude_fac` is what was proven to work empirically.

Options:

```shell
python fcc_towers.py --exclude-radius-ft 500   :: half-size of each zone (default 300 ft)
python fcc_towers.py --no-exclude              :: emit no exclusion zones at all
python fcc_towers.py --exclude-min-height 100  :: only zone towers >= this height (m); default 0
```

Two honest trade-offs:

- **Far-range under-cull.** A lower-priority impostor more than the radius
  (default 300 ft / ~90 m) away from the FCC position is *not* culled and
  will still double-draw at distance. If a specific site misplaces its
  impostor that far out, raise `--exclude-radius-ft` and rebuild.
- **Over-removal.** The zone culls *any* lower-priority object or facade
  inside it, not just towers — so legitimate base detail (houses, equipment)
  from another pack near a tower may also be suppressed. That is accepted:
  for a pilot, the tower's position, height and silhouette matter far more
  than the scenery at its base.

The zones add most of the pack's size (~7 MB without them). The exclusion
mechanism is pack-independent: it works for whatever is installed below us,
so it does not depend on buying a particular scenery product.

## One tower per registration (dedup)

FCC co-located array sites list **two rows per registration** — one
`coordinate_type = T` (true/exact) and one `A` (approximate), e.g. the
Northglenn 4TA1-4TA4 array is 8 rows that are really 4 towers. The build
places **exactly one object per registration**, at its **`T` coordinate**
(the most accurate position), and drops the `A` row. If a registration ever
lacks a `T` row, its first row is used. This removes the phantom duplicate
silhouettes the raw rows would otherwise produce. (~4,090 of the 164,282 rows
are dropped this way; 97.5% of registrations have a single row and are
unaffected.)

The same **physical** tower appearing under more than one *registration
number* (e.g. a replacement structure) is a separate case and is *not*
deduped; that remains a possible future refinement.

## Additional sites (`additional_sites.csv`)

Hand-curated towers the FCC data does not contain — e.g. the NIST WWV/WWVB
time-signal masts near Fort Collins, CO, which predate the 1981 ASR program
and never appear in ULS. Columns: `name, lat, lon, object_path
(optional), height_m (optional), exclusion_radius_ft (optional)`.

- Rows with an `object_path` add a tower placement (bypassing the
  state/height filters, `--radio-only`, and variant rotation).
- Rows with an `exclusion_radius_ft` (and no object) add a **site-wide
  exclusion box** centered on the lat/lon — used for the multi-mast WWV
  array, where one generous box around the site beats per-tower boxes.
- Missing file or bad rows are skipped silently.

Disable with `--no-additional-sites`, point elsewhere with
`--additional-sites <path>`.

## Showroom (object test gallery)

`python fcc_towers.py showroom` builds `output/FCC_TowerShowroom`: a fixed
grid of **every stock antenna object** the sim can offer **plus the generated
grey monopole set**, at their true heights, standing on a solid-white plinth
near Akron, CO. The point is a permanent place to judge placeholder styles
and heights in flight — and later, candidate custom/public-domain models —
without hunting real towers. The grid CSV (`showroom_antennas.csv`) is
regenerated by the command itself, and every row uses the `object_path`
column, so the showroom is independent of the type/height selection rules.

**Layout** — SE corner at 40.1932349, −103.2108206; rows run north at
125 m spacing, columns run west at 125 m (ragged on the west; a road just
east of the first column lines up with every row's start). The white plinth
extends 125 m beyond the grid on all sides (tuned via the
`SHOWROOM_PLINTH_*` constants at the top of `fcc_towers.py`):

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
the same physical files, so they would look identical.

**Viewing:** the tall rows are visible from the AKO runway itself — a nice
first confirmation that the pack loaded. To judge the objects properly,
depart **KAKO (Akron/Colorado-Yampa)** and fly **north** about 8 nm (15
km). The white plinth rectangle appears over the fields north of the
airport; the object grid stands on it (row 1 at the south end, row 5's
300 m radio tower is the landmark). Fly low — a few hundred feet AGL — to
judge the small rows (1–4).

As with `FCC_Towers`: if the objects do not appear, make sure the
`FCC_TowerShowroom` entry sits **above (before) the simHeaven (or similar)
entries** in `scenery_packs.ini` (same overlay conflict, silent failure).

## DSFTool

`fcc_towers.py` needs Laminar's DSFTool only for the final text→binary
conversion, and finds it in this order:

1. an explicit `--dsftool <path>`;
2. `DSFTool.exe` / `DSFTool` on the PATH;
3. a binary built from the vendored source in this repo
   (`sh tools/dsftool/build.sh`).

The complete vendored xptools source (pinned commit, licensed) lives in
`tools/dsftool/` — see its README for build requirements, platform support,
and official prebuilt download links. A Linux build from that source,
Laminar's official prebuilt Linux binary, and the official Windows
`DSFTool.exe` 2.4.0-b1 all produce **byte-identical** DSF output for
identical text input, so the choice of binary does not change the pack.

Two operational rules learned the hard way:

- DSFTool's CLI is purely positional — `--text2dsf <text> <dsf>` /
  `--dsf2text <dsf> <text>`. There is **no `-o` option**; any other token is
  taken as a file name. Never invent options and never convert a file "in
  place" (a made-up `-o` flag once clobbered installed DSF files during
  this project's development; the script's own converter is written to be
  immune).
- `fcc_towers.py` always passes distinct input/output paths and checks the
  return code, so the script itself is safe against this.

## Known quirks and caveats

Several items below depend on the contents of the FCC data, which is
refreshed weekly; treat the specific counts as "as of the first release"
(October 2026) rather than permanent facts.

- The FCC CDN (Akamai) rejects requests with custom or browser-like
  User-Agent headers (HTTP 403). `fcc_towers.py` therefore uses Python's
  default UA, which is accepted. If you change the download code, keep that
  in mind (plain `curl` also works).
- Source data has gaps: a few thousand records lack structure type, and 3
  active registrations have no coordinates at all (still listed, with blank
  lat/lon).
- A few coordinates fall outside the 48 states (Alaska, Hawaii, Puerto Rico,
  USVI, American Samoa) — that's expected for a national database.
- 3 rows with (0,0)-area coordinates (data errors from CO/AURORA and
  KS/WELLINGTON registrations) are skipped rather than placed in the Gulf
  of Guinea.
- Coordinates are NAD83, within a few meters of WGS84; observed base
  offsets of a few feet versus aerial photography are consistent with FCC
  position accuracy, not a bug in this pack.
