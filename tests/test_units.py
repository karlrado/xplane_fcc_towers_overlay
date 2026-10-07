"""Unit tests for the pure functions in fcc_towers.py.

No file I/O, no network, no DSFTool -- these pin down the conversion,
object-selection, region, and exclusion-zone math.
"""

import math

import pytest

import fcc_towers as ft


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

class TestParsing:
    def test_parse_float_valid(self):
        assert ft.parse_float("12.5") == 12.5
        assert ft.parse_float("  -7 ") == -7.0
        assert ft.parse_float("0") == 0.0

    def test_parse_float_invalid(self):
        assert ft.parse_float("") is None
        assert ft.parse_float("   ") is None
        assert ft.parse_float("abc") is None
        assert ft.parse_float(None) is None

    def test_dms_basic(self):
        assert ft.dms_to_decimal("29", "18", "0.0", "N") == 29.3
        assert ft.dms_to_decimal("95", "6", "46.8", "W") == -95.113
        assert ft.dms_to_decimal("0", "0", "0", "S") == 0
        assert ft.dms_to_decimal(" 29 ", "18", "0.0", "N") == 29.3

    def test_dms_invalid(self):
        assert ft.dms_to_decimal("29", "18", "0.0", "X") is None
        assert ft.dms_to_decimal("", "18", "0.0", "N") is None
        assert ft.dms_to_decimal("29", "x", "0.0", "N") is None
        assert ft.dms_to_decimal("29", "18", None, "N") is None

    def test_to_decimal_range(self):
        assert ft.to_decimal(29.3, None, True) == 29.3
        assert ft.to_decimal(-95.113, None, False) == -95.113
        assert ft.to_decimal(90.0, None, True) == 90.0        # inclusive
        assert ft.to_decimal(90.5, None, True) is None
        assert ft.to_decimal(181.0, None, False) is None
        assert ft.to_decimal(None, None, True) is None

    def test_to_decimal_rounds_to_6(self):
        assert ft.to_decimal(29.123456789, None, True) == 29.123457

    def test_feet(self):
        assert ft.feet(None) is None
        assert ft.feet(200.0) == 656.2
        assert ft.feet(0.0) == 0.0


# ---------------------------------------------------------------------------
# Type normalization + family routing
# ---------------------------------------------------------------------------

class TestTypeRouting:
    def test_norm_type_strips_digits(self):
        assert ft._norm_type("3TA2") == "TA"
        assert ft._norm_type(" 0LTA0 ") == "LTA"
        assert ft._norm_type("gtower") == "GTOWER"
        assert ft._norm_type("") == ""
        assert ft._norm_type(None) == ""

    def test_family_known(self):
        assert ft.family_for("GTOWER") == "big"
        assert ft.family_for("TOWER") == "big"
        assert ft.family_for("3TA2") == "big"
        assert ft.family_for("POLE") == "small"
        assert ft.family_for("UPOLE") == "small"
        assert ft.family_for("MAST") == "small"

    def test_family_suppressed(self):
        for t in ("B", "BANT", "BTWR", "BMAST", "BPOLE", "BPIPE",
                  "TANK", "TREE", "SILO", "PIPE", "STACK", "SIGN"):
            assert ft.family_for(t) is None, t

    def test_family_default(self):
        assert ft.family_for("") == "big"          # blank -> keep drawing
        assert ft.family_for("SOMETHING_NEW") == "big"  # unknown -> big


# ---------------------------------------------------------------------------
# Object selection
# ---------------------------------------------------------------------------

R = "/lib/global8/us/feat_RadioTower_10_10_650"   # radio-tower prefix
A = "lib/constructions/antennas/"                  # airport-library prefix
M = "fcc_towers/"                                  # generated monopoles


