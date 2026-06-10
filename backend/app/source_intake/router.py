"""WLV Source Intake API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from .models import (
    SourceIntakeClearRequest,
    SourceIntakeClearResponse,
    SourceIntakeHealth,
    SourceIntakeWorkbench,
    SourceRepositoryCreateRequest,
    SourceRepositoryRecord,
    SourceRepositoryScanResult,
)
from .service import SourceIntakeError, WlvSourceIntakeService

router = APIRouter(prefix="/api/wlv/source-intake", tags=["wlv-source-intake"])
_service = WlvSourceIntakeService()


@router.get("/health", response_model=SourceIntakeHealth, summary="WLV Source Intake health")
def source_intake_health() -> SourceIntakeHealth:
    return SourceIntakeHealth()


@router.post("/repositories", response_model=SourceRepositoryRecord, summary="Register a WLV source repository")
def create_repository(request: SourceRepositoryCreateRequest) -> SourceRepositoryRecord:
    try:
        return _service.create_repository(request)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/repositories", response_model=list[SourceRepositoryRecord], summary="List WLV source repositories")
def list_repositories() -> list[SourceRepositoryRecord]:
    return _service.list_repositories()


@router.post(
    "/repositories/{repository_id}/scan",
    response_model=SourceRepositoryScanResult,
    summary="Scan a WLV source repository",
)
def scan_repository(repository_id: str, include_subfolders: bool | None = None) -> SourceRepositoryScanResult:
    try:
        return _service.scan_repository(repository_id, include_subfolders=include_subfolders)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/workbench", response_model=SourceIntakeWorkbench, summary="Fetch WLV Source Intake workbench")
def get_workbench() -> SourceIntakeWorkbench:
    return _service.get_workbench()


@router.post("/workbench/clear", response_model=SourceIntakeClearResponse, summary="Clear active WLV Source Intake selection")
def clear_workbench(request: SourceIntakeClearRequest | None = None) -> SourceIntakeClearResponse:
    return _service.clear_workbench_selection(repository_id=request.repository_id if request else None)
