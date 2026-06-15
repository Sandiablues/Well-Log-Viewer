# WLV Local App Runtime Launcher

This runtime is the local desktop profile for the Well Log Viewer.

Fixed local endpoints:

- Backend: `http://127.0.0.1:8001`
- Frontend: `http://127.0.0.1:5173`

Runtime scripts:

- `scripts/wlv_runtime_lib.sh` — shared constants and safe helper functions.
- `scripts/wlv_app_start.sh` — starts backend and frontend only.
- `scripts/wlv_app_open.sh` — opens the dedicated Chrome app window only.
- `scripts/wlv_app_runtime.sh` — thin macOS app entry point: stop previous WLV runtime, start services, open app, monitor window/profile, stop services on close.
- `scripts/wlv_app_stop.sh` — idempotent WLV-owned cleanup only.
- `scripts/wlv_app_status.sh` — read-only status.
- `scripts/install_wlv_app_launcher.sh` — installs the macOS app bundle and Desktop app copy.

Design constraints:

- WLV backend is fixed to port `8001`.
- WLV frontend is fixed to port `5173` with Vite `--strictPort`.
- Non-WLV processes on WLV ports are reported and left untouched.
- SDV, SBLT, normal Chrome, and unrelated processes must not be killed.
- The Desktop app is a real `.app` bundle copy, not a Finder alias.
- The launcher never writes its own PID before calling a stop routine that can kill it.
- Stop/start/open/status responsibilities are separated.
