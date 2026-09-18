from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict
from app.services.source_artifact_maintenance_service import build_source_artifact_maintenance_preflight, execute_source_artifact_maintenance

from fastapi import APIRouter, HTTPException

from app.services.dataset_registry_service import (
    delete_dataset,
    delete_dataset_optimized_cache,
)
from app.services.job_service import JobService
from app.services.indexed_optimized_cache_service import IndexedOptimizedCacheService
from app.services.source_segy_lifecycle_service import build_source_segy_lifecycle
from app.services.managed_representation_request_service import ManagedRepresentationRequestService
from app.services.source_segy_representation_service import (
    build_source_segy_representations_by_id,
    index_source_segy_preview_by_id,
)
from app.services.volume_registry_service import delete_volume as delete_volume_service


router = APIRouter(prefix="/api/segy-files", tags=["source-segy-lifecycle"])

_lifecycle_job_service = JobService()
_lifecycle_indexed_cache_service = IndexedOptimizedCacheService(_lifecycle_job_service)
_lifecycle_cache_executor = ThreadPoolExecutor(max_workers=1)
_managed_representation_request_service = ManagedRepresentationRequestService()


def _raw_representations(segy_file_id: str, mode: str = "3d") -> Dict[str, Any]:
    payload = build_source_segy_representations_by_id(segy_file_id, mode=mode)
    reps = payload.get("representations") or {}
    if not isinstance(reps, dict):
        return {}
    return reps


def _dataset_id_for_source(segy_file_id: str, mode: str = "3d") -> str:
    reps = _raw_representations(segy_file_id, mode=mode)
    indexed = reps.get("indexed_preview") or {}
    dataset_id = indexed.get("dataset_id")
    if not dataset_id:
        raise FileNotFoundError(f"Indexed preview does not exist for source SEG-Y: {segy_file_id}")
    return str(dataset_id)


def _managed_volume_id_for_source(segy_file_id: str, mode: str = "3d") -> str:
    reps = _raw_representations(segy_file_id, mode=mode)
    managed = reps.get("zarr_full_conversion") or {}
    volume_id = managed.get("volume_id")
    if not volume_id:
        raise FileNotFoundError(f"Managed Zarr does not exist for source SEG-Y: {segy_file_id}")
    return str(volume_id)


def _with_lifecycle(
    *,
    segy_file_id: str,
    mode: str,
    action_result: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "status": "ok",
        "action_result": action_result,
        "lifecycle": build_source_segy_lifecycle(segy_file_id, mode=mode),
    }


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{segy_file_id}/lifecycle")
def get_source_segy_lifecycle(
    segy_file_id: str,
    mode: str = "3d",
) -> Dict[str, Any]:
    try:
        return build_source_segy_lifecycle(segy_file_id, mode=mode)
    except Exception as exc:
        _raise_http(exc)


@router.post("/{segy_file_id}/actions/create-index")
def create_index_preview(
    segy_file_id: str,
    mode: str = "3d",
) -> Dict[str, Any]:
    try:
        result = index_source_segy_preview_by_id(segy_file_id, mode=mode)
        return _with_lifecycle(segy_file_id=segy_file_id, mode=mode, action_result=result)
    except Exception as exc:
        _raise_http(exc)


