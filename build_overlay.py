#!/usr/bin/env python3
"""
build_overlay.py

Turn ``active_antennas.csv`` (produced by ``fcc_towers.py``) into an
X-Plane 12 **overlay scenery pack** that draws a placeholder tower object at
each antenna location.

How it works
------------
1. Every antenna is assigned to an X-Plane **1-degree sub-region**
   (e.g. ``+40-101``) and its parent **10-degree "big-region" folder**
   (e.g. ``+40-110``) -- exactly the layout World Editor emits.
2. For each sub-region we write a DSF *text* file: the region header
   (``PROPERTY sim/...``), one ``OBJECT_DEF`` per distinct placeholder
   object, and one ``OBJECT <index> <lon> <lat> <heading>`` line per antenna.
3. Each text file is converted to X-Plane 12's native binary (magic
   ``XPLNEDSF``) with Laminar's ``DSFTool --text2dsf``.

The result is a normal scenery pack:

    <out>/
        Earth nav data/
            +40-110/+40-101.dsf
            +29-90/+29-96.dsf
            ...

Copy the ``<out>`` folder into ``C:\\X-Plane 12\\Custom Scenery`` and it will
load as an overlay (the DSF carries ``PROPERTY sim/overlay 1``).

Placeholder objects
-------------------
Structure height (meters) selects the object:

* <= 25 m: the stock ``comm_tower_10m/15m/25m`` family (airport scenery
  library) -- the smallest stock radio tower is 50 m, so these are a much
  better size match for short towers.
* > 25 m: the stock radio-tower set (``r50`` .. ``r350``), verified to be
  meter-scaled (r50 = 50 m, r200 = 200 m, r350 = 300 m).

DSFTool's text format does not preserve a per-object *scale*, so size variety
is achieved by object choice rather than scaling. Swap the ``TOWER_OBJECTS``
table for custom/public-domain models later.

Standard library only. Requires ``DSFTool.exe`` (X-Plane SDK / XP12 Tools)
on the PATH.

Examples
--------
    python build_overlay.py --state TX --max-objects 300     # quick test set
    python build_overlay.py --min-height 100                 # only tall towers
    python build_overlay.py --dry-run                        # report only
    python build_overlay.py -h                               # full options
"""

import argparse
import concurrent.futures
import math
import os
import shutil
import subprocess
import sys
from collections import OrderedDict

# ---------------------------------------------------------------------------
# Placeholder object table
# ---------------------------------------------------------------------------
# Small buckets use the stock comm-tower family from the airport scenery
# library (airport scenery/library.txt):
#   EXPORT lib/constructions/antennas/comm_tower_10m_1.obj  Common_Elements/antennas/ctower_10m_01.obj
# (variants _1/_2/_3 are different styles; same for 12m/15m/25m)
# Larger buckets use the stock "900 us objects" radio-tower set (verified
# meter-scaled by measuring the OBJ geometry):
#   EXPORT /lib/global8/us/feat_RadioTower_10_10_650rNNN.obj  obstacles/radio_XX.obj
# Key = the maximum structure height (meters) the object stands in for.
TOWER_OBJECTS = OrderedDict([
    (10,  "lib/constructions/antennas/comm_tower_10m_1.obj"),
    (15,  "lib/constructions/antennas/comm_tower_15m_1.obj"),
    (25,  "lib/constructions/antennas/comm_tower_25m_1.obj"),
    (50,  "/lib/global8/us/feat_RadioTower_10_10_650r50.obj"),
    (100, "/lib/global8/us/feat_RadioTower_10_10_650r100.obj"),
    (150, "/lib/global8/us/feat_RadioTower_10_10_650r140.obj"),
    (200, "/lib/global8/us/feat_RadioTower_10_10_650r200.obj"),
    (250, "/lib/global8/us/feat_RadioTower_10_10_650r250.obj"),
    (300, "/lib/global8/us/feat_RadioTower_10_10_650r300.obj"),
    (350, "/lib/global8/us/feat_RadioTower_10_10_650r350.obj"),
])


