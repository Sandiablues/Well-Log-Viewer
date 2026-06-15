# WLV Runtime App Launcher

The supported local launch path is:

`/Users/donarcher/Applications/MultiViewer/Well Log Viewer.app`

The launcher starts only the WLV runtime:

- backend: `http://127.0.0.1:8001`
- frontend: `http://127.0.0.1:5173`

The frontend uses Vite `--strictPort`; it must not drift to 5174 or 5175.

The launcher opens a dedicated Chrome app window using a WLV-only Chrome profile
inside `.wlv_runtime/chrome-profile`. Closing that WLV browser window causes the
launcher to stop only WLV-owned backend/frontend processes.

The stop logic does not kill SDV/SBLT processes by port alone. If another app
owns a WLV-required port, the launcher fails clearly instead of killing it.
