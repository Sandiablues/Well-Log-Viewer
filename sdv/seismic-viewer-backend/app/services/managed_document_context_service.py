from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from app.services.source_intake_document_assignment_service import (
    get_candidate_effective_supporting_documents,
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _norm_mode(value: Any) -> str:
    raw = _clean(value).lower()
    if raw in {"2d", "2d_line", "zarr_2d"}:
        return "2d"
    if raw in {"3d", "3d_volume", "zarr_full_conversion", "zarr_3d"}:
        return "3d"
    return ""


def _candidate_id_from_managed_row(row: Dict[str, Any]) -> str:
    for key in ("source_candidate_id", "candidate_id", "source_segy_file_id", "segy_file_id"):
        value = _clean(row.get(key))
        if value:
            return value

    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    for key in ("source_candidate_id", "candidate_id", "source_segy_file_id", "segy_file_id"):
        value = _clean(metadata.get(key))
        if value:
            return value

    msi_dataset_id = _clean(row.get("msi_dataset_id") or metadata.get("msi_dataset_id"))
    if msi_dataset_id.startswith("source_segy:"):
        return msi_dataset_id.split(":", 1)[1].strip()

    # Fallback for MSI representation ids such as:
    # msi_repr:source_segy_segy_510...:zarr_uuid
    for value in (_clean(row.get("id")), _clean(row.get("volume_id")), _clean(row.get("msi_representation_id"))):
        match = re.search(r"source_segy_(segy_[A-Za-z0-9]+)", value)
        if match:
            return match.group(1)

    return ""


def _mode_from_managed_row(row: Dict[str, Any]) -> str:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    for value in (
        row.get("viewer_mode"),
        row.get("dataset_type"),
        row.get("representation_type"),
        metadata.get("viewer_mode"),
        metadata.get("dataset_type"),
        metadata.get("representation_type"),
    ):
        mode = _norm_mode(value)
        if mode:
            return mode
    return ""


def augment_managed_row_with_documents(row: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return row

    out = dict(row)
    metadata = dict(out.get("metadata") or {}) if isinstance(out.get("metadata"), dict) else {}

    candidate_id = _candidate_id_from_managed_row(out)
    mode = _mode_from_managed_row(out)

    if candidate_id:
        docs = get_candidate_effective_supporting_documents(candidate_id, mode=mode)
    else:
        docs = {
            "schema_version": "source_intake.effective_supporting_documents.v1",
            "candidate_id": "",
            "mode": mode,
            "document_count": 0,
            "supporting_document_count": 0,
            "supporting_documents": [],
            "document_assignment_status": "candidate_not_found",
        }

    supporting_documents = docs.get("supporting_documents") or []
    document_count = int(docs.get("document_count") or len(supporting_documents) or 0)

    out["source_candidate_id"] = candidate_id or out.get("source_candidate_id")
    out["document_count"] = document_count
    out["supporting_document_count"] = document_count
    out["supporting_documents"] = supporting_documents
    out["document_assignment_status"] = docs.get("document_assignment_status")
    out["document_context"] = docs

    metadata["source_candidate_id"] = candidate_id or metadata.get("source_candidate_id")
    metadata["document_count"] = document_count
    metadata["supporting_document_count"] = document_count
    metadata["supporting_documents"] = supporting_documents
    metadata["document_assignment_status"] = docs.get("document_assignment_status")
    metadata["document_context"] = docs
    out["metadata"] = metadata

    return out


def augment_managed_rows_with_documents(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [augment_managed_row_with_documents(row) for row in rows]