@router.post("/{segy_file_id}/actions/build-fast-zarr-cache")
def build_fast_zarr_cache(
    segy_file_id: str,
    mode: str = "3d",
) -> Dict[str, Any]:
    try:
        dataset_id = _dataset_id_for_source(segy_file_id, mode=mode)
        result = _lifecycle_indexed_cache_service.queue_build(dataset_id)
        job_id = result.get("job_id")
        if result.get("status") == "queued" and job_id:
            _lifecycle_cache_executor.submit(_lifecycle_indexed_cache_service.run, job_id)

        return _with_lifecycle(
            segy_file_id=segy_file_id,
            mode=mode,
            action_result={
                **result,
                "action": "build_fast_zarr_cache",
                "dataset_id": dataset_id,
            },
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/{segy_file_id}/actions/create-managed-zarr")
def create_managed_zarr(
    segy_file_id: str,
    mode: str = "3d",
    expected_dataset_type: str | None = None,
) -> Dict[str, Any]:
    try:
        clean_mode = str(mode).strip().lower()
        if clean_mode not in {"2d", "3d"}:
            raise ValueError(f"Managed Zarr creation mode must be 2d or 3d, got: {mode!r}")

        clean_expected_dataset_type = (expected_dataset_type or "").strip().lower() or None
        if clean_expected_dataset_type is None:
            clean_expected_dataset_type = "2d_line" if clean_mode == "2d" else "3d_volume"

        result = _managed_representation_request_service.build_managed_representation(
            candidate_id=segy_file_id,
            target_type=clean_expected_dataset_type,
        )
        return _with_lifecycle(segy_file_id=segy_file_id, mode=mode, action_result=result)
    except Exception as exc:
        _raise_http(exc)


@router.post("/{segy_file_id}/actions/create-managed-2d-line-zarr")
def create_managed_2d_line_zarr(
    segy_file_id: str,
    mode: str = "2d",
) -> Dict[str, Any]:
    clean_mode = str(mode).strip().lower()
    if clean_mode != "2d":
        raise HTTPException(
            status_code=400,
            detail=f"create-managed-2d-line-zarr requires mode=2d, got: {mode!r}",
        )

    return create_managed_zarr(
        segy_file_id=segy_file_id,
        mode="2d",
        expected_dataset_type="2d_line",
    )


@router.delete("/{segy_file_id}/representations/managed-2d-line-zarr")
def delete_managed_2d_line_zarr(
    segy_file_id: str,
    mode: str = "2d",
) -> Dict[str, Any]:
    clean_mode = str(mode).strip().lower()
    if clean_mode != "2d":
        raise HTTPException(
            status_code=400,
            detail=f"managed-2d-line-zarr delete requires mode=2d, got: {mode!r}",
        )

    return delete_managed_zarr(segy_file_id=segy_file_id, mode="2d")


@router.delete("/{segy_file_id}/representations/index-preview")
def delete_index_preview(
    segy_file_id: str,
    mode: str = "3d",
) -> Dict[str, Any]:
    try:
        dataset_id = _dataset_id_for_source(segy_file_id, mode=mode)
        result = delete_dataset(dataset_id)
        return _with_lifecycle(
            segy_file_id=segy_file_id,
            mode=mode,
            action_result={
                **result,
                "action": "delete_index_preview",
                "dependency_behavior": "Deleted Index / Preview and any attached Fast Zarr Cache.",
            },
        )
    except Exception as exc:
        _raise_http(exc)


@router.delete("/{segy_file_id}/representations/fast-zarr-cache")
def delete_fast_zarr_cache(
    segy_file_id: str,
    mode: str = "3d",
) -> Dict[str, Any]:
    try:
        dataset_id = _dataset_id_for_source(segy_file_id, mode=mode)
        result = delete_dataset_optimized_cache(dataset_id)
        return _with_lifecycle(
            segy_file_id=segy_file_id,
            mode=mode,
            action_result={
                **result,
                "action": "delete_fast_zarr_cache",
                "dependency_behavior": "Deleted Fast Zarr Cache only. Preserved Index / Preview.",
            },
        )
    except Exception as exc:
        _raise_http(exc)


@router.delete("/{segy_file_id}/representations/managed-zarr")
def delete_managed_zarr(
    segy_file_id: str,
    mode: str = "3d",
) -> Dict[str, Any]:
    try:
        clean_mode = str(mode).strip().lower()
        if clean_mode not in {"2d", "3d"}:
            raise ValueError(f"Managed Zarr delete mode must be 2d or 3d, got: {mode!r}")

        volume_id = _managed_volume_id_for_source(segy_file_id, mode=clean_mode)
        result = delete_volume_service(volume_id)
        return _with_lifecycle(
            segy_file_id=segy_file_id,
            mode=mode,
            action_result={
                **result,
                "action": "delete_managed_zarr",
                "dependency_behavior": "Deleted Managed Zarr only. Preserved Index / Preview and Fast Zarr Cache.",
            },
        )
    except Exception as exc:
        _raise_http(exc)


@router.get("/{segy_file_id}/maintenance/{artifact_key}/preflight")
def preflight_source_artifact_maintenance(
    segy_file_id: str,
    artifact_key: str,
    action: str = "delete",
    mode: str = "3d",
) -> Dict[str, Any]:
    """
    Read-only preflight for backend-owned source SEG-Y artifact maintenance.

    This endpoint does not delete, rebuild, mutate, or archive anything.
    It returns backend-owned impact and dependency semantics so the frontend
    does not infer derived-artifact behavior locally.
    """
    try:
        return build_source_artifact_maintenance_preflight(
            segy_file_id=segy_file_id,
            artifact_key=artifact_key,
            action=action,
            mode=mode,
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/{segy_file_id}/maintenance/{artifact_key}/execute")
def execute_source_artifact_maintenance_route(
    segy_file_id: str,
    artifact_key: str,
    action: str = "delete",
    mode: str = "3d",
    confirm: bool = False,
) -> Dict[str, Any]:
    """
    Execute backend-owned source SEG-Y artifact maintenance.

    Destructive actions require confirm=true. The frontend should use preflight
    first, then call this endpoint only after explicit user confirmation.
    """
    if not confirm:
        raise HTTPException(status_code=400, detail="Maintenance execution requires confirm=true.")

    try:
        return execute_source_artifact_maintenance(
            segy_file_id=segy_file_id,
            artifact_key=artifact_key,
            action=action,
            mode=mode,
            confirm=confirm,
        )
    except Exception as exc:
        _raise_http(exc)

