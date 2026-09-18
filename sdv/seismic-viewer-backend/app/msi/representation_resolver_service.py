from __future__ import annotations

from pathlib import Path
from typing import Any
import urllib.parse

from fastapi import HTTPException

from app.msi.repository import MSIRepository
from app.services.volume_registry_service import load_volumes
from app.storage.service import is_endrepo_zarr_url, resolve_endrepo_zarr_url_path


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _zarr_exists(zarr_url: str | None) -> bool:
    text = _clean(zarr_url)
    if not text:
        return False

    if text.startswith("/data/zarr/"):
        return (_backend_root() / text.lstrip("/")).exists()

    if is_endrepo_zarr_url(text):
        try:
            return resolve_endrepo_zarr_url_path(text).exists()
        except Exception:
            return False

    if text.startswith("local://zarr/"):
        return (_backend_root() / "data" / "zarr" / text.replace("local://zarr/", "", 1)).exists()

    if text.startswith("file://"):
        return Path(text.replace("file://", "", 1)).exists()

    if "://" in text:
        return True

    return Path(text).exists()


def _legacy_volume_by_id() -> dict[str, dict[str, Any]]:
    payload = load_volumes()

    if isinstance(payload, dict):
        rows = [row for row in payload.values() if isinstance(row, dict)]
    elif isinstance(payload, list):
        rows = [row for row in payload if isinstance(row, dict)]
    else:
        rows = []

    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        volume_id = _clean(row.get("id") or row.get("volume_id"))
        if volume_id:
            out[volume_id] = row
    return out


def resolve_msi_representation_volume(representation_id: str) -> dict[str, Any]:
    """
    Resolve an MSI representation id to the physical full-Zarr artifact identity
    and legacy-compatible metadata/info/report endpoint URLs.

    This is read-only. It does not mutate MSI, legacy volumes, source registry,
    load state, or artifacts.
    """
    representation_id = _clean(representation_id)

    if not representation_id:
        raise HTTPException(status_code=400, detail="Missing MSI representation id.")

    repo = MSIRepository()

    selected = None
    selected_dataset = None

    for dataset in repo.list_datasets():
        dataset_id = getattr(dataset, "dataset_id", None)
        if not dataset_id:
            continue

        try:
            representations = repo.list_representations(dataset_id)
        except Exception:
            representations = []

        for rep in representations:
            if getattr(rep, "representation_id", None) == representation_id:
                selected = rep
                selected_dataset = dataset
                break

        if selected is not None:
            break

    if selected is None:
        raise HTTPException(
            status_code=404,
            detail=f"MSI representation not found: {representation_id}",
        )

    artifact = getattr(selected, "artifact_summary", {}) or {}
    if not isinstance(artifact, dict):
        artifact = {}

    physical_volume_id = _clean(artifact.get("volume_id"))
    zarr_url = _clean(artifact.get("zarr_url"))
    dataset_id = getattr(selected, "dataset_id", None) or getattr(selected_dataset, "dataset_id", None)

    lifecycle_state = _clean(getattr(selected, "lifecycle_state", None))
    if not bool(getattr(selected, "viewer_ready", False)) or lifecycle_state != "viewer_ready":
        raise HTTPException(
            status_code=409,
            detail=f"MSI representation is not viewer-ready: {representation_id}",
        )

    legacy = _legacy_volume_by_id().get(physical_volume_id)

    if not physical_volume_id:
        raise HTTPException(
            status_code=409,
            detail=f"MSI representation has no physical volume id: {representation_id}",
        )

    if not zarr_url:
        raise HTTPException(
            status_code=409,
            detail=f"MSI representation has no zarr_url: {representation_id}",
        )

    if not _zarr_exists(zarr_url):
        raise HTTPException(
            status_code=409,
            detail=f"MSI representation points to a missing Zarr artifact: {representation_id}",
        )

    encoded_representation_id = urllib.parse.quote(representation_id, safe="")

    return {
        "ok": True,
        "representation_id": representation_id,
        "dataset_id": dataset_id,
        "physical_volume_id": physical_volume_id,
        "zarr_url": zarr_url,
        "zarr_exists": _zarr_exists(zarr_url),
        "dataset_type": getattr(selected_dataset, "dataset_type", None) if selected_dataset else None,
        "viewer_mode": getattr(selected, "viewer_mode", None),
        "representation_type": getattr(selected, "representation_type", None),
        "storage_uri": getattr(selected, "storage_uri", None),
        "lifecycle_state": getattr(selected, "lifecycle_state", None),
        "viewer_ready": bool(getattr(selected, "viewer_ready", False)),
        "is_preferred": bool(getattr(selected, "is_preferred", False)),
        "registration_state": getattr(selected_dataset, "registration_state", None) if selected_dataset else None,
        "legacy_volume_exists": bool(legacy),
        "legacy_volume_hidden": legacy.get("hidden") if legacy else None,
        "legacy_display_name": legacy.get("display_name") or legacy.get("filename") if legacy else None,
        "urls": {
            # MSI-native URLs are the public resolver contract for MSI rows.
            # volume_info remains legacy until an MSI-native info endpoint exists.
            "volume_info": f"/api/msi/representations/{encoded_representation_id}/info",
            "metadata_summary": f"/api/msi/representations/{encoded_representation_id}/metadata-summary",
            "normalized_metadata": f"/api/msi/representations/{encoded_representation_id}/metadata/normalized",
            "metadata_score_report": f"/api/msi/representations/{encoded_representation_id}/metadata-score-report",
            "documents": f"/api/msi/representations/{encoded_representation_id}/documents",
        },
        "legacy_bridge_urls": {
            "volume_info": f"/api/volumes/{physical_volume_id}/info",
            "metadata_summary": f"/api/volumes/{physical_volume_id}/metadata-summary",
            "normalized_metadata": f"/api/volumes/{physical_volume_id}/metadata/normalized",
            "metadata_score_report": f"/api/volumes/{physical_volume_id}/metadata-score-report",
            "documents": f"/api/volumes/{physical_volume_id}/documents",
        },
    }