class TestPickObject:
    def test_lattice_bands(self):
        assert ft.pick_object(200, "GTOWER") == f"{R}r200.obj"
        assert ft.pick_object(61, "TOWER") == f"{R}r100.obj"
        assert ft.pick_object(50, "TOWER") == f"{R}r50.obj"
        assert ft.pick_object(350, "TOWER") == f"{R}r300.obj"   # clamps
        assert ft.pick_object(1000, "GTOWER") == f"{R}r300.obj"

    def test_monopole_routing_above_cutover(self):
        assert ft.pick_object(45, "MTOWER") == f"{M}monopole_50.obj"
        assert ft.pick_object(70, "MTA") == f"{M}monopole_75.obj"
        assert ft.pick_object(90, "POLE") == f"{M}monopole_100.obj"
        assert ft.pick_object(120, "UPOLE") == f"{M}monopole_150.obj"
        assert ft.pick_object(400, "MAST") == f"{M}monopole_150.obj"  # clamps

    def test_monopole_cutover_boundary(self):
        # exactly 40 m is NOT > 40: stays in the stock (grey comm) set
        assert ft.pick_object(40, "MTOWER") == f"{A}comm_tower_25m_1.obj"

    def test_small_poles_below_cutover(self):
        assert ft.pick_object(12, "POLE") == f"{A}comm_tower_12m_1.obj"
        assert ft.pick_object(7, "POLE") == f"{A}antenna_8m_01.obj"
        assert ft.pick_object(4, "POLE") == f"{A}antenna_5m_01.obj"

    def test_suppressed_types(self):
        assert ft.pick_object(100, "BANT") is None
        assert ft.pick_object(100, "TANK") is None

    def test_missing_height_defaults_to_100(self):
        assert ft.pick_object(None, "TOWER") == f"{R}r100.obj"
        assert ft.pick_object(0, "TOWER") == f"{R}r100.obj"

    def test_forced_family(self):
        assert ft.pick_object(500, "MTOWER", family="big") == f"{R}r300.obj"
        assert ft.pick_object(500, "MTOWER", family="small") == f"{R}r300.obj"
        assert ft.pick_object(10, "TOWER", family="small") == f"{A}comm_tower_10m_1.obj"

    def test_pick_clamps_above_tallest(self):
        assert ft._pick(ft.MONOPOLES, 9999) == f"{M}monopole_150.obj"
        assert ft._pick(ft.BIG_TOWERS, 9999) == f"{R}r300.obj"


class TestPickVariant:
    def test_no_variant_sets_pass_through(self):
        assert ft.pick_variant(f"{R}r100.obj", "123") == f"{R}r100.obj"
        assert ft.pick_variant(f"{M}monopole_50.obj", "123") == f"{M}monopole_50.obj"

    def test_deterministic(self):
        p = f"{A}comm_tower_12m_1.obj"
        assert ft.pick_variant(p, "abc") == ft.pick_variant(p, "abc")
        assert ft.pick_variant(p, "abc") == ft.pick_variant(p, "abc")

    def test_stays_within_variant_set(self):
        for name, variants in ft.OBJECT_VARIANTS.items():
            for i in range(50):
                v = ft.pick_variant(name, f"key{i}")
                assert v in variants, (name, v)

    def test_all_variants_reachable(self):
        # 200 sample keys cover every bucket of every set (checked before
        # hardcoding this assertion)
        for name, variants in ft.OBJECT_VARIANTS.items():
            seen = {ft.pick_variant(name, f"sample{i}") for i in range(200)}
            assert seen == set(variants), (name, seen)

    def test_different_towers_can_differ(self):
        p = f"{A}comm_tower_12m_1.obj"
        assert len({ft.pick_variant(p, f"k{i}") for i in range(20)}) == 2


# ---------------------------------------------------------------------------
# Region math
# ---------------------------------------------------------------------------

