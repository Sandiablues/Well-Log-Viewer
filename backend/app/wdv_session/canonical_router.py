"""Versioned canonical WDV session API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.identity.wdv_contract_v2 import WdvCanonicalSession
from .canonical_command_service import CanonicalWdvCommandService
from .canonical_service import CanonicalWdvSessionService
from .view_contract import WdvCanonicalSessionView, project_canonical_session_view

router = APIRouter(prefix="/api/wlv/v2/wdv/sessions", tags=["wlv-wdv-canonical-session"])


class CanonicalSessionClearRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = "user_requested_clear"


def get_service() -> CanonicalWdvSessionService:
    return CanonicalWdvCommandService().session_service


@router.get("/{managed_well_uid}", response_model=WdvCanonicalSessionView)
def get_session(
    managed_well_uid: str,
    service: CanonicalWdvSessionService = Depends(get_service),
) -> WdvCanonicalSessionView:
    try:
        return project_canonical_session_view(service.get_session(managed_well_uid))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/{managed_well_uid}", response_model=WdvCanonicalSessionView)
def put_session(
    managed_well_uid: str,
    session: WdvCanonicalSession,
    service: CanonicalWdvSessionService = Depends(get_service),
) -> WdvCanonicalSessionView:
    if session.managed_well_uid != managed_well_uid:
        raise HTTPException(status_code=422, detail="Path and payload managed_well_uid must match")
    try:
        return project_canonical_session_view(service.put_session(session))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{managed_well_uid}/clear", response_model=WdvCanonicalSessionView)
def clear_session(
    managed_well_uid: str,
    request: CanonicalSessionClearRequest | None = None,
    service: CanonicalWdvSessionService = Depends(get_service),
) -> WdvCanonicalSessionView:
    try:
        return project_canonical_session_view(service.clear_session(
            managed_well_uid,
            (request.reason if request else "user_requested_clear"),
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

