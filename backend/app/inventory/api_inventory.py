"""Managed Well Inventory API routes.

Routes are intentionally thin. Persistence and registration logic live in the
service/repository layer, mirroring the SDV backend ownership pattern.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path
import json
import zipfile

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .models import (
    ManagedInventoryHealth,
    ManagedInventoryMaintenanceStatus,
    ManagedInventoryStatus,
    LoadManagedWellToWdvRequest,
    LoadManagedWellToWdvResponse,
    ExecuteWmdCleanupRequest,
    ExecuteWmdCleanupResponse,
    RebuildWmdPayloadRequest,
    RebuildWmdPayloadResponse,
    BulkLoadWdvWorkspaceRequest,
    BulkLoadWdvWorkspaceResponse,
    BulkUnloadWdvWorkspaceRequest,
    BulkUnloadWdvWorkspaceResponse,
    UnloadManagedWellFromWdvRequest,
    UnloadManagedWellFromWdvResponse,
    RemoveManagedDataFromMdpRequest,
    RemoveManagedDataFromMdpResponse,
    ManagedInventoryValidationResult,
    ManagedWellRecord,
    PublishFormationTopsRequest,
    PublishFormationTopsResponse,
    PublishLithologyIntervalsRequest,
    PublishLithologyIntervalsResponse,
    PublishCompletionComponentsRequest,
    PublishCompletionComponentsResponse,
    PublishCompoundCoreSegmentsRequest,
    PublishCompoundCoreSegmentsResponse,
    PublishDeviationSurveyRequest,
    PublishDeviationSurveyResponse,
    RegisterSeedWellResponse,
    ViewerPackageReference,
    SetActiveWdvWellRequest,
    SetCommonDepthUnitRequest,
    WdvWorkspaceStateResponse,
    WmdDownstreamRecoveryStatus,
    ReconcileExportReferencesRequest,
    ReleaseConsumerReferencesRequest,
    ResetViewerSessionRequest,
    ReconcileStaleConsumerReferencesRequest,
    WmdReferenceReconciliationResponse,
)
from .repository import ManagedInventoryStoreError, ManagedWellNotFoundError
from .service import ManagedWellInventoryService
from .managed_well_purge import (
    ManagedWellPurgeRequest,
    ManagedWellPurgeResponse,
    ManagedWellPurgeService,
)
from .mwd_transient_flush import (
    MwdTransientFlushRequest,
    MwdTransientFlushResponse,
    MwdTransientFlushService,
)
from .mwd_selected_delete import SelectedManagedDataDeleteService
from .curve_sample_service import CurveSampleService, CurveSampleServiceError

from app.saved_canvas.models import (
    SavedCanvasCreateRequest,
    SavedCanvasMetadata,
    SavedCanvasRecord,
    SavedCanvasRestoreRequest,
    SavedCanvasRestoreResponse,
    SavedCanvasUpdateRequest,
)
from app.saved_canvas.repository import SavedCanvasNotFoundError
from app.saved_canvas.service import (
    SavedCanvasMissingDataError,
    SavedCanvasRestoreInProgress,
    SavedCanvasService,
    SavedCanvasWorkspaceConfigurationMismatch,
    SavedCanvasWorkspaceRevisionConflict,
)

from app.wdv_session.canonical_service import CanonicalSessionRevisionConflict, CanonicalWdvSessionService
from app.identity.wdv_contract_v2 import WdvCanonicalSession, WdvTextOverlay

router = APIRouter(prefix="/api/wlv/inventory", tags=["wlv-inventory"])
_service = ManagedWellInventoryService()
_curve_sample_service = CurveSampleService(repository=_service.repository)
_purge_service = ManagedWellPurgeService(repository=_service.repository)
_mwd_flush_service = MwdTransientFlushService(repository=_service.repository)
_selected_delete_service = SelectedManagedDataDeleteService(repository=_service.repository)
_saved_canvas_service = SavedCanvasService(inventory_service=_service)
_wdv_canonical_session_service = CanonicalWdvSessionService()


class UpdateTrackTextOverlaysRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    text_overlays: tuple[WdvTextOverlay, ...] = ()


@router.put(
    "/wdv/session/{managed_well_uid}/tracks/{track_uid}/text-overlays",
    response_model=WdvCanonicalSession,
    summary="Replace one track's text box overlays",
)
def update_wdv_track_text_overlays(
    managed_well_uid: str,
    track_uid: str,
    request: UpdateTrackTextOverlaysRequest,
) -> WdvCanonicalSession:
    try:
        def mutation(current: WdvCanonicalSession) -> WdvCanonicalSession:
            found = False
            next_tracks = []
            for track in current.tracks:
                if track.track_uid != track_uid:
                    next_tracks.append(track)
                    continue
                if track.managed_well_uid != managed_well_uid:
                    raise ValueError("Text Overlay target track belongs to another managed well")
                found = True
                next_tracks.append(track.model_copy(update={"text_overlays": request.text_overlays}))
            if not found:
                raise ValueError("Text Overlay target track was not found")
            return current.model_copy(update={"tracks": tuple(next_tracks)})

        return _wdv_canonical_session_service.mutate_session_transactionally(
            managed_well_uid,
            expected_revision=request.expected_revision,
            mutation=mutation,
        )
    except CanonicalSessionRevisionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


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





@router.get(
    "/wdv-workspace",
    response_model=WdvWorkspaceStateResponse,
    summary="Return the backend-owned multi-well WDV workspace",
)
def get_wdv_workspace() -> WdvWorkspaceStateResponse:
    try:
        return _service.get_wdv_workspace()
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc




@router.post(
    "/wdv-workspace/{workspace_id}/saved-canvases",
    response_model=SavedCanvasRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Create one immutable workspace-level WDV Saved Canvas",
)
def create_saved_canvas(workspace_id: str, request: SavedCanvasCreateRequest) -> SavedCanvasRecord:
    try:
        return _saved_canvas_service.create(workspace_id, request)
    except SavedCanvasWorkspaceRevisionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.put(
    "/wdv-workspace/{workspace_id}/saved-canvases/{saved_canvas_uid}",
    response_model=SavedCanvasRecord,
    summary="Save current WDV canvas into an existing Saved Canvas",
)
def update_saved_canvas(
    workspace_id: str, saved_canvas_uid: str, request: SavedCanvasUpdateRequest
) -> SavedCanvasRecord:
    try:
        return _saved_canvas_service.update(workspace_id, saved_canvas_uid, request)
    except SavedCanvasNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved Canvas not found") from exc
    except SavedCanvasWorkspaceRevisionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get(
    "/wdv-workspace/{workspace_id}/saved-canvases",
    response_model=list[SavedCanvasMetadata],
    summary="List immutable Saved Canvases for one WDV workspace",
)
def list_saved_canvases(workspace_id: str) -> list[SavedCanvasMetadata]:
    try:
        return _saved_canvas_service.list(workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get(
    "/wdv-workspace/{workspace_id}/saved-canvases/{saved_canvas_uid}",
    response_model=SavedCanvasRecord,
    summary="Get one immutable WDV Saved Canvas",
)
def get_saved_canvas(workspace_id: str, saved_canvas_uid: str) -> SavedCanvasRecord:
    try:
        return _saved_canvas_service.get(workspace_id, saved_canvas_uid)
    except SavedCanvasNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved Canvas not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete(
    "/wdv-workspace/{workspace_id}/saved-canvases/{saved_canvas_uid}",
    response_model=SavedCanvasMetadata,
    summary="Physically delete one immutable WDV Saved Canvas",
)
def delete_saved_canvas(workspace_id: str, saved_canvas_uid: str) -> SavedCanvasMetadata:
    try:
        return _saved_canvas_service.delete(workspace_id, saved_canvas_uid)
    except SavedCanvasNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved Canvas not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/wdv-workspace/{workspace_id}/saved-canvases/{saved_canvas_uid}/restore",
    response_model=SavedCanvasRestoreResponse,
    summary="Atomically restore one immutable WDV Saved Canvas",
)
def restore_saved_canvas(
    workspace_id: str,
    saved_canvas_uid: str,
    request: SavedCanvasRestoreRequest,
) -> SavedCanvasRestoreResponse:
    try:
        return _saved_canvas_service.restore(workspace_id, saved_canvas_uid, request)
    except SavedCanvasNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved Canvas not found") from exc
    except (
        SavedCanvasRestoreInProgress,
        SavedCanvasWorkspaceRevisionConflict,
        CanonicalSessionRevisionConflict,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (
        SavedCanvasMissingDataError,
        SavedCanvasWorkspaceConfigurationMismatch,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.put(
    "/wdv-workspace/common-depth-unit",
    response_model=WdvWorkspaceStateResponse,
    summary="Set the backend-owned Common Depth Unit for the WDV workspace",
)
def set_common_depth_unit(request: SetCommonDepthUnitRequest) -> WdvWorkspaceStateResponse:
    try:
        return _service.set_common_depth_unit(request.common_depth_unit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.put(
    "/wdv-workspace/active-well",
    response_model=WdvWorkspaceStateResponse,
    summary="Set the active well within the loaded multi-well WDV workspace",
)
def set_active_wdv_well(request: SetActiveWdvWellRequest) -> WdvWorkspaceStateResponse:
    try:
        return _service.set_active_wdv_well(request.well_reference)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post(
    "/wdv-workspace/wells/load",
    response_model=BulkLoadWdvWorkspaceResponse,
    summary="Atomically load multiple managed wells into the WDV workspace",
)
def bulk_load_wdv_workspace(
    request: BulkLoadWdvWorkspaceRequest,
) -> BulkLoadWdvWorkspaceResponse:
    try:
        return _service.bulk_load_wdv_workspace(request.selections)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc



@router.post(
    "/wdv-workspace/wells/unload",
    response_model=BulkUnloadWdvWorkspaceResponse,
    summary="Atomically unload multiple managed wells from the WDV workspace",
)
def bulk_unload_wdv_workspace(request: BulkUnloadWdvWorkspaceRequest) -> BulkUnloadWdvWorkspaceResponse:
    try:
        return _service.bulk_unload_wdv_workspace(request.selections)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Managed well not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc



@router.post(
    "/references/export/reconcile",
    response_model=WmdReferenceReconciliationResponse,
    summary="Reconcile WMD references for one active export job",
)
def reconcile_export_references(
    request: ReconcileExportReferencesRequest,
) -> WmdReferenceReconciliationResponse:
    try:
        mapping = {item.well_reference: item.product_references for item in request.selections}
        records = _service.reconcile_export_references(str(request.export_uid), mapping)
        return WmdReferenceReconciliationResponse(
            owner_id=str(request.export_uid),
            touched_well_ids=[record.managed_well_id for record in records],
        )
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/references/export/release",
    response_model=WmdReferenceReconciliationResponse,
    summary="Release all WMD references owned by one export job",
)
def release_export_references(
    request: ReleaseConsumerReferencesRequest,
) -> WmdReferenceReconciliationResponse:
    records = _service.release_export_references(request.owner_uid)
    return WmdReferenceReconciliationResponse(
        owner_id=request.owner_uid,
        touched_well_ids=[record.managed_well_id for record in records],
    )


@router.post(
    "/references/viewer-session/reset",
    response_model=WmdReferenceReconciliationResponse,
    summary="Release ephemeral WBV viewer-session references",
)
def reset_viewer_session_references(
    request: ResetViewerSessionRequest,
) -> WmdReferenceReconciliationResponse:
    records = _service.reset_viewer_session_references(owner_id=request.owner_id)
    return WmdReferenceReconciliationResponse(
        owner_id=request.owner_id,
        touched_well_ids=[record.managed_well_id for record in records],
    )


@router.post(
    "/references/stale/reconcile",
    response_model=WmdReferenceReconciliationResponse,
    summary="Release stale export, saved-workspace, and WBV references",
)
def reconcile_stale_consumer_references(
    request: ReconcileStaleConsumerReferencesRequest,
) -> WmdReferenceReconciliationResponse:
    records = _service.reconcile_stale_consumer_references(
        active_export_owner_ids=set(request.active_export_owner_ids),
        active_saved_workspace_owner_ids=set(request.active_saved_workspace_owner_ids),
        active_wbv_owner_ids=set(request.active_wbv_owner_ids),
    )
    return WmdReferenceReconciliationResponse(
        touched_well_ids=[record.managed_well_id for record in records],
    )


@router.post(
    "/wmd/cleanup",
    response_model=ExecuteWmdCleanupResponse,
    summary="Clear eligible WLV-owned transient WMD viewer payloads",
)
def execute_wmd_cleanup(request: ExecuteWmdCleanupRequest) -> ExecuteWmdCleanupResponse:
    try:
        return _service.execute_wmd_cleanup(
            managed_well_id=request.well_reference,
            product_ids=request.product_references or None,
        )
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post(
    "/wmd/rebuild",
    response_model=RebuildWmdPayloadResponse,
    summary="Rebuild cleared transient WMD payloads from retained source provenance",
)
def rebuild_wmd_payload(request: RebuildWmdPayloadRequest) -> RebuildWmdPayloadResponse:
    try:
        return _service.rebuild_wmd_payload(
            managed_well_id=request.well_reference,
            product_ids=request.product_references or None,
        )
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post(
    "/load-to-wdv",
    response_model=LoadManagedWellToWdvResponse,
    summary="Load selected managed well data to the Well Data Viewer",
)
def load_managed_well_to_wdv(request: LoadManagedWellToWdvRequest) -> LoadManagedWellToWdvResponse:
    try:
        return _service.load_managed_well_to_wdv(
            managed_well_id=request.well_reference,
            product_ids=request.product_references,
        )
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
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
            managed_well_id=request.well_reference,
            product_ids=request.product_references,
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
    summary="Completely delete selected transient managed data from MWD",
)
def remove_managed_data_from_mdp(request: RemoveManagedDataFromMdpRequest) -> RemoveManagedDataFromMdpResponse:
    try:
        return _selected_delete_service.delete_selected(
            managed_well_ids=request.well_references,
            product_ids=request.product_references,
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



@router.post(
    "/wells/{managed_well_id}/formation-tops",
    response_model=PublishFormationTopsResponse,
    summary="Replace the selected MWD well's reviewed Formation Tops dataset",
)
def publish_formation_tops(
    managed_well_id: str,
    request: PublishFormationTopsRequest,
) -> PublishFormationTopsResponse:
    try:
        return _service.publish_formation_tops(managed_well_id, request)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post(
    "/wells/{managed_well_id}/deviation-survey",
    response_model=PublishDeviationSurveyResponse,
    summary="Append a reviewed deviation survey to the selected MWD well",
)
def publish_deviation_survey(
    managed_well_id: str,
    request: PublishDeviationSurveyRequest,
) -> PublishDeviationSurveyResponse:
    try:
        return _service.publish_deviation_survey(managed_well_id, request)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post(
    "/wells/{managed_well_id}/lithology-intervals",
    response_model=PublishLithologyIntervalsResponse,
    summary="Replace the selected MWD well's reviewed lithology interval dataset",
)
def publish_lithology_intervals(
    managed_well_id: str,
    request: PublishLithologyIntervalsRequest,
) -> PublishLithologyIntervalsResponse:
    try:
        return _service.publish_lithology_intervals(managed_well_id, request)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Managed well not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post(
    "/wells/{managed_well_id}/completion-components",
    response_model=PublishCompletionComponentsResponse,
    summary="Replace the selected MWD well's reviewed visualization completion dataset",
)
def publish_completion_components(
    managed_well_id: str,
    request: PublishCompletionComponentsRequest,
) -> PublishCompletionComponentsResponse:
    try:
        return _service.publish_completion_components(managed_well_id, request)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post(
    "/wells/{managed_well_id}/core-segment-packages",
    response_model=PublishCompoundCoreSegmentsResponse,
    summary="Upsert compound core packages as separate MWD assets",
)
def publish_compound_core_segments(
    managed_well_id: str,
    request: PublishCompoundCoreSegmentsRequest,
) -> PublishCompoundCoreSegmentsResponse:
    try:
        return _service.publish_compound_core_segments(managed_well_id, request)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.get(
    "/wells/{managed_well_id}/core-segment-image",
    summary="Return the depth-tied core image payload for one MWD core package",
)
def get_core_segment_image(
    managed_well_id: str,
    product_id: str = Query(..., min_length=1),
) -> Response:
    try:
        record = _service.repository.get_record(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc

    item = next(
        (
            candidate
            for group in record.product_groups
            for candidate in group.items
            if candidate.product_id == product_id
            and candidate.product_subgroup_key == "compound_core_segment"
        ),
        None,
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Core image package not found.")

    provenance = item.provenance if isinstance(item.provenance, dict) else {}
    package_path = Path(str(provenance.get("package_path") or ""))
    if not package_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Core image package asset is missing.")

    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            image_filename = str(manifest.get("image_filename") or "")
            if not image_filename:
                raise ValueError("Core package manifest does not identify an image.")
            payload = archive.read(image_filename)
            suffix = Path(image_filename).suffix.lower()
            media_type = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".tif": "image/tiff",
                ".tiff": "image/tiff",
            }.get(suffix, "application/octet-stream")
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to read core image package: {exc}",
        ) from exc

    return Response(
        content=payload,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get(
    "/wells/{managed_well_id}/core-segment-display-chunks",
    summary="Return depth-indexed display chunks for a continuous core package",
)
def get_core_segment_display_chunks(
    managed_well_id: str,
    product_id: str = Query(..., min_length=1),
) -> dict:
    try:
        record = _service.repository.get_record(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc

    item = next(
        (
            candidate
            for group in record.product_groups
            for candidate in group.items
            if candidate.product_id == product_id
            and candidate.product_subgroup_key == "compound_core_segment"
        ),
        None,
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Core image package not found.",
        )

    provenance = item.provenance if isinstance(item.provenance, dict) else {}
    package_path = Path(str(provenance.get("package_path") or ""))
    if not package_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Core image package asset is missing.",
        )

    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            manifest = json.loads(
                archive.read("manifest.json").decode("utf-8")
            )

            chunks = manifest.get("display_chunks") or []
            if not isinstance(chunks, list):
                raise ValueError(
                    "Core package display_chunks manifest value is invalid."
                )

            return {
                "product_id": product_id,
                "segment_id": manifest.get("segment_id"),
                "segment_name": manifest.get("segment_name"),
                "top_depth": manifest.get("top_depth"),
                "base_depth": manifest.get("base_depth"),
                "depth_unit": manifest.get("depth_unit"),
                "display_contract_version": manifest.get(
                    "display_contract_version"
                ),
                "schema_version": manifest.get("schema_version"),
                "chunks": chunks,
            }

    except (
        OSError,
        KeyError,
        ValueError,
        zipfile.BadZipFile,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to read core display chunk manifest: {exc}",
        ) from exc


@router.get(
    "/wells/{managed_well_id}/core-segment-display-chunk",
    summary="Return one continuous-core display chunk image",
)
def get_core_segment_display_chunk(
    managed_well_id: str,
    product_id: str = Query(..., min_length=1),
    chunk_id: str = Query(..., min_length=1),
) -> Response:
    try:
        record = _service.repository.get_record(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc

    item = next(
        (
            candidate
            for group in record.product_groups
            for candidate in group.items
            if candidate.product_id == product_id
            and candidate.product_subgroup_key == "compound_core_segment"
        ),
        None,
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Core image package not found.",
        )

    provenance = item.provenance if isinstance(item.provenance, dict) else {}
    package_path = Path(str(provenance.get("package_path") or ""))
    if not package_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Core image package asset is missing.",
        )

    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            manifest = json.loads(
                archive.read("manifest.json").decode("utf-8")
            )

            chunks = manifest.get("display_chunks") or []
            chunk = next(
                (
                    candidate
                    for candidate in chunks
                    if str(candidate.get("chunk_id")) == chunk_id
                ),
                None,
            )
            if chunk is None:
                raise KeyError(
                    f"Display chunk not found: {chunk_id}"
                )

            image_filename = str(
                chunk.get("image_filename") or ""
            )
            if not image_filename:
                raise ValueError(
                    f"Display chunk {chunk_id} has no image filename."
                )

            payload = archive.read(image_filename)

            media_type = str(chunk.get("mime_type") or "")
            if not media_type:
                suffix = Path(image_filename).suffix.lower()
                media_type = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                    ".tif": "image/tiff",
                    ".tiff": "image/tiff",
                }.get(suffix, "application/octet-stream")

    except (
        OSError,
        KeyError,
        ValueError,
        zipfile.BadZipFile,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to read core display chunk: {exc}",
        ) from exc

    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=3600, immutable",
        },
    )


@router.get(
    "/wells/{managed_well_id}/downstream-recovery",
    response_model=WmdDownstreamRecoveryStatus,
    summary="Return backend-owned WMD downstream recovery status",
)
def get_wmd_downstream_recovery_status(
    managed_well_id: str,
    product_id: list[str] = Query(default=[]),
) -> WmdDownstreamRecoveryStatus:
    try:
        return _service.get_wmd_downstream_recovery_status(managed_well_id, product_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
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


@router.get(
    "/wells/{managed_well_id}/products/{product_id}/source-file",
    response_class=FileResponse,
    summary="Download the retained source file for one managed product",
)
def download_managed_product_source(
    managed_well_id: str,
    product_id: str,
) -> FileResponse:
    try:
        record = _service.get_well(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc

    product = next(
        (
            item
            for group in record.product_groups
            for item in group.items
            if item.product_id == product_id
        ),
        None,
    )
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed product not found: {product_id}",
        )

    source_reference = next(
        (
            source
            for source in record.source_references
            if source.source_id == product.source_id
            or (
                product.managed_source_uid is not None
                and source.managed_source_uid == product.managed_source_uid
            )
        ),
        None,
    )
    if source_reference is None or not source_reference.original_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Managed product has no retained source file: {product_id}",
        )

    source_path = Path(source_reference.original_path).expanduser().resolve()
    if not source_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retained source file is unavailable: {source_reference.file_name or source_path.name}",
        )

    return FileResponse(
        path=source_path,
        filename=source_reference.file_name or source_path.name,
        media_type="text/csv" if source_path.suffix.lower() == ".csv" else "application/octet-stream",
    )


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

@router.post(
    "/mwd/flush",
    response_model=MwdTransientFlushResponse,
    summary="Atomically flush all transient MWD managed data and reset linked WSI candidates",
)
def flush_mwd_transient_data(
    request: MwdTransientFlushRequest,
) -> MwdTransientFlushResponse:
    try:
        return _mwd_flush_service.flush(request=request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.post(
    "/managed-wells/{well_reference}/purge-reset",
    response_model=ManagedWellPurgeResponse,
    summary="Atomically purge one managed well and reset its linked WSI candidates",
)
def purge_managed_well(
    well_reference: str,
    request: ManagedWellPurgeRequest,
) -> ManagedWellPurgeResponse:
    try:
        return _purge_service.purge_and_reset(
            well_reference=well_reference,
            request=request,
        )
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

