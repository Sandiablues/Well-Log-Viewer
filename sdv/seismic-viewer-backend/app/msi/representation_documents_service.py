from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.api.documents import build_volume_documents_payload
from app.msi.representation_metadata_service import get_representation_metadata_summary
from app.msi.representation_resolver_service import resolve_msi_representation_volume


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _document_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("document_id") or "").strip(),
        str(item.get("filename") or item.get("original_filename") or "").strip(),
        str(item.get("download_url") or item.get("open_url") or "").strip(),
    )


def _supporting_documents_from_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
    documents_block = _as_dict(summary.get("documents"))
    supporting = documents_block.get("supporting_documents")
    return [dict(item) for item in _as_list(supporting) if isinstance(item, dict)]


def _legacy_documents(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in _as_list(payload.get("documents")) if isinstance(item, dict)]


def _merge_documents(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for group in groups:
        for item in group:
            key = _document_key(item)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)

    return merged


def list_representation_documents(representation_id: str) -> dict[str, Any]:
    """
    MSI-native documents endpoint.

    This endpoint is the public document contract for MSI representations.
    It resolves the MSI representation once, then uses the same backend-owned
    document context as the MSI metadata summary so Info Page document truth
    cannot diverge between /documents and /metadata-summary.

    Legacy volume-document lookup remains an internal compatibility source,
    but it is no longer the authority for MSI document truth.
    """
    resolved = resolve_msi_representation_volume(representation_id)
    physical_volume_id = str(resolved.get("physical_volume_id") or "").strip()

    if not physical_volume_id:
        raise HTTPException(
            status_code=409,
            detail=f"MSI representation has no physical volume id: {representation_id}",
        )

    legacy_payload = build_volume_documents_payload(physical_volume_id)
    summary = get_representation_metadata_summary(representation_id)

    summary_documents = _supporting_documents_from_summary(summary)
    legacy_documents = _legacy_documents(legacy_payload)
    documents = _merge_documents(summary_documents, legacy_documents)

    documents_block = dict(_as_dict(summary.get("documents")))
    documents_block["supporting_documents"] = documents
    documents_block["supporting_document_count"] = len(documents)

    payload = {
        **legacy_payload,
        "documents": documents,
        "supporting_documents": documents,
        "document_count": len(documents),
        "supporting_document_count": len(documents),
        "documents_block": documents_block,
        "msi_representation_id": representation_id,
        "msi_dataset_id": resolved.get("dataset_id"),
        "physical_volume_id": physical_volume_id,
        "resolved_by": "msi_representation_documents_service",
        "document_authority": "msi_metadata_summary_document_context",
        "legacy_volume_document_count": len(legacy_documents),
        "summary_document_count": len(summary_documents),
    }

    if documents:
        payload.pop("warning", None)
    elif legacy_payload.get("warning"):
        payload["warning"] = legacy_payload.get("warning")

    return payload
