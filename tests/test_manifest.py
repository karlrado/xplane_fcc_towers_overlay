"""Tests for the antenna manifest (antenna_manifest.csv) and the
week-over-week ``diff`` subcommand.

Hermetic: uses the synthetic FCC zip (see conftest) and small hand-written
manifests -- no network, no real FCC data.
"""

import csv
import sys
from pathlib import Path

from conftest import run_script

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import fcc_towers as ft  # noqa: E402


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _make_active_csv(fcc_zip, cwd):
    """Produce active_antennas.csv in ``cwd`` via the csv subcommand."""
    p = run_script(["csv", "--zip-path", str(fcc_zip),
                    "--csv-out", "active_antennas.csv"], cwd=cwd)
    assert p.returncode == 0, p.stderr
    return cwd / "active_antennas.csv"


def _write_manifest(path, rows):
    """Write a manifest from (reg, lat, lon, height, type, state) tuples."""
    path.write_text(
        "registration_number,latitude,longitude,"
        "height_structure_m,structure_type,state\n"
        + "".join(f"{r},{la},{lo},{h},{t},{s}\n"
                  for r, la, lo, h, t, s in rows),
        encoding="utf-8")


# ===========================================================================
# manifest_rows / write_manifest
# ===========================================================================

def test_manifest_one_row_per_reg_sorted_t_preferred(fcc_zip, tmp_path):
    cwd = tmp_path / "work"
    cwd.mkdir()
    active = _make_active_csv(fcc_zip, cwd)
    rows = ft.manifest_rows(str(active))

    regs = [r[0] for r in rows]
    assert regs == sorted(regs)              # deterministic ordering
    assert len(regs) == len(set(regs))       # one row per registration
    assert all(len(r) == len(ft.MANIFEST_COLUMNS) for r in rows)

    by_reg = {r[0]: r for r in rows}
    # A9000009 / reg 1999901 has a T + A coordinate pair; the manifest must
    # use the T-preferred point (40.1), not the A point (40.10005).
    assert float(by_reg["1999901"][1]) < 40.1001


def test_write_manifest_file(fcc_zip, tmp_path):
    cwd = tmp_path / "work"
    cwd.mkdir()
    active = _make_active_csv(fcc_zip, cwd)
    dest = tmp_path / "pack" / "antenna_manifest.csv"
    n = ft.write_manifest(str(active), str(dest))
    assert dest.is_file()
    rows = _read(dest)
    assert len(rows) == n
    assert list(rows[0].keys()) == ft.MANIFEST_COLUMNS


# ===========================================================================
# diff_manifests / format_diff_report
# ===========================================================================

def test_diff_buckets(tmp_path):
    cur = tmp_path / "cur.csv"
    prev = tmp_path / "prev.csv"
    _write_manifest(cur, [
        ("100", "40.0", "-105.0", "100.0", "RADIO_TOWER", "CO"),  # unchanged
        ("200", "41.0", "-106.0", "120.0", "RADIO_TOWER", "CO"),  # added
        ("300", "40.0", "-105.0", "110.0", "RADIO_TOWER", "CO"),  # changed (h)
    ])
    _write_manifest(prev, [
        ("100", "40.0", "-105.0", "100.0", "RADIO_TOWER", "CO"),  # unchanged
        ("300", "40.0", "-105.0", "100.0", "RADIO_TOWER", "CO"),  # changed (h)
        ("400", "42.0", "-107.0", "90.0", "MONOPOLE", "MA"),      # removed
    ])
    d = ft.diff_manifests(str(cur), str(prev))
    assert d["added"] == ["200"]
    assert d["removed"] == ["400"]
    assert d["changed"] == ["300"]
    assert d["unchanged"] == ["100"]

    rep = ft.format_diff_report(d, "test-prev", max_list=200)
    assert "vs test-prev" in rep
    assert "+ 200" in rep
    assert "- 400" in rep
    assert "height 100.0 m -> 110.0 m" in rep


