"""Integration tests: run fcc_towers.py end to end on the synthetic FCC
zip (hermetic -- no network, no real FCC data).

Covers the CLI option surface, the CSV pipeline, dedup, region routing,
exclusion zones, additional sites, assets, and the showroom build.  The
DSFTool round-trip lives in test_dsf.py.
"""

import csv
import math
import pathlib
import re

import pytest

from conftest import run_script

OBJ = re.compile(r"^OBJECT \d+ ", re.M)
OBJDEF = re.compile(r"^OBJECT_DEF ", re.M)
EXCL = re.compile(r"^PROPERTY sim/exclude_(obj|fac) ", re.M)


def objects(text):
    return OBJ.findall(text)


def objects_or_zero(stage_read, sub_region):
    """Object count for a region, or 0 if the build wrote no file for it
    (e.g. every candidate was filtered out)."""
    try:
        return len(objects(stage_read(sub_region)))
    except AssertionError:
        return 0


# ===========================================================================
# csv subcommand
# ===========================================================================

def _csv_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _by_reg(rows, reg):
    return [r for r in rows if r["registration_number"] == reg]


class TestCsv:
    def test_default_rows(self, fcc_zip, tmp_path):
        out = tmp_path / "active_antennas.csv"
        p = run_script(["csv", "--zip-path", str(fcc_zip),
                        "--csv-out", str(out)], cwd=tmp_path)
        assert p.returncode == 0, p.stderr
        rows = _csv_rows(out)
        # 13 active RAs; A9000009 has two coordinate rows (T + A) -> 14 rows.
        # A9000012 (no CO at all) and A9000013 (only an invalid CO) each get
        # one row with blank lat/lon.
        assert len(rows) == 14, [r["registration_number"] for r in rows]
        regs = {r["registration_number"] for r in rows}
        assert "1254229" not in regs   # archived (archive=A) excluded
        assert "1254230" not in regs   # status D excluded by default
        blank = {r["registration_number"] for r in rows if not r["latitude"]}
        assert blank == {"1254231", "1254232"}   # unplaceable, listed blank

    def test_t_a_pair_kept_in_csv(self, fcc_zip, tmp_path):
        out = tmp_path / "active_antennas.csv"
        p = run_script(["csv", "--zip-path", str(fcc_zip),
                        "--csv-out", str(out)], cwd=tmp_path)
        assert p.returncode == 0, p.stderr
        pair = _by_reg(_csv_rows(out), "1999901")
        assert len(pair) == 2
        ctypes = {r["coordinate_type"] for r in pair}
        assert ctypes == {"T", "A"}
        assert len({(r["latitude"], r["longitude"]) for r in pair}) == 2

    def test_no_coord_ra_emitted_blank(self, fcc_zip, tmp_path):
        out = tmp_path / "active_antennas.csv"
        p = run_script(["csv", "--zip-path", str(fcc_zip),
                        "--csv-out", str(out)], cwd=tmp_path)
        assert p.returncode == 0, p.stderr
        solo = _by_reg(_csv_rows(out), "1254231")
        assert len(solo) == 1
        assert solo[0]["latitude"] == "" and solo[0]["longitude"] == ""

    def test_include_archived(self, fcc_zip, tmp_path):
        out = tmp_path / "active_antennas.csv"
        p = run_script(["csv", "--zip-path", str(fcc_zip),
                        "--csv-out", str(out),
                        "--include-archived"], cwd=tmp_path)
        assert p.returncode == 0, p.stderr
        assert len(_by_reg(_csv_rows(out), "1254229")) == 1

    def test_status_includes_d(self, fcc_zip, tmp_path):
        out = tmp_path / "active_antennas.csv"
        p = run_script(["csv", "--zip-path", str(fcc_zip),
                        "--csv-out", str(out),
                        "--status", "C,G,D"], cwd=tmp_path)
        assert p.returncode == 0, p.stderr
        assert len(_by_reg(_csv_rows(out), "1254230")) == 1

    def test_zip_path_missing(self, tmp_path):
        p = run_script(["csv", "--zip-path", str(tmp_path / "nope.zip"),
                        "--csv-out", "x.csv"], cwd=tmp_path)
        assert p.returncode == 2
        assert "does not exist" in p.stderr

    def test_no_download_without_cache(self, tmp_path):
        cache = tmp_path / "empty_cache"
        cache.mkdir()
        p = run_script(["csv", "--no-download",
                        "--cache-dir", str(cache),
                        "--csv-out", "x.csv"], cwd=tmp_path)
        assert p.returncode == 2
        assert "no cached zip" in p.stderr


