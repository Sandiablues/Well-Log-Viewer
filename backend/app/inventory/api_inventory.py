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

router = APIRouter(prefix="/api/wlv/inventory", tags=["wlv-inventory"])
_service = ManagedWellInventoryService()
_curve_sample_service = CurveSampleService(repository=_service.repository)
_purge_service = ManagedWellPurgeService(repository=_service.repository)
_mwd_flush_service = MwdTransientFlushService(repository=_service.repository)
_selected_delete_service = SelectedManagedDataDeleteService(repository=_service.repository)


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

