# WLV App Icon

The Well Log Viewer macOS app uses a minimal MultiViewer-family icon:
a dark navy rounded-square icon with a single yellow well-log curve down the
middle.

Canonical source image:

```text
assets/app_icons/wlv_icon_single_curve.png
```

Install/update the icon in the macOS app bundle with:

```bash
cd "$HOME/Applications/MultiViewer/Well-Log-Viewer"
scripts/install_wlv_app_icon.sh
```

The installer writes:

```text
/Users/donarcher/Applications/MultiViewer/Well Log Viewer.app/Contents/Resources/WLVIcon.icns
```

and sets `CFBundleIconFile` in the app `Info.plist`.
