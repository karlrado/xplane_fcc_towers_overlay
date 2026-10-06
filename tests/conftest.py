"""Shared fixtures for the fcc_towers test suite.

Hermetic by design: tests never touch the network and never read the real
FCC dataset.  A tiny synthetic ``r_tower.zip`` (RA.dat + CO.dat, the same
pipe-delimited ULS format the FCC publishes) covers every interesting code
path: type/height routing, dedup, region math, filters, and known sites.
"""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCRIPT = ROOT / "fcc_towers.py"

# ---------------------------------------------------------------------------
# Synthetic FCC ULS data
# ---------------------------------------------------------------------------
# RA.dat: 49 pipe-delimited fields (index 0 = "RA" tag).
_RA_IDX = dict(
    tag=0, kind=1, file=2, reg=3, usi=4, purpose=5, status=8,
    date_action=14, archive=15, city=24, state=25,
    height_m=28, ground_m=29, ag_m=30, amsl_m=31,
    stype=32, faa=34,
)


def _ra(**kw):
    f = [""] * 49
    f[_RA_IDX["tag"]] = "RA"
    f[_RA_IDX["kind"]] = "REG"
    for key, val in kw.items():
        f[_RA_IDX[key]] = val
    return "|".join(f)


# CO.dat: 18 pipe-delimited fields (index 0 = "CO" tag).
def _co(file_num, ctype, lat, lon):
    """lat/lon as (deg, min, sec, DIR) tuples."""
    f = [""] * 18
    f[0], f[1], f[2] = "CO", "REG", file_num
    f[5] = ctype
    f[6:10] = [str(x) for x in lat]
    f[11:15] = [str(x) for x in lon]
    return "|".join(f)


RA_RECORDS = [
    # file, reg, status, archive, state, height_m, type, comment
    ("A9000001", "1254220", "C", "C", "TX", "200.0", "GTOWER",
     "tall lattice -> r200"),
    ("A9000002", "1254221", "C", "C", "CO", "45.0", "MTOWER",
     "monopole band 50"),
    ("A9000003", "1254222", "C", "C", "CO", "70.0", "MTA",
     "monopole band 75"),
    ("A9000004", "1254223", "C", "C", "CO", "90.0", "POLE",
     "monopole band 100"),
    ("A9000005", "1254224", "C", "C", "CO", "120.0", "UPOLE",
     "monopole band 150"),
    ("A9000006", "1254225", "C", "C", "CO", "400.0", "MAST",
     "clamps to monopole 150"),
    ("A9000007", "1254226", "C", "C", "TX", "12.0", "POLE",
     "small pole -> comm_tower_12m (variant _2 by hash)"),
    ("A9000008", "1254227", "C", "C", "TX", "100.0", "BANT",
     "suppressed type (building antenna)"),
    ("A9000009", "1999901", "C", "C", "CO", "99.0", "TOWER",
     "T+A coordinate pair -> one object at the T point"),
    ("A9000010", "1254229", "C", "A", "CO", "80.0", "TOWER",
     "archived (archive=A): excluded unless --include-archived"),
    ("A9000011", "1254230", "D", "C", "CO", "60.0", "TOWER",
     "status D: excluded unless --status includes D"),
    ("A9000012", "1254231", "C", "C", "KS", "150.0", "GTOWER",
     "no CO record at all -> CSV row without coords, not placed"),
    ("A9000013", "1254232", "C", "C", "KS", "150.0", "GTOWER",
     "invalid CO (bad direction) -> dropped"),
    ("A9000014", "1254233", "C", "C", "TX", "", "TOWER",
     "missing height -> default 100 m -> r100"),
    ("A9000015", "1254234", "C", "C", "CO", "55.0", "TOWER",
     "only an A (approximate) coordinate -> still placed"),
]

