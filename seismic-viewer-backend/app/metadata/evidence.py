from __future__ import annotations

from typing import Any, Dict, List


def indexed_segy_evidence_status(index: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize current evidence state for an indexed SEG-Y dataset.

    This is intentionally deterministic. It does not infer document-backed
    business metadata, CRS, datum, contractor, block/license, or acquisition
    provenance.
    """
    return {
        "evidence_status": "headers_only",
        "sources": {
            "segy_index": bool(index),
            "text_header": bool(index.get("text_header")),
            "text_header_decode": bool(index.get("text_header_decode")),
            "binary_header": bool(index.get("binary_header")),
            "trace_header_summary": bool(index.get("trace_header_summary")),
            "supporting_documents": False,
            "optimized_zarr_cache": index.get("optimized_cache_status") == "available",
        },
        "limitations": [
            "Metadata is derived from indexed SEG-Y headers and generated sidecars.",
            "Supporting documents have not been scanned or validated.",
            "CRS, datum, business metadata, contractor, block/license, and survey provenance are not verified.",
        ],
    }
