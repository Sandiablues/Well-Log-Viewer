# Seismic Viewer Backend

This is the backend service for the Seismic Viewer application. It provides endpoints for uploading SEG-Y files, parsing them, and converting them to Zarr format for efficient web-based visualization.

## Tech Stack
- **Framework:** FastAPI
- **Seismic Processing:** segyio, NumPy
- **Data Format:** Zarr (V3)
- **Server:** Uvicorn

## Project Structure
- `app/`: Main application code
  - `api/`: API endpoints
  - `services/`: Business logic (SEG-Y parsing, Zarr conversion)
  - `models/`: Pydantic models
- `data/`: Local storage for uploaded files and Zarr data
- `scripts/`: Utility scripts (e.g., dummy data generator)

## Getting Started

### Installation
```bash
pip install -r requirements.txt
```

### Running the Server
```bash
python3 main.py
```
The server will start at `http://0.0.0.0:8000`.

### API Endpoints
- `POST /api/upload`: Upload a SEG-Y file. Returns metadata and a URL to the Zarr dataset.
- `GET /api/volumes`: List available volumes.
- `GET /api/volumes/{volume_id}/metadata`: Get metadata for a specific volume.
- `GET /data/zarr/{volume_id}.zarr/...`: Direct access to Zarr chunks and metadata.

## Desktop Mode and Packaging

The application can be run as a standalone desktop application using `pywebview`.

### Running in Desktop Mode (Development)
```bash
python3 main_packaged.py
```
This will start the FastAPI server in a background thread and open a native window pointing to it.

### Command Line Arguments
- `--server`: Run in server mode (no window).
- `--host`: Host for the server (default: 127.0.0.1).
- `--port`: Port for the server (default: 8000).

### Packaging as Standalone Executable
To package the app into a single executable for distribution:
1. Ensure `pyinstaller` and `pywebview` are installed.
2. Build the frontend and place it in the `dist/` directory.
3. Run PyInstaller using the provided spec file:
   ```bash
   pyinstaller seismic-viewer.spec
   ```
The resulting executable will be in the `dist/` folder. It bundles the FastAPI backend, the React frontend, and any sample data in the `data/` folder.
