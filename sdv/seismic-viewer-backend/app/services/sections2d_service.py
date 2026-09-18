from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

import numpy as np
import zarr
from fastapi import HTTPException

from app.services.processing_2d import process_2d_section
from app.services.zarr_slice_service import resolve_slice_zarr_path


def _read_effective_sample_interval_sec(arr_path: Path, zarr_path: str, fallback_sec: float) -> float:
    effective_sample_interval_sec = fallback_sec

    try:
        candidate_metadata_paths = [
            Path(str(arr_path) + ".viewer_metadata.json"),
        ]

        if arr_path.name.endswith(".zarr"):
            stripped = arr_path.with_name(arr_path.name[:-5])
            candidate_metadata_paths.append(Path(str(stripped) + ".viewer_metadata.json"))

        viewer_metadata = None
        for viewer_metadata_path in candidate_metadata_paths:
            if viewer_metadata_path.exists():
                with open(viewer_metadata_path, "r") as f:
                    viewer_metadata = json.load(f)
                break

        if viewer_metadata:
            sidecar_sample_interval_sec = viewer_metadata.get("sample_interval_sec")
            sidecar_sample_interval_ms = viewer_metadata.get("sample_interval_ms") or viewer_metadata.get("sample_rate")
            sidecar_sample_interval_us = viewer_metadata.get("sample_interval_us")

            if not (sidecar_sample_interval_sec or sidecar_sample_interval_ms or sidecar_sample_interval_us):
                binary_header_path = Path(str(zarr_path) + ".segy_binary_header.json")
                if binary_header_path.exists():
                    try:
                        binary_header = json.loads(binary_header_path.read_text(encoding="utf-8"))
                        sidecar_sample_interval_us = binary_header.get("sample_interval_us")
                    except Exception:
                        sidecar_sample_interval_us = None

            if sidecar_sample_interval_sec:
                effective_sample_interval_sec = float(sidecar_sample_interval_sec)
            elif sidecar_sample_interval_ms:
                effective_sample_interval_sec = float(sidecar_sample_interval_ms) / 1000.0
            elif sidecar_sample_interval_us:
                effective_sample_interval_sec = float(sidecar_sample_interval_us) / 1000000.0
    except Exception:
        effective_sample_interval_sec = fallback_sec

    return effective_sample_interval_sec




def _validate_window_bounds(
    *,
    trace_start: int,
    trace_end: int,
    sample_start: int,
    sample_end: int,
    trace_count: int,
    sample_count: int,
) -> tuple[int, int, int, int]:
    """Validate and clamp an explicit source-data window for 2D section rendering."""
    t0 = int(trace_start)
    t1 = int(trace_end)
    s0 = int(sample_start)
    s1 = int(sample_end)

    if t0 < 0 or s0 < 0:
        raise HTTPException(status_code=400, detail="Window start indices must be >= 0")
    if t1 > trace_count or s1 > sample_count:
        raise HTTPException(
            status_code=400,
            detail=(
                "Window end indices exceed source shape: "
                f"trace_end={t1}/{trace_count}, sample_end={s1}/{sample_count}"
            ),
        )
    if t1 <= t0 or s1 <= s0:
        raise HTTPException(status_code=400, detail="Window end indices must be greater than start indices")

    return t0, t1, s0, s1


def _resample_2d_bilinear(data: np.ndarray, output_width: int, output_height: int) -> np.ndarray:
    """
    Resample a [trace, sample] 2D section to [output_width, output_height].

    This is display resampling only. It does not alter stored seismic data.
    """
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim != 2:
        raise ValueError(f"Expected 2D array [trace, sample], got shape {arr.shape}")

    in_trace_count, in_sample_count = arr.shape
    out_trace_count = max(1, int(output_width))
    out_sample_count = max(1, int(output_height))

    if in_trace_count == out_trace_count and in_sample_count == out_sample_count:
        return np.asarray(arr, dtype=np.float32, order="C")

    trace_pos = np.linspace(0, in_trace_count - 1, out_trace_count, dtype=np.float32)
    sample_pos = np.linspace(0, in_sample_count - 1, out_sample_count, dtype=np.float32)

    t0 = np.floor(trace_pos).astype(np.int64)
    s0 = np.floor(sample_pos).astype(np.int64)
    t1 = np.minimum(t0 + 1, in_trace_count - 1)
    s1 = np.minimum(s0 + 1, in_sample_count - 1)

    wt = (trace_pos - t0).astype(np.float32)
    ws = (sample_pos - s0).astype(np.float32)

    # Interpolate along the trace axis first, then along the sample axis.
    trace_interp = (
        arr[t0, :] * (1.0 - wt)[:, None]
        + arr[t1, :] * wt[:, None]
    ).astype(np.float32)

    out = (
        trace_interp[:, s0] * (1.0 - ws)[None, :]
        + trace_interp[:, s1] * ws[None, :]
    ).astype(np.float32)

    return np.asarray(out, dtype=np.float32, order="C")


