from __future__ import annotations

from typing import Any, Dict, List, Optional

import re


from fastapi import APIRouter, HTTPException


from app.msi.routes import viewer_resolver
from app.msi.representation_resolver_service import resolve_msi_representation_volume
from app.services.managed_document_context_service import augment_managed_rows_with_documents

from app.services.volume_registry_service import (
    delete_volume as delete_volume_service,
    get_volume_info as get_volume_info_service,
    get_volume_metadata as get_volume_metadata_service,
    list_volumes as list_volumes_service,
    update_volume as update_volume_service,
)

router = APIRouter(tags=["volumes"])



def _canonical_info_key(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    raw = raw.split("?")[0]
    raw = raw.replace("\\", "/").rstrip("/").split("/")[-1]
    return re.sub(r"[^a-z0-9]+", "", raw.lower())


def _add_canonical_info_keys(keys: Dict[str, Dict[str, Any]], row: Dict[str, Any]) -> None:
    for field in [
        "id",
        "volume_id",
        "dataset_id",
        "physical_volume_id",
        "source_candidate_id",
        "source_segy_file_id",
        "display_name",
        "filename",
        "name",
        "relative_path",
        "source_relative_path",
        "zarr_url",
        "storage_uri",
    ]:
        value = row.get(field)
        if value:
            keys[str(value).strip()] = row
            normalized = _canonical_info_key(value)
            if normalized:
                keys[f"norm:{normalized}"] = row


def _managed_rows_with_documents() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    for source_rows in [
        viewer_resolver.loaded_volumes_compatible(),
        viewer_resolver.managed_volumes_compatible(),
    ]:
        for row in augment_managed_rows_with_documents(source_rows):
            key = str(row.get("id") or row.get("volume_id") or row.get("physical_volume_id") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            rows.append(row)
    return rows


def _find_catalog_volume(volume_id: str) -> Optional[Dict[str, Any]]:
    target = str(volume_id or "").strip()
    target_norm = _canonical_info_key(target)
    for row in list_volumes_service():
        if not isinstance(row, dict):
            continue
        candidate_values = [
            row.get("id"),
            row.get("volume_id"),
            row.get("physical_volume_id"),
            row.get("source_candidate_id"),
            row.get("display_name"),
            row.get("filename"),
            row.get("name"),
            row.get("zarr_url"),
            row.get("storage_uri"),
        ]
        for value in candidate_values:
            if not value:
                continue
            if str(value).strip() == target or _canonical_info_key(value) == target_norm:
                return row
    return None


def _find_managed_document_row_for_volume(volume_id: str) -> Optional[Dict[str, Any]]:
    managed_rows = _managed_rows_with_documents()
    by_key: Dict[str, Dict[str, Any]] = {}
    for row in managed_rows:
        if isinstance(row, dict):
            _add_canonical_info_keys(by_key, row)

    candidates: List[Any] = [volume_id]
    catalog_row = _find_catalog_volume(volume_id)
    if catalog_row:
        for field in [
            "id",
            "volume_id",
            "dataset_id",
            "physical_volume_id",
            "source_candidate_id",
            "source_segy_file_id",
            "display_name",
            "filename",
            "name",
            "relative_path",
            "source_relative_path",
            "zarr_url",
            "storage_uri",
        ]:
            candidates.append(catalog_row.get(field))
        metadata = catalog_row.get("metadata") if isinstance(catalog_row.get("metadata"), dict) else {}
        for field in [
            "source_candidate_id",
            "source_segy_file_id",
            "display_name",
            "filename",
            "original_filename",
            "original_relative_path",
            "zarr_url",
            "storage_uri",
        ]:
            candidates.append(metadata.get(field))

    for value in candidates:
        if not value:
            continue
        exact = by_key.get(str(value).strip())
        if exact:
            return exact
        normalized = _canonical_info_key(value)
        if normalized and by_key.get(f"norm:{normalized}"):
            return by_key[f"norm:{normalized}"]
    return None


def _attach_managed_document_context(info: Dict[str, Any], volume_id: str) -> Dict[str, Any]:
    managed = _find_managed_document_row_for_volume(volume_id)
    if not managed:
        return info

    supporting_documents = managed.get("supporting_documents") or (managed.get("document_context") or {}).get("supporting_documents") or []
    document_count = managed.get("document_count")
    if document_count is None:
        document_count = (managed.get("document_context") or {}).get("document_count")
    if document_count is None:
        document_count = len(supporting_documents)

    enriched = dict(info or {})
    enriched["managed_id"] = managed.get("id") or managed.get("volume_id") or enriched.get("managed_id")
    enriched["volume_id"] = enriched.get("volume_id") or managed.get("volume_id")
    enriched["physical_volume_id"] = enriched.get("physical_volume_id") or managed.get("physical_volume_id")
    enriched["source_candidate_id"] = enriched.get("source_candidate_id") or managed.get("source_candidate_id")
    enriched["source_segy_file_id"] = enriched.get("source_segy_file_id") or managed.get("source_segy_file_id")
    enriched["dataset_type"] = enriched.get("dataset_type") or managed.get("dataset_type")
    enriched["viewer_mode"] = enriched.get("viewer_mode") or managed.get("viewer_mode")
    enriched["document_count"] = document_count
    enriched["supporting_document_count"] = managed.get("supporting_document_count") or (managed.get("document_context") or {}).get("supporting_document_count") or document_count
    enriched["supporting_documents"] = supporting_documents
    enriched["document_context"] = managed.get("document_context") or enriched.get("document_context")

    metadata = dict(enriched.get("metadata") or {})
    metadata["document_count"] = enriched["document_count"]
    metadata["supporting_document_count"] = enriched["supporting_document_count"]
    metadata["supporting_documents"] = supporting_documents
    metadata["document_context"] = enriched.get("document_context")
    metadata["source_candidate_id"] = enriched.get("source_candidate_id") or metadata.get("source_candidate_id")
    metadata["managed_id"] = enriched.get("managed_id") or metadata.get("managed_id")
    enriched["metadata"] = metadata

    summary = dict(enriched.get("metadata_summary") or enriched.get("summary") or {})
    documents_summary = dict(summary.get("documents") or {})
    documents_summary["document_count"] = document_count
    documents_summary["supporting_documents"] = supporting_documents
    documents_summary["document_context"] = enriched.get("document_context")
    summary["documents"] = documents_summary
    enriched["metadata_summary"] = summary

    return enriched


def _physical_volume_id_from_msi_representation(volume_id: str) -> Optional[str]:
    if not str(volume_id or "").strip().startswith("msi_repr:"):
        return None
    try:
        resolved = resolve_msi_representation_volume(volume_id)
    except Exception:
        resolved = {}

    physical_volume_id = str(resolved.get("physical_volume_id") or "").strip()
    if physical_volume_id:
        return physical_volume_id

    # Defensive fallback for representation ids shaped as:
    # msi_repr:source_segy_<candidate>:zarr_<physical_volume_uuid>
    match = re.search(r":zarr_([0-9a-fA-F-]{16,})$", str(volume_id or "").strip())
    if match:
        return match.group(1)

    return None


def _reject_msi_representation_id(volume_id: str, action: str) -> None:
    if str(volume_id or "").strip().startswith("msi_repr:"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Refusing legacy volume {action} for MSI representation id. "
                "Use MSI lifecycle/metadata endpoints instead."
            ),
        )


@router.get("/volumes")
async def list_volumes():
    return list_volumes_service()


@router.get("/volumes/{volume_id}/metadata")
async def get_metadata(volume_id: str):
    return get_volume_metadata_service(volume_id)


@router.patch("/volumes/{volume_id}")
async def update_volume(volume_id: str, updates: Dict[str, Any]):
    _reject_msi_representation_id(volume_id, "update")
    return update_volume_service(volume_id, updates)


@router.delete("/volumes/{volume_id}")
async def delete_volume(volume_id: str):
    _reject_msi_representation_id(volume_id, "delete")
    return delete_volume_service(volume_id)


@router.get("/volumes/{volume_id}/info")
async def get_volume_info(volume_id: str):
    requested_volume_id = volume_id
    physical_volume_id = _physical_volume_id_from_msi_representation(volume_id)
    lookup_volume_id = physical_volume_id or volume_id

    info = get_volume_info_service(lookup_volume_id)
    if isinstance(info, dict):
        enriched = _attach_managed_document_context(info, requested_volume_id)
        if physical_volume_id:
            enriched["requested_volume_id"] = requested_volume_id
            enriched["physical_volume_id"] = physical_volume_id

            # Preserve the resolved physical volume metadata when a legacy
            # /api/volumes/{msi_repr}/info request is bridged to a physical
            # volume.  Older code created a nearly empty top-level metadata
            # object here, causing the Info page to prefer that empty object
            # over info.volume.metadata and lose 3D geometry fields.
            volume_payload = enriched.get("volume") if isinstance(enriched.get("volume"), dict) else {}
            volume_metadata = volume_payload.get("metadata") if isinstance(volume_payload.get("metadata"), dict) else {}
            metadata = dict(enriched.get("metadata") or volume_metadata or {})
            metadata["requested_volume_id"] = requested_volume_id
            metadata["physical_volume_id"] = physical_volume_id
            enriched["metadata"] = metadata
        return enriched
    return info
