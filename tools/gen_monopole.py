"""Generate grey monopole cell-tower objects in X-Plane's "800 OBJ" format.

Purpose
-------
Stock X-Plane scenery has no monopole-style tower above 25 m (the grey
comm_tower meshes stop there; everything taller stock is red/white lattice).
FCC-registered MTOWER/MTA/POLE/UPOLE/MAST towers above 40 m are usually
real-world grey cell monopoles -- a tapered pole with a ring of antenna
panels near the top -- so this tool generates the missing style.  The FCC
height distribution for those types is 93% in 40-75 m with a thin tail past
100 m, hence the default 50/75/100/150 m set (taller clamps to 150 m).

Geometry
--------
* Tapered pole: SEGMENTS radial quads, base radius max(0.6, 0.012*h),
  top radius max(0.25, 0.004*h); no caps.
* Panel ring: PANELS boxes (1.1 m wide x 0.25 m deep) centered ~7 m below
  the top, 0.9 m off the pole surface.  Each face gets its own 4 vertices
  with a true face normal -- X-Plane trusts stored normals and does not
  recompute them (zero normals render flat/unlit; the stock
  radio_100.obj duplicates corner vertices per face for this reason).
* No light bank (site-specific in the real world).
* Flat light-grey PNG texture (written alongside; X-Plane also probes a
  .dds of the same name, but stock objects prove PNG is accepted).

800-OBJ format (reverse-engineered from stock 900-us-objects and
SimHeaven files):
  A
  800
  OBJ
  <blank>
  TEXTURE\\t<name.png>
  POINT_COUNTS <nverts> 0 0 <nidx>    nidx = index count = 3 * ntris
  VT x y z nx ny nz u v               (Y-up, 8 floats per vertex)
  IDX10 i0..i9 / IDX i0..i2           (plain 0-based vertex indices,
                                       3 per triangle, blocks of 10)
  ATTR_no_cull
  TRIS 0 <nidx>                       (also the index count!)

The counts are the number of IDX values, NOT triangles -- a file that
writes the triangle count there fails in X-Plane with "IDX10 index is out
of range".  Do not emit standard Wavefront .obj: X-Plane rejects it with
"bad header or old unsupported version".

Usage
-----
    python tools/gen_monopole.py                     # 50/75/100/150 m -> objects/
    python tools/gen_monopole.py --heights 60 90 --out somewhere/else

Writes <out>/monopole_<H>.obj per height + one shared <out>/monopole_tex.png.
The pack's library.txt (written by fcc_towers.py) EXPORTs them as
fcc_towers/monopole_<H>.obj.
"""
import argparse
import math
import os
import struct


SEGMENTS = 16
PANELS = 8
TEX_NAME = "monopole_tex.png"


def write_png(path, rgb):
    """Minimal 8-bit RGB PNG (standard library only)."""
    import zlib

    r, g, b = rgb
    w = h = 64
    row = b"\x00" + bytes([r, g, b] * w)
    raw = row * h

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit RGB
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", zlib.compress(raw)))
        f.write(chunk(b"IEND", b""))