class TestRegionFor:
    def test_us_west(self):
        sub, big, props = ft.region_for(29.3, -95.113)
        assert sub == "+29-096"
        assert big == "+20-100"
        assert props == {"west": -96, "east": -95, "south": 29, "north": 30}

    def test_us_west_2(self):
        sub, big, _ = ft.region_for(40.05, -105.05)
        assert sub == "+40-106"
        assert big == "+40-110"

    def test_us_west_3(self):
        sub, big, _ = ft.region_for(40.1, -104.95)
        assert sub == "+40-105"
        assert big == "+40-110"

    def test_east_hemisphere(self):
        sub, big, _ = ft.region_for(48.8, 2.3)
        assert sub == "+48+002"
        assert big == "+40+000"

    def test_southern_hemisphere(self):
        sub, big, props = ft.region_for(-33.5, -70.6)
        assert sub == "-34-071"
        assert big == "-40-080"
        assert props == {"west": -71, "east": -70, "south": -34, "north": -33}

    def test_integer_boundary(self):
        # exactly on a degree line belongs to the SW cell (floor semantics)
        sub, _, _ = ft.region_for(40.0, -105.0)
        assert sub == "+40-105"


# ---------------------------------------------------------------------------
# Exclusion boxes
# ---------------------------------------------------------------------------

class TestExclusionBoxes:
    def test_single_box_geometry(self):
        lon, lat = -105.0, 40.0
        boxes = ft.exclusion_boxes([(lon, lat, "x.obj", 100.0)], 300.0)
        assert len(boxes) == 1
        w, s, e, n = boxes[0]
        r_m = 300.0 * 0.3048
        dlat = r_m / 111_000.0
        dlon = r_m / (111_000.0 * math.cos(math.radians(lat)))
        expected = (lon - dlon, lat - dlat, lon + dlon, lat + dlat)
        assert all(abs(a - b) < 1e-12
                   for a, b in zip((w, s, e, n), expected))
        assert w < lon < e and s < lat < n

    def test_radius_scales(self):
        b100 = ft.exclusion_boxes([(-105.0, 40.0, "x", 100.0)], 100.0)[0]
        b300 = ft.exclusion_boxes([(-105.0, 40.0, "x", 100.0)], 300.0)[0]
        assert (b300[2] - b300[0]) / (b100[2] - b100[0]) == 3.0

    def test_colocated_share_a_box(self):
        # a few meters apart (same ~5 m dedupe cell) -> one box
        p = [(-105.0, 40.0, "a", 100.0),
             (-105.0, 40.0 + 2.0 / 111_000.0, "b", 100.0)]
        assert len(ft.exclusion_boxes(p, 300.0)) == 1

    def test_min_height_filter(self):
        p = [(-105.0, 40.0, "a", 50.0),
             (-105.0, 41.0, "b", 200.0)]
        boxes = ft.exclusion_boxes(p, 300.0, min_height=100.0)
        assert len(boxes) == 1
        assert boxes[0][1] < 41.0 < boxes[0][3]   # the 200 m tower's box

    def test_zero_or_negative_radius(self):
        p = [(-105.0, 40.0, "a", 100.0)]
        assert ft.exclusion_boxes(p, 0.0) == []
        assert ft.exclusion_boxes(p, -5.0) == []


# ---------------------------------------------------------------------------
# DSF text generation
# ---------------------------------------------------------------------------

PROPS = {"west": -105, "east": -104, "south": 40, "north": 41}


