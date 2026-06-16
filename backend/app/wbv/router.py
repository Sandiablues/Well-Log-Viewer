"""3D Wellbore Viewer API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.inventory.repository import ManagedInventoryStoreError, ManagedWellNotFoundError

from .models import (
    WbvSessionContract,
    WbvSetActiveTrajectoryRequest,
    WbvSetActiveTrajectoryResponse,
    WbvTrajectoryListContract,
    WbvViewerPackageContract,
)
from .service import WbvService

router = APIRouter(prefix="/api/wlv/wbv", tags=["wlv-wbv"])
_service = WbvService()


@router.get("/health", summary="WBV backend contract health")
def health() -> dict[str, object]:
    return {"ok": True, "service": "wlv-wbv", "scope": "wbv_backend_contract"}


@router.get("/session", response_model=WbvSessionContract, summary="Fetch active WBV session from backend-owned WDV load state")
def get_wbv_session() -> WbvSessionContract:
    try:
        return _service.get_session()
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get(
    "/wells/{managed_well_id}/trajectories",
    response_model=WbvTrajectoryListContract,
    summary="List backend-managed wellbore geometry records for a managed well",
)
def list_wbv_trajectories(managed_well_id: str) -> WbvTrajectoryListContract:
    try:
        return _service.list_trajectories(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post(
    "/wells/{managed_well_id}/trajectories/active",
    response_model=WbvSetActiveTrajectoryResponse,
    summary="Set the backend-owned active trajectory for WBV/WDV correlation",
)
def set_active_wbv_trajectory(
    managed_well_id: str,
    request: WbvSetActiveTrajectoryRequest,
) -> WbvSetActiveTrajectoryResponse:
    try:
        return _service.set_active_trajectory(
            managed_well_id,
            request.trajectory_id,
            requested_by=request.requested_by,
            note=request.note,
        )
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get(
    "/wells/{managed_well_id}/viewer-package",
    response_model=WbvViewerPackageContract,
    summary="Fetch backend-owned WBV viewer package for a managed well",
)
def get_wbv_viewer_package(managed_well_id: str) -> WbvViewerPackageContract:
    try:
        return _service.get_viewer_package(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
