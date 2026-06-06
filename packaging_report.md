# Research Report: Packaging Seismic Viewer as a Standalone Executable

## 1. Objective
To identify the most efficient and reliable method for packaging the Seismic Viewer (FastAPI backend + React frontend) into a single standalone executable for Windows and Linux.

## 2. Evaluated Approaches

### A. PyInstaller + pywebview (Recommended)
This approach involves bundling the entire Python application (FastAPI) and the compiled React static files into a single binary using PyInstaller. `pywebview` is used to create a native window that displays the web interface.

*   **Pros:**
    *   Single `.exe` or Linux binary.
    *   Relatively small size (~60-100MB).
    *   No Node.js/Rust dependency in the final package.
    *   FastAPI handles both API and static UI serving.
*   **Cons:**
    *   Depends on the host OS's native webview (Edge WebView2 on Windows, WebKitGTK on Linux).
*   **Suitability:** High. Ideal for scientific tools where a simple, lightweight distribution is preferred.

### B. Electron with Python Sidecar
Electron acts as the shell, running the React app and spawning the FastAPI server as a background subprocess.

*   **Pros:**
    *   Guaranteed consistent UI (uses Chromium).
    *   Rich desktop integration features (notifications, tray, etc.).
*   **Cons:**
    *   Large footprint (>200MB).
    *   Complexity in managing two distinct environments (Node.js and Python).
*   **Suitability:** Medium. Recommended only if advanced browser features or a specific Electron-only plugin is required.

### C. Tauri with Python Sidecar
Similar to Electron but uses a Rust-based shell and the system's native webview.

*   **Pros:**
    *   Extremely small footprint (~20-40MB + Python bundle).
    *   High performance.
*   **Cons:**
    *   Requires Rust knowledge for configuration.
    *   Packaging Python as a "sidecar" can be brittle.
*   **Suitability:** Low-Medium. Good for production-grade apps but might be overkill for this stage.

## 3. Recommended Implementation Plan

### Step 1: Frontend Preparation
- Build the React application: `npm run build`.
- This produces a `dist/` or `build/` folder.

### Step 2: Backend Integration
- Configure FastAPI to serve the static files:
  ```python
  from fastapi.staticfiles import StaticFiles
  app.mount("/", StaticFiles(directory="dist", html=True), name="static")
  ```
- Use `pywebview` to launch the window:
  ```python
  import webview
  import threading
  import uvicorn

  def start_server():
      uvicorn.run(app, host="127.0.0.1", port=8000)

  if __name__ == "__main__":
      t = threading.Thread(target=start_server)
      t.daemon = True
      t.start()
      webview.create_window("Seismic Viewer", "http://127.0.0.1:8000")
      webview.start()
  ```

### Step 3: Packaging with PyInstaller
- Create a `.spec` file or use a command:
  ```bash
  pyinstaller --onefile --noconsole --add-data "dist:dist" main.py
  ```
- Use `Runtime Configuration` to ensure the app knows where to find the `dist` folder when running from a temporary PyInstaller directory (`sys._MEIPASS`).

## 4. Final Recommendation
Use **PyInstaller + pywebview**. It provides the best balance of distribution simplicity (single file), development speed (pure Python), and user experience.
