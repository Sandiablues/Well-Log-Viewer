"""Managed Well Inventory API routes.

Routes are intentionally thin. Persistence and registration logic live in the
service/repository layer, mirroring the SDV backend ownership pattern.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from .models import (
    ManagedInventoryHealth,
    ManagedInventoryMaintenanceStatus,
    ManagedInventoryStatus,
    ManagedInventoryValidationResult,
    ManagedWellRecord,
    RegisterSeedWellResponse,
    ViewerPackageReference,
)
from .repository import ManagedInventoryStoreError, ManagedWellNotFoundError
from .service import ManagedWellInventoryService

router = APIRouter(prefix="/api/wlv/inventory", tags=["wlv-inventory"])
_service = ManagedWellInventoryService()


@router.get("/health", response_model=ManagedInventoryHealth, summary="Managed Well Inventory health")
def health() -> ManagedInventoryHealth:
    return _service.health()


@router.get("/status", response_model=ManagedInventoryStatus, summary="Managed Well Inventory status")
def status_summary() -> ManagedInventoryStatus:
    try:
        return _service.status()
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/validate", response_model=ManagedInventoryValidationResult, summary="Validate managed inventory integrity")
def validate_inventory() -> ManagedInventoryValidationResult:
    try:
        return _service.validate_inventory()
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get(
    "/maintenance/status",
    response_model=ManagedInventoryMaintenanceStatus,
    summary="Managed inventory maintenance status",
)
def maintenance_status() -> ManagedInventoryMaintenanceStatus:
    try:
        return _service.maintenance_status()
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/wells", response_model=list[ManagedWellRecord], summary="List managed WLV wells")
def list_wells() -> list[ManagedWellRecord]:
    try:
        return _service.list_wells()
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get(
    "/wells/{managed_well_id}",
    response_model=ManagedWellRecord,
    summary="Fetch managed WLV well inventory record",
)
def get_well(managed_well_id: str) -> ManagedWellRecord:
    try:
        return _service.get_well(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        )
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post(
    "/wells/register-seed",
    response_model=RegisterSeedWellResponse,
    summary="Register the current deterministic seed well into managed inventory",
)
def register_seed_well() -> RegisterSeedWellResponse:
    return _service.register_seed_well()


@router.get(
    "/viewer-packages",
    response_model=list[ViewerPackageReference],
    summary="List viewer-package references registered in managed inventory",
)
def list_viewer_packages() -> list[ViewerPackageReference]:
    try:
        return _service.list_viewer_packages()
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
