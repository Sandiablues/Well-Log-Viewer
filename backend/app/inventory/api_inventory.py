"""Managed Well Inventory API routes.

Routes are intentionally thin. Persistence and registration logic live in the
service/repository layer, mirroring the SDV backend ownership pattern.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from .models import (
    ManagedInventoryHealth,
    ManagedInventoryMaintenanceStatus,
    ManagedInventoryStatus,
    LoadManagedWellToWdvRequest,
    LoadManagedWellToWdvResponse,
    UnloadManagedWellFromWdvRequest,
    UnloadManagedWellFromWdvResponse,
    RemoveManagedDataFromMdpRequest,
    RemoveManagedDataFromMdpResponse,
    ManagedInventoryValidationResult,
    ManagedWellRecord,
    RegisterSeedWellResponse,
    ViewerPackageReference,
)
from .repository import ManagedInventoryStoreError, ManagedWellNotFoundError
from .service import ManagedWellInventoryService
from .curve_sample_service import CurveSampleService, CurveSampleServiceError

router = APIRouter(prefix="/api/wlv/inventory", tags=["wlv-inventory"])
_service = ManagedWellInventoryService()
_curve_sample_service = CurveSampleService(repository=_service.repository)


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




@router.post(
    "/load-to-wdv",
    response_model=LoadManagedWellToWdvResponse,
    summary="Load selected managed well data to the Well Data Viewer",
)
def load_managed_well_to_wdv(request: LoadManagedWellToWdvRequest) -> LoadManagedWellToWdvResponse:
    try:
        return _service.load_managed_well_to_wdv(
            managed_well_id=request.managed_well_id,
            product_ids=request.product_ids,
        )
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

@router.post(
    "/unload-from-wdv",
    response_model=UnloadManagedWellFromWdvResponse,
    summary="Unload selected managed well data from the Well Data Viewer",
)
def unload_managed_well_from_wdv(request: UnloadManagedWellFromWdvRequest) -> UnloadManagedWellFromWdvResponse:
    try:
        return _service.unload_managed_well_from_wdv(
            managed_well_id=request.managed_well_id,
            product_ids=request.product_ids,
        )
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

@router.post(
    "/remove-from-mdp",
    response_model=RemoveManagedDataFromMdpResponse,
    summary="Remove selected managed well data from the Managed Data Page",
)
def remove_managed_data_from_mdp(request: RemoveManagedDataFromMdpRequest) -> RemoveManagedDataFromMdpResponse:
    try:
        return _service.remove_managed_data_from_mdp(
            managed_well_ids=request.managed_well_ids,
            product_ids=request.product_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well or product not found: {exc.args[0]}",
        ) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

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

@router.get(
    "/wells/{managed_well_id}/viewer-package",
    response_model=dict[str, Any],
    summary="Fetch backend-owned viewer package contract for managed WLV well",
)
def get_managed_well_viewer_package(managed_well_id: str) -> dict[str, Any]:
    try:
        return _service.get_viewer_package_contract(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well viewer package not found: {exc.args[0]}",
        )
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))




@router.get(
    "/wells/{managed_well_id}/curve-samples",
    response_model=dict[str, Any],
    summary="Fetch product-id-backed curve samples for WDV rendering",
)
def get_managed_well_curve_samples(
    managed_well_id: str,
    product_id: str = Query(..., min_length=1),
    max_samples: int = Query(12000, ge=100, le=100000),
) -> dict[str, Any]:
    try:
        return _curve_sample_service.get_curve_samples(
            managed_well_id=managed_well_id,
            product_id=product_id,
            max_samples=max_samples,
        )
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well or product not found: {exc.args[0]}",
        ) from exc
    except CurveSampleServiceError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

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