class TestRegionText:
    def test_header(self):
        t = ft.region_text(PROPS, [(-104.5, 40.5, "x.obj", 100.0)])
        lines = t.splitlines()
        assert lines[0] == "I"
        assert "800" in lines and "DSF2TEXT" in lines
        assert "PROPERTY sim/west -105" in lines
        assert "PROPERTY sim/east -104" in lines
        assert "PROPERTY sim/north 41" in lines
        assert "PROPERTY sim/south 40" in lines
        assert "PROPERTY sim/planet earth" in lines
        assert "PROPERTY sim/creation_agent fcc_towers" in lines
        assert "PROPERTY sim/overlay 1" in lines
        assert "PROPERTY sim/require_agpoint 1/0" in lines
        assert "PROPERTY sim/require_object 1/0" in lines

    def test_object_def_order_and_indexing(self):
        p = [(-104.9, 40.1, "second.obj", 10.0),
             (-104.5, 40.5, "first.obj", 100.0),
             (-104.2, 40.8, "second.obj", 10.0)]
        t = ft.region_text(PROPS, p)
        defs = [ln for ln in t.splitlines() if ln.startswith("OBJECT_DEF")]
        assert defs == ["OBJECT_DEF second.obj", "OBJECT_DEF first.obj"]
        objs = [ln for ln in t.splitlines() if ln.startswith("OBJECT ")]
        assert objs == ["OBJECT 0 -104.9000000 40.1000000 0.0",
                        "OBJECT 1 -104.5000000 40.5000000 0.0",
                        "OBJECT 0 -104.2000000 40.8000000 0.0"]
        # definitions come before geometry
        assert t.index("OBJECT_DEF") < t.index("OBJECT ")

    def test_exclusion_lines(self):
        box = (-105.1, 40.1, -104.9, 40.3)
        t = ft.region_text(PROPS, [(-104.5, 40.5, "x.obj", 100.0)],
                           exclude_boxes=[box])
        line = f"{box[0]:.7f}/{box[1]:.7f}/{box[2]:.7f}/{box[3]:.7f}"
        assert f"PROPERTY sim/exclude_obj {line}" in t
        assert f"PROPERTY sim/exclude_fac {line}" in t
        # exclusion lines sit right after sim/overlay
        lines = t.splitlines()
        i_overlay = lines.index("PROPERTY sim/overlay 1")
        assert lines[i_overlay + 1].startswith("PROPERTY sim/exclude_obj")

    def test_plinth(self):
        t = ft.region_text(PROPS, [(-104.5, 40.5, "x.obj", 100.0)],
                           plinth=(-104.9, 40.1, -104.1, 40.9))
        assert "POLYGON_DEF texture/white.pol" in t
        assert "BEGIN_POLYGON 0 255 2" in t
        assert t.count("POLYGON_POINT") == 4
        assert "END_POLYGON" in t

    def test_deterministic(self):
        p = [(-104.9, 40.1, "a.obj", 10.0), (-104.5, 40.5, "b.obj", 100.0)]
        boxes = ft.exclusion_boxes(p, 300.0)
        assert ft.region_text(PROPS, p, exclude_boxes=boxes) == \
            ft.region_text(PROPS, p, exclude_boxes=boxes)


# ---------------------------------------------------------------------------
# Plinth clipping + additional sites
# ---------------------------------------------------------------------------

class TestClipPlinth:
    def test_contained(self):
        rect = (-104.9, -104.1, 40.1, 40.9)   # (lon0, lon1, lat0, lat1)
        # the result is (lon0, lat0, lon1, lat1)
        assert ft.clip_plinth_to_region(rect, PROPS) == \
            (-104.9, 40.1, -104.1, 40.9)

    def test_partial(self):
        rect = (-105.5, -103.5, 39.5, 41.5)
        assert ft.clip_plinth_to_region(rect, PROPS) == (-105.0, 40.0, -104.0, 41.0)

    def test_no_overlap(self):
        assert ft.clip_plinth_to_region((-103.0, -102.0, 40.0, 41.0),
                                        PROPS) is None
        # touching an edge is not an intersection
        assert ft.clip_plinth_to_region((-104.0, -103.0, 40.0, 41.0),
                                        PROPS) is None


