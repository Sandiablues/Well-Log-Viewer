#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
APP_DIR="$HOME/Applications/MultiViewer/Well Log Viewer.app"
DESKTOP_APP="$HOME/Desktop/Well Log Viewer.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
ICON_SOURCE="$PROJECT/assets/app_icons/wlv_icon_single_curve.png"
ICON_ICNS="$PROJECT/.wlv_runtime/iconbuild/WLVIcon.icns"

mkdir -p "$MACOS" "$RESOURCES" "$PROJECT/.wlv_runtime/iconbuild"

if [ -f "$ICON_SOURCE" ]; then
  ICONSET="$PROJECT/.wlv_runtime/iconbuild/WLVIcon.iconset"
  rm -rf "$ICONSET"
  mkdir -p "$ICONSET"
  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$ICON_SOURCE" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    dbl=$((size * 2))
    sips -z "$dbl" "$dbl" "$ICON_SOURCE" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$ICON_ICNS"
fi

cat > "$CONTENTS/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>Well Log Viewer</string>
  <key>CFBundleExecutable</key>
  <string>WellLogViewerLauncher</string>
  <key>CFBundleIconFile</key>
  <string>WLVIcon</string>
  <key>CFBundleIdentifier</key>
  <string>com.multiviewer.welllogviewer</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>Well Log Viewer</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.2</string>
  <key>CFBundleVersion</key>
  <string>1.2</string>
  <key>LSMinimumSystemVersion</key>
  <string>10.15</string>
  <key>LSUIElement</key>
  <true/>
  <key>NSAppleEventsUsageDescription</key>
  <string>Well Log Viewer checks its own app window so it can stop its local runtime cleanly.</string>
</dict>
</plist>
PLIST

cat > "$MACOS/WellLogViewerLauncher" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
exec "$HOME/Applications/MultiViewer/Well-Log-Viewer/scripts/wlv_app_runtime.sh"
LAUNCHER
chmod +x "$MACOS/WellLogViewerLauncher"

if [ -f "$ICON_ICNS" ]; then
  cp "$ICON_ICNS" "$RESOURCES/WLVIcon.icns"
elif [ -f "$APP_DIR/Contents/Resources/WLVIcon.icns" ]; then
  true
fi

plutil -lint "$CONTENTS/Info.plist" >/dev/null
xattr -dr com.apple.quarantine "$APP_DIR" 2>/dev/null || true

rm -rf "$DESKTOP_APP"
cp -R "$APP_DIR" "$DESKTOP_APP"
chmod +x "$DESKTOP_APP/Contents/MacOS/WellLogViewerLauncher"
xattr -dr com.apple.quarantine "$DESKTOP_APP" 2>/dev/null || true

touch "$APP_DIR" "$APP_DIR/Contents/Info.plist" "$DESKTOP_APP" "$DESKTOP_APP/Contents/Info.plist"
killall Finder 2>/dev/null || true

echo "Installed Well Log Viewer app launcher: $APP_DIR"
echo "Installed Desktop app copy: $DESKTOP_APP"
echo "Executable: $MACOS/WellLogViewerLauncher"
