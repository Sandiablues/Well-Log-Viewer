#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
APP_DIR="$HOME/Applications/MultiViewer/Well Log Viewer.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

mkdir -p "$MACOS" "$RESOURCES"

cat > "$CONTENTS/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>Well Log Viewer</string>
  <key>CFBundleExecutable</key>
  <string>WellLogViewerLauncher</string>
  <key>CFBundleIdentifier</key>
  <string>com.multiviewer.welllogviewer</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>Well Log Viewer</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.1</string>
  <key>CFBundleVersion</key>
  <string>1.1</string>
  <key>LSMinimumSystemVersion</key>
  <string>10.15</string>
  <key>LSUIElement</key>
  <true/>
  <key>NSAppleEventsUsageDescription</key>
  <string>Well Log Viewer may check whether its own browser window is still open so it can stop its local runtime cleanly.</string>
</dict>
</plist>
PLIST

cat > "$MACOS/WellLogViewerLauncher" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
exec "$HOME/Applications/MultiViewer/Well-Log-Viewer/scripts/wlv_app_runtime.sh"
LAUNCHER

chmod +x "$MACOS/WellLogViewerLauncher"

if command -v plutil >/dev/null 2>&1; then
  plutil -lint "$CONTENTS/Info.plist" >/dev/null
fi

echo "Installed Well Log Viewer app launcher: $APP_DIR"
echo "Executable: $MACOS/WellLogViewerLauncher"
