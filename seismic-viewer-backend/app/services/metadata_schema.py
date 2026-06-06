from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


NORMALIZED_METADATA_SCHEMA_VERSION = "normalized_metadata.v1"


SOURCE_BINARY_HEADER = "binary_header"
SOURCE_TEXTUAL_HEADER = "textual_header"
SOURCE_TRACE_HEADER_SUMMARY = "trace_header_summary"
SOURCE_VIEWER_METADATA = "viewer_metadata"
SOURCE_CONVERSION_METADATA = "conversion_metadata"
SOURCE_SUPPORTING_DOCUMENT = "supporting_document"
SOURCE_RULE_ENRICHED = "rule_enriched"
SOURCE_AI_ENRICHED = "ai_enriched"
SOURCE_USER_ENTERED = "user_entered"
SOURCE_USER_APPROVED = "user_approved"
SOURCE_UNKNOWN = "unknown"


STATUS_EXTRACTED = "extracted"
STATUS_SUGGESTED = "suggested"
STATUS_AUTO_APPLIED = "auto_applied"
STATUS_USER_APPROVED = "user_approved"
STATUS_REJECTED = "rejected"
STATUS_OVERRIDDEN = "overridden"
STATUS_MISSING = "missing"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalized_field(
    value: Any,
    source: str,
    confidence: float,
    status: str,
    basis: list[str],
) -> dict:
    return {
        "value": value,
        "source": source,
        "confidence": confidence,
        "status": status,
        "basis": basis,
    }


def missing_field(reason: str = "not available") -> dict:
    return {
        "value": None,
        "source": SOURCE_UNKNOWN,
        "confidence": 0.0,
        "status": STATUS_MISSING,
        "basis": [reason],
    }


def empty_normalized_metadata(
    volume_id: str,
    volume_path: str,
    evidence_paths: dict,
) -> dict:
    return {
        "schema_version": NORMALIZED_METADATA_SCHEMA_VERSION,
        "volume_id": volume_id,
        "generated_at": now_iso(),
        "volume_path": volume_path,
        "identity": {},
        "geometry": {},
        "coordinate_crs": {},
        "processing": {},
        "conversion": {},
        "viewer_defaults": {},
        "quality": {},
        "evidence_paths": evidence_paths,
    }