def get_2d_section_window(
    *,
    zarr_path: str,
    trace_start: int,
    trace_end: int,
    sample_start: int,
    sample_end: int,
    output_width: int,
    output_height: int,
    clip_percentile: float,
    processing_mode: str,
    sample_interval_sec: float,
    agc_window_sec: float,
    filter_type: str,
    f1: float | None,
    f2: float | None,
    f3: float | None,
    f4: float | None,
) -> Dict[str, Any]:
    """
    Return an explicitly windowed 2D seismic section from a Zarr array.

    The source window is selected in native trace/sample coordinates, processed,
    then display-resampled to the requested output size. This is the backend
    contract needed to avoid magnifying a fixed low-resolution full-line preview
    when the frontend zooms into a 2D section.
    """
    render_started_at = time.perf_counter()
    arr_path = resolve_slice_zarr_path(zarr_path)

    try:
        arr = zarr.open_array(str(arr_path), mode="r")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to open Zarr array: {exc}")

    source_shape = tuple(arr.shape)

    if len(source_shape) != 2:
        raise HTTPException(status_code=400, detail=f"Expected 2D Zarr array, got shape {source_shape}")

    trace_count, sample_count = (int(source_shape[0]), int(source_shape[1]))
    t0, t1, s0, s1 = _validate_window_bounds(
        trace_start=trace_start,
        trace_end=trace_end,
        sample_start=sample_start,
        sample_end=sample_end,
        trace_count=trace_count,
        sample_count=sample_count,
    )

    out_width = max(1, int(output_width))
    out_height = max(1, int(output_height))

    try:
        data = arr[t0:t1, s0:s1].astype("float32")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read 2D section window: {exc}")

    effective_sample_interval_sec = _read_effective_sample_interval_sec(
        arr_path=arr_path,
        zarr_path=zarr_path,
        fallback_sec=sample_interval_sec,
    )

    try:
        processed, processing_info = process_2d_section(
            data,
            sample_interval_sec=effective_sample_interval_sec,
            processing_mode=processing_mode,
            clip_percentile=clip_percentile,
            agc_window_sec=agc_window_sec,
            filter_type=filter_type,
            f1=f1,
            f2=f2,
            f3=f3,
            f4=f4,
        )
        rendered = _resample_2d_bilinear(processed, out_width, out_height)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to process 2D section window: {exc}")

    window_trace_count = t1 - t0
    window_sample_count = s1 - s0

    render_time_ms = (time.perf_counter() - render_started_at) * 1000.0

    return {
        "source_shape": [trace_count, sample_count],
        "shape": [int(rendered.shape[0]), int(rendered.shape[1])],
        "source_window": {
            "trace_start": t0,
            "trace_end": t1,
            "sample_start": s0,
            "sample_end": s1,
            "trace_count": window_trace_count,
            "sample_count": window_sample_count,
        },
        "trace_stride": float(window_trace_count) / float(max(1, rendered.shape[0])),
        "sample_stride": float(window_sample_count) / float(max(1, rendered.shape[1])),
        "clip_abs": processing_info.clip_abs,
        "clip_percentile": clip_percentile,
        "preview": True,
        "windowed": True,
        "render_time_ms": render_time_ms,
        "source_window_pixel_count": int(window_trace_count * window_sample_count),
        "output_pixel_count": int(rendered.shape[0] * rendered.shape[1]),
        "processing_mode": processing_info.processing_mode,
        "processing": processing_info.__dict__,
        "sample_interval_sec": effective_sample_interval_sec,
        "sample_interval_ms": effective_sample_interval_sec * 1000.0,
        "sample_interval_us": int(round(effective_sample_interval_sec * 1000000.0)),
        "data": rendered.ravel().tolist(),
    }

def get_2d_section_preview(
    *,
    zarr_path: str,
    max_width: int,
    max_height: int,
    clip_percentile: float,
    processing_mode: str,
    sample_interval_sec: float,
    agc_window_sec: float,
    filter_type: str,
    f1: float | None,
    f2: float | None,
    f3: float | None,
    f4: float | None,
) -> Dict[str, Any]:
    """
    Return a display-sized 2D seismic section preview from a Zarr array with shape [trace, sample].
    """
    render_started_at = time.perf_counter()
    arr_path = resolve_slice_zarr_path(zarr_path)

    try:
        arr = zarr.open_array(str(arr_path), mode="r")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to open Zarr array: {exc}")

    source_shape = tuple(arr.shape)

    if len(source_shape) != 2:
        raise HTTPException(status_code=400, detail=f"Expected 2D Zarr array, got shape {source_shape}")

    trace_count, sample_count = source_shape

    trace_stride = max(1, int(np.ceil(trace_count / max_width)))
    sample_stride = max(1, int(np.ceil(sample_count / max_height)))

    try:
        data = arr[::trace_stride, ::sample_stride].astype("float32")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read 2D section preview: {exc}")

    effective_sample_interval_sec = _read_effective_sample_interval_sec(
        arr_path=arr_path,
        zarr_path=zarr_path,
        fallback_sec=sample_interval_sec,
    )

    try:
        data, processing_info = process_2d_section(
            data,
            sample_interval_sec=effective_sample_interval_sec * sample_stride,
            processing_mode=processing_mode,
            clip_percentile=clip_percentile,
            agc_window_sec=agc_window_sec,
            filter_type=filter_type,
            f1=f1,
            f2=f2,
            f3=f3,
            f4=f4,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to process 2D section preview: {exc}")

    render_time_ms = (time.perf_counter() - render_started_at) * 1000.0

    return {
        "source_shape": list(source_shape),
        "shape": list(data.shape),
        "trace_stride": trace_stride,
        "sample_stride": sample_stride,
        "clip_abs": processing_info.clip_abs,
        "clip_percentile": clip_percentile,
        "preview": True,
        "windowed": False,
        "render_time_ms": render_time_ms,
        "source_window_pixel_count": int(trace_count * sample_count),
        "output_pixel_count": int(data.shape[0] * data.shape[1]),
        "processing_mode": processing_info.processing_mode,
        "processing": processing_info.__dict__,
        "sample_interval_sec": effective_sample_interval_sec,
        "sample_interval_ms": effective_sample_interval_sec * 1000.0,
        "sample_interval_us": int(round(effective_sample_interval_sec * 1000000.0)),
        "data": data.ravel().tolist(),
    }