def pick_object(height_m, structure_type, table):
    """Return the resource path for a placeholder object.

    Height-based: pick the shortest object whose cap is >= the structure
    height (so a 61 m tower gets the 100 m object, a 400 m tower the 350 m
    object). ``structure_type`` is reserved for future type-aware mapping.
    """
    if not (height_m and height_m > 0):
        height_m = 100.0  # sensible default when height is missing
    for cap in table:
        if height_m <= cap:
            return table[cap]
    return table[max(table)]


# ---------------------------------------------------------------------------
# Region math
# ---------------------------------------------------------------------------
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

    props = dict(west=s_lon, east=s_lon + 1, south=s_lat, north=s_lat + 1)
    return name(s_lat, s_lon), name(b_lat, b_lon), props


# ---------------------------------------------------------------------------
# DSF text
# ---------------------------------------------------------------------------
def region_text(props, placements):
    """Build the DSF text for one sub-region.

    ``placements`` is a list of (lon, lat, resource_path). Object indices are
    assigned in first-seen order, matching how DSFTool numbers OBJECT_DEFs.
    """
    order = []
    index = {}
    for _, _, path in placements:
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
        "PROPERTY sim/creation_agent build_overlay",
        "PROPERTY sim/overlay 1",
        "PROPERTY sim/require_agpoint 1/0",
        "PROPERTY sim/require_object 1/0",
    ]
    for path in order:
        out.append(f"OBJECT_DEF {path}")
    for lon, lat, path in placements:
        out.append(f"OBJECT {index[path]} {lon:.7f} {lat:.7f} 0.0")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# DSFTool discovery / conversion
# ---------------------------------------------------------------------------
def find_dsftool(explicit):
    """Locate DSFTool: an explicit --dsftool path wins, otherwise it must
    be runnable from the PATH."""
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        raise SystemExit(f"--dsftool not found: {explicit}")
    tool = shutil.which("DSFTool.exe") or shutil.which("DSFTool")
    if tool:
        return tool
    raise SystemExit(
        "Could not find DSFTool on the PATH.\n"
        "Get DSFTool.exe from https://developer.x-plane.com (part of the\n"
        "X-Plane SDK) and add its folder to your PATH, or pass an explicit\n"
        "path with --dsftool <path>."
    )


