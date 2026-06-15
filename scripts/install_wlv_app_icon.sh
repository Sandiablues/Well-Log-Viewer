#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
APP="${APP:-$HOME/Applications/MultiViewer/Well Log Viewer.app}"
ICON_SRC="$PROJECT/assets/app_icons/wlv_icon_single_curve.png"
ICON_NAME="WLVIcon"
RESOURCES="$APP/Contents/Resources"
ICONSET="$PROJECT/.wlv_runtime/iconbuild/${ICON_NAME}.iconset"
ICNS_OUT="$RESOURCES/${ICON_NAME}.icns"
INFO_PLIST="$APP/Contents/Info.plist"

if [ ! -d "$PROJECT" ]; then
  echo "STOP: project not found: $PROJECT" >&2
  exit 1
fi
if [ ! -f "$ICON_SRC" ]; then
  echo "STOP: icon source not found: $ICON_SRC" >&2
  exit 1
fi
if [ ! -d "$APP" ]; then
  echo "STOP: app bundle not found: $APP" >&2
  exit 1
fi
if [ ! -f "$INFO_PLIST" ]; then
  echo "STOP: app Info.plist not found: $INFO_PLIST" >&2
  exit 1
fi
if ! command -v sips >/dev/null 2>&1; then
  echo "STOP: sips is required on macOS to build iconset" >&2
  exit 1
fi
if ! command -v iconutil >/dev/null 2>&1; then
  echo "STOP: iconutil is required on macOS to build .icns" >&2
  exit 1
fi

mkdir -p "$RESOURCES" "$ICONSET"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"

make_png() {
  local size="$1"
  local scale="$2"
  local px=$(( size * scale ))
  local suffix=""
  if [ "$scale" -eq 2 ]; then
    suffix="@2x"
  fi
  sips -s format png -z "$px" "$px" "$ICON_SRC" --out "$ICONSET/icon_${size}x${size}${suffix}.png" >/dev/null
}

make_png 16 1
make_png 16 2
make_png 32 1
make_png 32 2
make_png 128 1
make_png 128 2
make_png 256 1
make_png 256 2
make_png 512 1
make_png 512 2

iconutil -c icns "$ICONSET" -o "$ICNS_OUT"

/usr/libexec/PlistBuddy -c "Set :CFBundleIconFile ${ICON_NAME}" "$INFO_PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string ${ICON_NAME}" "$INFO_PLIST"

touch "$APP"

cat <<EOF
Installed WLV app icon.
App:  $APP
Icon: $ICNS_OUT
EOF