class TestLoadAdditionalSites:
    def test_valid_and_bad_rows(self, tmp_path):
        p = tmp_path / "ks.csv"
        p.write_text(
            "# comment line\n"
            "name,lat,lon,object_path,height_m,exclusion_radius_ft\n"
            "Alpha,40.1,-104.9,lib/x.obj,55,400\n"
            "Beta,40.2,-104.8,,,\n"
            "Bad,999.0,-104.9,lib/x.obj,55,0\n",
            encoding="utf-8")
        sites = ft.load_additional_sites(str(p))
        assert [s["name"] for s in sites] == ["Alpha", "Beta"]
        alpha = sites[0]
        assert alpha["object_path"] == "lib/x.obj"
        assert alpha["height_m"] == 55.0
        assert alpha["box_ft"] == 400.0
        beta = sites[1]
        assert beta["object_path"] == ""
        assert beta["height_m"] == 100.0      # default
        assert beta["box_ft"] == 0.0          # default

    def test_missing_file(self, tmp_path):
        assert ft.load_additional_sites(str(tmp_path / "nope.csv")) == []


# ---------------------------------------------------------------------------
# DSFTool discovery
# ---------------------------------------------------------------------------

def _fake_vendored(tmp_path):
    """Create an executable fake binary at <tmp>/tools/dsftool/DSFTool."""
    vend = tmp_path / "tools" / "dsftool" / "DSFTool"
    vend.parent.mkdir(parents=True)
    vend.write_text("fake dsftool")
    vend.chmod(0o755)   # required for the os.access(X_OK) check on POSIX
    return vend


class TestFindDsfTool:
    def test_explicit_path_wins(self, tmp_path, monkeypatch):
        p = tmp_path / "mytool"
        p.write_text("x")
        monkeypatch.setattr(ft.shutil, "which", lambda name: None)
        assert ft.find_dsftool(str(p)) == str(p)

    def test_explicit_missing_raises(self):
        with pytest.raises(SystemExit):
            ft.find_dsftool(str("/no/such/dsftool"))

    def test_path_wins_over_vendored(self, tmp_path, monkeypatch):
        vend = _fake_vendored(tmp_path)
        onpath = tmp_path / "bin" / "DSFTool.exe"
        onpath.parent.mkdir()
        onpath.write_text("fake")
        monkeypatch.setattr(
            ft.shutil, "which",
            lambda name: str(onpath) if name == "DSFTool.exe" else None)
        monkeypatch.setattr(ft, "HERE", tmp_path)
        assert ft.find_dsftool("") == str(onpath)
        assert ft.find_dsftool("") != str(vend)

    def test_vendored_fallback(self, tmp_path, monkeypatch):
        vend = _fake_vendored(tmp_path)
        monkeypatch.setattr(ft.shutil, "which", lambda name: None)
        monkeypatch.setattr(ft, "HERE", tmp_path)
        assert ft.find_dsftool("") == str(vend)

    def test_none_found_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ft.shutil, "which", lambda name: None)
        monkeypatch.setattr(ft, "HERE", tmp_path)
        with pytest.raises(SystemExit) as exc:
            ft.find_dsftool("")
        assert "tools/dsftool/build.sh" in str(exc.value)


# ---------------------------------------------------------------------------
# Help output
# ---------------------------------------------------------------------------

class TestHelp:
    def test_terse_help_lists_commands_and_flags(self, capsys):
        with pytest.raises(SystemExit) as exc:
            ft.main(["-h"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        for token in ("build", "showroom", "csv",
                      "--radio-only", "--exclude-radius-ft",
                      "--help-detailed"):
            assert token in out
        # The long module docstring must NOT be part of the terse help.
        assert "pipe-delimited" not in out

    def test_help_detailed_prints_full_docstring(self, capsys):
        assert ft.main(["--help-detailed"]) == 0
        out = capsys.readouterr().out
        assert "pipe-delimited" in out
        assert "RA.dat" in out

    def test_subcommand_help_still_full(self, capsys):
        with pytest.raises(SystemExit) as exc:
            ft.main(["build", "-h"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "--exclude-radius-ft" in out
        # The per-option description text is still present here.
        assert "exclusion-zone" in out
