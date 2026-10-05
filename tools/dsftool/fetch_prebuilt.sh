#!/bin/sh
# Fallback for CI: download Laminar's official prebuilt DSFTool (Linux)
# instead of building from the vendored sources in this directory.
#
# Usage:  sh fetch_prebuilt.sh [output-name]     (default output name: DSFTool)
#
# Requires: curl, unzip. The URL/version can be overridden via DSFTOOL_URL.
set -e
cd "$(dirname "$0")"

URL="${DSFTOOL_URL:-https://files.x-plane.com/public/xptools/xptools_lin_24-5.zip}"
OUT="${1:-DSFTool}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

curl -fL "$URL" -o "$tmp/xptools.zip"
if command -v unzip >/dev/null 2>&1; then
    unzip -o -q "$tmp/xptools.zip" -d "$tmp"
else
    python3 -m zipfile -e "$tmp/xptools.zip" "$tmp/"
fi
install -m 755 "$tmp/tools/DSFTool" "$OUT"

echo "Fetched official prebuilt:"
"$OUT" --version
