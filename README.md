# Seismic Viewer Inc. - Project Handover & Handover Notes

## Project Overview
Seismic Viewer Inc. is a high-performance, web-based 2D/3D seismic data visualization application. It is designed to handle large SEG-Y files by converting them into a cloud-optimized, chunked format (**Zarr V3**) that allows for random access and efficient streaming of spatial slices (Inline, Crossline, Time) directly to the browser.

---

## Architecture
The system follows a modern decoupled architecture, unified for distribution as a single package.

### 1. Data Layer (Zarr V3)
*   **Format:** We moved away from direct SEG-Y reading in the browser due to latency and memory constraints.
*   **Ingestion:** The backend parses SEG-Y files using `segyio` and converts them into N-dimensional Zarr arrays.
*   **Optimization:** Data is stored in spatial chunks. The frontend only downloads the specific chunks (bytes) required for the slice the user is currently viewing.

### 2. Backend (FastAPI / Python)
*   **Role:** Metadata management, data ingestion/conversion, and static file serving.
*   **Path:** `/home/team/shared/seismic-viewer-backend`
*   **Key Files:**
    *   `main.py`: Standard API entry point.
    *   `main_packaged.py`: Unified entry point for the desktop app (starts FastAPI + GUI).
    *   `app/services/seismic_service.py`: Core logic for SEG-Y parsing and Zarr conversion.
    *   `API_SPEC.md`: Documentation for the REST endpoints.

### 3. Frontend (React / TypeScript / Vite)
*   **Role:** Interactive UI and GPU-accelerated visualization.
*   **Path:** `/home/team/shared/seismic-viewer-frontend`
*   **3D Viewer:** Uses `@react-three/fiber` (Three.js) to render orthogonal slices in a 3D coordinate system.
*   **2D Viewer:** Uses HTML5 Canvas for ultra-fast trace-by-trace rendering with custom gain/amplification control.
*   **Zarr Integration:** Uses `zarrita.js` and `numcodecs` to stream binary chunks over HTTP.

### 4. Packaging (PyInstaller / pywebview)
*   **Role:** Bundles the entire stack into a single portable binary.
*   **Artifacts:** `/home/team/shared/build_artifacts/seismic-viewer`
*   **Capabilities:**
    *   **Desktop Mode:** Launches a native OS window with the app UI.
    *   **Server Mode:** Use `--server` to run as a standard headless web server.

---

## How to Run

### Production / Standalone
```bash
# Run as a server on port 8000
./seismic-viewer --server --port 8000

# Run as a desktop application (requires a display environment)
./seismic-viewer
```

### Development Mode
1.  **Backend:**
    ```bash
    cd /home/team/shared/seismic-viewer-backend
    source venv/bin/activate
    python3 main.py
    ```
2.  **Frontend:**
    ```bash
    cd /home/team/shared/seismic-viewer-frontend
    npm run dev
    ```

---

## Current Status & Features
- [x] **SEG-Y to Zarr Pipeline:** Automatic conversion of uploaded SEG-Y files.
- [x] **3D Orthogonal Slicing:** Interactive Inline, Crossline, and Time sliders.
- [x] **2D Section Viewer:** High-performance Canvas rendering with Gain control.
- [x] **Volume Registry:** Persists processed datasets across restarts.
- [x] **Standalone Distribution:** Linux executable ready for use.

---

## Roadmap & Future Development
1.  **Cross-Platform Support:** Re-run the build script on Windows and Mac OS environments to generate native `.exe` and `.app` files.
2.  **Multi-Resolution (LOD):** Implement an Octree or downsampled pyramids within the Zarr conversion for even faster loading of massive (>10GB) volumes.
3.  **Geophysical Tools:** 
    *   **Horizon Picking:** Add interactive drawing of interpreted surfaces on 2D and 3D views.
    *   **Color Maps:** Add a library of standard geophysical color maps (e.g., Seismic, Viridis, Greyscale).
4.  **Attribute Computation:** Implement server-side or WebWorker-based computation of seismic attributes (Coherence, RMS Amplitude, Phase).
5.  **Multi-Volume Overlay:** Allow users to overlay Coherence attributes on top of Amplitude volumes with transparency controls.

---

## Handover Artifacts
- **Executable:** `/home/team/shared/build_artifacts/seismic-viewer`
- **Design Docs:** `/home/team/shared/architecture.md`
- **Build Specs:** `/home/team/shared/packaging_report.md`
- **Backend API:** `/home/team/shared/seismic-viewer-backend/API_SPEC.md`