def convert(dsf_tool, txt, dsf, pool_cache):
    """Run DSFTool --text2dsf. Returns (dsf, ok, err)."""
    try:
        r = subprocess.run(
            [dsf_tool, "--text2dsf", txt, dsf],
            capture_output=True, text=True, timeout=120,
        )
        ok = r.returncode == 0 and os.path.isfile(dsf)
        err = (r.stderr or r.stdout).strip()[-300:]
        return dsf, ok, err
    except Exception as e:  # noqa: BLE001
        return dsf, False, str(e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--csv", default=os.path.join(here, "active_antennas.csv"),
                   help="input CSV (default: active_antennas.csv)")
    p.add_argument("--out", default=os.path.join(here, "output", "FCC_Towers"),
                   help="output scenery-pack folder (default: output/FCC_Towers)")
    p.add_argument("--min-height", type=float, default=0.0,
                   help="minimum structure height in meters (default 0)")
    p.add_argument("--max-height", type=float, default=float("inf"),
                   help="maximum structure height in meters (default none)")
    p.add_argument("--state", default="",
                   help="comma-separated state codes to keep, e.g. TX,CA (default all)")
    p.add_argument("--max-objects", type=int, default=0,
                   help="cap total objects emitted (0 = no cap); useful for a quick test")
    p.add_argument("--object", default="radio",
                   help="placeholder family (currently: radio)")
    p.add_argument("--text-only", action="store_true",
                   help="write .txt only; skip DSFTool conversion")
    p.add_argument("--keep-text", action="store_true",
                   help="leave the .txt sources alongside the .dsf files")
    p.add_argument("--dry-run", action="store_true",
                   help="report the region/object plan without writing or converting")
    p.add_argument("--workers", type=int, default=6,
                   help="parallel DSFTool conversions (default 6)")
    p.add_argument("--dsftool", default="", help="path to DSFTool.exe")
    a = p.parse_args(argv)

    table = TOWER_OBJECTS  # (extend for other --object families here)

    states = {s.strip().upper() for s in a.state.split(",") if s.strip()}

    # ---- read + group ----------------------------------------------------
    regions = {}          # sub_name -> dict(props=..., placements=[(lon,lat,path)])
    big_of = {}           # sub_name -> big_name
    total = kept = skipped = 0
    type_hist = {}
    with open(a.csv, newline="") as f:
        header = None
        for row in _csv_dict_reader(f):
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
            if not (a.min_height <= h_eff <= a.max_height):
                skipped += 1
                continue
            if a.max_objects and kept >= a.max_objects:
                continue
            typ = row.get("structure_type") or ""
            type_hist[typ] = type_hist.get(typ, 0) + 1
            # An explicit ``object_path`` column (X-Plane resource path) places
            # that exact object, bypassing height-based selection. This is the
            # hook for custom/public-domain models and test galleries.
            explicit = (row.get("object_path") or "").strip()
            path = explicit if explicit else pick_object(h_eff, typ, table)
            sub, big, props = region_for(lat, lon)
            regions.setdefault(sub, {"props": props, "placements": []})
            regions[sub]["placements"].append((lon, lat, path))
            big_of[sub] = big
            kept += 1

    n_regions = len(regions)
    per_region = [len(v["placements"]) for v in regions.values()]
    max_per = max(per_region) if per_region else 0

    if a.dry_run:
        print(f"[dry-run] total={total} kept={kept} skipped={skipped}")
        print(f"[dry-run] sub-regions={n_regions}  "
              f"big-regions={len(set(big_of.values()))}  "
              f"max-objects/region={max_per}")
        print("[dry-run] top structure types:",
              sorted(type_hist.items(), key=lambda x: -x[1])[:8])
        return 0

    if kept == 0:
        print("No antennas matched the filters; nothing to build.")
        return 0

    # ---- layout ----------------------------------------------------------
    nav_root = os.path.join(a.out, "Earth nav data")
    staging = os.path.join(here, "tmp", "overlay_build")
    if os.path.isdir(nav_root):
        shutil.rmtree(nav_root)
    for big in set(big_of.values()):
        os.makedirs(os.path.join(nav_root, big), exist_ok=True)
    os.makedirs(staging, exist_ok=True)

    dsf_tool = None if a.text_only else find_dsftool(a.dsftool)
    if dsf_tool:
        print(f"DSFTool: {dsf_tool}")

    # ---- write text, then convert in parallel ---------------------------
    jobs = []  # (txt_path, dsf_path)
    for sub, info in regions.items():
        big = big_of[sub]
        txt = os.path.join(staging, big, sub + ".txt")
        dsf = os.path.join(nav_root, big, sub + ".dsf")
        os.makedirs(os.path.dirname(txt), exist_ok=True)
        with open(txt, "w") as f:
            f.write(region_text(info["props"], info["placements"]))
        jobs.append((txt, dsf))

    ok = fail = 0
    failures = []
    if not a.text_only:
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
            futs = [ex.submit(convert, dsf_tool, txt, dsf, None) for txt, dsf in jobs]
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
    if not a.keep_text:
        shutil.rmtree(staging, ignore_errors=True)

    # ---- summary --------------------------------------------------------
    total_dsf = sum(os.path.getsize(dsf) for _, dsf in jobs if os.path.isfile(dsf)) if not a.text_only else 0
    print(f"\nBuilt {n_regions} sub-region DSF files "
          f"across {len(set(big_of.values()))} big-region folders.")
    print(f"  antennas placed : {kept:,}")
    print(f"  max per region  : {max_per:,}")
    if not a.text_only:
        print(f"  converted OK/fail: {ok:,}/{fail}")
        if failures:
            print("  first failures:")
            for name, err in failures:
                print(f"    {name}: {err}")
    print(f"  output          : {a.out}")
    if not a.text_only:
        print(f"  dsf total size  : {total_dsf/1024/1024:.1f} MB")
    print(f"\nNext: copy the '{os.path.basename(a.out)}' folder into")
    print("      C:\\X-Plane 12\\Custom Scenery  and test in X-Plane 12.")
    return 1 if (fail and ok == 0) else 0


def _f(s):
    if s is None:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _csv_dict_reader(f):
    import csv
    r = csv.DictReader(f)
    return r


if __name__ == "__main__":
    sys.exit(main())
