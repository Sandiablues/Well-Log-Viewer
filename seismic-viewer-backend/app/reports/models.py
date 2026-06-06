from __future__ import annotations

from typing import Any, Dict


REPORT_LABEL_METADATA_SCORE = "Metadata Score Rating"

# Indexed SEG-Y scoring semantics:
# - technical readiness reflects whether fast index/header evidence is usable for preview
# - metadata maturity remains lower/provisional until optimized cache, CRS, business metadata,
#   and supporting-document validation exist
INDEXED_METADATA_COMPLETENESS_PERCENT = 90
INDEXED_PREVIEW_READINESS_STATUS = "indexed_preview_available"


def indexed_metadata_score(index_exists: bool) -> Dict[str, Any]:
    return {
        "overall_percent": INDEXED_METADATA_COMPLETENESS_PERCENT if index_exists else 0,
        "status": "indexed_provisional" if index_exists else "missing_index",
        "label": REPORT_LABEL_METADATA_SCORE,
    }


def indexed_technical_readiness(index_exists: bool) -> Dict[str, Any]:
    # Kept as a compatibility payload key for the existing renderer.
    # Rendered as Preview Status, not as a competing score.
    return {
        "percent": None,
        "status": INDEXED_PREVIEW_READINESS_STATUS if index_exists else "missing_index",
    }


def indexed_validation_state() -> Dict[str, Any]:
    return {
        "status": "headers_only",
        "document_validation": "not_started",
        "crs_validation": "not_started",
    }
