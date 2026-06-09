"""
WLV backend foundation API.

Routes expose backend-owned well/log/curve/interval/viewer-package contracts.
The current implementation is a deterministic seed repository; later blocks can
swap the repository without changing these endpoint contracts.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from .models import Curve, IntervalColumn, WellDetail, WellMultitrackV1, WellSummary
from .seed_repository import SeedWellRepository, WellNotFoundError

router = APIRouter(prefix="/api/wlv", tags=["wlv"])
_repository = SeedWellRepository()


@router.get("/health", summary="WLV backend health check")
def health() -> dict[str, object]:
    return {"ok": True, "service": "wlv", "scope": "backend_foundation"}


@router.get("/wells", response_model=list[WellSummary], summary="List WLV wells")
def list_wells() -> list[WellSummary]:
    return _repository.list_wells()


@router.get("/wells/{well_id}", response_model=WellDetail, summary="Fetch WLV well detail")
def get_well(well_id: str) -> WellDetail:
    try:
        return _repository.get_well(well_id)
    except WellNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Well not found: {exc.args[0]}")


@router.get("/wells/{well_id}/curves", response_model=list[Curve], summary="List curves for a well")
def list_curves(well_id: str) -> list[Curve]:
    try:
        return _repository.list_curves(well_id)
    except WellNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Well not found: {exc.args[0]}")


@router.get(
    "/wells/{well_id}/interval-columns",
    response_model=list[IntervalColumn],
    summary="List interval columns for a well",
)
def list_interval_columns(well_id: str) -> list[IntervalColumn]:
    try:
        return _repository.list_interval_columns(well_id)
    except WellNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Well not found: {exc.args[0]}")


@router.get(
    "/wells/{well_id}/viewer-package",
    response_model=WellMultitrackV1,
    summary="Fetch backend-owned viewer package for a well",
)
def get_viewer_package(well_id: str) -> WellMultitrackV1:
    try:
        return _repository.get_viewer_package(well_id)
    except WellNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Well not found: {exc.args[0]}")
