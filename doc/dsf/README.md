# DSF reference material

Reference material for building and debugging the X-Plane 12 DSF overlay in
`fcc_towers.py`. Kept here so the project is self-documenting and the
references survive cleanup of machine-local scratch folders.

## Files

| File | What it is |
|---|---|
| `dsf_spec.txt` | Laminar's **DSF File Format Specification** (readable text). The primary reference for atom/property/command/point-pool layout. Note: this is the XP8/9-era spec and does *not* cover later additions (e.g. the `sim/exclude_*` overlay properties) — see `dsf_usage_in_xplane.md`. |
| `dsf_usage_in_xplane.md` | Laminar's official **"DSF Usage In X-Plane"** file-format doc for **X-Plane 11/12** (developer.x-plane.com, snapshot of 2026-09-16, HTML→Markdown). Authoritative for `sim/overlay` and the `sim/exclude_obj/_fac/_for/_bch/_net/_lin/_pol/_str` exclusion zones, `sim/require_*`, XP12 polygonal exclusions, airport-ID filtering, AGL-offset OBJ placement, and overlay restrictions. |
| `kbd_dsf2text_reference.txt` | `DSFTool --dsf2text` output of the stock **KBDL** airport DSF — the authoritative example of the *text* grammar we emit (OBJECT_DEF, OBJECT, POLYGON_DEF, `BEGIN_POLYGON <def> 255 2`, `POLYGON_POINT <lon> <lat>`). |
| `all_exports.txt` | A dump of the `EXPORT` lines from the default-scenery library files. Use it to look up exact object resource paths and to confirm a `lib/…` string matches an `EXPORT` name byte-for-byte (X-Plane does not normalize these). |
| `source/DSF2TextGUI.cpp` | DSF2Text GUI front-end (from Laminar's open-source xptools). |
| `source/README.dsf` | Laminar's DSF module README. |
| `source/README.dsf2text` | DSF2Text tool README. |

For the DSF library source itself — atom IDs and header/footer structs
(`DSFDefs.h`), the 16-bit step point-pool encoding (`DSFPointPool.*`),
and the **text-grammar authority** for the exact `--dsf2text` /
`--text2dsf` line formats (`DSFTools/DSF2Text.cpp`,
`DSFTools/DSFToolCmdLine.cpp`) — see the complete vendored xptools source
in `tools/dsftool/` (pinned commit, licensed).

## Provenance

- `dsf_spec.txt`, `dsf_usage_in_xplane.md`, `source/DSF2TextGUI.cpp`, and
  the two `source/README.*` files are from Laminar Research's open-source
  X-Plane tooling (`xptools`) and the published DSF spec; the rest of the
  xptools source lives in `tools/dsftool/`.
- `kbd_dsf2text_reference.txt` and `all_exports.txt` were generated on the
  build machine from the installed X-Plane 12 default scenery (KBDL airport
  pack and the library `EXPORT` tables).
