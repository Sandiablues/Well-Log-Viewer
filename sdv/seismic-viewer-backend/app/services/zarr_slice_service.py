from __future__ import annotations

import os
import threading
from collections import OrderedDict
from pathlib import Path
from app.storage.service import is_endrepo_zarr_url, resolve_endrepo_zarr_url_path
from typing import Any, Dict, Tuple

import numpy as np
import zarr
from fastapi import HTTPException
from fastapi.responses import Response


_SLICE_CACHE_LOCK = threading.Lock()
_SLICE_CACHE_MAX_BYTES = int(os.environ.get("SLICE_CACHE_MAX_BYTES", str(256 * 1024 * 1024)))
_slice_cache: OrderedDict[Tuple[str, int, int], Dict[str, Any]] = OrderedDict()
_slice_cache_bytes = 0


def _slice_cache_get(cache_key):
    global _slice_cache
    with _SLICE_CACHE_LOCK:
        item = _slice_cache.get(cache_key)
        if item is None:
            return None
        _slice_cache.move_to_end(cache_key)
        return item


def _slice_cache_put(cache_key, payload: bytes, shape):
    global _slice_cache_bytes

    size = len(payload)
    if size > _SLICE_CACHE_MAX_BYTES:
        return

    with _SLICE_CACHE_LOCK:
        old = _slice_cache.pop(cache_key, None)
        if old is not None:
            _slice_cache_bytes -= old["size"]

        _slice_cache[cache_key] = {
            "payload": payload,
            "shape": tuple(int(v) for v in shape),
            "size": size,
        }
        _slice_cache_bytes += size

        while _slice_cache_bytes > _SLICE_CACHE_MAX_BYTES and _slice_cache:
            _, evicted = _slice_cache.popitem(last=False)
            _slice_cache_bytes -= evicted["size"]


def _slice_cache_clear():
    global _slice_cache_bytes
    with _SLICE_CACHE_LOCK:
        count = len(_slice_cache)
        bytes_used = _slice_cache_bytes
        _slice_cache.clear()
        _slice_cache_bytes = 0
    return {"cleared": True, "entries_removed": count, "bytes_removed": bytes_used}


def _slice_cache_info():
    with _SLICE_CACHE_LOCK:
        return {
            "entries": len(_slice_cache),
            "bytes": _slice_cache_bytes,
            "max_bytes": _SLICE_CACHE_MAX_BYTES,
        }


def _slice_response_headers(shape, dim: int, index: int, cache_status: str):
    return {
        "X-Slice-Shape": ",".join(str(int(v)) for v in shape),
        "X-Slice-Dim": str(int(dim)),
        "X-Slice-Index": str(int(index)),
        "X-Slice-Dtype": "float32",
        "X-Slice-Cache": cache_status,
    }


def _slice_backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _slice_zarr_root() -> Path:
    return Path(os.environ.get("ZARR_DIR", _slice_backend_root() / "data" / "zarr")).resolve()


def resolve_slice_zarr_path(zarr_path: str) -> Path:
    if not zarr_path:
        raise HTTPException(status_code=400, detail="Missing zarr_path")

    if is_endrepo_zarr_url(zarr_path):
        try:
            candidate = resolve_endrepo_zarr_url_path(zarr_path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid EndRepo zarr_path: {exc}")

        if not candidate.exists():
            raise HTTPException(status_code=404, detail=f"Zarr volume not found: {zarr_path}")

        return candidate

    if zarr_path.startswith("/data/zarr/"):
        relative = zarr_path[len("/data/zarr/"):]
    else:
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


def get_raw_zarr_slice(zarr_path: str, dim: int, index: int) -> Response:
    arr_path = resolve_slice_zarr_path(zarr_path)

    cache_key = (str(arr_path), int(dim), int(index))
    cached = _slice_cache_get(cache_key)
    if cached is not None:
        return Response(
            content=cached["payload"],
            media_type="application/octet-stream",
            headers=_slice_response_headers(cached["shape"], dim, index, "hit"),
        )

    try:
        arr = zarr.open_array(str(arr_path), mode="r")
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

        data = np.asarray(data, dtype=np.float32, order="C")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read Zarr slice: {exc}")

    payload = data.tobytes(order="C")
    _slice_cache_put(cache_key, payload, data.shape)

    return Response(
        content=payload,
        media_type="application/octet-stream",
        headers=_slice_response_headers(data.shape, dim, index, "miss"),
    )


def get_slice_cache_info():
    return _slice_cache_info()


def clear_slice_cache():
    return _slice_cache_clear()
