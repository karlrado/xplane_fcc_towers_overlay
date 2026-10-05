#!/bin/sh
# Build DSFTool from the vendored X-Plane xptools sources (see LICENSE-dsftool.txt).
#
# Requirements: a C compiler (cc/gcc), a C++ compiler (c++/g++), and the
# zlib development package (e.g. "zlib1g-dev" on Ubuntu/Debian).
#
# Usage:  sh build.sh [output-name]     (default output name: DSFTool)
#
# The compiler flags mirror the official xptools CMake recipe
# (cmake/DSFTool.cmake) from https://github.com/X-Plane/xptools.
set -e
cd "$(dirname "$0")"

CC="${CC:-cc}"
CXX="${CXX:-c++}"
OUT="${1:-DSFTool}"

INCS="-IDSF -IDSFTools -IUtils -IGUI -IObj -IXPTools -Ilzma19/C -IDSF/tri_stripper_101"
# Platform/endianness macros, per xptools CMakeLists.txt (UNIX, Release build):
DEFS="-DLIN=1 -DIBM=0 -DAPL=0 -DDEV=0 -DBIG=0 -DLIL=1"
COMMON="-O2 $DEFS -include Obj/XDefs.h $INCS"

mkdir -p build
rm -f build/*.o

C_SRCS="Utils/EndianUtils.c
Utils/md5.c
Utils/zip.c
Utils/unzip.c
lzma19/C/7zArcIn.c
lzma19/C/7zAlloc.c
lzma19/C/7zBuf.c
lzma19/C/7zCrc.c
lzma19/C/7zCrcOpt.c
lzma19/C/7zDec.c
lzma19/C/7zFile.c
lzma19/C/7zStream.c
lzma19/C/Bcj2.c
lzma19/C/Bra.c
lzma19/C/Bra86.c
lzma19/C/BraIA64.c
lzma19/C/CpuArch.c
lzma19/C/Delta.c
lzma19/C/LzmaDec.c
lzma19/C/Lzma2Dec.c"

CXX_SRCS="DSF/DSFLib.cpp
DSF/DSFLib_Print.cpp
DSF/DSFLibWrite.cpp
DSF/DSFPointPool.cpp
DSF/tri_stripper_101/tri_stripper.cpp
DSFTools/DSF2Text.cpp
DSFTools/DSFToolCmdLine.cpp
Utils/AssertUtils.cpp
Utils/FileUtils.cpp
Utils/MemFileUtils.cpp
Utils/XChunkyFileUtils.cpp
GUI/GUI_Unicode.cpp"

OBJS=""
for s in $C_SRCS; do
    o="build/c_$(echo "$s" | tr '/' '_').o"
    echo "CC   $s"
    $CC $COMMON -c "$s" -o "$o"
    OBJS="$OBJS $o"
done
for s in $CXX_SRCS; do
    o="build/cxx_$(echo "$s" | tr '/' '_').o"
    echo "CXX  $s"
    $CXX $COMMON -c "$s" -o "$o"
    OBJS="$OBJS $o"
done

echo "LINK $OUT"
$CXX $OBJS -lz -o "$OUT"
echo "Built $OUT"
