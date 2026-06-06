from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import HTMLResponse

from .lifecycle_service import MSILifecycleService
from .viewer_resolver import MSIViewerResolver
from .ownership_audit_service import build_msi_ownership_audit
from .registration_reconcile_service import reconcile_converted_source_segy_to_msi
from .representation_resolver_service import resolve_msi_representation_volume
from .representation_documents_service import list_representation_documents
from .representation_metadata_service import get_representation_metadata_summary, get_representation_normalized_metadata, render_representation_metadata_score_report
from .representation_info_service import get_representation_info
from .representation_info_page_service import build_representation_info_page
from .dataset_admin_service import DatasetDisplayNameUpdateRequest, DatasetMetadataUpdateRequest, AdminDatasetFieldsUpdateRequest, update_dataset_display_name, update_representation_display_name, update_dataset_descriptive_metadata, update_representation_dataset_metadata, admin_update_dataset_fields, admin_update_representation_dataset_fields, require_admin_action_signal
from .schemas import ResolveTargetRequest
from .existing_registry_adapter import ExistingRegistryAdapter
from app.services.package_registry_service import reset_segy_file_conversion_state
from app.storage.service import is_endrepo_zarr_url, resolve_endrepo_zarr_url_path, storage_service


router = APIRouter(prefix="/api/msi", tags=["MSI"])

lifecycle_service = MSILifecycleService()
viewer_resolver = MSIViewerResolver(lifecycle_service.repo)


def _source_segy_file_id_from_representation_id(representation_id: str) -> str:
    """Best-effort parser for msi_repr:source_segy_<segy_id>:zarr_<volume_id>."""
    text = str(representation_id or "").strip()
    marker = "msi_repr:source_segy_"
    if not text.startswith(marker):
        return ""
    tail = text[len(marker):]
    if ":zarr_" not in tail:
        return ""
    return tail.split(":zarr_", 1)[0].strip()


def _delete_managed_artifact_from_storage(artifact_summary: dict) -> dict:
    """Delete a managed Zarr artifact when it resolves to an app-owned managed path."""
    artifact_summary = artifact_summary or {}
    zarr_url = str(artifact_summary.get("zarr_url") or "").strip()
    storage_uri = str(artifact_summary.get("storage_uri") or "").strip()

    target: Path | None = None
    resolved_from = None

    try:
        if zarr_url and is_endrepo_zarr_url(zarr_url):
            target = resolve_endrepo_zarr_url_path(zarr_url)
            resolved_from = "zarr_url"
        elif storage_uri.startswith("endrepo://"):
            target = Path(storage_service().resolve_uri(storage_uri).local_path)
            resolved_from = "storage_uri"
        elif zarr_url.startswith("/data/zarr/"):
            backend_root = Path(__file__).resolve().parents[2]
            target = (backend_root / zarr_url.lstrip("/")).resolve()
            try:
                target.relative_to((backend_root / "data" / "zarr").resolve())
            except ValueError:
                return {"deleted": False, "reason": "local_zarr_path_outside_backend_data", "zarr_url": zarr_url}
            resolved_from = "local_zarr_url"
    except Exception as exc:
        return {"deleted": False, "reason": "artifact_resolve_failed", "error": str(exc), "zarr_url": zarr_url, "storage_uri": storage_uri}

    if target is None:
        return {"deleted": False, "reason": "no_managed_artifact_path", "zarr_url": zarr_url, "storage_uri": storage_uri}

    if not target.exists():
        return {"deleted": False, "reason": "artifact_already_missing", "path": str(target), "resolved_from": resolved_from}

    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    except Exception as exc:
        return {"deleted": False, "reason": "artifact_delete_failed", "path": str(target), "error": str(exc), "resolved_from": resolved_from}

    return {"deleted": True, "path": str(target), "resolved_from": resolved_from}


@router.get("/health")
def msi_health():
    return {
        "ok": True,
        "service": "msi",
        "scope": "lifecycle_core",
    }


@router.get("/datasets")
def list_datasets():
    return lifecycle_service.list_datasets()


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str):
    dataset = lifecycle_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset_id}")
    return dataset


@router.get("/datasets/{dataset_id}/representations")
def list_representations(dataset_id: str):
    dataset = lifecycle_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset_id}")
    return lifecycle_service.list_representations(dataset_id)


