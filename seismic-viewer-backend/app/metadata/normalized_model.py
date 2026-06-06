from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.metadata.evidence import indexed_segy_evidence_status


def _range(a: Any, b: Any) -> Optional[List[Any]]:
    if a is None or b is None:
        return None
    return [a, b]


def _sample_index_range(index: Dict[str, Any]) -> Optional[List[int]]:
    sample_count = index.get("sample_count")
    if isinstance(sample_count, int) and sample_count > 0:
        return [0, sample_count - 1]
    return None


def _record_length_ms(index: Dict[str, Any]) -> Optional[float]:
    sample_count = index.get("sample_count")
    sample_interval_ms = index.get("sample_interval_ms")
    if isinstance(sample_count, int) and isinstance(sample_interval_ms, (int, float)):
        return (sample_count - 1) * float(sample_interval_ms)
    return None


def _time_range_ms(index: Dict[str, Any]) -> Optional[List[float]]:
    end = _record_length_ms(index)
    if end is None:
        return None
    return [0, end]


def _expected_trace_positions(index: Dict[str, Any]) -> Optional[int]:
    inline_count = index.get("inline_count")
    crossline_count = index.get("crossline_count")
    if isinstance(inline_count, int) and isinstance(crossline_count, int):
        return inline_count * crossline_count
    return None


def _missing_trace_positions(index: Dict[str, Any]) -> Optional[int]:
    expected = _expected_trace_positions(index)
    trace_count = index.get("trace_count")
    if isinstance(expected, int) and isinstance(trace_count, int):
        return expected - trace_count
    return None


def build_indexed_segy_normalized_metadata(index: Dict[str, Any]) -> Dict[str, Any]:
    """Build provisional normalized metadata for indexed SEG-Y datasets.

    This function is deliberately conservative. It only uses deterministic
    indexed SEG-Y evidence and generated sidecars. It must not invent CRS,
    contractor, block/license, datum, survey dates, business metadata, or
    document-backed provenance.
    """
    dataset_id = index.get("dataset_id")
    source_file_name = index.get("source_file_name")
    display_name = index.get("display_name") or index.get("short_name") or source_file_name or dataset_id

    evidence = indexed_segy_evidence_status(index)

    return {
        "schema_version": "0.2",
        "metadata_status": "provisional",
        "evidence_status": evidence["evidence_status"],
        "identity": {
            "dataset_id": dataset_id,
            "dataset_type": "3d_volume" if index.get("is_3d") else "unknown",
            "display_name": display_name,
            "source_file_name": source_file_name,
            "source_path": index.get("source_path"),
            "source_format": "SEG-Y",
            "read_mode": "indexed_segy",
        },
        "geometry": {
            "shape": index.get("shape"),
            "axis_order": index.get("axis_order", ["inline", "crossline", "sample"]),
            "trace_count": index.get("trace_count"),
            "inline_count": index.get("inline_count"),
            "crossline_count": index.get("crossline_count"),
            "sample_count": index.get("sample_count"),
            "inline_range": _range(index.get("inline_min"), index.get("inline_max")),
            "crossline_range": _range(index.get("crossline_min"), index.get("crossline_max")),
            "sample_index_range": _sample_index_range(index),
            "sample_interval_ms": index.get("sample_interval_ms"),
            "time_range_ms": _time_range_ms(index),
            "record_length_ms": _record_length_ms(index),
            "geometry_source": "indexed_segy_headers",
        },
        "headers": {
            "text_header_available": bool(index.get("text_header")),
            "text_header_encoding": index.get("text_header_encoding"),
            "text_header_confidence": index.get("text_header_confidence"),
            "binary_header_available": bool(index.get("binary_header")),
            "trace_header_summary_available": bool(index.get("trace_header_summary")),
            "binary_header": index.get("binary_header") or {},
            "trace_header_summary": index.get("trace_header_summary") or {},
        },
        "conversion": {
            "source_format": "SEG-Y",
            "target_format": "indexed_segy_preview",
            "read_mode": "indexed_segy",
            "optimized_cache_status": index.get("optimized_cache_status", "not_started"),
            "expected_trace_positions": _expected_trace_positions(index),
            "missing_trace_positions": _missing_trace_positions(index),
        },
        "evidence": evidence,
        "quality": {
            "metadata_maturity": "provisional",
            "technical_readiness": "indexed_preview_available",
            "validation_status": "headers_only",
            "missing_fields": [
                "optimized_zarr_cache",
                "document_validation",
                "business_metadata",
                "crs_validation",
            ],
            "derived_fields": [
                "shape",
                "inline_range",
                "crossline_range",
                "sample_interval_ms",
                "time_range_ms",
                "trace_count",
            ],
            "warnings": [
                "Indexed SEG-Y normalized metadata is provisional and header-derived.",
                "Optimized Zarr cache has not been completed.",
                "Supporting documents have not been scanned or validated.",
                "CRS, business metadata, and document-backed provenance are not verified.",
            ],
        },
    }
