"""Generate synthetic_antennas.csv: a 6-row object showroom grid near Erie, CO.

Layout (south to north), each row one object family, heights ramping W->E:
  1. Radio tower 10x10 series: r50  r100  r200  r300  r450  r650
  2. Radio tower 5x5 series:   r50  r100  r200  r300  r450  r650
  3. Smokestacks:              r50  r100  r200  r400
  4. Comm towers:              10m  12m  15m  25m  25m(var3)
  5. Antenna 5m shapes:        01 02 03 04 05 06
  6. Antenna 8m shapes:        01 02 03 04 05 06

Grid: 150 m column spacing (E-W), 250 m row spacing (N-S).
All points land in X-Plane region +40-105 (folder +40-110), ~1-2.3 km ESE
of Erie, CO (40.0406, -104.7255).
"""
import csv
import math

LAT0 = 40.0280          # south row (row 6)
LON0 = -104.6720        # west column
COL_STEP_M = 150.0
ROW_STEP_M = 250.0

LAT_PER_DEG = 111_000.0
LON_PER_DEG = 111_000.0 * math.cos(math.radians(LAT0))

RADIO10 = "/lib/global8/us/feat_RadioTower_10_10_650r"
RADIO5 = "/lib/global8/us/feat_RadioTower_5_5_650r"
SMOKE = "/lib/global8/us/feat_Smokestack_100_100_400r"
ANT = "lib/constructions/antennas/"

# rows listed SOUTH -> NORTH
ROWS = [
    ("antenna_8m shapes",
     [(f"antenna_8m_{i:02d}", f"{ANT}antenna_8m_{i:02d}.obj", 8) for i in range(1, 7)]),
    ("antenna_5m shapes",
     [(f"antenna_5m_{i:02d}", f"{ANT}antenna_5m_{i:02d}.obj", 5) for i in range(1, 7)]),
    ("comm towers (height ramp)",
     [("ct10", f"{ANT}comm_tower_10m_1.obj", 10),
      ("ct12", f"{ANT}comm_tower_12m_1.obj", 12),
      ("ct15", f"{ANT}comm_tower_15m_1.obj", 15),
      ("ct25", f"{ANT}comm_tower_25m_1.obj", 25),
      ("ct25v3", f"{ANT}comm_tower_25m_3.obj", 25)]),
    ("smokestacks (height ramp)",
     [("ss50", f"{SMOKE}50.obj", 50),
      ("ss100", f"{SMOKE}100.obj", 100),
      ("ss200", f"{SMOKE}200.obj", 200),
      ("ss400", f"{SMOKE}400.obj", 400)]),
    ("radio 5x5 (height ramp)",
     [(f"r55_{n}", f"{RADIO5}{n}.obj", n) for n in (50, 100, 200, 300, 450, 650)]),
    ("radio 10x10 (height ramp)",
     [(f"r1010_{n}", f"{RADIO10}{n}.obj", n) for n in (50, 100, 200, 300, 450, 650)]),
]

rows_out = []
for r_idx, (label, items) in enumerate(ROWS):
    lat = LAT0 + r_idx * ROW_STEP_M / LAT_PER_DEG
    for c_idx, (name, path, h) in enumerate(items):
        lon = LON0 + c_idx * COL_STEP_M / LON_PER_DEG
        rows_out.append({
            "latitude": f"{lat:.7f}",
            "longitude": f"{lon:.7f}",
            "height_structure_m": h,
            "state": "CO",
            "structure_type": "SHOWROOM",
            "object_path": path,
            "note": f"row={label} col={c_idx+1} {name}",
        })

# sanity: everything must be in one region
import importlib.util, os
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
for r_idx, (label, items) in enumerate(ROWS):
    lat = LAT0 + r_idx * ROW_STEP_M / LAT_PER_DEG
    lon_w = LON0
    lon_e = LON0 + (len(items) - 1) * COL_STEP_M / LON_PER_DEG
    print(f"  row {6-r_idx} ({label:<28}): {lat:.5f}, {lon_w:.5f} .. {lon_e:.5f}")
