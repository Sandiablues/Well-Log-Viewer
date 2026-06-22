"""API routes for backend-owned WDV layout/session state."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .models import (
    WdvSessionLayoutClearRequest,
    WdvSessionLayoutPutRequest,
    WdvSessionLayoutStateResponse,
    WdvSessionLayoutStateView,
)
from .service import WdvSessionLayoutStateService

router = APIRouter(prefix="/api/wlv/wdv/sessions", tags=["wlv-wdv-session-layout"])


def get_wdv_session_layout_service() -> WdvSessionLayoutStateService:
    return WdvSessionLayoutStateService()


@router.get("/{managed_well_id}/layout", response_model=WdvSessionLayoutStateView)
def get_wdv_session_layout(
    managed_well_id: str,
    service: WdvSessionLayoutStateService = Depends(get_wdv_session_layout_service),
) -> WdvSessionLayoutStateView:
    """Return the backend-owned active WDV layout/session for one managed well."""
    return service.get_layout(managed_well_id)


@router.put("/{managed_well_id}/layout", response_model=WdvSessionLayoutStateView)
def put_wdv_session_layout(
    managed_well_id: str,
    request: WdvSessionLayoutPutRequest,
    service: WdvSessionLayoutStateService = Depends(get_wdv_session_layout_service),
) -> WdvSessionLayoutStateView:
    """Replace the backend-owned active WDV layout/session for one managed well."""
    try:
        return service.put_layout(managed_well_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": "invalid_wdv_layout_state", "message": str(exc)}) from exc


@router.post("/{managed_well_id}/layout/clear", response_model=WdvSessionLayoutStateView)
def clear_wdv_session_layout(
    managed_well_id: str,
    request: WdvSessionLayoutClearRequest | None = None,
    service: WdvSessionLayoutStateService = Depends(get_wdv_session_layout_service),
) -> WdvSessionLayoutStateView:
    """Clear the backend-owned active WDV layout/session for one managed well."""
    reason = request.reason if request else "user_requested_clear"
    return service.clear_layout(managed_well_id, reason=reason)
