"""DSFTool round-trip test: build the pack for real (binary .dsf files),
then decode a region back to text with DSFTool --dsf2text and check the
structure.

Skipped when DSFTool is not on the PATH (dev boxes that only do
--text-only builds).  The GitHub test job builds DSFTool from the vendored
source and puts it on the PATH, so this test runs in CI.

Deliberately loose on formatting: --dsf2text output details (line order,
precision, property casing) can differ between DSFTool builds, so we
assert structure and content, not exact coordinates.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import run_script

DSFTOOL = shutil.which("DSFTool.exe") or shutil.which("DSFTool")

pytestmark = pytest.mark.skipif(
    DSFTOOL is None,
    reason="DSFTool not found on the PATH",
)

OBJ = re.compile(r"^OBJECT \d+ ", re.M)


def dsf2text(dsf: Path, out_txt: Path) -> str:
    r = subprocess.run(
        [DSFTOOL, "--dsf2text", str(dsf), str(out_txt)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return out_txt.read_text(encoding="utf-8")


def test_round_trip(fcc_zip, tmp_path):
    out = tmp_path / "pack"
    p = run_script(["build",
                    "--zip-path", str(fcc_zip),
                    "--csv-out", "active_antennas.csv",
                    "--out", str(out),
                    "--no-additional-sites"], cwd=tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "converted OK/fail: 3/0" in p.stdout

    nav = out / "Earth nav data"
    dsfs = sorted(d.relative_to(nav).as_posix() for d in nav.rglob("*.dsf"))
    assert dsfs == ["+20-100/+29-096.dsf",
                    "+40-110/+40-105.dsf",
                    "+40-110/+40-106.dsf"], dsfs

    # binary sanity: X-Plane 12 DSF magic
    for rel in dsfs:
        head = (nav / rel).read_bytes()[:8]
        assert head == b"XPLNEDSF", (rel, head)

    # decode the DUP region: exactly one tower (T+A deduped), one box
    t = dsf2text(nav / "+40-110" / "+40-105.dsf", tmp_path / "decoded.txt")
    assert len(OBJ.findall(t)) == 1
    assert len(re.findall(r"^OBJECT_DEF ", t, re.M)) == 1
    assert "sim/overlay 1" in t
    assert "creation_agent" in t and "fcc_towers" in t
    assert "sim/exclude_obj" in t
    assert "sim/exclude_fac" in t
    # the tower object must reference a known stock/generic path
    defs = re.findall(r"^OBJECT_DEF (\S+)$", t, re.M)
    assert len(defs) == 1
    assert "comm_tower" in defs[0] or "RadioTower" in defs[0] or \
        "monopole" in defs[0], defs