CO_RECORDS = [
    ("A9000001", "T", (29, 18, 0.0, "N"), (95, 6, 46.8, "W")),    # 29.300083, -95.113  (+29-096)
    ("A9000002", "T", (40, 3, 0.0, "N"), (105, 3, 0.0, "W")),     # 40.05, -105.05 (+40-106)
    ("A9000003", "T", (40, 3, 18.0, "N"), (105, 3, 0.0, "W")),
    ("A9000004", "T", (40, 3, 36.0, "N"), (105, 3, 0.0, "W")),
    ("A9000005", "T", (40, 4, 0.0, "N"), (105, 3, 0.0, "W")),
    ("A9000006", "T", (40, 4, 18.0, "N"), (105, 3, 0.0, "W")),
    ("A9000007", "T", (29, 19, 0.0, "N"), (95, 7, 0.0, "W")),
    ("A9000008", "T", (29, 20, 0.0, "N"), (95, 8, 0.0, "W")),
    # DUP: T (exact) and A (approximate) for the SAME registration.
    ("A9000009", "T", (40, 6, 0.0, "N"), (104, 57, 0.0, "W")),    # 40.1, -104.95 (+40-105)
    ("A9000009", "A", (40, 6, 1.8, "N"), (104, 56, 58.2, "W")),   # 40.10005, -104.9495
    ("A9000010", "T", (40, 5, 0.0, "N"), (105, 5, 0.0, "W")),
    ("A9000011", "T", (40, 5, 30.0, "N"), (105, 5, 0.0, "W")),
    # BADCOORD: nonsense direction letter, empty total-seconds fallback.
    ("A9000013", "T", (40, 5, 0.0, "X"), (105, 5, 0.0, "W")),
    ("A9000014", "T", (29, 21, 0.0, "N"), (95, 9, 0.0, "W")),
    ("A9000015", "A", (40, 7, 0.0, "N"), (105, 4, 0.0, "W")),
]


def make_fcc_zip(path: Path) -> Path:
    """Write a synthetic r_tower.zip with RA.dat + CO.dat members."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        ra = "\n".join(
            _ra(file=f, reg=r, status=s, archive=a, state=st,
                height_m=h, stype=t)
            for f, r, s, a, st, h, t, _ in RA_RECORDS) + "\n"
        co = "\n".join(_co(*rec) for rec in CO_RECORDS) + "\n"
        zf.writestr("RA.dat", ra)
        zf.writestr("CO.dat", co)
        zf.writestr("counts", "RA: %d\nCO: %d\n" % (len(RA_RECORDS), len(CO_RECORDS)))
    return path


@pytest.fixture(scope="session")
def fcc_zip(tmp_path_factory) -> Path:
    """Session-scoped synthetic FCC zip (built once)."""
    return make_fcc_zip(tmp_path_factory.mktemp("fccdata") / "r_tower.zip")


# Known-sites fixture (hermetic stand-in for known_sites.csv).
KNOWN_SITES_CSV = """\
name,lat,lon,object_path,height_m,exclusion_radius_ft
TestSiteTower,40.110000,-104.960000,lib/constructions/antennas/comm_tower_25m_1.obj,55,400
# a bad row: out-of-range lat, must be skipped silently
BadSite,120.0,-104.96,lib/constructions/antennas/comm_tower_25m_1.obj,55,0
"""


@pytest.fixture()
def known_sites_csv(tmp_path) -> Path:
    p = tmp_path / "known_sites.csv"
    p.write_text(KNOWN_SITES_CSV, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Script runner helpers
# ---------------------------------------------------------------------------

def run_script(args, cwd, extra_env=None):
    """Run fcc_towers.py as a subprocess; return the CompletedProcess."""
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        cwd=str(cwd), env=env,
        capture_output=True, text=True, timeout=300,
    )


@pytest.fixture()
def workdir(tmp_path):
    """Per-test working directory (keeps the repo clean)."""
    d = tmp_path / "work"
    d.mkdir()
    return d


@pytest.fixture()
def build_pack_run(fcc_zip, known_sites_csv):
    """Run a --text-only build in a fresh workdir; return (proc, workdir, paths).

    Pass --no-known-sites or your own --known-sites to the args; the
    default run uses the hermetic known-sites fixture.
    """
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="ft_test_"))
    out = d / "pack"
    args = ["build",
            "--zip-path", str(fcc_zip),
            "--csv-out", "active_antennas.csv",
            "--out", str(out),
            "--known-sites", str(known_sites_csv),
            "--text-only", "--keep-text"]
    proc = run_script(args, cwd=d)
    return proc, d, out


@pytest.fixture()
def stage_text():
    """Return a function reading the staged .txt for a sub-region.

    ``build --keep-text`` leaves the DSF text under
    <repo>/tmp/overlay_build/<big>/<sub>.txt.
    """
    staging = ROOT / "tmp" / "overlay_build"

    def read(sub_region):
        matches = list(staging.glob(f"*/{sub_region}.txt"))
        if not matches:
            raise AssertionError(f"no staged text for {sub_region}; have: "
                                 f"{list(staging.glob('*.txt'))}")
        return matches[0].read_text(encoding="utf-8")

    return read