def generate(h, out_dir):
    """Build one monopole of height h (meters) as <out_dir>/monopole_<H>.obj."""
    r_base = max(0.6, h * 0.012)
    r_top = max(0.25, h * 0.004)
    verts, tris = [], []

    def add_v(x, y, z, nx, ny, nz, u, v):
        verts.append((x, y, z, nx, ny, nz, u, v))
        return len(verts) - 1

    def quad(a, b, c, d):
        tris.append((a, b, c))
        tris.append((a, c, d))

    # --- tapered pole, SEGMENTS radial quads, no caps -------------------
    bot, top = [], []
    for i in range(SEGMENTS):
        a = 2 * math.pi * i / SEGMENTS
        x, z = math.cos(a), math.sin(a)
        u = i / SEGMENTS
        bot.append(add_v(r_base * x, 0.0, r_base * z, x, 0, z, u, 0.0))
        top.append(add_v(r_top * x, h, r_top * z, x, 0, z, u, h / 10.0))
    for i in range(SEGMENTS):
        j = (i + 1) % SEGMENTS
        quad(bot[i], bot[j], top[j], top[i])

    # --- panel ring: PANELS boxes near the top ---------------------------
    # Per-face vertices with real face normals (X-Plane does not recompute
    # normals; zero normals render flat/unlit -- see stock radio_100.obj).
    ph = max(2.5, h * 0.035)
    pw, pd = 1.1, 0.25
    cy = h - max(4.0, h * 0.07) - ph / 2 + 1.0   # centered ~7 m below top
    ring_r = r_top + 0.9
    vuv = cy / 10.0

    def face(corners, n):
        """4 corners (in quad order) + face normal -> 4 verts, 2 tris."""
        idx = [add_v(x, y, z, n[0], n[1], n[2], 0.0, vuv)
               for (x, y, z) in corners]
        quad(idx[0], idx[1], idx[2], idx[3])

    for i in range(PANELS):
        a = 2 * math.pi * i / PANELS + math.pi / PANELS
        ca, sa = math.cos(a), math.sin(a)
        cx, cz = ring_r * ca, ring_r * sa
        # local axes: +x local = tangent t, +z local = outward o
        tx, tz = -sa, ca
        ox, oz = ca, sa

        def P(lx, ly, lz):
            return (cx + lx * tx + lz * ox, cy + ly, cz + lx * tz + lz * oz)

        hb, hd = pw / 2, pd / 2
        face([P(-hb, 0, hd), P(hb, 0, hd), P(hb, ph, hd), P(-hb, ph, hd)], (ox, 0, oz))   # outward
        face([P(-hb, 0, -hd), P(-hb, ph, -hd), P(hb, ph, -hd), P(hb, 0, -hd)], (-ox, 0, -oz))  # inward
        face([P(-hb, 0, -hd), P(hb, 0, -hd), P(hb, 0, hd), P(-hb, 0, hd)], (0, -1, 0))  # bottom
        face([P(-hb, ph, -hd), P(-hb, ph, hd), P(hb, ph, hd), P(hb, ph, -hd)], (0, 1, 0))    # top
        face([P(hb, 0, -hd), P(hb, ph, -hd), P(hb, ph, hd), P(hb, 0, hd)], (tx, 0, tz))      # side +t
        face([P(-hb, 0, -hd), P(-hb, 0, hd), P(-hb, ph, hd), P(-hb, ph, -hd)], (-tx, 0, -tz))  # side -t

    nverts, ntris = len(verts), len(tris)
    nidx = 3 * ntris
    obj_path = os.path.join(out_dir, f"monopole_{int(h)}.obj")
    with open(obj_path, "w") as f:
        f.write("A\n800\nOBJ\n\n")
        f.write(f"TEXTURE\t{TEX_NAME}\n")
        f.write(f"POINT_COUNTS {nverts} 0 0 {nidx}\n")
        for (x, y, z, nx, ny, nz, u, v) in verts:
            f.write(f"VT {x:.6f} {y:.6f} {z:.6f} {nx:.6f} {ny:.6f} {nz:.6f} {u:.6f} {v:.6f}\n")
        idx_flat = [i for t in tris for i in t]
        assert len(idx_flat) == nidx
        assert all(0 <= i < nverts for i in idx_flat), "index out of range!"
        for k in range(0, len(idx_flat), 10):
            chunk = idx_flat[k:k + 10]
            name = "IDX10" if len(chunk) == 10 else "IDX"
            f.write(name + " " + " ".join(map(str, chunk)) + "\n")
        f.write("ATTR_no_cull\n")
        f.write(f"TRIS 0 {nidx}\n")
    print(f"wrote {obj_path}: {nverts} verts, {ntris} tris ({nidx} idx)")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--heights", type=float, nargs="+", default=[50, 75, 100, 150],
                   help="tower heights in meters (default: 50 75 100 150)")
    p.add_argument("--out", default="objects",
                   help="output folder (default: objects/)")
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for h in a.heights:
        if h <= 0:
            raise SystemExit(f"height must be > 0 m, got {h}")
        generate(h, a.out)
    write_png(os.path.join(a.out, TEX_NAME), (158, 160, 164))
    print(f"wrote {os.path.join(a.out, TEX_NAME)} (flat light grey)")


if __name__ == "__main__":
    main()
