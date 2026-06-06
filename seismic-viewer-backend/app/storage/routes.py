from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .service import storage_service


router = APIRouter(prefix="/api/storage", tags=["Storage"])


class ResolveStorageUriRequest(BaseModel):
    uri: str


class ManagedZarrCopyRequest(BaseModel):
    execute: bool = False


@router.get("/health")
def storage_health():
    return storage_service().health()


@router.post("/resolve")
def resolve_storage_uri(request: ResolveStorageUriRequest):
    try:
        resolved = storage_service().resolve_uri(request.uri)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "ok": True,
        "uri": resolved.uri,
        "scheme": resolved.scheme,
        "relative_path": resolved.relative_path,
        "local_path": resolved.local_path,
        "exists": resolved.exists,
        "is_dir": resolved.is_dir,
        "is_file": resolved.is_file,
        "resolved_by": "end_seismic_repository_storage_service",
    }


@router.get("/inventory")
def storage_inventory():
    return storage_service().inventory()


@router.get("/migration-plan")
def storage_migration_plan():
    return storage_service().migration_plan()


@router.post("/migration-plan/export")
def export_storage_migration_plan_review():
    return storage_service().export_migration_plan_review()


@router.post("/migration/execute-managed-zarr-copy")
def execute_managed_zarr_copy(request: ManagedZarrCopyRequest):
    return storage_service().execute_managed_zarr_copy(execute=request.execute)
