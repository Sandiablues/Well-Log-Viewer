"""WLV Source Intake API routes."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from .models import (
    SourceFileCandidate,
    SourceIntakeCandidateDiagnostics,
    SourceIntakeDepthNormalizationRequest,
    SourceIntakeClearRequest,
    SourceIntakeClearResponse,
    SourceIntakeHealth,
    SourceIntakeBulkResolutionRequest,
    SourceIntakeBulkResolutionResponse,
    SourceIntakeOccurrenceAccounting,
    SourceIntakeOverlayExportPackage,
    SourceIntakeOverlayExportRequest,
    SourceIntakeRegisterRequest,
    SourceIntakeRegisterResponse,
    SourceIntakeSavedWorkspaceDeleteResponse,
    SourceIntakeSavedWorkspaceRecord,
    SourceIntakeSavedWorkspaceSaveRequest,
    SourceIntakeSavedWorkspaceRecoveryResult,
    SourceIntakeSourceRecoveryResult,
    SourceIntakeRestoreToMdpRequest,
    SourceIntakeRestoreToMdpResponse,
    SourceIntakeWorkbench,
    SourceRepositoryCreateRequest,
    SourceRepositoryRecord,
    SourceRepositoryRemoveResponse,
    SourceRepositoryScanResult,
)
from .service import SourceIntakeError, WlvSourceIntakeService
from app.inventory.service import ManagedWellInventoryService

router = APIRouter(prefix="/api/wlv/source-intake", tags=["wlv-source-intake"])
_service = WlvSourceIntakeService()
_inventory_service = ManagedWellInventoryService()


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
    "/ingest-files",
    response_model=SourceRepositoryScanResult,
    summary="Ingest uploaded files through the normal WLV Source Intake pipeline",
)
async def ingest_files(files: list[UploadFile] = File(...)) -> SourceRepositoryScanResult:
    try:
        payloads = [(upload.filename or "", await upload.read()) for upload in files]
        return _service.ingest_uploaded_files(payloads)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        for upload in files:
            await upload.close()


@router.delete(
    "/repositories/{repository_id}",
    response_model=SourceRepositoryRemoveResponse,
    summary="Remove a WLV source repository from Source Intake",
)
def remove_repository(repository_id: str) -> SourceRepositoryRemoveResponse:
    # WLV-WSI-REMOVE-SOURCE-1: repository removal is backend-owned.
    try:
        return _service.remove_repository(repository_id)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


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


@router.get(
    "/candidates/{candidate_id}/diagnostics",
    response_model=SourceIntakeCandidateDiagnostics,
    summary="Fetch backend-owned diagnostics for a WLV Source Intake candidate",
)
def get_candidate_diagnostics(candidate_id: str) -> SourceIntakeCandidateDiagnostics:
    # WLV-WSI-FLAGS-DETAIL-1: diagnostic flags and actions are backend-owned.
    try:
        return _service.get_candidate_diagnostics(candidate_id)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/accounting",
    response_model=SourceIntakeOccurrenceAccounting,
    summary="Account for every WLV Source Intake occurrence",
)
def get_occurrence_accounting() -> SourceIntakeOccurrenceAccounting:
    return _service.get_occurrence_accounting()


@router.post(
    "/resolve",
    response_model=SourceIntakeBulkResolutionResponse,
    summary="Resolve WLV Source Intake review flags",
)
def resolve_candidates(request: SourceIntakeBulkResolutionRequest) -> SourceIntakeBulkResolutionResponse:
    try:
        return _service.resolve_candidates(request)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/workbench/clear", response_model=SourceIntakeClearResponse, summary="Clear active WLV Source Intake selection")
def clear_workbench(request: SourceIntakeClearRequest | None = None) -> SourceIntakeClearResponse:
    # WLV-WSI-CLEAR-CANDIDATE-ROWS-1: candidate row removal is backend-owned.
    return _service.clear_workbench_selection(
        repository_id=request.repository_id if request else None,
        candidate_ids=request.candidate_ids if request else None,
    )




@router.post(
    "/restore-to-mdp",
    response_model=SourceIntakeRestoreToMdpResponse,
    summary="Restore retained MSI records for selected WSI candidates to the Managed Data Page",
)
def restore_candidates_to_mdp(request: SourceIntakeRestoreToMdpRequest) -> SourceIntakeRestoreToMdpResponse:
    try:
        return _service.restore_candidates_to_mdp(request, inventory_service=_inventory_service)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/register", response_model=SourceIntakeRegisterResponse, summary="Register WLV Source Intake candidates to managed inventory")
def register_candidates(request: SourceIntakeRegisterRequest) -> SourceIntakeRegisterResponse:
    try:
        return _service.register_candidates(request, inventory_service=_inventory_service)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/export-overlays",
    response_model=SourceIntakeOverlayExportPackage,
    summary="Export QAQC findings and metadata overlays as a read-only sidecar package",
)
def export_overlays(request: SourceIntakeOverlayExportRequest) -> SourceIntakeOverlayExportPackage:
    try:
        return _service.export_overlay_package(request.candidate_ids)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/saved-workspaces",
    response_model=SourceIntakeSavedWorkspaceRecord,
    summary="Save source references and workspace state without retaining parsed samples",
)
def save_workspace(request: SourceIntakeSavedWorkspaceSaveRequest) -> SourceIntakeSavedWorkspaceRecord:
    try:
        return _service.save_workspace(request)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/saved-workspaces",
    response_model=list[SourceIntakeSavedWorkspaceRecord],
    summary="List saved WSI workspaces",
)
def list_saved_workspaces() -> list[SourceIntakeSavedWorkspaceRecord]:
    return _service.list_saved_workspaces()


@router.get(
    "/saved-workspaces/{workspace_uid}",
    response_model=SourceIntakeSavedWorkspaceRecord,
    summary="Fetch one saved WSI workspace",
)
def get_saved_workspace(workspace_uid: str) -> SourceIntakeSavedWorkspaceRecord:
    try:
        return _service.get_saved_workspace(workspace_uid)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete(
    "/saved-workspaces/{workspace_uid}",
    response_model=SourceIntakeSavedWorkspaceDeleteResponse,
    summary="Delete saved workspace state and release its source references",
)
def delete_saved_workspace(workspace_uid: str) -> SourceIntakeSavedWorkspaceDeleteResponse:
    try:
        return _service.delete_saved_workspace(workspace_uid)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc




@router.post(
    "/candidates/{candidate_id}/recover",
    response_model=SourceIntakeSourceRecoveryResult,
    summary="Check an external source and rebuild changed derived data",
)
def recover_candidate_source(candidate_id: str, rebuild_changed: bool = True) -> SourceIntakeSourceRecoveryResult:
    try:
        return _service.recover_candidate_source(candidate_id, rebuild_changed=rebuild_changed)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/saved-workspaces/{workspace_uid}/recover",
    response_model=SourceIntakeSavedWorkspaceRecoveryResult,
    summary="Validate and recover external sources referenced by a saved workspace",
)
def recover_saved_workspace(workspace_uid: str, rebuild_changed: bool = True) -> SourceIntakeSavedWorkspaceRecoveryResult:
    try:
        return _service.recover_saved_workspace(workspace_uid, rebuild_changed=rebuild_changed)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/candidates/{candidate_id}/depth-normalization",
    response_model=SourceFileCandidate,
    summary="Resolve a WSI candidate depth target unit",
)
def set_candidate_depth_normalization(
    candidate_id: str,
    request: SourceIntakeDepthNormalizationRequest,
) -> SourceFileCandidate:
    try:
        return _service.set_depth_normalization(candidate_id, request)
    except SourceIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