# ===========================================================================
# build subcommand (--text-only)
# ===========================================================================
# Default run (build_pack_run fixture):
#   +29-096 : TALL-LAT r200, SMALL ct12m, NOHEIGHT r100   (BANT suppressed)
#   +40-106 : mono 50/75/100/150/150(clamp) + AONLY r100
#   +40-105 : DUP (one object at the T point) + known site
# kept=10, deduped=1.

class TestBuildDefaults:
    def test_exit0(self, build_pack_run):
        proc, _, _ = build_pack_run
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "antennas placed : 10" in proc.stdout
        assert "deduped 1 duplicate antenna rows" in proc.stdout

    def test_pack_assets(self, build_pack_run):
        _, _, out = build_pack_run
        names = {p.name for p in pathlib.Path(out / "objects").iterdir()}
        for n in ("monopole_50.obj", "monopole_75.obj", "monopole_100.obj",
                  "monopole_150.obj", "monopole_tex.png"):
            assert n in names, names
        lib = (out / "library.txt").read_text(encoding="utf-8")
        assert lib.count("EXPORT ") == 4
        for n in (50, 75, 100, 150):
            assert f"EXPORT fcc_towers/monopole_{n}.obj\tobjects/monopole_{n}.obj" in lib

    def test_region_29_096(self, build_pack_run, stage_text):
        _, _, _ = build_pack_run
        t = stage_text("+29-096")
        assert len(objects(t)) == 3
        assert len(OBJDEF.findall(t)) == 3
        assert "OBJECT_DEF /lib/global8/us/feat_RadioTower_10_10_650r200.obj" in t
        # reg 1254226 (the 12 m POLE) hashes to variant _2 of its 2-variant set
        assert "OBJECT_DEF lib/constructions/antennas/comm_tower_12m_2.obj" in t
        assert "OBJECT_DEF /lib/global8/us/feat_RadioTower_10_10_650r100.obj" in t
        assert len(EXCL.findall(t)) == 6            # 3 boxes x obj+fac

    def test_region_40_106(self, build_pack_run, stage_text):
        _, _, _ = build_pack_run
        t = stage_text("+40-106")
        assert len(objects(t)) == 6
        assert len(OBJDEF.findall(t)) == 5
        for n in (50, 75, 100, 150):
            assert f"OBJECT_DEF fcc_towers/monopole_{n}.obj" in t
        assert len(EXCL.findall(t)) == 12          # 6 boxes x obj+fac

    def test_region_40_105_dedup(self, build_pack_run, stage_text):
        _, _, _ = build_pack_run
        t = stage_text("+40-105")
        assert len(objects(t)) == 2                # DUP + known site
        # exactly one DUP object, at the T (exact) coordinate
        dup_lines = [ln for ln in t.splitlines()
                     if ln.startswith("OBJECT ") and "-104.9500000 40.1000000" in ln]
        assert len(dup_lines) == 1
        # the A (approximate) coordinate must not be placed
        assert "-104.9495000" not in t
        # known site placed with its explicit object
        assert "OBJECT_DEF lib/constructions/antennas/comm_tower_25m_1.obj" in t
        # 2 per-tower boxes + 1 known-site box
        assert len(EXCL.findall(t)) == 6


