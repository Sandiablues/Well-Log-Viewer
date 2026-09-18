import os
import sys
import threading
import uvicorn
import webview
import argparse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.endpoints import router as api_router

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

app = FastAPI(title="Seismic Viewer")

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
# For data persistence, we might want to use a user directory if not provided
DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), ".seismic-viewer")
DATA_DIR = os.environ.get("SEISMIC_DATA_DIR", get_resource_path("data"))

# If we are in PyInstaller, the bundled 'data' is read-only and temporary.
# If we want uploads to persist, we should probably use a persistent location.
# But for now, let's stick to the bundled one or the one provided by env var.

UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
ZARR_DIR = os.path.join(DATA_DIR, "zarr")
VOLUMES_JSON = os.path.join(DATA_DIR, "volumes.json")
FRONTEND_DIST = get_resource_path("dist")

# Set env vars for endpoints
os.environ["UPLOADS_DIR"] = UPLOADS_DIR
os.environ["ZARR_DIR"] = ZARR_DIR
os.environ["VOLUMES_JSON"] = VOLUMES_JSON

# Ensure directories exist
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(ZARR_DIR, exist_ok=True)

# API
app.include_router(api_router, prefix="/api")

# Static Files for Zarr
app.mount("/data/zarr", StaticFiles(directory=ZARR_DIR), name="zarr_data")

# Frontend
if os.path.exists(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:
    print(f"Warning: Frontend dist not found at {FRONTEND_DIST}")

def start_server(host="127.0.0.1", port=8000):
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seismic Viewer Standalone")
    parser.add_argument("--server", action="store_true", help="Run in server mode (no window)")
    parser.add_argument("--host", default="127.0.0.1", help="Host for the server")
    parser.add_argument("--port", type=int, default=8000, help="Port for the server")
    args = parser.parse_args()

    if args.server:
        start_server(host=args.host, port=args.port)
    else:
        # Start FastAPI in a background thread
        t = threading.Thread(target=start_server, kwargs={"host": "127.0.0.1", "port": args.port})
        t.daemon = True
        t.start()

        # Create a pywebview window
        webview.create_window("Seismic Viewer", f"http://127.0.0.1:{args.port}")
        webview.start()
