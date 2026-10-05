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
# Placeholder object tables (one style family per FCC structure family)
# ---------------------------------------------------------------------------
# Object sources (stock library; heights verified by measuring the OBJ
# geometry):
#  * comm-tower family, airport scenery library (binary OBJ, named heights):
#      EXPORT lib/constructions/antennas/comm_tower_10m_1.obj  Common_Elements/antennas/ctower_10m_01.obj
#    (variants _1/_2/_3 are different styles; same for 12m/15m/25m).  The
#    smallest stock radio tower is 50 m, so comm towers cover <= 25 m.
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

    props = {"west": s_lon, "east": s_lon + 1, "south": s_lat, "north": s_lat + 1}
    return name(s_lat, s_lon), name(b_lat, b_lon), props


# ---------------------------------------------------------------------------
# DSF text
# ---------------------------------------------------------------------------
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
        "PROPERTY sim/creation_agent build_overlay",
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
            check=False,  # intentional: we inspect returncode/output ourselves
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
    p.add_argument("--plinth-z", type=float, default=0.0,
                   help="if > 0, also emit a flat textured ground patch "
                        "(plinth) under the whole object set at this constant "
                        "elevation in meters MSL (default 0 = no plinth)")
    p.add_argument("--plinth-margin", type=float, default=125.0,
                   help="plinth margin beyond the object bounding box, meters "
                        "(default 125 = one tower spacing)")
    p.add_argument("--plinth-texture", default="texture/white.pol",
                   help="texture path for the plinth, relative to the scenery "
                        "pack root (default: texture/white.pol, generated "
                        "together with a solid-white white.png)")
    p.add_argument("--object", default="",
                   help="force one style family for every record: big or "
                        "small (default: pick per FCC structure_type)")
    p.add_argument("--text-only", action="store_true",
                   help="write .txt only; skip DSFTool conversion")
    p.add_argument("--keep-text", action="store_true",
                   help="leave the .txt sources alongside the .dsf files")
    p.add_argument("--dry-run", action="store_true",
                   help="report the region/object plan without writing or converting")
    p.add_argument("--exclude-radius-ft", type=float, default=300.0,
                   help="exclusion-zone half-size in feet around each drawn "
                        "tower (default 300); 0 disables the zones")
    p.add_argument("--no-exclude", action="store_true",
                   help="emit no exclusion zones at all")
    p.add_argument("--exclude-min-height", type=float, default=0.0,
                   help="only emit exclusion zones for towers at or above "
                        "this structure height in meters (default 0 = all)")
    p.add_argument("--workers", type=int, default=6,
                   help="parallel DSFTool conversions (default 6)")
    p.add_argument("--dsftool", default="", help="path to DSFTool.exe")
    a = p.parse_args(argv)

    forced_family = a.object if a.object in FAMILIES else None

    states = {s.strip().upper() for s in a.state.split(",") if s.strip()}

    # ---- read + group ----------------------------------------------------
    regions = {}          # sub_name -> dict(props=..., placements=[(lon,lat,path,h)])
    big_of = {}           # sub_name -> big_name
    total = kept = skipped = 0
    deduped = 0
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
    with open(a.csv, newline="") as f:
        for row in _csv_dict_reader(f):
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

    with open(a.csv, newline="") as f:
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
            sub, big, props = region_for(lat, lon)
            regions.setdefault(sub, {"props": props, "placements": []})
            regions[sub]["placements"].append((lon, lat, path, h_eff))
            big_of[sub] = big
            seen.add(dedup_key)
            kept += 1

    n_regions = len(regions)
    per_region = [len(v["placements"]) for v in regions.values()]
    max_per = max(per_region) if per_region else 0

    # Optional plinth: bounding box of everything we placed, extended by the
    # margin on each side; clipped per region when writing (a polygon cannot
    # cross a 1-degree region boundary).
    plinth_rect = None
    if a.plinth_z > 0 and kept:
        lons = [pl[0] for v in regions.values() for pl in v["placements"]]
        lats = [pl[1] for v in regions.values() for pl in v["placements"]]
        m_lat = a.plinth_margin / 111_000.0
        m_lon = a.plinth_margin / (111_000.0 * math.cos(math.radians(sum(lats) / len(lats))))
        plinth_rect = (min(lons) - m_lon, max(lons) + m_lon,
                       min(lats) - m_lat, max(lats) + m_lat)
        print(f"Plinth: rect lon {plinth_rect[0]:.7f}..{plinth_rect[1]:.7f}, "
              f"lat {plinth_rect[2]:.7f}..{plinth_rect[3]:.7f}, "
              f"z = {a.plinth_z:.1f} m MSL, texture {a.plinth_texture}")

    if a.dry_run:
        print(f"[dry-run] total={total} kept={kept} skipped={skipped} deduped={deduped}")
        print(f"[dry-run] sub-regions={n_regions}  "
              f"big-regions={len(set(big_of.values()))}  "
              f"max-objects/region={max_per}")
        print("[dry-run] top structure types:",
              sorted(type_hist.items(), key=lambda x: -x[1])[:8])
        if suppressed_hist:
            print("[dry-run] suppressed types:",
                  sorted(suppressed_hist.items(), key=lambda x: -x[1]))
        return 0

    if kept == 0:
        print("No antennas matched the filters; nothing to build.")
        return 0

    # ---- layout ----------------------------------------------------------
    nav_root = os.path.join(a.out, "Earth nav data")
    staging = os.path.join(here, "tmp", "overlay_build")
    # Every pack ships the generated monopole objects + library.txt (each
    # scenery pack is self-contained; the DSF resolves the fcc_towers/
    # resource names through the pack's own library.txt).
    write_pack_assets(a.out, os.path.join(here, "objects"))
    if os.path.isdir(nav_root):
        shutil.rmtree(nav_root)
    for big in set(big_of.values()):
        os.makedirs(os.path.join(nav_root, big), exist_ok=True)
    os.makedirs(staging, exist_ok=True)

    if plinth_rect is not None:
        tex_path = os.path.join(a.out, a.plinth_texture)
        write_plinth_texture(tex_path)

    dsf_tool = None if a.text_only else find_dsftool(a.dsftool)
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
        if not a.no_exclude and a.exclude_radius_ft > 0:
            boxes = exclusion_boxes(info["placements"],
                                    a.exclude_radius_ft, a.exclude_min_height)
            n_boxes += len(boxes)
        with open(txt, "w") as f:
            f.write(region_text(info["props"], info["placements"], plinth,
                                a.plinth_texture, boxes))
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
    print(f"  antennas placed : {kept:,}  (deduped {deduped:,} duplicate antenna rows)")
    if not a.no_exclude and a.exclude_radius_ft > 0:
        print(f"  exclude zones   : {n_boxes:,} (radius {a.exclude_radius_ft:.0f} ft, "
              f"min height {a.exclude_min_height:.0f} m)")
    if suppressed_hist:
        print(f"  suppressed types: {sum(suppressed_hist.values()):,} "
              f"({', '.join(sorted(suppressed_hist))})")
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