class TestBuildOptions:
    def _run(self, fcc_zip, additional_sites_csv, tmp_path, *extra):
        out = tmp_path / "pack"
        args = ["build",
                "--zip-path", str(fcc_zip),
                "--csv-out", "active_antennas.csv",
                "--out", str(out),
                "--additional-sites", str(additional_sites_csv),
                "--text-only", "--keep-text"] + list(extra)
        p = run_script(args, cwd=tmp_path)
        assert p.returncode == 0, p.stdout + p.stderr
        return out

    def test_no_exclude(self, fcc_zip, additional_sites_csv, tmp_path, stage_text):
        self._run(fcc_zip, additional_sites_csv, tmp_path, "--no-exclude")
        for sub in ("+29-096", "+40-106", "+40-105"):
            assert len(EXCL.findall(stage_text(sub))) == 0

    def test_exclude_radius_100(self, fcc_zip, additional_sites_csv, tmp_path, stage_text):
        self._run(fcc_zip, additional_sites_csv, tmp_path,
                  "--exclude-radius-ft", "100", "--no-additional-sites")
        t = stage_text("+40-105")                  # only the DUP tower now
        lines = [ln for ln in t.splitlines()
                 if ln.startswith("PROPERTY sim/exclude_obj ")]
        assert len(lines) == 1
        w, s, e, n = (float(x) for x in lines[0].split(" ", 2)[2].split("/"))
        dlat = 100.0 * 0.3048 / 111_000.0
        # 1e-6: the text format rounds coordinates to 7 decimal places
        assert abs((n - s) - 2 * dlat) < 1e-6

    def test_exclude_min_height(self, fcc_zip, additional_sites_csv, tmp_path, stage_text):
        self._run(fcc_zip, additional_sites_csv, tmp_path,
                  "--exclude-min-height", "100")
        # +29-096: TALL-LAT (200) + NOHEIGHT (default 100) box; SMALL (12) not
        t = stage_text("+29-096")
        assert len(EXCL.findall(t)) == 4

    def test_max_objects(self, fcc_zip, additional_sites_csv, tmp_path, stage_text):
        self._run(fcc_zip, additional_sites_csv, tmp_path,
                  "--max-objects", "4", "--no-additional-sites")
        total = sum(objects_or_zero(stage_text, s)
                    for s in ("+29-096", "+40-106", "+40-105"))
        assert total == 4

    def test_state_filter(self, fcc_zip, additional_sites_csv, tmp_path, stage_text):
        self._run(fcc_zip, additional_sites_csv, tmp_path, "--state", "TX")
        assert len(objects(stage_text("+29-096"))) == 3
        # CO towers filtered out; the known site bypasses state filters
        assert len(objects(stage_text("+40-105"))) == 1
        with pytest.raises(AssertionError):
            stage_text("+40-106")

    def test_min_height(self, fcc_zip, additional_sites_csv, tmp_path, stage_text):
        self._run(fcc_zip, additional_sites_csv, tmp_path, "--min-height", "50")
        # SMALL (12 m) and MONO50 (45 m) drop out; everything else stays
        assert len(objects(stage_text("+29-096"))) == 2
        assert len(objects(stage_text("+40-106"))) == 5

    def test_max_height(self, fcc_zip, additional_sites_csv, tmp_path, stage_text):
        self._run(fcc_zip, additional_sites_csv, tmp_path, "--max-height", "100")
        # TALL-LAT (200), MONO150 (120), MONOCLAMP (400) drop out
        assert len(objects(stage_text("+29-096"))) == 2
        assert len(objects(stage_text("+40-106"))) == 4

    def test_object_family_override(self, fcc_zip, additional_sites_csv, tmp_path, stage_text):
        self._run(fcc_zip, additional_sites_csv, tmp_path, "--object", "small")
        t = stage_text("+40-106")
        assert "fcc_towers/monopole" not in t       # routing bypassed
        assert "OBJECT_DEF /lib/global8/us/feat_RadioTower_10_10_650r50.obj" in t

    def test_radio_only(self, fcc_zip, additional_sites_csv, tmp_path, stage_text):
        self._run(fcc_zip, additional_sites_csv, tmp_path, "--radio-only")
        t = stage_text("+29-096")
        assert len(objects(t)) == 2                # GTOWER r200 + TOWER r100
        assert "comm_tower" not in t               # 12 m POLE skipped
        assert ("OBJECT_DEF /lib/global8/us/"
                "feat_RadioTower_10_10_650r200.obj") in t
        assert ("OBJECT_DEF /lib/global8/us/"
                "feat_RadioTower_10_10_650r100.obj") in t
        t = stage_text("+40-106")
        assert len(objects(t)) == 1                # TOWER 55 m -> r100
        assert "monopole" not in t
        assert ("OBJECT_DEF /lib/global8/us/"
                "feat_RadioTower_10_10_650r100.obj") in t
        t = stage_text("+40-105")
        assert len(objects(t)) == 2                # TOWER r100 + known site
        assert ("OBJECT_DEF lib/constructions/antennas/comm_tower_25m_1.obj"
                ) in t

    def test_radio_only_dry_run(self, fcc_zip, additional_sites_csv, tmp_path):
        out = tmp_path / "pack"
        args = ["build",
                "--zip-path", str(fcc_zip),
                "--csv-out", "active_antennas.csv",
                "--out", str(out),
                "--additional-sites", str(additional_sites_csv),
                "--dry-run", "--radio-only"]
        p = run_script(args, cwd=tmp_path)
        assert p.returncode == 0, p.stdout + p.stderr
        assert "kept=4" in p.stdout
        assert "radio-only: skipped 6 non-lattice objects" in p.stdout
        assert not out.exists()                    # nothing written

    def test_dry_run(self, fcc_zip, additional_sites_csv, tmp_path):
        out = tmp_path / "pack"
        args = ["build",
                "--zip-path", str(fcc_zip),
                "--csv-out", "active_antennas.csv",
                "--out", str(out),
                "--additional-sites", str(additional_sites_csv),
                "--dry-run"]
        p = run_script(args, cwd=tmp_path)
        assert p.returncode == 0, p.stdout + p.stderr
        assert "[dry-run]" in p.stdout
        assert "kept=10" in p.stdout
        assert "deduped=1" in p.stdout
        assert not out.exists()                     # nothing written

    def test_no_additional_sites(self, fcc_zip, additional_sites_csv, tmp_path, stage_text):
        self._run(fcc_zip, additional_sites_csv, tmp_path, "--no-additional-sites")
        t = stage_text("+40-105")
        assert len(objects(t)) == 1                 # DUP only
        assert "comm_tower_25m_1" not in t
        assert len(EXCL.findall(t)) == 2            # one tower box

    def test_deterministic_output(self, fcc_zip, additional_sites_csv, tmp_path,
                                  stage_text):
        self._run(fcc_zip, additional_sites_csv, tmp_path, "--out", "pack1")
        first = {s: stage_text(s) for s in ("+29-096", "+40-106", "+40-105")}
        self._run(fcc_zip, additional_sites_csv, tmp_path, "--out", "pack2")
        for sub, text in first.items():
            assert stage_text(sub) == text, sub


# ===========================================================================
# showroom subcommand
# ===========================================================================

class TestShowroom:
    def test_build(self, tmp_path, stage_text):
        out = tmp_path / "sr"
        p = run_script(["showroom", "--out", str(out),
                        "--text-only", "--keep-text"], cwd=tmp_path)
        assert p.returncode == 0, p.stdout + p.stderr

        import pathlib
        names = {q.name for q in pathlib.Path(out / "objects").iterdir()}
        assert "monopole_150.obj" in names
        lib = (out / "library.txt").read_text(encoding="utf-8")
        assert lib.count("EXPORT ") == 4

        # plinth texture generated alongside the pack
        assert (out / "texture" / "white.pol").exists()
        assert (out / "texture" / "white.png").exists()

        t = stage_text("+40-104")
        # 25 small-cluster + 11 tall-cluster objects, all distinct
        assert len(objects(t)) == 36
        assert len(OBJDEF.findall(t)) == 36
        assert "BEGIN_POLYGON 0 255 2" in t
        assert "fcc_towers/monopole_50.obj" in t