@router.get("/datasets/{dataset_id}/lifecycle")
def get_lifecycle(dataset_id: str):
    lifecycle = lifecycle_service.lifecycle(dataset_id)
    if not lifecycle:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset_id}")
    return lifecycle


@router.post("/datasets/{dataset_id}/display-name")
def update_dataset_display_name_route(dataset_id: str, request: DatasetDisplayNameUpdateRequest):
    return update_dataset_display_name(dataset_id, request)


@router.post("/datasets/{dataset_id}/metadata")
def update_dataset_metadata_route(
    dataset_id: str,
    request: DatasetMetadataUpdateRequest,
    x_msi_admin_action: str | None = Header(default=None, alias="X-MSI-Admin-Action"),
):
    require_admin_action_signal(x_msi_admin_action)
    return update_dataset_descriptive_metadata(dataset_id, request)


@router.post("/admin/datasets/{dataset_id}/fields")
def admin_update_dataset_fields_route(dataset_id: str, request: AdminDatasetFieldsUpdateRequest):
    return admin_update_dataset_fields(dataset_id, request)


@router.post("/viewer/resolve-target")
def resolve_viewer_target(request: ResolveTargetRequest):
    return viewer_resolver.resolve(request)


@router.get("/viewer/loaded-targets")
def loaded_targets():
    return viewer_resolver.loaded_targets()


@router.get("/viewer/loaded-volumes-compatible")
def loaded_volumes_compatible():
    return viewer_resolver.loaded_volumes_compatible()


@router.get("/viewer/managed-volumes-compatible")
def managed_volumes_compatible():
    return viewer_resolver.managed_volumes_compatible()


@router.get("/viewer/compatibility-identity-audit")
def compatibility_identity_audit():
    return viewer_resolver.compatibility_identity_audit()





@router.post("/representations/{representation_id}/load")
def load_representation(representation_id: str):
    try:
        return lifecycle_service.load_representation(representation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/representations/{representation_id}/unload")
def unload_representation(representation_id: str):
    try:
        return lifecycle_service.unload_representation(representation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))



