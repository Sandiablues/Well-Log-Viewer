"""3D Wellbore Viewer API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.inventory.repository import ManagedInventoryStoreError, ManagedWellNotFoundError

from .models import (
    WbvDisplayLayerFilesContract,
    WbvFormationTopProductsContract,
    WbvLithologyProductsContract,
    WbvCompletionProductsContract,
    WbvDisplayLayerConfigurationContract,
    WbvDisplayLayerConfigurationRequest,
    WbvCurveOverlayNormalizationContract,
    WbvCurveOverlayNormalizationRequest,
    WbvCurveOverlayProductsContract,
    WbvCurveOverlayRenderContract,
    WbvDisplaySettingsContract,
    WbvDisplaySettingsRequest,
    WbvSessionContract,
    WbvSetActiveWellRequest,
    WbvSurveyQaqcContract,
    WbvSetActiveTrajectoryRequest,
    WbvSetActiveTrajectoryResponse,
    WbvTrajectoryListContract,
    WbvViewerPackageContract,
)
from .service import WbvService
from .interaction import (
    WbvAoiTransferResult, WbvInteractionService, WbvInteractionState,
    WbvIntervalPickRequest, WbvPointSelectionRequest, WbvSelectionModeRequest,
)
from .interaction_domain.contracts import (
    WbvAoiTransferResultV2, WbvInteractionModeRequestV2, WbvInteractionObservationV2,
    WbvInteractionStateV2, WbvTrackSessionCommandV2,
)
from .interaction_domain.service import WbvInteractionDomainService

router = APIRouter(prefix="/api/wlv/wbv", tags=["wlv-wbv"])
_service = WbvService()
_interaction_service = WbvInteractionService(
    _service.repository, trajectory_package_provider=_service.get_viewer_package
)
_interaction_domain_service = WbvInteractionDomainService(
    _service.repository, trajectory_package_provider=_service.get_viewer_package
)


@router.get("/health", summary="WBV backend contract health")
def health() -> dict[str, object]:
    return {"ok": True, "service": "wlv-wbv", "scope": "wbv_backend_contract"}


@router.get("/session", response_model=WbvSessionContract, summary="Fetch the independently selected active WBV session")
def get_wbv_session() -> WbvSessionContract:
    try:
        return _service.get_session()
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.put(
    "/session/active-well",
    response_model=WbvSessionContract,
    summary="Set the active WBV managed well without changing WDV selection",
)
def set_wbv_active_well(request: WbvSetActiveWellRequest) -> WbvSessionContract:
    try:
        return _service.set_active_well(request.managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get(
    "/wells/{managed_well_id}/display-layer-files",
    response_model=WbvDisplayLayerFilesContract,
    summary="List WMD-registered display-layer files for a managed well",
)
def get_wbv_display_layer_files(managed_well_id: str) -> WbvDisplayLayerFilesContract:
    try:
        return _service.get_display_layer_files(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get(
    "/wells/{managed_well_id}/formation-top-products",
    response_model=WbvFormationTopProductsContract,
    summary="List MWD formation-top products and managed top rows for WBV",
)
def get_wbv_formation_top_products(managed_well_id: str) -> WbvFormationTopProductsContract:
    try:
        return _service.get_formation_top_products(managed_well_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/wells/{managed_well_id}/lithology-products",
    response_model=WbvLithologyProductsContract,
    summary="List MWD reviewed lithology products and intervals for WBV",
)
def get_wbv_lithology_products(managed_well_id: str) -> WbvLithologyProductsContract:
    try:
        return _service.get_lithology_products(managed_well_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/wells/{managed_well_id}/completion-products",
    response_model=WbvCompletionProductsContract,
    summary="List MWD reviewed completion products and KR-governed components for WBV",
)
def get_wbv_completion_products(managed_well_id: str) -> WbvCompletionProductsContract:
    try:
        return _service.get_completion_products(managed_well_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/wells/{managed_well_id}/curve-overlay-products",
    response_model=WbvCurveOverlayProductsContract,
    summary="List WMD curve products and managed curves for WBV selection",
)
def get_wbv_curve_overlay_products(managed_well_id: str) -> WbvCurveOverlayProductsContract:
    try:
        return _service.get_curve_overlay_products(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Managed well not found: {exc.args[0]}") from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post(
    "/wells/{managed_well_id}/curve-overlays/normalize",
    response_model=WbvCurveOverlayNormalizationContract,
    summary="Resolve backend-governed WBV normalization for selected managed curves",
)
def normalize_wbv_curve_overlays(
    managed_well_id: str, request: WbvCurveOverlayNormalizationRequest
) -> WbvCurveOverlayNormalizationContract:
    try:
        return _service.normalize_curve_overlays(managed_well_id, request.curve_product_ids)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Managed well or curve not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get(
    "/wells/{managed_well_id}/curve-overlays/render-package",
    response_model=WbvCurveOverlayRenderContract,
    summary="Fetch backend-normalized WBV curve geometry samples",
)
def get_wbv_curve_overlay_render_package(managed_well_id: str) -> WbvCurveOverlayRenderContract:
    try:
        return _service.get_curve_overlay_render_package(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Managed well not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get(
    "/wells/{managed_well_id}/display-layer-configuration",
    response_model=WbvDisplayLayerConfigurationContract,
    summary="Fetch backend-owned WBV display-layer configuration",
)
def get_wbv_display_layer_configuration(managed_well_id: str) -> WbvDisplayLayerConfigurationContract:
    try:
        return _service.get_display_layer_configuration(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Managed well not found: {exc.args[0]}") from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.put(
    "/wells/{managed_well_id}/display-layer-configuration",
    response_model=WbvDisplayLayerConfigurationContract,
    summary="Persist backend-owned WBV display-layer configuration",
)
def put_wbv_display_layer_configuration(
    managed_well_id: str, request: WbvDisplayLayerConfigurationRequest
) -> WbvDisplayLayerConfigurationContract:
    try:
        return _service.set_display_layer_configuration(managed_well_id, request.layers, request.tracks, request.track_spacing)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Managed well not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ManagedInventoryStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get(
    "/wells/{managed_well_id}/survey-qaqc",
    response_model=WbvSurveyQaqcContract,
    summary="Inspect backend-derived directional survey QAQC for a managed well",
)
def get_wbv_survey_qaqc(managed_well_id: str) -> WbvSurveyQaqcContract:
    try:
        return _service.get_survey_qaqc(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Managed well not found: {exc.args[0]}",
        ) from exc
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
            request.canonical_or_legacy_reference,
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


@router.put(
    "/wells/{managed_well_id}/display-settings",
    response_model=WbvDisplaySettingsContract,
    summary="Persist backend-owned WBV display settings for a managed well",
)
def set_wbv_display_settings(
    managed_well_id: str, request: WbvDisplaySettingsRequest
) -> WbvDisplaySettingsContract:
    try:
        return _service.set_display_depth_unit(managed_well_id, request.depth_unit)
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


@router.get("/wells/{managed_well_id}/interaction", response_model=WbvInteractionState)
def get_wbv_interaction(managed_well_id: str) -> WbvInteractionState:
    try:
        return _interaction_service.get(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Managed well not found: {exc.args[0]}") from exc


@router.put("/wells/{managed_well_id}/interaction/mode", response_model=WbvInteractionState)
def set_wbv_interaction_mode(managed_well_id: str, request: WbvSelectionModeRequest) -> WbvInteractionState:
    try:
        return _interaction_service.set_mode(managed_well_id, request.mode)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Managed well not found: {exc.args[0]}") from exc


@router.put("/wells/{managed_well_id}/interaction/point", response_model=WbvInteractionState)
def set_wbv_selected_point(managed_well_id: str, request: WbvPointSelectionRequest) -> WbvInteractionState:
    try:
        return _interaction_service.select_point(managed_well_id, request.point)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Managed well not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/wells/{managed_well_id}/interaction/interval/pick", response_model=WbvInteractionState)
def pick_wbv_interval_point(managed_well_id: str, request: WbvIntervalPickRequest) -> WbvInteractionState:
    try:
        return _interaction_service.pick_interval(managed_well_id, request.point)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Managed well not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/wells/{managed_well_id}/interaction/interval", response_model=WbvInteractionState)
def clear_wbv_interval(managed_well_id: str) -> WbvInteractionState:
    try:
        return _interaction_service.clear_interval(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Managed well not found: {exc.args[0]}") from exc


@router.post("/wells/{managed_well_id}/interaction/interval/send-to-wdv", response_model=WbvAoiTransferResult)
def send_wbv_interval_to_wdv(managed_well_id: str) -> WbvAoiTransferResult:
    try:
        return _interaction_service.send_interval_to_wdv(managed_well_id)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Managed well not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# WBV Interaction Domain v2 — isolated backend-owned projection/state contract.
@router.get("/wells/{managed_well_id}/interaction-v2", response_model=WbvInteractionStateV2)
def get_wbv_interaction_v2(managed_well_id: str) -> WbvInteractionStateV2:
    try:
        return _interaction_domain_service.get(managed_well_id)
    except (ManagedWellNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.put("/wells/{managed_well_id}/interaction-v2/mode", response_model=WbvInteractionStateV2)
def set_wbv_interaction_mode_v2(managed_well_id: str, request: WbvInteractionModeRequestV2) -> WbvInteractionStateV2:
    try:
        return _interaction_domain_service.set_mode(managed_well_id, request)
    except (ManagedWellNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/wells/{managed_well_id}/interaction-v2/observe", response_model=WbvInteractionStateV2)
def observe_wbv_interaction_v2(managed_well_id: str, request: WbvInteractionObservationV2) -> WbvInteractionStateV2:
    try:
        return _interaction_domain_service.observe(managed_well_id, request)
    except (ManagedWellNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/wells/{managed_well_id}/interaction-v2/tracking/start", response_model=WbvInteractionStateV2)
def start_wbv_tracking_v2(managed_well_id: str, request: WbvTrackSessionCommandV2) -> WbvInteractionStateV2:
    try:
        return _interaction_domain_service.start_tracking(managed_well_id, request)
    except (ManagedWellNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/wells/{managed_well_id}/interaction-v2/tracking/update", response_model=WbvInteractionStateV2)
def update_wbv_tracking_v2(managed_well_id: str, request: WbvTrackSessionCommandV2) -> WbvInteractionStateV2:
    try:
        return _interaction_domain_service.update_tracking(managed_well_id, request)
    except (ManagedWellNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/wells/{managed_well_id}/interaction-v2/tracking/commit", response_model=WbvInteractionStateV2)
def commit_wbv_tracking_v2(managed_well_id: str, request: WbvTrackSessionCommandV2) -> WbvInteractionStateV2:
    try:
        return _interaction_domain_service.commit_tracking(managed_well_id, request)
    except (ManagedWellNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/wells/{managed_well_id}/interaction-v2/tracking/cancel", response_model=WbvInteractionStateV2)
def cancel_wbv_tracking_v2(managed_well_id: str, request: WbvTrackSessionCommandV2) -> WbvInteractionStateV2:
    try:
        return _interaction_domain_service.cancel_tracking(managed_well_id, request)
    except (ManagedWellNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete("/wells/{managed_well_id}/interaction-v2/interval", response_model=WbvInteractionStateV2)
def clear_wbv_interval_v2(managed_well_id: str, expected_revision: int | None = None) -> WbvInteractionStateV2:
    try:
        return _interaction_domain_service.clear_interval(managed_well_id, expected_revision)
    except (ManagedWellNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/wells/{managed_well_id}/interaction-v2/interval/send-to-wdv", response_model=WbvAoiTransferResultV2)
def send_wbv_interval_to_wdv_v2(managed_well_id: str) -> WbvAoiTransferResultV2:
    try:
        return _interaction_domain_service.send_interval_to_wdv(managed_well_id)
    except (ManagedWellNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
