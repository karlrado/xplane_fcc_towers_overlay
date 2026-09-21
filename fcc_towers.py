#!/usr/bin/env python3
"""
fcc_towers.py — Download FCC Antenna Structure Registration (ASR) data and
build a CSV of active antenna structures (lat/lon, tower type, tower heights).

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

Output
------
One CSV row per (active RA record x coordinate record).  Lat/lon are decimal
degrees (FCC data is NAD83, which is within a few meters of WGS84).  Heights
are written both in meters (as recorded) and feet (m x 3.28084).

Usage
-----
  python fcc_towers.py                      # active registrations -> active_antennas.csv
  python fcc_towers.py --source application # granted applications (a_tower.zip)
  python fcc_towers.py --zip-path tmp/r_tower.zip   # skip download, use local zip
  python fcc_towers.py --status C --out active_constructed.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

REGISTRATION_URL = "https://data.fcc.gov/download/pub/uls/complete/r_tower.zip"
APPLICATION_URL = "https://data.fcc.gov/download/pub/uls/complete/a_tower.zip"

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


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def download(url: str, dest: Path, force: bool) -> Path:
    """Download url to dest (zip), reusing an existing file unless forced."""
    if dest.exists() and not force:
        log(f"Using cached {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
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


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Active-antenna extraction
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Build a CSV of active FCC-registered antenna structures.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--source", choices=["registration", "application"],
                    default="registration",
                    help="registration = r_tower.zip (active antennas, recommended); "
                         "application = a_tower.zip (application history)")
    ap.add_argument("--status", default=None,
                    help="comma-separated RA status codes to keep "
                         "(default: C,G for registration; G for application)")
    ap.add_argument("--include-archived", action="store_true",
                    help="do not require Archive Flag = C (current version)")
    ap.add_argument("--zip-url", default=None, help="override the zip URL")
    ap.add_argument("--zip-path", default=None,
                    help="use an existing local zip file instead of downloading")
    ap.add_argument("--cache-dir",
                    default=str(Path(__file__).resolve().parent / "tmp"),
                    help="where downloaded zips are cached")
    ap.add_argument("--force", action="store_true",
                    help="re-download even if a cached zip exists")
    ap.add_argument("--out", default="active_antennas.csv",
                    help="output CSV path")
    args = ap.parse_args(argv)

    if args.source == "registration":
        url = args.zip_url or REGISTRATION_URL
        default_status = "C,G"
    else:
        url = args.zip_url or APPLICATION_URL
        default_status = "G"
    status_set = {s.strip().upper() for s in
                  (args.status or default_status).split(",") if s.strip()}
    require_current = args.source == "registration" and not args.include_archived

    if args.zip_path:
        zip_path = Path(args.zip_path)
        if not zip_path.exists():
            log(f"error: --zip-path {zip_path} does not exist")
            return 2
    else:
        cache_dir = Path(args.cache_dir)
        zip_path = download(url, cache_dir / Path(url).name, args.force)

    t0 = time.time()
    ra_by_file, scanned, active = load_active_ra(zip_path, status_set,
                                                 require_current)
    log(f"RA records scanned: {scanned:,}")
    log(f"Active RA records:  {active:,} "
        f"(status in {sorted(status_set)}, "
        f"{'archive=C required' if require_current else 'no archive filter'})")
    if not ra_by_file:
        log("No active records found; nothing to write.")
        return 1

    out_path = Path(args.out)
    stats = build_csv(zip_path, ra_by_file, out_path)
    log(f"CSV rows written:   {stats['rows']:,} -> {out_path}")
    log(f"Coordinates used:   {stats['coords_used']:,} "
        f"(invalid skipped: {stats['coords_invalid']:,})")
    log(f"RA with coords:     {stats['ra_matched']:,} "
        f"(no coords: {stats['ra_unmatched']:,})")
    log(f"Done in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
