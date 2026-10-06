# DSFTool (vendored source)

This directory contains the unmodified C/C++ source of **DSFTool**,
Laminar Research's text <-> DSF converter, vendored from the official
[X-Plane XPTools repository](https://github.com/X-Plane/xptools)
(see `LICENSE-dsftool.txt` for license and the pinned commit).

`fcc_towers.py` uses DSFTool to compile the generated region text files
into `.dsf` scenery (the `--text2dsf` direction). The `--dsftool` option
of `fcc_towers.py` points at any working DSFTool binary; this vendored
copy lets CI (and anyone without the Windows SDK binary) build one from
source.

## Building

Requirements: a C compiler (`cc`/`gcc`), a C++ compiler (`c++`/`g++`),
and the zlib development package (`zlib1g-dev` on Ubuntu/Debian).

```sh
sh build.sh          # produces ./DSFTool
```

`build.sh` mirrors the official `cmake/DSFTool.cmake` recipe from the
xptools repository.

`fcc_towers.py` finds a locally built binary automatically (after
checking an explicit `--dsftool` path and the PATH), so no extra setup
is needed once the build succeeds.

## Platforms

| Platform | Status |
|----------|--------|
| Linux (gcc or clang + zlib dev package) | **Proven** -- the CI build runs it on ubuntu-24.04 |
| macOS (Apple clang + `brew install zlib`) | Expected to work, untested |
| Windows, native (MSVC) | Not supported -- `build.sh` uses GCC/Clang flag syntax and `-lz` linking |
| Windows via WSL | Works (it is Linux); note the output is a Linux binary, so run the whole build inside WSL |

On Windows the official prebuilt `DSFTool.exe` (links further below)
is the simplest option.

## Usage

```sh
./DSFTool --text2dsf input.txt output.dsf
./DSFTool --dsf2text input.dsf output.txt
./DSFTool --version
```

## Verification

A Linux binary built from this source (and Laminar's official prebuilt
Linux binary, xptools 24-5) both produce **byte-identical** DSF output
to the official Windows `DSFTool.exe` (2.4.0-b1) for identical `text2dsf`
input.

If building from source is not possible, Laminar hosts official prebuilt
binaries (as of 2026-10-05):

```
https://files.x-plane.com/public/xptools/xptools_lin_24-5.zip   (Linux)
https://files.x-plane.com/public/xptools/xptools_win_24-5.zip   (Windows)
```
