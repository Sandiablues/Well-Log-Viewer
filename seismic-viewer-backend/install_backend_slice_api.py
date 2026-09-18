#!/usr/bin/env python3
"""
Install backend raw-slice API into app/api/endpoints.py.

Run from:
  /Users/donarcher/Desktop/Seismic_Viewer/seismic_viewer_project/seismic-viewer-backend

Command:
  python install_backend_slice_api.py
"""

from pathlib import Path

ENDPOINTS_FILE = Path("app/api/endpoints.py")
MARKER = "# --- Backend raw slice API for seismic viewer ---"

SLICE_API_CODE = r'''

# --- Backend raw slice API for seismic viewer ---
# Returns one raw float32 2D slice from a Zarr volume.
#
# Frontend endpoint:
#   GET /api/slice?zarr_path=/data/zarr/f3_seismic.zarr&dim=0&index=325
#
# Axis convention:
#   Zarr shape = [inline, crossline, sample/time]
#   dim=0 -> inline slice    arr[index, :, :]  shape [crossline, sample]
#   dim=1 -> crossline slice arr[:, index, :]  shape [inline, sample]
#   dim=2 -> time slice      arr[:, :, index]  shape [inline, crossline]

from fastapi import Query, HTTPException
from fastapi.responses import Response
import numpy as np
import os
from pathlib import Path
import zarr as _slice_zarr


def _slice_backend_root() -> Path:
    # endpoints.py is normally app/api/endpoints.py, so parents[2] is backend root.
    return Path(__file__).resolve().parents[2]


def _slice_zarr_root() -> Path:
    return Path(os.environ.get("ZARR_DIR", _slice_backend_root() / "data" / "zarr")).resolve()


def _resolve_slice_zarr_path(zarr_path: str) -> Path:
    if not zarr_path:
        raise HTTPException(status_code=400, detail="Missing zarr_path")

    # Expected frontend input: /data/zarr/<volume>.zarr
    if zarr_path.startswith("/data/zarr/"):
        relative = zarr_path[len("/data/zarr/"):]
    else:
        # Also allow just f3_seismic.zarr for direct API testing.
        relative = zarr_path.lstrip("/")

    if ".." in Path(relative).parts:
        raise HTTPException(status_code=400, detail="Invalid zarr_path")

    if not relative.endswith(".zarr"):
        raise HTTPException(status_code=400, detail="zarr_path must point to a .zarr directory")

    root = _slice_zarr_root()
    candidate = (root / relative).resolve()

    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="zarr_path escapes Zarr root")

    if not candidate.exists():
        raise HTTPException(status_code=404, detail=f"Zarr volume not found: {relative}")

    return candidate


@router.get("/slice")
def get_raw_zarr_slice(
    zarr_path: str = Query(..., description="Zarr path, e.g. /data/zarr/f3_seismic.zarr"),
    dim: int = Query(..., ge=0, le=2, description="0=inline, 1=crossline, 2=time/depth"),
    index: int = Query(..., ge=0, description="Slice index along selected dimension"),
):
    arr_path = _resolve_slice_zarr_path(zarr_path)

    try:
        arr = _slice_zarr.open_array(str(arr_path), mode="r")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to open Zarr array: {exc}")

    shape = tuple(int(v) for v in arr.shape)

    if len(shape) != 3:
        raise HTTPException(status_code=400, detail=f"Expected 3D Zarr array, got shape {shape}")

    if index >= shape[dim]:
        raise HTTPException(
            status_code=400,
            detail=f"Index {index} out of bounds for dim {dim} with size {shape[dim]}",
        )

    try:
        if dim == 0:
            data = arr[index, :, :]
        elif dim == 1:
            data = arr[:, index, :]
        else:
            data = arr[:, :, index]

        # Force predictable row-major float32 output for the browser.
        data = np.asarray(data, dtype=np.float32, order="C")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read Zarr slice: {exc}")

    headers = {
        "X-Slice-Shape": ",".join(str(int(v)) for v in data.shape),
        "X-Slice-Dtype": "float32",
        "X-Slice-Axis": str(dim),
        "X-Slice-Index": str(index),
        "Access-Control-Expose-Headers": "X-Slice-Shape, X-Slice-Dtype, X-Slice-Axis, X-Slice-Index",
    }

    return Response(
        content=data.tobytes(order="C"),
        media_type="application/octet-stream",
        headers=headers,
    )
'''


def main() -> None:
    if not ENDPOINTS_FILE.exists():
        raise SystemExit(f"Cannot find {ENDPOINTS_FILE}. Run this from the backend root folder.")

    text = ENDPOINTS_FILE.read_text()

    if MARKER in text:
        print("Backend raw-slice API is already installed.")
        return

    if "router" not in text:
        raise SystemExit(
            "Could not find a router reference in app/api/endpoints.py. "
            "Open the file and confirm it uses FastAPI APIRouter."
        )

    ENDPOINTS_FILE.write_text(text.rstrip() + "\n" + SLICE_API_CODE + "\n")
    print(f"Installed backend raw-slice API into {ENDPOINTS_FILE}")
    print("Restart the backend, then test:")
    print('  curl -I "http://localhost:8000/api/slice?zarr_path=/data/zarr/f3_seismic.zarr&dim=0&index=325"')


if __name__ == "__main__":
    main()
