"""Generate synthetic_antennas.csv: a 2-cluster object showroom near Akron, CO.

Cluster S (small, 5-25 m) -- style comparisons at comparable scale:
  S1: antenna_5m styles 01..09           (5 m)
  S2: antenna_8m styles 01..06           (8 m)
  S3: comm_tower 10 m styles 1..3        (10 m)
  S4: comm_tower 12/15/25 m styles       (12-25 m)

Cluster T (tall, 50-300 m):
  T1: radio 10x10: r50 r100 r140 r200 r250 r300
  T2: antenna_100m (dish style, distinct from the lattice radio towers)

Design notes (v2, after the v1 flight review):
  * v1 mixed 5-25 m objects in rows adjacent to 300 m giants; the small rows
    were invisible from altitude. v2 groups by scale and separates the
    clusters by ~2.5 km.
  * Stock radio geometry above 300 m does not exist: r350..r650 all map to
    the same 300 m model (verified by measuring the OBJ geometry), so v1's
    ramp "r300 r450 r650" showed repeated heights. v2 ramps stop at r300.
  * The 5x5 and 10x10 radio series export the SAME obj files (verified via
    library.txt), so the rows were indistinguishable. T2 is now the distinct
    antenna_100m dish antenna instead.
  * The stock smokestack is a 700-format object and X-Plane 12 does NOT
    render 700 objects (confirmed by in-sim test: a 700 test instance
    placed between r250/r300 showed as a gap; E/SCN log shows the smokestack
    resource loads but never draws). Smokestacks are therefore excluded.
  * Resource strings in the DSF must match the library.txt EXPORT name
    EXACTLY (leading slash included/excluded); X-Plane does not normalize.
    antenna_100m exports WITHOUT a leading slash.

Near Akron, CO / KAKO: grid's SE corner at 40.1932349, -103.2108206
(a road runs just E of -103.2108206 and lines up with the first column).
Rows extend N with even spacing; columns extend W, ragged on the west.
All points land in X-Plane region +40-104 (folder +40-110).
"""
import csv
import importlib.util
import math

# Anchor: SE corner of the grid (bottom row, first column). Rows grow
# N from here at even spacing; each row's first column sits at
# LON_START (the road) and remaining columns extend W (ragged west).
LAT_START = 40.1932349
LON_START = -103.2108206

ROW_STEP = 125.0   # even row spacing, meters N
COL_STEP = 125.0   # column spacing, meters W

LAT_PER_DEG = 111_000.0
LON_PER_DEG = 111_000.0 * math.cos(math.radians(LAT_START))

ANT = "lib/constructions/antennas/"
RADIO10 = "/lib/global8/us/feat_RadioTower_10_10_650r"
# NOTE: the leading slash is REQUIRED -- the 900-us-objects library.txt
# EXPORTs these names WITH a leading slash, and X-Plane matches resource
# strings exactly (it does not normalize). The airport-library paths
# EXPORT without one, hence the two styles.
ANT100 = "lib/g10/US/commercial/antenna_100m.obj"  # dish antenna, 100 m

# (label, [ (name, resource_path, height_m), ... ])
CLUSTER_S = [
    ("antenna_5m styles",
     [(f"a5_{i:02d}", f"{ANT}antenna_5m_{i:02d}.obj", 5) for i in range(1, 10)]),
    ("antenna_8m styles",
     [(f"a8_{i:02d}", f"{ANT}antenna_8m_{i:02d}.obj", 8) for i in range(1, 7)]),
    ("comm 10m styles",
     [("ct10_1", f"{ANT}comm_tower_10m_1.obj", 10),
      ("ct10_2", f"{ANT}comm_tower_10m_2.obj", 10),
      ("ct10_3", f"{ANT}comm_tower_10m_3.obj", 10)]),
    ("comm 12-25m styles",
     [("ct12_1", f"{ANT}comm_tower_12m_1.obj", 12),
      ("ct12_2", f"{ANT}comm_tower_12m_2.obj", 12),
      ("ct15_1", f"{ANT}comm_tower_15m_1.obj", 15),
      ("ct15_2", f"{ANT}comm_tower_15m_2.obj", 15),
      ("ct25_1", f"{ANT}comm_tower_25m_1.obj", 25),
      ("ct25_2", f"{ANT}comm_tower_25m_2.obj", 25),
      ("ct25_3", f"{ANT}comm_tower_25m_3.obj", 25)]),
]
CLUSTER_T = [
    ("radio 10x10 (50-300m)",
     [(f"r1010_{n}", f"{RADIO10}{n}.obj", {50: 50, 100: 100, 140: 150,
                                            200: 200, 250: 250, 300: 300}[n])
      for n in (50, 100, 140, 200, 250, 300)]),
    ("antenna_100m (dish style)",
     [("a100", ANT100, 100)]),
]

ROWS = [(label, items) for label, items in CLUSTER_S]
ROWS += [(label, items) for label, items in CLUSTER_T]


def build_rows():
    out = []
    for r_idx, (label, items) in enumerate(ROWS):
        lat = LAT_START + r_idx * ROW_STEP / LAT_PER_DEG
        for c_idx, (name, path, h) in enumerate(items):
            lon = LON_START - c_idx * COL_STEP / LON_PER_DEG
            out.append({
                "latitude": f"{lat:.7f}",
                "longitude": f"{lon:.7f}",
                "height_structure_m": h,
                "state": "CO",
                "structure_type": "SHOWROOM",
                "object_path": path,
                "note": f"row={label} col={c_idx+1} {name}",
            })
    return out


rows_out = build_rows()

# sanity: everything must be in one region
spec = importlib.util.spec_from_file_location("bo", "build_overlay.py")
bo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bo)
regions = {bo.region_for(float(r["latitude"]), float(r["longitude"]))[0] for r in rows_out}
assert len(regions) == 1, f"grid spans multiple regions: {regions}"

out = "synthetic_antennas.csv"
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
    w.writeheader()
    w.writerows(rows_out)

print(f"wrote {out}: {len(rows_out)} objects in region {regions.pop()}")
seen = []
for r in rows_out:
    label = r["note"].split("row=")[1].split(" col=")[0]
    if label not in seen:
        seen.append(label)
        same = [x for x in rows_out
                if x["note"].split("row=")[1].split(" col=")[0] == label]
        print(f"  row {label:<24}: {float(r['latitude']):.5f}, "
              f"{float(r['longitude']):.5f} .. {max(float(x['longitude']) for x in same):.5f}")
