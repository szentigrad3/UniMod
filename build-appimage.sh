#!/usr/bin/env bash
# Build UniMod x86_64 AppImage; requires PyInstaller and appimagetool.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
ARCH_TYPE="$(uname -m)"
if [[ "$ARCH_TYPE" != x86_64 ]]; then
  echo "This builder currently supports x86_64 only (got $ARCH_TYPE)." >&2
  exit 2
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! "$PYTHON_BIN" -c 'import PyInstaller' >/dev/null 2>&1; then
  cat >&2 <<EOF
Missing PyInstaller for $PYTHON_BIN.
Set up a build virtualenv on Linux:
    python3 -m venv .buildvenv
    .buildvenv/bin/python -m pip install pyinstaller
    PYTHON_BIN=.buildvenv/bin/python ./build-appimage.sh
EOF
  exit 2
fi
APPIMAGETOOL="${APPIMAGETOOL:-$(command -v appimagetool || true)}"
if [[ -z "$APPIMAGETOOL" || ! -x "$APPIMAGETOOL" ]]; then
  echo "Missing appimagetool. Download the official x86_64 binary from https://github.com/AppImage/appimagetool/releases and pass APPIMAGETOOL=/path/to/appimagetool." >&2
  exit 2
fi
BUILD_DIR="${BUILD_DIR:-$PWD/build-appimage}"
OUTPUT_DIR="${OUTPUT_DIR:-$PWD/dist-appimage}"
mkdir -p "$BUILD_DIR" "$OUTPUT_DIR"
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean --collect-all json5 --hidden-import instance_bridge --hidden-import nexus_queue --hidden-import nxm_handler --hidden-import archive_discovery --hidden-import source_receipts --hidden-import source_provenance --hidden-import bepinex_nexus_evidence --hidden-import bepinex_search_hints --hidden-import candidate_review --hidden-import provider_access --hidden-import provider_catalogues --hidden-import provider_downloads --hidden-import provider_staging --hidden-import modio_files --hidden-import modio_managed --hidden-import modio_diagnostics --hidden-import modio_selftest --hidden-import modio_live_probe --hidden-import modio_guide --hidden-import minecraft_profiles --hidden-import minecraft_dependencies --hidden-import minecraft_mrpack --hidden-import nexus_oauth --hidden-import nexus_integration --add-data "$PWD/stardew-aio-nexus-links.json:." --windowed --onedir --name unimod \
  --distpath "$BUILD_DIR/dist" --workpath "$BUILD_DIR/work" --specpath "$BUILD_DIR/spec" \
  "$PWD/unimod.py"
APPDIR="$BUILD_DIR/UniMod.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$BUILD_DIR/dist/unimod" "$APPDIR/usr/lib/unimod"
cp unimod.desktop "$APPDIR/"; cp unimod.desktop "$APPDIR/usr/share/applications/"
cp unimod.png "$APPDIR/"; cp unimod.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export PYTHONNOUSERSITE=1
# Arch/CachyOS may use /etc/ssl/cert.pem while the Python runtime was built
# on Debian/Ubuntu. Respect an explicit SSL_CERT_FILE when supplied.
if [ -z "${SSL_CERT_FILE:-}" ]; then
  for cert in /etc/ssl/cert.pem /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt; do
    if [ -r "$cert" ]; then export SSL_CERT_FILE="$cert"; break; fi
  done
fi
exec "$HERE/usr/lib/unimod/unimod" "$@"
EOF
chmod +x "$APPDIR/AppRun"
ARCH=x86_64 VERSION=0.55-test12 "$APPIMAGETOOL" "$APPDIR" "$OUTPUT_DIR/UniMod-0.55-test12-x86_64.AppImage"
chmod +x "$OUTPUT_DIR/UniMod-0.55-test12-x86_64.AppImage"
echo "Created $OUTPUT_DIR/UniMod-0.55-test12-x86_64.AppImage"
echo "Note: AppImage host compatibility depends on the system used to build PyInstaller and its bundled glibc dependencies."
