from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.services.segy_index_service import SegyIndexService, SEGY_INDEX_DIR
from app.services.segy_index_slice_service import IndexedSegySliceService


router = APIRouter(prefix="/api/segy-index", tags=["segy-index"])


@router.get("/{dataset_id}")
def get_index_summary(dataset_id: str) -> Dict[str, Any]:
    try:
        index = SegyIndexService.load_index(dataset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    index_dir = SEGY_INDEX_DIR / dataset_id

    text_header = None
    text_header_path = index_dir / "segy_text_header.txt"
    if text_header_path.exists():
        text_header = text_header_path.read_text(encoding="utf-8", errors="replace")

    binary_header = {}
    binary_header_path = index_dir / "segy_binary_header.json"
    if binary_header_path.exists():
        try:
            binary_header = json.loads(binary_header_path.read_text(encoding="utf-8"))
        except Exception:
            binary_header = {}

    sample_count = index.get("sample_count")
    sample_interval_ms = index.get("sample_interval_ms")

    record_length_ms = None
    if isinstance(sample_count, int) and isinstance(sample_interval_ms, (int, float)):
        record_length_ms = sample_count * sample_interval_ms

    inline_count = index.get("inline_count")
    crossline_count = index.get("crossline_count")

    expected_trace_positions = None
    missing_trace_positions = None
    if isinstance(inline_count, int) and isinstance(crossline_count, int):
        expected_trace_positions = inline_count * crossline_count
        trace_count = index.get("trace_count")
        if isinstance(trace_count, int):
            missing_trace_positions = expected_trace_positions - trace_count

    trace_header_summary = {
        "trace_count": index.get("trace_count"),
        "inline_count": inline_count,
        "crossline_count": crossline_count,
        "sample_count": sample_count,
        "inline_min": index.get("inline_min"),
        "inline_max": index.get("inline_max"),
        "crossline_min": index.get("crossline_min"),
        "crossline_max": index.get("crossline_max"),
        "sample_min": 0,
        "sample_max": sample_count,
        "sample_interval_ms": sample_interval_ms,
        "record_length_ms": record_length_ms,
        "valid_trace_header_count": index.get("valid_trace_header_count"),
        "invalid_trace_header_count": index.get("invalid_trace_header_count"),
    }

    conversion_info = {
        "read_mode": "indexed_segy",
        "source_format": "SEG-Y",
        "target_format": "indexed_segy_preview",
        "optimized_cache_status": index.get("optimized_cache_status", "not_started"),
        "geometry_source": "indexed_segy_headers",
        "input_trace_count": index.get("trace_count"),
        "written_traces": None,
        "skipped_traces": None,
        "expected_trace_positions": expected_trace_positions,
        "missing_trace_positions": missing_trace_positions,
        "missing_trace_fill": None,
        "batch_size": None,
        "batch_writes": None,
    }

    metadata = {
        "is_3d": True,
        "shape": index.get("shape"),
        "sample_rate": sample_interval_ms,
        "sample_interval_ms": sample_interval_ms,
        "trace_count": index.get("trace_count"),
        "inline_count": inline_count,
        "crossline_count": crossline_count,
        "sample_count": sample_count,
        "inline_min": index.get("inline_min"),
        "inline_max": index.get("inline_max"),
        "crossline_min": index.get("crossline_min"),
        "crossline_max": index.get("crossline_max"),
        "sample_min": 0,
        "sample_max": sample_count,
        "record_length_ms": record_length_ms,
        "geometry_source": "indexed_segy_headers",
        "data_type": "float32",
        "read_mode": "indexed_segy",
        "optimized_cache_status": index.get("optimized_cache_status", "not_started"),
        "axis_order": index.get("axis_order", ["inline", "crossline", "sample"]),
        "conversion_info": conversion_info,
        "zarr": {
            "shape": index.get("shape"),
            "chunks": None,
            "dtype": "float32",
            "axis_order": index.get("axis_order", ["inline", "crossline", "sample"]),
            "is_3d": True,
            "geometry_source": "indexed_segy_headers",
            "read_mode": "indexed_segy",
            "optimized_cache_status": index.get("optimized_cache_status", "not_started"),
        },
    }

    return {
        **index,
        "geometry_source": "indexed_segy_headers",
        "data_type": "float32",
        "text_header": text_header,
        "binary_header": binary_header,
        "trace_header_summary": trace_header_summary,
        "conversion_info": conversion_info,
        "metadata": metadata,
    }

@router.get("/{dataset_id}/slice")
def get_indexed_slice(
    dataset_id: str,
    dim: int = Query(..., ge=0, le=2),
    index: int = Query(..., ge=0),
    format: str = Query("json", pattern="^(json|binary)$"),
):
    try:
        result = IndexedSegySliceService.read_slice(dataset_id, dim, index)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except IndexError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    data = result.pop("data")

    if format == "binary":
        payload = data.astype(np.float32, copy=False).tobytes(order="C")
        headers = {
            "X-Shape": json.dumps(result["shape"]),
            "X-Dtype": "float32",
            "X-Read-Mode": "indexed_segy",
            "X-Dim": str(result["dim"]),
            "X-Index": str(result["index"]),
            "X-Axis-Value": str(result["axis_value"]),
        }
        return Response(
            content=payload,
            media_type="application/octet-stream",
            headers=headers,
        )

    result["data"] = data.tolist()
    return result
