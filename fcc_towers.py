#!/usr/bin/env python3
"""
fcc_towers.py — Build the FCC_Towers and FCC_TowerShowroom X-Plane 12
scenery packs from FCC Antenna Structure Registration (ASR) data.

One script, three commands:

    python fcc_towers.py                 # = build (default)
    python fcc_towers.py build           # download fresh FCC data + build the
                                         # FCC_Towers pack (output/FCC_Towers)
    python fcc_towers.py showroom        # build the FCC_TowerShowroom pack
                                         # (object-style gallery; no download)
    python fcc_towers.py csv             # download fresh FCC data and write
                                         # active_antennas.csv only

The FCC publishes a new complete registration archive weekly, so the default
is to download fresh data on every build.  Use --no-download to reuse the
cached zip (tmp/r_tower.zip) or --zip-path <file> to use a local zip.

Data sources
------------
The FCC ULS public access files are pipe-delimited text files inside a zip.
Two complete "tower" archives are relevant (see the FCC "ULS Database Public
Access Files" introduction document):

* r_tower.zip — REGISTRATIONS.  The currently registered (i.e. ACTIVE)
  antenna structures.  This is the recommended source for an "active
  antennas" list.  ~200k registrations / ~200k coordinate records.

* a_tower.zip — APPLICATIONS.  The full application history (granted,
  dismissed, withdrawn, ...).  ~1.5M application records.  Use
  --source application if you specifically want this archive.

Files used inside the zip (field layouts per the FCC "patower" definitions):
* RA.dat — one record per application/registration: 49 fields
           (status, purpose, city/state, heights in METERS, structure type)
* CO.dat — one record per structure coordinate: 18 fields
           (lat/lon in deg-min-sec + total seconds; arrays have several)
Records are joined on the File Number field (field 3 in both files).

"Active" default filter
------------------------
* registrations: Archive Flag = C (current version) AND Status in {C, G}
  (C = Constructed, G = Granted)
* applications:  Status = G (Granted)

Use --status / --include-archived to override.

CSV
---
One row per (active RA record x coordinate record).  Lat/lon are decimal
degrees (FCC data is NAD83, which is within a few meters of WGS84).  Heights
are written both in meters (as recorded) and feet (m x 3.28084).

Pack build
----------
1. Every antenna is assigned to an X-Plane **1-degree sub-region**
   (e.g. ``+40-101``) and its parent **10-degree "big-region" folder**
   (e.g. ``+40-110``) -- exactly the layout World Editor emits.
2. For each sub-region we write a DSF *text* file: the region header
   (``PROPERTY sim/...``), one ``OBJECT_DEF`` per distinct placeholder
   object, one ``OBJECT <index> <lon> <lat> <heading>`` line per antenna,
   and ``sim/exclude_obj`` / ``sim/exclude_fac`` rectangles that suppress
   conflicting lower-priority scenery (default: 300 ft around each tower).
3. Each text file is converted to X-Plane 12's native binary (magic
   ``XPLNEDSF``) with Laminar's ``DSFTool --text2dsf``.

The result is a normal scenery pack:

    <out>/
        Earth nav data/
            +40-110/+40-101.dsf
            +29-90/+29-96.dsf
            ...

Copy the ``<out>`` folder into ``C:\\X-Plane 12\\Custom Scenery`` and it
will load as an overlay (the DSF carries ``PROPERTY sim/overlay 1``).

Placeholder objects
-------------------
The FCC ``structure_type`` selects a style family, and the structure height
(meters) selects the object within that family:

* big (TOWER, LTOWER, GTOWER, MTOWER, ...): the stock
  ``comm_tower_10m/15m/25m`` family (airport scenery library) up to 40 m
  -- the 25 m mesh stands in to 40 m because the smallest stock radio
  tower is 50 m -- then the stock radio-tower set (``r50`` .. ``r300``),
  verified meter-scaled.  Stock radio geometry tops out at the 300 m mesh
  (``r350``..``r650`` all export the same model), so taller structures
  clamp to the 300 m object.
* small (POLE, MAST, UPOLE, ...): the same ramp with finer resolution at
  the bottom (5/8/12 m stock objects).
* monopole (MTOWER, MTA, POLE, UPOLE, MAST) above 40 m: generated grey
  monopole cell towers (``objects/monopole_50/75/100/150.obj``,
  ``tools/gen_monopole.py``) -- stock scenery has no monopole-style
  object above 25 m, so these fill the gap; above 150 m they clamp to
  the 150 m mesh.  At <= 40 m the stock grey comm_tower meshes are still
  used (better size match).
* building-attached / non-tower types (B, BANT, BTWR, TANK, TREE, SILO,
  PIPE, STACK, SIGN, ...) are not drawn: they are antennas on other
  structures, or not towers at all.

An explicit ``object_path`` CSV column always wins (custom/public-domain
models, test galleries).  DSFTool's text format does not preserve a
per-object *scale*, so size variety is achieved by object choice rather
than scaling.

Additional sites (curated supplement)
-------------------------------------
``additional_sites.csv`` (next to this script, or
``--additional-sites <path>``) adds hand-curated towers that the FCC data
does not contain -- e.g. the NIST WWV/WWVB time-signal masts, which predate
the 1981 ASR program and never appear in ULS.  Columns: ``name, lat, lon,
object_path (optional), height_m (optional), exclusion_radius_ft
(optional)``.  A row with ``object_path`` places that object; a row with
``exclusion_radius_ft`` emits a site-wide exclusion box around the point
(for lower-priority scenery clusters that spread farther than the per-tower
box reaches); either or both may be set.  Additional-site rows bypass the
--state / height filters (they are curated, not filtered data).

Showroom
--------
``showroom`` builds FCC_TowerShowroom: a grid of sample tower objects near
Akron, CO (region +40-104) showing every style family and height bucket the
pack uses.  A draped white plinth (see the SHOWROOM_PLINTH_* constants at
the top of this file) gives the grid a solid ground to stand out against
the terrain.  The showroom never reads the
additional-sites supplement (the plinth covers the bounding box of all
placed objects, so unknown-region towers would stretch the patch).

Design history and rationale (exclusion-zone tests, dedup, object
selection, DSF format details) live in DESIGN.md.

Standard library only.  The ``build``/``showroom`` commands require
``DSFTool`` (X-Plane SDK / XP12 Tools) unless --text-only is used;
--dsftool <path> locates it.

Examples
--------
    python fcc_towers.py                                # fresh data + full pack
    python fcc_towers.py --no-download                  # rebuild from cached zip
    python fcc_towers.py build --state TX --max-objects 300   # quick test set
    python fcc_towers.py build --min-height 100         # only tall towers
    python fcc_towers.py build --dry-run                # report only
    python fcc_towers.py showroom                       # object gallery pack
    python fcc_towers.py csv --source application       # inspect the data
    python fcc_towers.py -h                             # full options
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import math
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent

REGISTRATION_URL = "https://data.fcc.gov/download/pub/uls/complete/r_tower.zip"
APPLICATION_URL = "https://data.fcc.gov/download/pub/uls/complete/a_tower.zip"

# ---------------------------------------------------------------------------
# Tunable presentation settings (edit here; not exposed on the command line)
# ---------------------------------------------------------------------------
# Showroom: the object gallery stands on a flat white "plinth" (a
# DRAPED_POLYGON draping onto the terrain mesh) so the grid reads clearly
# against the landscape.  The main pack never uses a plinth.
SHOWROOM_PLINTH_Z_M = 1.0            # plinth elevation, meters MSL (0 = off)
SHOWROOM_PLINTH_MARGIN_M = 125.0     # margin beyond the object bounding box
SHOWROOM_PLINTH_TEXTURE = "texture/white.pol"  # .pol + generated .png in texture/


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ===========================================================================
# FCC ULS data: download + parse
# ===========================================================================
# ---------------------------------------------------------------------------
# Field positions (0-based) per the FCC "patower" field definitions.
# ---------------------------------------------------------------------------
# RA.dat (49 fields)
RA_FILE_NUMBER = 2
RA_REG_NUMBER = 3
RA_USI = 4          # Unique System Identifier
RA_PURPOSE = 5      # NE new, NT constructed, MD modification, OC ownership, ...
RA_STATUS = 8       # C constructed, G granted, D dismissed, W withdrawn, ...
RA_DATE_ACTION = 14
RA_ARCHIVE = 15     # C current version, A archive
RA_STREET = 23
RA_CITY = 24
RA_STATE = 25
RA_HEIGHT_STRUCTURE_M = 28    # Height of Structure (meters)
RA_GROUND_ELEVATION_M = 29    # Ground Elevation (meters)
RA_OVERALL_AG_M = 30          # Overall Height Above Ground (meters)
RA_OVERALL_AMSL_M = 31        # Overall Height AMSL (meters)
RA_STRUCTURE_TYPE = 32        # TOWER, POLE, MAST, GTOWER, ...
RA_FAA_STUDY = 34

RA_EXPECTED_FIELDS = 49

# CO.dat (18 fields)
CO_FILE_NUMBER = 2
CO_COORD_TYPE = 5   # T tower, A array
CO_LAT_DEG = 6
CO_LAT_MIN = 7
CO_LAT_SEC = 8
CO_LAT_DIR = 9
CO_LAT_TOTAL_SEC = 10
CO_LON_DEG = 11
CO_LON_MIN = 12
CO_LON_SEC = 13
CO_LON_DIR = 14
CO_LON_TOTAL_SEC = 15
CO_ARRAY_POSITION = 16
CO_ARRAY_TOTAL = 17

CO_EXPECTED_FIELDS = 18

M_TO_FT = 3.28084

CSV_COLUMNS = [
    "file_number", "registration_number", "usi",
    "state", "city",
    "latitude", "longitude",
    "structure_type",
    "height_structure_ft", "height_structure_m",
    "ground_elevation_ft", "ground_elevation_m",
    "overall_height_ag_ft", "overall_height_ag_m",
    "overall_height_amsl_ft", "overall_height_amsl_m",
    "status", "purpose",
    "coordinate_type", "array_position", "array_total",
    "faa_study_number", "date_action",
]


def download(url: str, dest: Path, force: bool) -> Path:
    """Download url to dest (zip), reusing an existing file unless forced."""
    if dest.exists() and not force:
        log(f"Using cached {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if force and dest.exists():
        # Windows os.rename() cannot overwrite an existing destination.
        dest.unlink()
    part = dest.with_name(dest.name + ".part")
    # Note: the FCC's CDN (Akamai) rejects custom/browser User-Agents with a
    # 403, so we rely on Python's default UA ("Python-urllib/..."), which is
    # accepted.
    req = urllib.request.Request(url)
    log(f"Downloading {url}")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        chunk = 1 << 20
        last_report = 0.0
        while True:
            block = resp.read(chunk)
            if not block:
                break
            f.write(block)
            got += len(block)
            now = time.time()
            if now - last_report > 2:
                if total:
                    log(f"  {got / 1e6:.0f} / {total / 1e6:.0f} MB "
                        f"({100 * got // total}%)")
                else:
                    log(f"  {got / 1e6:.0f} MB")
                last_report = now
    part.rename(dest)
    log(f"Saved {dest} ({dest.stat().st_size / 1e6:.1f} MB in {time.time() - t0:.0f}s)")
    return dest


def resolve_zip(args) -> Path:
    """Locate the FCC zip per the command's download options.

    Priority: --zip-path (no download) > --no-download (cached zip) >
    fresh download (the default; the FCC re-publishes weekly).
    """
    if getattr(args, "zip_path", None):
        p = Path(args.zip_path)
        if not p.exists():
            log(f"error: --zip-path {p} does not exist")
            raise SystemExit(2)
        return p
    url = (REGISTRATION_URL if args.source == "registration"
           else APPLICATION_URL)
    cache = HERE / "tmp" / Path(url).name if args.cache_dir is None \
        else Path(args.cache_dir) / Path(url).name
    if getattr(args, "no_download", False):
        if not cache.exists():
            log(f"error: --no-download but no cached zip at {cache}.\n"
                f"Run once without --no-download, or pass --zip-path <file>.")
            raise SystemExit(2)
        log(f"Using cached {cache} ({cache.stat().st_size / 1e6:.1f} MB)")
        return cache
    return download(url, cache, force=True)


def iter_records(zip_path: Path, member: str, record_type: str):
    """Yield the field list for each pipe-delimited record of `record_type`."""
    with zipfile.ZipFile(zip_path) as zf, zf.open(member) as f:
        for raw in f:
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line.startswith(record_type + "|"):
                continue
            yield line.split("|")


def parse_float(s: str | None):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def dms_to_decimal(deg, minutes, seconds, direction):
    """deg/min/sec + N/S/E/W -> signed decimal degrees, or None if invalid."""
    d, m, s = parse_float(deg), parse_float(minutes), parse_float(seconds)
    if d is None or m is None or s is None:
        return None
    if direction not in ("N", "S", "E", "W"):
        return None
    value = d + m / 60.0 + s / 3600.0
    if direction in ("S", "W"):
        value = -value
    return value


def to_decimal(coord: str, total_seconds: str | None, is_lat: bool):
    """Validate a signed decimal degree; out-of-range -> None."""
    if coord is None:
        return None
    limit = 90.0 if is_lat else 180.0
    if coord < -limit or coord > limit:
        return None
    return round(coord, 6)


def feet(m):
    return None if m is None else round(m * M_TO_FT, 1)


def load_active_ra(zip_path: Path, status_set: set, require_current: bool):
    """
    Stream RA.dat and keep only the active records.
    Returns (ra_by_file, records_scanned, active_records).
    RA rows are stored compactly (only the fields we emit).
    """
    ra_by_file: dict[str, list[tuple]] = {}
    scanned = 0
    active = 0
    for f in iter_records(zip_path, "RA.dat", "RA"):
        scanned += 1
        if len(f) != RA_EXPECTED_FIELDS:
            continue
        status = f[RA_STATUS].strip().upper()
        if status not in status_set:
            continue
        if require_current and f[RA_ARCHIVE].strip().upper() != "C":
            continue
        key = f[RA_FILE_NUMBER].strip()
        if not key:
            continue
        row = (
            f[RA_FILE_NUMBER], f[RA_REG_NUMBER], f[RA_USI],
            f[RA_STATE], f[RA_CITY],
            f[RA_STRUCTURE_TYPE],
            f[RA_HEIGHT_STRUCTURE_M], f[RA_GROUND_ELEVATION_M],
            f[RA_OVERALL_AG_M], f[RA_OVERALL_AMSL_M],
            status, f[RA_PURPOSE], f[RA_FAA_STUDY], f[RA_DATE_ACTION],
        )
        ra_by_file.setdefault(key, []).append(row)
        active += 1
    return ra_by_file, scanned, active


def build_csv(zip_path: Path, ra_by_file: dict, out_path: Path) -> dict:
    """
    Stream CO.dat, join with active RA records, and write the CSV.
    RA records with no coordinate record are still emitted (blank lat/lon).
    """
    stats = {"rows": 0, "coords_used": 0, "coords_invalid": 0,
             "ra_matched": 0, "ra_unmatched": 0}
    matched: set[str] = set()

    def base_row(ra):
        (fn, reg, usi, state, city, stype,
         h_struct, ground, ag, amsl, status, purpose, faa, date_action) = ra
        return [fn, reg, usi, state, city, "", "", stype,
                feet(parse_float(h_struct)), (h_struct or "").strip(),
                feet(parse_float(ground)), (ground or "").strip(),
                feet(parse_float(ag)), (ag or "").strip(),
                feet(parse_float(amsl)), (amsl or "").strip(),
                status, purpose, "", "", "", faa, date_action]

    with open(out_path, "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(CSV_COLUMNS)

        for c in iter_records(zip_path, "CO.dat", "CO"):
            if len(c) != CO_EXPECTED_FIELDS:
                continue
            key = c[CO_FILE_NUMBER].strip()
            ra_list = ra_by_file.get(key)
            if ra_list is None:
                continue

            lat = dms_to_decimal(c[CO_LAT_DEG], c[CO_LAT_MIN],
                                 c[CO_LAT_SEC], c[CO_LAT_DIR].strip().upper())
            lon = dms_to_decimal(c[CO_LON_DEG], c[CO_LON_MIN],
                                 c[CO_LON_SEC], c[CO_LON_DIR].strip().upper())
            if lat is None:  # fall back to total-seconds fields
                lat = (parse_float(c[CO_LAT_TOTAL_SEC]) or 0) / 3600.0 or None
                if lat is not None and c[CO_LAT_DIR].strip().upper() == "S":
                    lat = -abs(lat)
            if lon is None:
                lon = (parse_float(c[CO_LON_TOTAL_SEC]) or 0) / 3600.0 or None
                if lon is not None and c[CO_LON_DIR].strip().upper() == "W":
                    lon = -abs(lon)
            lat = to_decimal(lat, None, True)
            lon = to_decimal(lon, None, False)
            if lat is None or lon is None:
                stats["coords_invalid"] += 1
                continue

            matched.add(key)
            for ra in ra_list:
                row = base_row(ra)
                row[5], row[6] = lat, lon
                row[18] = c[CO_COORD_TYPE]
                row[19] = c[CO_ARRAY_POSITION]
                row[20] = c[CO_ARRAY_TOTAL]
                writer.writerow(row)
                stats["rows"] += 1
                stats["coords_used"] += 1

        # Active RA records that have no coordinate record at all.
        for key, ra_list in ra_by_file.items():
            if key in matched:
                continue
            for ra in ra_list:
                writer.writerow(base_row(ra))
                stats["rows"] += 1
            stats["ra_unmatched"] += 1
        stats["ra_matched"] = len(matched)
    return stats


def fetch_csv(args) -> Path:
    """Download (per args) and write the active-antenna CSV. Returns its path."""
    if args.source == "registration":
        default_status = "C,G"
    else:
        default_status = "G"
    status_set = {s.strip().upper() for s in
                  (args.status or default_status).split(",") if s.strip()}
    require_current = args.source == "registration" and not args.include_archived

    zip_path = resolve_zip(args)

    t0 = time.time()
    ra_by_file, scanned, active = load_active_ra(zip_path, status_set,
                                                 require_current)
    log(f"RA records scanned: {scanned:,}")
    log(f"Active RA records:  {active:,} "
        f"(status in {sorted(status_set)}, "
        f"{'archive=C required' if require_current else 'no archive filter'})")
    if not ra_by_file:
        log("No active records found; nothing to write.")
        raise SystemExit(1)

    out_path = Path(args.csv_out)
    stats = build_csv(zip_path, ra_by_file, out_path)
    log(f"CSV rows written:   {stats['rows']:,} -> {out_path}")
    log(f"Coordinates used:   {stats['coords_used']:,} "
        f"(invalid skipped: {stats['coords_invalid']:,})")
    log(f"RA with coords:     {stats['ra_matched']:,} "
        f"(no coords: {stats['ra_unmatched']:,})")
    log(f"CSV done in {time.time() - t0:.0f}s")
    return out_path


# ===========================================================================
# Object selection (FCC structure_type + height -> X-Plane object)
# ===========================================================================
# Object sources (stock library; heights verified by measuring the OBJ
# geometry):
#  * comm-tower family, airport scenery library (binary OBJ, named heights):
#      EXPORT lib/constructions/antennas/comm_tower_10m_1.obj  Common_Elements/antennas/ctower_10m_01.obj
#    Variants are different styles per height (verified against the
#    installed library.txts): 10m _1/_2/_3, 12m _1/_2, 15m _1/_2,
#    25m _1/_2/_3 -- see OBJECT_VARIANTS.  The smallest stock radio tower
#    is 50 m, so comm towers cover <= 25 m.
#  * small antenna family, airport scenery library:
#      lib/constructions/antennas/antenna_5m_01.obj .. antenna_8m_06.obj
#  * radio-tower set, "900 us objects" pack (meter-scaled):
#      EXPORT /lib/global8/us/feat_RadioTower_10_10_650rNNN.obj  obstacles/radio_XX.obj
#    The 5x5 and 10x10 series export the SAME physical files, and the
#    physical size ramp is 50/100/150/200/250/300 m -- r350..r650 all
#    export the 300 m mesh, so nothing stock exists above 300 m.
# Resource strings must match each library's EXPORT name EXACTLY --
# X-Plane does not normalize them, which is why the radio-tower paths
# carry a leading slash and the airport-library paths do not.
# Table key = the maximum structure height (meters) the object stands in for.
BIG_TOWERS = OrderedDict([
    (10,  "lib/constructions/antennas/comm_tower_10m_1.obj"),
    (15,  "lib/constructions/antennas/comm_tower_15m_1.obj"),
    # 25 m mesh stands in for towers up to 40 m: at ~40 m its height
    # error (37% short) equals the 50 m lattice's (25% tall), and the
    # lattice is the wrong style for monopoles, so grey wins below 40 m.
    (40,  "lib/constructions/antennas/comm_tower_25m_1.obj"),
    (50,  "/lib/global8/us/feat_RadioTower_10_10_650r50.obj"),
    (100, "/lib/global8/us/feat_RadioTower_10_10_650r100.obj"),
    (150, "/lib/global8/us/feat_RadioTower_10_10_650r140.obj"),
    (200, "/lib/global8/us/feat_RadioTower_10_10_650r200.obj"),
    (250, "/lib/global8/us/feat_RadioTower_10_10_650r250.obj"),
    (300, "/lib/global8/us/feat_RadioTower_10_10_650r300.obj"),
])

SMALL_MASTS = OrderedDict([
    (5,   "lib/constructions/antennas/antenna_5m_01.obj"),
    (8,   "lib/constructions/antennas/antenna_8m_01.obj"),
    (10,  "lib/constructions/antennas/comm_tower_10m_1.obj"),
    (12,  "lib/constructions/antennas/comm_tower_12m_1.obj"),
    (15,  "lib/constructions/antennas/comm_tower_15m_1.obj"),
    (40,  "lib/constructions/antennas/comm_tower_25m_1.obj"),
    (50,  "/lib/global8/us/feat_RadioTower_10_10_650r50.obj"),
    (100, "/lib/global8/us/feat_RadioTower_10_10_650r100.obj"),
    (150, "/lib/global8/us/feat_RadioTower_10_10_650r140.obj"),
    (200, "/lib/global8/us/feat_RadioTower_10_10_650r200.obj"),
    (250, "/lib/global8/us/feat_RadioTower_10_10_650r250.obj"),
    (300, "/lib/global8/us/feat_RadioTower_10_10_650r300.obj"),
])

FAMILIES = {"big": BIG_TOWERS, "small": SMALL_MASTS}

# Generated grey monopole cell towers (tools/gen_monopole.py), shipped in
# the pack's objects/ folder and EXPORTed via library.txt as
# fcc_towers/monopole_<H>.obj.  Stock scenery has no monopole-style
# object above 25 m, so these cover the mono-type FCC towers the stock
# set cannot (MTOWER/MTA/POLE/UPOLE/MAST above MONO_CUTOVER_M).  93% of
# those towers are 40-75 m with a thin tail past 100 m; anything above
# the tallest mesh clamps to it, same convention as the lattice set
# clamping at r300.
MONO_CUTOVER_M = 40.0
MONO_TYPES = {"MTOWER", "MTA", "POLE", "UPOLE", "MAST"}
MONOPOLES = OrderedDict([
    (50,  "fcc_towers/monopole_50.obj"),
    (75,  "fcc_towers/monopole_75.obj"),
    (100, "fcc_towers/monopole_100.obj"),
    (150, "fcc_towers/monopole_150.obj"),
])

# FCC structure_type -> style family.  Codes are normalized by stripping
# leading/trailing digits first ("3TA2" -> "TA", "2TOWER" -> "TOWER").
# None = suppressed (not drawn).  Unlisted codes fall back to DEFAULT_FAMILY.
TYPE_FAMILY = {
    # self-supporting / guyed / monopole towers
    "TOWER": "big", "LTOWER": "big", "GTOWER": "big", "MTOWER": "big",
    "LTA": "big", "GTA": "big", "MTA": "big", "TA": "big",
    # free-standing poles and masts
    "POLE": "small", "UPOLE": "small", "MAST": "small",
    # building-attached antennas or non-tower structures (do not draw)
    "B": None, "BANT": None, "BTWR": None, "BMAST": None, "BPOLE": None,
    "BPIPE": None, "TANK": None, "TREE": None, "SILO": None, "PIPE": None,
    "STACK": None, "SIGN": None,
}
DEFAULT_FAMILY = "big"  # blank/unknown types keep drawing (a tower beats nothing)


def _norm_type(structure_type):
    """Uppercase an FCC structure_type and strip leading/trailing digits
    (structure number / structures at site): "3TA2" -> "TA"."""
    return (structure_type or "").strip().upper().strip("0123456789")


def family_for(structure_type):
    """Map an FCC structure_type to a style family, or None (suppressed).

    Leading digits (structure number) and trailing digits (structures at
    site) are stripped first: "3TA2" -> "TA", "0LTA0" -> "LTA".
    """
    t = _norm_type(structure_type)
    if not t:
        return DEFAULT_FAMILY
    return TYPE_FAMILY.get(t, DEFAULT_FAMILY)


def _pick(table, height_m):
    """Shortest object whose cap is >= height_m; above the tallest, clamp."""
    for cap in table:
        if height_m <= cap:
            return table[cap]
    return table[max(table)]


# Visual variants of the stock antenna/comm-tower objects, keyed by the
# first variant path the tables above pick.  Only sets that actually exist in
# the installed X-Plane library are listed (verified against the library.txt
# EXPORT lines): 12 m and 15 m have two variants, the others three, plus the
# small-antenna families (9 and 6).  The radio-tower set (feat_RadioTower)
# exports the same mesh across its 5x5/10x10 series and the generated
# monopoles have none, so neither appears here.
OBJECT_VARIANTS = {
    "lib/constructions/antennas/comm_tower_10m_1.obj":
        [f"lib/constructions/antennas/comm_tower_10m_{i}.obj"
         for i in (1, 2, 3)],
    "lib/constructions/antennas/comm_tower_12m_1.obj":
        [f"lib/constructions/antennas/comm_tower_12m_{i}.obj"
         for i in (1, 2)],
    "lib/constructions/antennas/comm_tower_15m_1.obj":
        [f"lib/constructions/antennas/comm_tower_15m_{i}.obj"
         for i in (1, 2)],
    "lib/constructions/antennas/comm_tower_25m_1.obj":
        [f"lib/constructions/antennas/comm_tower_25m_{i}.obj"
         for i in (1, 2, 3)],
    "lib/constructions/antennas/antenna_5m_01.obj":
        [f"lib/constructions/antennas/antenna_5m_{i:02d}.obj"
         for i in range(1, 10)],
    "lib/constructions/antennas/antenna_8m_01.obj":
        [f"lib/constructions/antennas/antenna_8m_{i:02d}.obj"
         for i in range(1, 7)],
}


def pick_variant(path, key):
    """Deterministically rotate a stock object through its visual variants.

    ``key`` identifies the tower (its FCC registration number, or rounded
    coordinates when absent).  The SHA-256 digest of the key selects the
    variant, so the same tower always gets the same style while different
    towers spread across the set.  This is stable across weekly FCC data
    refreshes and across Python processes (the built-in ``hash()`` is
    salted per process and would not be).  Paths with no verified variant
    set (radio towers, generated monopoles) come back unchanged.
    """
    variants = OBJECT_VARIANTS.get(path)
    if not variants:
        return path
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return variants[int(digest, 16) % len(variants)]


def pick_object(height_m, structure_type, family=None):
    """Return a resource path for a tower object, or None to skip.

    Type-aware: ``family_for`` routes the FCC structure_type to a style
    family (suppressed types return None).  FCC monopole/pole/mast types
    (MTOWER/MTA/POLE/UPOLE/MAST) above MONO_CUTOVER_M use the generated
    grey monopole set -- stock scenery has no tall monopole, so the stock
    lattice would be the wrong style.  Everything else uses the stock
    tables, picking the shortest object whose cap is >= the structure
    height (a 61 m lattice tower gets the 100 m object; anything above
    the tallest mesh clamps to it).  ``family`` forces one stock family
    for every record (``--object``).
    """
    if not (height_m and height_m > 0):
        height_m = 100.0  # sensible default when height is missing
    if family:
        return _pick(FAMILIES[family], height_m)
    fam = family_for(structure_type)
    if fam is None:
        return None
    if height_m > MONO_CUTOVER_M and _norm_type(structure_type) in MONO_TYPES:
        return _pick(MONOPOLES, height_m)
    return _pick(FAMILIES[fam], height_m)


# ===========================================================================
# Region math + DSF text
# ===========================================================================
def region_for(lat, lon):
    """Map a point to its 1-degree sub-region and 10-degree big-region folder.

    Returns (sub_name, big_name, props) where props holds the region bounds
    used in the DSF header (sim/west, sim/east, sim/north, sim/south).
    Handles the US (north latitude, west longitude); other hemispheres fall
    out of the same math but are not exercised by the FCC data.
    """
    s_lat = math.floor(lat)
    s_lon = math.floor(lon)                 # west edge (negative for W)
    b_lat = (s_lat // 10) * 10
    b_lon = (s_lon // 10) * 10              # // floors toward -inf for negatives

    def name(c_lat, c_lon):
        # X-Plane region name: lat sign is explicit; the separator '-' means
        # west and '+' means east, followed by the longitude magnitude.
        lat_part = ("+" if c_lat >= 0 else "-") + f"{abs(c_lat):02d}"
        if c_lon < 0:
            return f"{lat_part}-{abs(c_lon):03d}"   # e.g. +40-110 (west)
        return f"{lat_part}+{abs(c_lon):03d}"       # e.g. +40+110 (east)

    props = {"west": s_lon, "east": s_lon + 1, "south": s_lat, "north": s_lat + 1}
    return name(s_lat, s_lon), name(b_lat, b_lon), props


def region_text(props, placements, plinth=None, plinth_texture="texture/white.pol",
                exclude_boxes=None):
    """Build the DSF text for one sub-region.

    ``placements`` is a list of (lon, lat, resource_path, height_m). Object
    indices are assigned in first-seen order, matching how DSFTool numbers
    OBJECT_DEFs.

    ``exclude_boxes`` is a list of (west, south, east, north) rectangles in
    absolute degrees, emitted as ``sim/exclude_obj`` and ``sim/exclude_fac``
    right after ``sim/overlay``. These cull objects AND facades (building
    polygons, autogen primitives) from LOWER-priority scenery (packs later
    in scenery_packs.ini); this DSF itself is unaffected, so the towers it
    places always draw. (Simpsonville, KY test: autogen impostor towers
    required both properties to be culled.)

    ``plinth`` is an optional (lon0, lat0, lon1, lat1) rectangle in ABSOLUTE
    degrees: a flat DRAPED_POLYGON that drapes onto the terrain mesh and fills
    the area under the placed objects -- used e.g. to give small showroom
    towers a solid white ground to stand out against the terrain.
    ``plinth_texture`` is the POLYGON_DEF path (a .pol in the pack).

    All definitions (OBJECT_DEF + POLYGON_DEF) are emitted before any
    geometry (OBJECT + BEGIN_POLYGON), matching the KBDL airport pack.
    """
    order = []
    index = {}
    for _, _, path, _h in placements:
        if path not in index:
            index[path] = len(order)
            order.append(path)

    out = [
        "I",
        "800",
        "DSF2TEXT",
        "DIVISIONS 32",
        "HEIGHTS 0.03125 -1.0",
        f"PROPERTY sim/west {props['west']}",
        f"PROPERTY sim/east {props['east']}",
        f"PROPERTY sim/north {props['north']}",
        f"PROPERTY sim/south {props['south']}",
        "PROPERTY sim/planet earth",
        "PROPERTY sim/creation_agent fcc_towers",
        "PROPERTY sim/overlay 1",
    ]
    if exclude_boxes:
        for w, s, e, n in exclude_boxes:
            out.append(f"PROPERTY sim/exclude_obj {w:.7f}/{s:.7f}/{e:.7f}/{n:.7f}")
            out.append(f"PROPERTY sim/exclude_fac {w:.7f}/{s:.7f}/{e:.7f}/{n:.7f}")
    out += [
        "PROPERTY sim/require_agpoint 1/0",
        "PROPERTY sim/require_object 1/0",
    ]
    # ---- definitions (before any geometry) ----------------------------
    for path in order:
        out.append(f"OBJECT_DEF {path}")
    if plinth is not None:
        out.append(f"POLYGON_DEF {plinth_texture}")
    # ---- geometry ------------------------------------------------------
    for lon, lat, path, _h in placements:
        out.append(f"OBJECT {index[path]} {lon:.7f} {lat:.7f} 0.0")
    if plinth is not None:
        out.extend(plinth_text(plinth))
    return "\n".join(out) + "\n"


def exclusion_boxes(placements, radius_ft, min_height=0.0):
    """Build sim/exclude_obj + sim/exclude_fac rectangles (west, south, east,
    north, degrees).

    One ~square zone per drawn tower, radius_ft (half-width) around the FCC
    position.  X-Plane uses these to cull objects from lower-priority
    scenery (packs later in scenery_packs.ini); the declaring DSF is
    unaffected, so our own towers always draw.  Co-located placements
    (FCC array pads, a few meters apart) share one zone.
    """
    r_m = radius_ft * 0.3048
    if r_m <= 0:
        return []
    cell = 0.00005  # ~5 m dedupe cell
    seen = set()
    boxes = []
    for lon, lat, _path, h in placements:
        if h < min_height:
            continue
        key = (int(lon / cell), int(lat / cell))
        if key in seen:
            continue
        seen.add(key)
        dlat = r_m / 111_000.0
        dlon = r_m / (111_000.0 * math.cos(math.radians(lat)))
        boxes.append((lon - dlon, lat - dlat, lon + dlon, lat + dlat))
    return boxes


def plinth_text(plinth):
    """DSF text for one flat DRAPED_POLYGON (a solid-color ground patch).

    Point coordinates are ABSOLUTE DEGREES (lon, lat) -- 2 values per point,
    the convention both the KBDL airport pack and DSFTool's round-trip use
    (``BEGIN_POLYGON <def_index> 255 2``). The polygon drapes onto the
    terrain mesh, so it sits a hair above the ground with no explicit
    elevation.
    """
    lon0, lat0, lon1, lat1 = plinth
    pts = [(lon0, lat0), (lon1, lat0), (lon1, lat1), (lon0, lat1)]  # CCW from SW
    out = ["BEGIN_POLYGON 0 255 2", "BEGIN_WINDING"]
    for lon, lat in pts:
        out.append(f"POLYGON_POINT {lon:.7f} {lat:.7f}")
    out += ["END_WINDING", "END_POLYGON"]
    return out


def clip_plinth_to_region(rect, props):
    """Clip a (lon0, lon1, lat0, lat1) rect to one 1-degree region.

    Returns (lon0, lat0, lon1, lat1) ABSOLUTE-degree corners, or None if the
    rect does not intersect the region (polygons cannot cross region files).
    """
    lon0, lon1, lat0, lat1 = rect
    w, e = props["west"], props["east"]
    s, n = props["south"], props["north"]
    cx0, cx1 = max(lon0, w), min(lon1, e)
    cy0, cy1 = max(lat0, s), min(lat1, n)
    if cx1 <= cx0 or cy1 <= cy0:
        return None
    return (cx0, cy0, cx1, cy1)


def write_white_png(path, size=64):
    """Write a solid-white RGB PNG (standard library only)."""
    import struct
    import zlib

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    row = b"\x00" + b"\xff\xff\xff" * size
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
           chunk(b"IDAT", zlib.compress(row * size, 9)) +
           chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def write_white_pol(path):
    """Write a DRAPED_POLYGON .pol that tiles a solid-white PNG.

    X-Plane polygon textures are .pol (drape) files -- the KBDL airport pack
    only ever references .pol/.lin/.fac/.for, never a raw image. This .pol
    points at white.png (written next to it) in the same folder, modeled on
    the stock apt_lines/safe_area_white.pol.
    """
    pol = (
        "A\n"
        "850\n"
        "DRAPED_POLYGON\n"
        "TEXTURE white.png\n"
        "SURFACE asphalt\n"
        "SCALE 4 4\n"
    )
    with open(path, "w") as f:
        f.write(pol)


def write_plinth_texture(tex_path):
    """Write the plinth texture referenced by POLYGON_DEF.

    For a .pol (the guaranteed X-Plane polygon type) we also emit the
    solid-white PNG it tiles. A raw image path is written as-is (fallback).
    """
    d = os.path.dirname(tex_path)
    if d:
        os.makedirs(d, exist_ok=True)
    if tex_path.lower().endswith(".pol"):
        write_white_pol(tex_path)
        write_white_png(os.path.join(d, "white.png"))
    else:
        write_white_png(tex_path)


def write_pack_assets(out_root, assets_dir):
    """Copy the generated monopole objects into the pack and write the
    library.txt that EXPORTs them.

    Every scenery pack must carry its own objects/ folder + library.txt;
    the DSF OBJECT_DEF resource strings (fcc_towers/monopole_*.obj) are
    resolved through the pack's own library.txt EXPORT names, and
    X-Plane matches those strings exactly.
    """
    if not os.path.isdir(assets_dir) or not [
            n for n in os.listdir(assets_dir) if n.lower().endswith(".obj")]:
        raise SystemExit(
            f"monopole assets not found in {assets_dir!r} -- run "
            f"`python tools/gen_monopole.py --out objects` first.")
    obj_dst = os.path.join(out_root, "objects")
    os.makedirs(obj_dst, exist_ok=True)
    for name in sorted(os.listdir(assets_dir)):
        src = os.path.join(assets_dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(obj_dst, name))
    with open(os.path.join(out_root, "library.txt"), "w") as f:
        f.write("A\n800\nLIBRARY\n")
        for _cap, res in MONOPOLES.items():
            f.write(f"EXPORT {res}\tobjects/{os.path.basename(res)}\n")


# ===========================================================================
# DSFTool discovery / conversion
# ===========================================================================
def find_dsftool(explicit):
    """Locate DSFTool.

    Search order:
      1. an explicit --dsftool <path> (must exist); otherwise
      2. DSFTool.exe / DSFTool on the PATH; otherwise
      3. a binary built from the vendored source in this repo
         (``sh tools/dsftool/build.sh``).
    """
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        raise SystemExit(f"--dsftool not found: {explicit}")
    tool = shutil.which("DSFTool.exe") or shutil.which("DSFTool")
    if tool:
        return tool
    for name in ("DSFTool", "DSFTool.exe"):
        local = HERE / "tools" / "dsftool" / name
        if local.is_file() and os.access(local, os.X_OK):
            return str(local)
    raise SystemExit(
        "Could not find DSFTool.\n"
        "Options:\n"
        "  1. Build the vendored copy:  sh tools/dsftool/build.sh\n"
        "     (needs a C/C++ compiler and the zlib dev package; see\n"
        "      tools/dsftool/README.md for requirements and prebuilt\n"
        "      download links)\n"
        "  2. Put a DSFTool binary on your PATH, or pass an explicit\n"
        "     path with --dsftool <path>.\n"
        "  3. Or write the region text files only, with --text-only."
    )


def convert(dsf_tool, txt, dsf, pool_cache):
    """Run DSFTool --text2dsf. Returns (dsf, ok, err)."""
    try:
        r = subprocess.run(
            [dsf_tool, "--text2dsf", txt, dsf],
            capture_output=True, text=True, timeout=120,
            check=False,  # intentional: we inspect returncode/output ourselves
        )
        ok = r.returncode == 0 and os.path.isfile(dsf)
        err = (r.stderr or r.stdout).strip()[-300:]
        return dsf, ok, err
    except Exception as e:  # noqa: BLE001
        return dsf, False, str(e)


# ===========================================================================
# Additional sites (curated supplement)
# ===========================================================================
def _f(s):
    if s is None:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def load_additional_sites(path):
    """Read the curated ``additional_sites.csv`` supplement.

    Columns: name, lat, lon, object_path (optional), height_m (optional),
    exclusion_radius_ft (optional).  Rows with an object_path add a tower
    placement; rows with an exclusion_radius_ft add a site-wide exclusion
    box; either or both may be present.  Missing file / bad rows are
    skipped silently.
    """
    sites = []
    if not os.path.isfile(path):
        return sites
    with open(path, newline="") as f:
        lines = [ln for ln in f
                 if ln.strip() and not ln.lstrip().startswith("#")]
    for row in csv.DictReader(lines):
        lat = _f(row.get("lat"))
        lon = _f(row.get("lon"))
        if (lat is None or lon is None
                or not (-90 <= lat <= 90) or not (-180 <= lon <= 180)):
            continue
        sites.append({
            "name": (row.get("name") or "").strip(),
            "lat": lat, "lon": lon,
            "height_m": _f(row.get("height_m")) or 100.0,
            "object_path": (row.get("object_path") or "").strip(),
            "box_ft": _f(row.get("exclusion_radius_ft")) or 0.0,
        })
    return sites


# ===========================================================================
# Showroom grid (object-style gallery near Akron, CO)
# ===========================================================================
# Anchor: SE corner of the grid (bottom row, first column). Rows grow
# N from here at even spacing; each row's first column sits at
# LON_START (a road runs just E of it) and remaining columns extend W.
# All points land in X-Plane region +40-104 (folder +40-110).
#
# Design notes (v2, after the v1 flight review):
#  * v1 mixed 5-25 m objects in rows adjacent to 300 m giants; the small rows
#    were invisible from altitude. v2 groups by scale and separates the
#    clusters by ~2.5 km.
#  * Stock radio geometry above 300 m does not exist: r350..r650 all map to
#    the same 300 m model (verified by measuring the OBJ geometry), so v1's
#    ramp "r300 r450 r650" showed repeated heights. v2 ramps stop at r300.
#  * The 5x5 and 10x10 radio series export the SAME obj files (verified via
#    library.txt), so the rows were indistinguishable. T2 is now the distinct
#    antenna_100m dish antenna instead.
#  * The stock smokestack is a 700-format object and X-Plane 12 does NOT
#    render 700 objects (confirmed by in-sim test). Smokestacks are excluded.
#  * Resource strings in the DSF must match the library.txt EXPORT name
#    EXACTLY (leading slash included/excluded); X-Plane does not normalize.
#    antenna_100m exports WITHOUT a leading slash.
SHOWROOM_LAT_START = 40.1932349
SHOWROOM_LON_START = -103.2108206
SHOWROOM_ROW_STEP = 125.0   # even row spacing, meters N
SHOWROOM_COL_STEP = 125.0   # column spacing, meters W

_SHOWROOM_ANT = "lib/constructions/antennas/"
# NOTE: the leading slash is REQUIRED -- the 900-us-objects library.txt
# EXPORTs these names WITH a leading slash, and X-Plane matches resource
# strings exactly (it does not normalize).
_SHOWROOM_RADIO10 = "/lib/global8/us/feat_RadioTower_10_10_650r"
_SHOWROOM_ANT100 = "lib/g10/US/commercial/antenna_100m.obj"  # dish, 100 m

# (label, [ (name, resource_path, height_m), ... ])
CLUSTER_S = [
    ("antenna_5m styles",
     [(f"a5_{i:02d}", f"{_SHOWROOM_ANT}antenna_5m_{i:02d}.obj", 5)
      for i in range(1, 10)]),
    ("antenna_8m styles",
     [(f"a8_{i:02d}", f"{_SHOWROOM_ANT}antenna_8m_{i:02d}.obj", 8)
      for i in range(1, 7)]),
    ("comm 10m styles",
     [("ct10_1", f"{_SHOWROOM_ANT}comm_tower_10m_1.obj", 10),
      ("ct10_2", f"{_SHOWROOM_ANT}comm_tower_10m_2.obj", 10),
      ("ct10_3", f"{_SHOWROOM_ANT}comm_tower_10m_3.obj", 10)]),
    ("comm 12-25m styles",
     [("ct12_1", f"{_SHOWROOM_ANT}comm_tower_12m_1.obj", 12),
      ("ct12_2", f"{_SHOWROOM_ANT}comm_tower_12m_2.obj", 12),
      ("ct15_1", f"{_SHOWROOM_ANT}comm_tower_15m_1.obj", 15),
      ("ct15_2", f"{_SHOWROOM_ANT}comm_tower_15m_2.obj", 15),
      ("ct25_1", f"{_SHOWROOM_ANT}comm_tower_25m_1.obj", 25),
      ("ct25_2", f"{_SHOWROOM_ANT}comm_tower_25m_2.obj", 25),
      ("ct25_3", f"{_SHOWROOM_ANT}comm_tower_25m_3.obj", 25)]),
]
CLUSTER_T = [
    ("radio 10x10 (50-300m)",
     [(f"r1010_{n}", f"{_SHOWROOM_RADIO10}{n}.obj",
       {50: 50, 100: 100, 140: 150, 200: 200, 250: 250, 300: 300}[n])
      for n in (50, 100, 140, 200, 250, 300)]),
    ("antenna_100m (dish style)",
     [("a100", _SHOWROOM_ANT100, 100)]),
    # Generated grey monopole set (tools/gen_monopole.py).  Resource names
    # come from the pack's OWN library.txt (written by write_pack_assets),
    # not a stock library -- no leading slash, exactly as EXPORTed.
    ("monopole 50-150m (generated)",
     [(f"mono{n}", f"fcc_towers/monopole_{n}.obj", n)
      for n in (50, 75, 100, 150)]),
]

SHOWROOM_ROWS = [(label, items) for label, items in CLUSTER_S]
SHOWROOM_ROWS += [(label, items) for label, items in CLUSTER_T]


def showroom_rows():
    """Build the showroom CSV rows (one dict per object)."""
    lat_per_deg = 111_000.0
    lon_per_deg = 111_000.0 * math.cos(math.radians(SHOWROOM_LAT_START))
    out = []
    for r_idx, (_label, items) in enumerate(SHOWROOM_ROWS):
        lat = SHOWROOM_LAT_START + r_idx * SHOWROOM_ROW_STEP / lat_per_deg
        for c_idx, (name, path, h) in enumerate(items):
            lon = SHOWROOM_LON_START - c_idx * SHOWROOM_COL_STEP / lon_per_deg
            out.append({
                "latitude": f"{lat:.7f}",
                "longitude": f"{lon:.7f}",
                "height_structure_m": h,
                "state": "CO",
                "structure_type": "SHOWROOM",
                "object_path": path,
                "note": f"row={_label} col={c_idx+1} {name}",
            })
    # sanity: everything must be in one region
    regions = {region_for(float(r["latitude"]), float(r["longitude"]))[0]
               for r in out}
    if len(regions) != 1:
        raise SystemExit(f"showroom grid spans multiple regions: {regions}")
    return out


def write_showroom_csv(path):
    rows = showroom_rows()
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    region = region_for(float(rows[0]["latitude"]),
                        float(rows[0]["longitude"]))[0]
    log(f"wrote {path}: {len(rows)} objects in region {region}")
    return path


# ===========================================================================
# Pack build orchestration
# ===========================================================================
def build_pack(csv_path, opts) -> int:
    """Read a CSV of antenna rows and build the scenery pack.

    ``opts`` is an argparse namespace carrying the shared build options
    (out, min_height, max_height, state, max_objects, object, radio_only,
    plinth_z, plinth_margin, plinth_texture, text_only, keep_text, dry_run,
    exclude_radius_ft, no_exclude, exclude_min_height, workers, dsftool,
    additional_sites, no_additional_sites).
    """
    forced_family = opts.object if opts.object in FAMILIES else None
    states = {s.strip().upper() for s in opts.state.split(",") if s.strip()}

    # ---- read + group ----------------------------------------------------
    regions = {}          # sub_name -> dict(props=..., placements=[(lon,lat,path,h)])
    big_of = {}           # sub_name -> big_name
    total = kept = skipped = 0
    deduped = 0
    radio_skipped = 0
    type_hist = {}
    suppressed_hist = {}
    seen = set()  # dedup keys: one object per physical tower (registration)

    # FCC co-located array sites list two rows per registration: one
    # coordinate_type='T' (true/exact) and one 'A' (approximate), e.g. Northglenn
    # 4TA1-4TA4. Keep the 'T' coordinate (the most accurate position); if a
    # registration has no 'T' row, keep its first row. Pre-scan so the main pass
    # below can place exactly one object per registration at the right point.
    keeper = {}    # reg -> (lat, lon) to place
    keeper_is_T = {}  # reg -> True once the keeper came from a 'T' row
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            reg = (row.get("registration_number") or "").strip()
            if not reg:
                continue
            lat = _f(row.get("latitude"))
            lon = _f(row.get("longitude"))
            if lat is None or lon is None:
                continue
            is_T = (row.get("coordinate_type") or "").strip().upper() == "T"
            if reg not in keeper:
                keeper[reg] = (lat, lon)
                keeper_is_T[reg] = is_T
            elif is_T and not keeper_is_T[reg]:
                keeper[reg] = (lat, lon)
                keeper_is_T[reg] = True

    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            total += 1
            lat = _f(row.get("latitude"))
            lon = _f(row.get("longitude"))
            if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                skipped += 1
                continue
            # Drop (0,0)-area data errors (e.g. CO/AURORA, KS/WELLINGTON rows)
            # that would otherwise land in the Gulf of Guinea.
            if abs(lat) < 1 and abs(lon) < 1:
                skipped += 1
                continue
            h = _f(row.get("height_structure_m"))
            st = (row.get("state") or "").strip().upper()
            if states and st not in states:
                skipped += 1
                continue
            h_eff = h if h is not None else 100.0
            if not (opts.min_height <= h_eff <= opts.max_height):
                skipped += 1
                continue
            if opts.max_objects and kept >= opts.max_objects:
                continue
            typ = row.get("structure_type") or ""
            type_hist[typ] = type_hist.get(typ, 0) + 1
            # One object per physical tower. A registration_number is the FCC's
            # identity for a structure; array sites list two rows per
            # registration (one 'T' true + one 'A' approximate coordinate), e.g.
            # Northglenn 4TA1-4TA4 -> 8 rows that are really 4 towers. Place the
            # single 'T' keeper row and drop the rest so we don't draw phantom
            # duplicate silhouettes. Fall back to the coordinate when there is no
            # registration number.
            reg = (row.get("registration_number") or "").strip()
            dedup_key = reg if reg else (lat, lon)
            if dedup_key in seen:
                deduped += 1
                continue
            if reg and (lat, lon) != keeper.get(reg):
                deduped += 1
                continue
            # An explicit ``object_path`` column (X-Plane resource path) places
            # that exact object, bypassing type/height selection. This is the
            # hook for custom/public-domain models and test galleries.
            explicit = (row.get("object_path") or "").strip()
            if explicit:
                path = explicit
            else:
                path = pick_object(h_eff, typ, forced_family)
                if path is None:  # suppressed type (building-attached, tree, ...)
                    key = typ if typ else "(blank)"
                    suppressed_hist[key] = suppressed_hist.get(key, 0) + 1
                    skipped += 1
                    continue
                # --radio-only: keep only the tall red/white lattice radio
                # towers (the stock feat_RadioTower set); grey monopoles and
                # comm-tower-style objects are skipped.  Explicit object_path
                # rows (e.g. additional sites) are unaffected.
                if opts.radio_only and "feat_RadioTower" not in path:
                    radio_skipped += 1
                    skipped += 1
                    continue
                # Rotate through this object's visual variants (the stock
                # library ships several styles per height).  Deterministic
                # per tower, stable across weekly FCC data refreshes.
                path = pick_variant(
                    path, reg if reg else f"{lat:.7f},{lon:.7f}")
            sub, big, props = region_for(lat, lon)
            regions.setdefault(sub, {"props": props, "placements": []})
            regions[sub]["placements"].append((lon, lat, path, h_eff))
            big_of[sub] = big
            seen.add(dedup_key)
            kept += 1

    # ---- additional sites (curated supplement) --------------------------
    # Hand-curated towers the FCC data does not contain (e.g. the NIST
    # WWV/WWVB time-signal masts, predating the 1981 ASR program).  Rows
    # with an object_path become placements (and get the standard per-tower
    # exclusion box below); rows with exclusion_radius_ft add a site-wide
    # box for lower-priority clusters spread over more ground than the
    # per-tower box reaches.  Curated rows bypass the state/height filters.
    if opts.no_additional_sites:
        additional = []
    else:
        additional = load_additional_sites(opts.additional_sites)
    additional_sites_placed = 0
    site_boxes = {}  # sub_name -> [(w, s, e, n), ...]
    for s in additional:
        sub, big, props = region_for(s["lat"], s["lon"])
        if s["object_path"]:
            regions.setdefault(sub, {"props": props, "placements": []})
            regions[sub]["placements"].append(
                (s["lon"], s["lat"], s["object_path"], s["height_m"]))
            big_of[sub] = big
            additional_sites_placed += 1
        if s["box_ft"] > 0 and not opts.no_exclude:
            r_m = s["box_ft"] * 0.3048
            dlat = r_m / 111_000.0
            dlon = r_m / (111_000.0 * math.cos(math.radians(s["lat"])))
            site_boxes.setdefault(sub, []).append(
                (s["lon"] - dlon, s["lat"] - dlat,
                 s["lon"] + dlon, s["lat"] + dlat))

    n_regions = len(regions)
    per_region = [len(v["placements"]) for v in regions.values()]
    max_per = max(per_region) if per_region else 0

    # Optional plinth: bounding box of everything we placed, extended by the
    # margin on each side; clipped per region when writing (a polygon cannot
    # cross a 1-degree region boundary).
    plinth_rect = None
    if opts.plinth_z > 0 and kept:
        lons = [pl[0] for v in regions.values() for pl in v["placements"]]
        lats = [pl[1] for v in regions.values() for pl in v["placements"]]
        m_lat = opts.plinth_margin / 111_000.0
        m_lon = (opts.plinth_margin /
                 (111_000.0 * math.cos(math.radians(sum(lats) / len(lats)))))
        plinth_rect = (min(lons) - m_lon, max(lons) + m_lon,
                       min(lats) - m_lat, max(lats) + m_lat)
        print(f"Plinth: rect lon {plinth_rect[0]:.7f}..{plinth_rect[1]:.7f}, "
              f"lat {plinth_rect[2]:.7f}..{plinth_rect[3]:.7f}, "
              f"z = {opts.plinth_z:.1f} m MSL, texture {opts.plinth_texture}")

    if opts.dry_run:
        print(f"[dry-run] total={total} kept={kept} skipped={skipped} deduped={deduped}")
        print(f"[dry-run] additional sites: {additional_sites_placed} "
              f"placements, {sum(len(v) for v in site_boxes.values())} site boxes")
        print(f"[dry-run] sub-regions={n_regions}  "
              f"big-regions={len(set(big_of.values()))}  "
              f"max-objects/region={max_per}")
        print("[dry-run] top structure types:",
              sorted(type_hist.items(), key=lambda x: -x[1])[:8])
        if suppressed_hist:
            print("[dry-run] suppressed types:",
                  sorted(suppressed_hist.items(), key=lambda x: -x[1]))
        if radio_skipped:
            print(f"[dry-run] radio-only: skipped {radio_skipped} "
                  f"non-lattice objects")
        return 0

    if kept == 0 and additional_sites_placed == 0:
        print("No antennas matched the filters; nothing to build.")
        return 0

    # ---- layout ----------------------------------------------------------
    nav_root = os.path.join(opts.out, "Earth nav data")
    staging = os.path.join(HERE, "tmp", "overlay_build")
    # Every pack ships the generated monopole objects + library.txt (each
    # scenery pack is self-contained; the DSF resolves the fcc_towers/
    # resource names through the pack's own library.txt).
    write_pack_assets(opts.out, str(HERE / "objects"))
    if os.path.isdir(nav_root):
        shutil.rmtree(nav_root)
    if os.path.isdir(staging):
        # Drop stale text from a previous --keep-text build so the staging
        # tree always mirrors exactly the regions of this build.
        shutil.rmtree(staging)
    for big in set(big_of.values()):
        os.makedirs(os.path.join(nav_root, big), exist_ok=True)
    os.makedirs(staging, exist_ok=True)

    if plinth_rect is not None:
        tex_path = os.path.join(opts.out, opts.plinth_texture)
        write_plinth_texture(tex_path)

    dsf_tool = None if opts.text_only else find_dsftool(opts.dsftool)
    if dsf_tool:
        print(f"DSFTool: {dsf_tool}")

    # ---- write text, then convert in parallel ---------------------------
    jobs = []  # (txt_path, dsf_path)
    n_boxes = 0
    for sub, info in regions.items():
        big = big_of[sub]
        txt = os.path.join(staging, big, sub + ".txt")
        dsf = os.path.join(nav_root, big, sub + ".dsf")
        os.makedirs(os.path.dirname(txt), exist_ok=True)
        plinth = None
        if plinth_rect is not None:
            c = clip_plinth_to_region(plinth_rect, info["props"])
            if c is not None:
                plinth = c
        boxes = []
        if not opts.no_exclude and opts.exclude_radius_ft > 0:
            boxes = exclusion_boxes(info["placements"],
                                    opts.exclude_radius_ft, opts.exclude_min_height)
            n_boxes += len(boxes)
        if sub in site_boxes:
            boxes += site_boxes[sub]
            n_boxes += len(site_boxes[sub])
        with open(txt, "w") as f:
            f.write(region_text(info["props"], info["placements"], plinth,
                                opts.plinth_texture, boxes))
        jobs.append((txt, dsf))

    ok = fail = 0
    failures = []
    if not opts.text_only:
        with concurrent.futures.ThreadPoolExecutor(max_workers=opts.workers) as ex:
            futs = [ex.submit(convert, dsf_tool, txt, dsf, None)
                    for txt, dsf in jobs]
            for fut in concurrent.futures.as_completed(futs):
                dsf, good, err = fut.result()
                if good:
                    ok += 1
                else:
                    fail += 1
                    if len(failures) < 10:
                        failures.append((os.path.basename(dsf), err))
    else:
        ok = len(jobs)

    # ---- cleanup text staging ------------------------------------------
    if not opts.keep_text:
        shutil.rmtree(staging, ignore_errors=True)

    # ---- summary --------------------------------------------------------
    total_dsf = sum(os.path.getsize(dsf) for _, dsf in jobs if os.path.isfile(dsf)) if not opts.text_only else 0
    print(f"\nBuilt {n_regions} sub-region DSF files "
          f"across {len(set(big_of.values()))} big-region folders.")
    print(f"  antennas placed : {kept:,}  (deduped {deduped:,} duplicate antenna rows)")
    if not opts.no_exclude and opts.exclude_radius_ft > 0:
        print(f"  exclude zones   : {n_boxes:,} (radius {opts.exclude_radius_ft:.0f} ft, "
              f"min height {opts.exclude_min_height:.0f} m)")
    if additional:
        print(f"  additional sites: {additional_sites_placed} placements, "
              f"{sum(len(v) for v in site_boxes.values())} site boxes "
              f"({', '.join(s['name'] for s in additional if s['name'])[:120]})")
    if suppressed_hist:
        print(f"  suppressed types: {sum(suppressed_hist.values()):,} "
              f"({', '.join(sorted(suppressed_hist))})")
    if radio_skipped:
        print(f"  radio-only      : skipped {radio_skipped:,} "
              f"non-lattice objects")
    print(f"  max per region  : {max_per:,}")
    if not opts.text_only:
        print(f"  converted OK/fail: {ok:,}/{fail}")
        if failures:
            print("  first failures:")
            for name, err in failures:
                print(f"    {name}: {err}")
    print(f"  output          : {opts.out}")
    if not opts.text_only:
        print(f"  dsf total size  : {total_dsf/1024/1024:.1f} MB")
    print(f"\nNext: copy the '{os.path.basename(opts.out)}' folder into")
    print("      C:\\X-Plane 12\\Custom Scenery  and test in X-Plane 12.")
    return 1 if (fail and ok == 0) else 0


# ===========================================================================
# CLI
# ===========================================================================
def _add_data_options(p):
    p.add_argument("--no-download", action="store_true",
                   help="use the cached zip in tmp/ instead of downloading "
                        "(fails if there is no cache)")
    p.add_argument("--zip-path", default=None,
                   help="use an existing local zip file instead of downloading")
    p.add_argument("--source", choices=["registration", "application"],
                   default="registration",
                   help="registration = r_tower.zip (active antennas, "
                        "recommended); application = a_tower.zip "
                        "(application history)")
    p.add_argument("--status", default=None,
                   help="comma-separated RA status codes to keep "
                        "(default: C,G for registration; G for application)")
    p.add_argument("--include-archived", action="store_true",
                   help="do not require Archive Flag = C (current version)")
    p.add_argument("--cache-dir", default=None,
                   help="where downloaded zips are cached (default: tmp/)")


def _add_build_options(p, default_out,
                       default_csv="active_antennas.csv"):
    p.add_argument("--csv", default=default_csv,
                   help=f"input CSV (default: {default_csv})")
    p.add_argument("--out", default=str(default_out),
                   help=f"output scenery-pack folder (default: {default_out})")
    p.add_argument("--min-height", type=float, default=0.0,
                   help="minimum structure height in meters (default 0)")
    p.add_argument("--max-height", type=float, default=float("inf"),
                   help="maximum structure height in meters (default none)")
    p.add_argument("--state", default="",
                   help="comma-separated state codes to keep, e.g. TX,CA "
                        "(default all)")
    p.add_argument("--max-objects", type=int, default=0,
                   help="cap total objects emitted (0 = no cap); useful for "
                        "a quick test")
    p.add_argument("--object", default="",
                   help="force one style family for every record: big or "
                        "small (default: pick per FCC structure_type)")
    p.add_argument("--radio-only", action="store_true",
                   help="draw only the tall red/white lattice radio towers; "
                        "skip grey monopole and comm-tower-style objects "
                        "(explicit object_path rows, e.g. additional "
                        "sites, still draw)")
    p.add_argument("--exclude-radius-ft", type=float, default=300.0,
                   help="exclusion-zone half-size in feet around each drawn "
                        "tower (default 300); 0 disables the zones")
    p.add_argument("--no-exclude", action="store_true",
                   help="emit no exclusion zones at all (per-tower and "
                        "known-site boxes)")
    p.add_argument("--exclude-min-height", type=float, default=0.0,
                   help="only emit exclusion zones for towers at or above "
                        "this structure height in meters (default 0 = all)")
    p.add_argument("--additional-sites",
                   default=str(HERE / "additional_sites.csv"),
                   help="curated additional-sites supplement CSV (default: "
                        "additional_sites.csv; missing file = no additional "
                        "sites)")
    p.add_argument("--no-additional-sites", action="store_true",
                   help="ignore the additional-sites supplement entirely")
    p.add_argument("--workers", type=int, default=6,
                   help="parallel DSFTool conversions (default 6)")
    p.add_argument("--dsftool", default="", help="path to DSFTool")
    p.add_argument("--text-only", action="store_true",
                   help="write .txt only; skip DSFTool conversion")
    p.add_argument("--keep-text", action="store_true",
                   help="leave the .txt sources alongside the .dsf files")
    p.add_argument("--dry-run", action="store_true",
                   help="report the region/object plan without writing or "
                        "converting")


def _terse_epilog(sub) -> str:
    """For the terse top-level -h: the option flags of each command, with
    no description text (see <command> -h for that).  Generated from the
    real subparsers so the list cannot drift from the actual options."""
    lines = ["options (see <command> -h for descriptions and defaults):"]
    width = 74
    for name, parser in sub.choices.items():
        flags = [s for a in parser._actions
                 for s in a.option_strings
                 if s not in ("-h", "--help")]
        line = f"  {name}:"
        for flag in flags:
            if len(line) + 1 + len(flag) > width:
                lines.append(line)
                line = " " * 11 + flag
            else:
                line += " " + flag
        lines.append(line)
    lines.append("")
    lines.append("  --help-detailed   full documentation (data sources, "
                 "filters, build steps)")
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Full documentation (the module docstring), on request.
    if "--help-detailed" in argv:
        print(__doc__.strip("\n"))
        return 0
    # Default command: build.
    if not argv or argv[0] not in ("build", "showroom", "csv",
                                   "-h", "--help"):
        argv = ["build"] + argv

    ap = argparse.ArgumentParser(
        description="Build X-Plane 12 scenery packs from FCC antenna "
                    "Structure Registration (ASR) data",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command")

    pb = sub.add_parser("build",
                        help="download fresh FCC data and build the "
                             "FCC_Towers pack (default command)")
    _add_data_options(pb)
    pb.add_argument("--csv-out", default="active_antennas.csv",
                    help="where to write the downloaded CSV (default: "
                         "active_antennas.csv)")
    _add_build_options(pb, HERE / "output" / "FCC_Towers",
                       default_csv="active_antennas.csv")

    ps = sub.add_parser("showroom",
                        help="build the FCC_TowerShowroom object gallery "
                             "(no FCC download)")
    _add_build_options(ps, HERE / "output" / "FCC_TowerShowroom",
                       default_csv="showroom_antennas.csv")

    pc = sub.add_parser("csv",
                        help="download fresh FCC data and write the CSV "
                             "only (no pack build)")
    _add_data_options(pc)
    pc.add_argument("--csv-out", default="active_antennas.csv",
                    help="where to write the CSV (default: active_antennas.csv)")

    ap.epilog = _terse_epilog(sub)
    args = ap.parse_args(argv)

    # The plinth is showroom presentation (SHOWROOM_PLINTH_* constants at the
    # top of this file); build_pack reads it from the options namespace.
    args.plinth_z = (SHOWROOM_PLINTH_Z_M if args.command == "showroom"
                     else 0.0)
    args.plinth_margin = SHOWROOM_PLINTH_MARGIN_M
    args.plinth_texture = SHOWROOM_PLINTH_TEXTURE

    if args.command == "csv":
        fetch_csv(args)
        return 0

    if args.command == "showroom":
        csv_path = write_showroom_csv(args.csv)
        # The showroom never reads the additional-sites supplement (the
        # plinth covers the bounding box of all placed objects, so
        # unknown-region towers would stretch the patch).
        args.no_additional_sites = True
        return build_pack(str(csv_path), args)

    # build
    csv_path = fetch_csv(args)
    args.csv = str(csv_path)
    return build_pack(str(csv_path), args)


if __name__ == "__main__":
    raise SystemExit(main())