def test_diff_type_change_detected(tmp_path):
    cur = tmp_path / "cur.csv"
    prev = tmp_path / "prev.csv"
    _write_manifest(cur, [("100", "40.0", "-105.0", "100.0",
                           "MONOPOLE", "CO")])
    _write_manifest(prev, [("100", "40.0", "-105.0", "100.0",
                            "RADIO_TOWER", "CO")])
    d = ft.diff_manifests(str(cur), str(prev))
    assert d["changed"] == ["100"]
    assert d["unchanged"] == []
    assert "type RADIO_TOWER -> MONOPOLE" in ft.format_diff_report(d, "p")


def test_diff_missing_previous_is_all_added(tmp_path):
    cur = tmp_path / "cur.csv"
    _write_manifest(cur, [("100", "40.0", "-105.0", "100.0",
                           "RADIO_TOWER", "CO")])
    d = ft.diff_manifests(str(cur), str(tmp_path / "does_not_exist.csv"))
    assert d["prev"] == {}
    assert d["added"] == ["100"]
    assert d["removed"] == []
    assert d["changed"] == []
    assert d["unchanged"] == []


def test_diff_max_list_truncates(tmp_path):
    cur = tmp_path / "cur.csv"
    prev = tmp_path / "prev.csv"
    _write_manifest(cur, [
        (str(i), "40.0", "-105.0", "100.0", "RADIO_TOWER", "CO")
        for i in range(1, 11)
    ])
    _write_manifest(prev, [])
    d = ft.diff_manifests(str(cur), str(prev))
    rep = ft.format_diff_report(d, "prev", max_list=3)
    assert "100.0 m" in rep
    assert "... and 7 more" in rep


# ===========================================================================
# diff subcommand (CLI)
# ===========================================================================

def test_diff_cli_reports(tmp_path):
    cur = tmp_path / "cur.csv"
    prev = tmp_path / "prev.csv"
    _write_manifest(cur, [("100", "40.0", "-105.0", "110.0",
                           "RADIO_TOWER", "CO")])
    _write_manifest(prev, [("100", "40.0", "-105.0", "100.0",
                            "RADIO_TOWER", "CO")])
    out = tmp_path / "report.txt"
    p = run_script(["diff", "--current", str(cur), "--previous", str(prev),
                    "--label", "weekly-2026-10-19", "--out", str(out)],
                   cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    txt = out.read_text(encoding="utf-8")
    assert "vs weekly-2026-10-19" in txt
    assert "height 100.0 m -> 110.0 m" in txt


def test_diff_cli_missing_previous(tmp_path):
    cur = tmp_path / "cur.csv"
    _write_manifest(cur, [("100", "40.0", "-105.0", "100.0",
                           "RADIO_TOWER", "CO")])
    out = tmp_path / "report.txt"
    p = run_script(["diff", "--current", str(cur), "--previous", "none.csv",
                    "--out", str(out)], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "no prior manifest to compare" in out.read_text(encoding="utf-8")


# ===========================================================================
# build writes the manifest into the pack
# ===========================================================================

def test_build_writes_manifest(fcc_zip, additional_sites_csv, tmp_path):
    d = tmp_path / "work"
    d.mkdir()
    out = d / "pack"
    p = run_script(["build", "--zip-path", str(fcc_zip),
                    "--csv-out", "active_antennas.csv", "--out", str(out),
                    "--additional-sites", str(additional_sites_csv),
                    "--text-only"], cwd=d)
    assert p.returncode == 0, p.stderr
    m = out / "antenna_manifest.csv"
    assert m.is_file()
    rows = _read(m)
    regs = [r["registration_number"] for r in rows]
    assert regs == sorted(regs)
    assert len(regs) == len(set(regs))
    # The synthetic set has 13 active registrations.
    assert len(regs) == 13