@router.delete("/representations/{representation_id:path}")
def delete_representation_from_managed_data(representation_id: str):
    """
    Fully delete an MSI-managed representation from the managed lifecycle.

    Current product rule: Delete from Managed Data removes the MSI managed
    record, clears source-side conversion linkage so the row can be converted
    again, and deletes the app-owned managed Zarr artifact where resolvable.
    It does not delete the original source SEG-Y file.
    """
    try:
        deletion = lifecycle_service.repo.delete_managed_representation_full(representation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if deletion is None:
        raise HTTPException(status_code=404, detail=f"Representation not found: {representation_id}")

    source_reference = deletion.get("source_reference") or {}
    artifact_summary = deletion.get("artifact_summary") or {}
    source_segy_file_id = str(
        source_reference.get("source_segy_file_id")
        or artifact_summary.get("source_segy_file_id")
        or _source_segy_file_id_from_representation_id(representation_id)
        or ""
    ).strip()

    source_reset = {"attempted": False, "reason": "missing_source_segy_file_id"}
    if source_segy_file_id:
        try:
            updated = reset_segy_file_conversion_state(
                source_segy_file_id,
                reason="Managed Data full delete reset source conversion state.",
            )
            source_reset = {
                "attempted": True,
                "reset": True,
                "source_segy_file_id": source_segy_file_id,
                "conversion_status": updated.get("conversion_status"),
            }
        except Exception as exc:
            source_reset = {
                "attempted": True,
                "reset": False,
                "source_segy_file_id": source_segy_file_id,
                "error": str(exc),
            }

    artifact_delete = _delete_managed_artifact_from_storage(artifact_summary)

    return {
        "status": "deleted",
        "delete_mode": "full_managed_lifecycle",
        "representation_id": representation_id,
        "dataset_id": deletion.get("dataset_id"),
        "dataset_deleted": deletion.get("dataset_deleted"),
        "source_reset": source_reset,
        "artifact_delete": artifact_delete,
        "original_source_segy_preserved": True,
        "hard_delete_authoritative": True,
        "reconciliation_resurrection_blocked_by_source_reset": bool(source_reset.get("reset")),
    }


@router.post("/representations/{representation_id:path}/display-name")
def update_representation_display_name_route(representation_id: str, request: DatasetDisplayNameUpdateRequest):
    return update_representation_display_name(representation_id, request)


@router.post("/representations/{representation_id:path}/metadata")
def update_representation_dataset_metadata_route(
    representation_id: str,
    request: DatasetMetadataUpdateRequest,
    x_msi_admin_action: str | None = Header(default=None, alias="X-MSI-Admin-Action"),
):
    require_admin_action_signal(x_msi_admin_action)
    return update_representation_dataset_metadata(representation_id, request)


@router.post("/admin/representations/{representation_id:path}/fields")
def admin_update_representation_dataset_fields_route(
    representation_id: str,
    request: AdminDatasetFieldsUpdateRequest,
):
    return admin_update_representation_dataset_fields(representation_id, request)


@router.get("/adapters/source-registry/preview")
def preview_existing_source_registry(sample_limit: int = 12):
    adapter = ExistingRegistryAdapter()
    safe_limit = max(1, min(sample_limit, 100))
    return adapter.preview(sample_limit=safe_limit)


@router.get("/adapters/source-registry/artifact-presence-preview")
def preview_existing_artifact_presence(sample_limit: int = 20):
    adapter = ExistingRegistryAdapter()
    safe_limit = max(1, min(sample_limit, 200))
    return adapter.artifact_presence_preview(sample_limit=safe_limit)


@router.get("/adapters/source-registry/artifact-metadata-correlation-inspection")
def inspect_artifact_metadata_correlation(sample_limit: int = 50):
    adapter = ExistingRegistryAdapter()
    safe_limit = max(1, min(sample_limit, 200))
    return adapter.artifact_metadata_correlation_inspection(sample_limit=safe_limit)


@router.get("/adapters/source-registry/representation-candidate-preview")
def preview_representation_candidates(sample_limit: int = 80):
    adapter = ExistingRegistryAdapter()
    safe_limit = max(1, min(sample_limit, 300))
    return adapter.representation_candidate_preview(sample_limit=safe_limit)


@router.get("/adapters/source-registry/test-seed-plan-preview")
def preview_test_seed_plan(sample_limit: int = 100):
    adapter = ExistingRegistryAdapter()
    safe_limit = max(1, min(sample_limit, 500))
    return adapter.test_seed_plan_preview(sample_limit=safe_limit)


@router.post("/adapters/source-registry/test-seed")
def execute_test_seed():
    adapter = ExistingRegistryAdapter()
    return adapter.execute_test_seed()


@router.post("/adapters/source-registry/purge-test-seed")
def purge_test_seed():
    adapter = ExistingRegistryAdapter()
    return adapter.execute_test_seed_purge()


@router.get("/audit/ownership")
def msi_ownership_audit():
    return build_msi_ownership_audit()


@router.post("/registration/reconcile-converted")
def reconcile_converted_registration(dry_run: bool = True):
    return reconcile_converted_source_segy_to_msi(dry_run=dry_run)


@router.get("/representations/{representation_id:path}/resolved-volume")
def resolve_representation_volume(representation_id: str):
    return resolve_msi_representation_volume(representation_id)


@router.get("/representations/{representation_id:path}/documents")
def representation_documents(representation_id: str):
    return list_representation_documents(representation_id)


@router.get("/representations/{representation_id:path}/metadata-summary")
def representation_metadata_summary(representation_id: str):
    return get_representation_metadata_summary(representation_id)


@router.get("/representations/{representation_id:path}/metadata/normalized")
def representation_normalized_metadata(representation_id: str):
    return get_representation_normalized_metadata(representation_id)


@router.get("/representations/{representation_id:path}/metadata-score-report", response_class=HTMLResponse)
def representation_metadata_score_report(representation_id: str):
    return HTMLResponse(render_representation_metadata_score_report(representation_id))


@router.get("/representations/{representation_id:path}/info-page")
def representation_info_page(representation_id: str):
    return build_representation_info_page(representation_id)


@router.get("/representations/{representation_id:path}/info")
def representation_info(representation_id: str):
    return get_representation_info(representation_id)

