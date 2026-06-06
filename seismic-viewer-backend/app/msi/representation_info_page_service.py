from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.msi.repository import MSIRepository
from app.msi.representation_info_service import get_representation_info
from app.msi.representation_metadata_service import (
    get_representation_metadata_summary,
    get_representation_normalized_metadata,
)
from app.msi.representation_resolver_service import resolve_msi_representation_volume


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _field_value(field: Any) -> Any:
    if isinstance(field, dict) and "value" in field:
        return field.get("value")
    return field


def _identity_value(identity: dict[str, Any], key: str) -> Any:
    return _field_value(identity.get(key))


def _supporting_documents_from_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
    documents = _as_dict(summary.get("documents"))
    supporting = documents.get("supporting_documents")
    if not isinstance(supporting, list):
        return []
    return [item for item in supporting if isinstance(item, dict)]


def build_representation_info_page(representation_id: str) -> dict[str, Any]:
    """
    MSI-owned Info Page contract for managed representations.

    This endpoint is the public metadata/info authority for MSI-managed rows.
    It may resolve the physical artifact internally, but frontend callers should
    not use /api/volumes routes to govern managed-data Info Page metadata.
    """
    resolved = resolve_msi_representation_volume(representation_id)
    physical_volume_id = str(resolved.get("physical_volume_id") or "").strip()
    dataset_id = str(resolved.get("dataset_id") or "").strip()

    if not physical_volume_id:
        raise HTTPException(
            status_code=409,
            detail=f"MSI representation has no physical volume id: {representation_id}",
        )

    info = get_representation_info(representation_id)
    summary = get_representation_metadata_summary(representation_id)
    normalized_payload = get_representation_normalized_metadata(representation_id)
    normalized = _as_dict(normalized_payload.get("normalized_metadata"))

    repo = MSIRepository()
    dataset = repo.get_dataset(dataset_id) if dataset_id else None
    representation = repo.get_representation(representation_id)

    metadata = _as_dict(info.get("metadata"))
    volume = _as_dict(info.get("volume"))
    volume_metadata = _as_dict(volume.get("metadata"))
    identity = _as_dict(normalized.get("identity"))
    source_reference = getattr(dataset, "source_reference", None) or {}

    documents_block = dict(_as_dict(summary.get("documents")))
    supporting_documents = _supporting_documents_from_summary(summary)
    documents_block["supporting_documents"] = supporting_documents
    documents_block["supporting_document_count"] = len(supporting_documents)

    display_name = _first_text(
        getattr(dataset, "display_name", None),
        getattr(representation, "display_name", None),
        summary.get("display_name"),
        volume.get("display_name"),
        volume.get("filename"),
        info.get("display_name"),
        physical_volume_id,
    )

    dataset_type = _first_text(
        getattr(dataset, "dataset_type", None),
        getattr(representation, "dataset_type", None),
        summary.get("dataset_type"),
        info.get("dataset_type"),
        metadata.get("dataset_type"),
    )

    identity_block = {
        "display_name": display_name,
        "source_name": _first_text(
            _identity_value(identity, "source_file_name"),
            source_reference.get("filename"),
            source_reference.get("relative_path"),
            summary.get("source", {}).get("filename") if isinstance(summary.get("source"), dict) else None,
        ),
        "survey_name": _first_text(
            getattr(dataset, "survey_name", None),
            getattr(representation, "survey_name", None),
            metadata.get("survey_name"),
            source_reference.get("survey_name"),
            _identity_value(identity, "survey_name"),
        ),
        "line_name": _first_text(
            getattr(dataset, "line_name", None),
            getattr(representation, "line_name", None),
            metadata.get("line_name"),
            source_reference.get("line_name"),
            _identity_value(identity, "line_name"),
        ),
        "volume_name": _first_text(
            getattr(dataset, "volume_name", None),
            getattr(representation, "volume_name", None),
            metadata.get("volume_name"),
            source_reference.get("volume_name"),
            _identity_value(identity, "volume_name"),
        ),
        "dataset_type": dataset_type,
        "representation_type": _first_text(
            getattr(representation, "representation_type", None),
            summary.get("representation_type"),
            volume.get("representation_type"),
        ),
    }

    warnings = list(_as_list(summary.get("warnings")))

    # Preserve the legacy-compatible top-level fields that the current Info Page
    # renderer expects, while making MSI the authoritative envelope.
    payload: dict[str, Any] = {
        **info,
        "schema_version": "msi.info_page.v1",
        "authority": "msi",
        "resolved_by": "msi_representation_info_page_service",
        "representation_id": representation_id,
        "msi_representation_id": representation_id,
        "dataset_id": dataset_id or None,
        "msi_dataset_id": dataset_id or None,
        "physical_volume_id": physical_volume_id,
        "volume_id": representation_id,
        "identity": identity_block,
        "geometry": _as_dict(summary.get("geometry")),
        "headers": _as_dict(summary.get("headers")),
        "source": _as_dict(summary.get("source")),
        "metadata_summary": summary,
        "normalized_metadata": normalized,
        "documents": documents_block,
        "supporting_documents": supporting_documents,
        "supporting_document_count": len(supporting_documents),
        "document_count": len(supporting_documents),
        "warnings": warnings,
        "metadata_score": _as_dict(summary.get("metadata_quality")),
        "artifact_reference": {
            "physical_volume_id": physical_volume_id,
            "storage_uri": resolved.get("storage_uri"),
            "zarr_url": resolved.get("zarr_url"),
        },
    }

    # Keep metadata useful to the existing sections while adding MSI identity.
    merged_metadata = dict(metadata or volume_metadata or {})
    merged_metadata.update({
        "msi_representation_id": representation_id,
        "msi_dataset_id": dataset_id or None,
        "physical_volume_id": physical_volume_id,
        "survey_name": identity_block.get("survey_name"),
        "line_name": identity_block.get("line_name"),
        "volume_name": identity_block.get("volume_name"),
        "supporting_documents": supporting_documents,
        "supporting_document_count": len(supporting_documents),
        "document_context": {
            "supporting_documents": supporting_documents,
            "document_count": len(supporting_documents),
            "source": "msi_info_page_contract",
        },
    })
    payload["metadata"] = merged_metadata

    return payload
