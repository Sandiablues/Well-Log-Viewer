"""Shared canvas API router (Phase 5A).

Exposes profile, activation, binding, and session resolution through:

  GET  /api/wlv/v2/wdv/shared-canvas/profiles
  GET  /api/wlv/v2/wdv/shared-canvas/profiles/{profile_uid}
  GET  /api/wlv/v2/wdv/shared-canvas/profiles/{profile_uid}/revisions
  GET  /api/wlv/v2/wdv/shared-canvas/revisions/{profile_revision_uid}
  GET  /api/wlv/v2/wdv/shared-canvas/scopes/{scope_type}/{scope_uid}/active-revision
  POST /api/wlv/v2/wdv/shared-canvas/scopes/{scope_type}/{scope_uid}/activate
  GET  /api/wlv/v2/wdv/shared-canvas/bindings/{managed_well_uid}/{profile_revision_uid}
  POST /api/wlv/v2/wdv/shared-canvas/bindings/{managed_well_uid}/{profile_revision_uid}
  PATCH /api/wlv/v2/wdv/shared-canvas/bindings/{binding_uid}/slots/{slot_uid}
  GET  /api/wlv/v2/wdv/shared-canvas/workspaces/{managed_well_uid}

Runtime rules:
  - GET /workspaces is read-only; no profile, binding, or session mutation.
  - No writes to canonical_sessions_v2_1.json or session_layouts.json.
  - No implicit rebinding or migration.
  - Cross-well curve leakage rejected at 422.
  - Stale bindings rejected at 409.
  - Revision conflicts rejected at 409.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .binding_models import BindingStatus, WellCanvasBinding, WellCanvasSlotBinding
from .binding_repository import WellCanvasBindingRevisionConflict
from .binding_service import (
    CrossWellCurveError,
    SlotValidationError,
    WellBindingService,
)
from .models import SharedCanvasActivation, SharedCanvasProfile, SharedCanvasProfileRevision
from .repository import SharedCanvasProfileNotFound
from .resolution_service import (
    ArchivedProfileResolutionError,
    CanvasResolutionService,
    MissingActiveProfileError,
    MissingBindingError,
    StaleBindingError,
)
from .service import SharedCanvasArchivedError, SharedCanvasProfileService
from .session_models import ResolvedWdvCanvasSession


# ---------------------------------------------------------------------------
# Module-level service instances (replaced in tests for isolation)
# ---------------------------------------------------------------------------

_profile_svc: SharedCanvasProfileService | None = None
_binding_svc: WellBindingService | None = None
_resolution_svc: CanvasResolutionService | None = None


def _get_profile_svc() -> SharedCanvasProfileService:
    return _profile_svc or SharedCanvasProfileService()


def _get_binding_svc() -> WellBindingService:
    return _binding_svc or WellBindingService()


def _get_resolution_svc() -> CanvasResolutionService:
    return _resolution_svc or CanvasResolutionService()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/api/wlv/v2/wdv/shared-canvas",
    tags=["wlv-wdv-shared-canvas"],
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ActivateRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_revision_uid: str
    activated_by: str = "api"


class CreateBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_uid: str
    profile_revision_number: int = Field(ge=0)
    created_by: str = "api"


class UpdateSlotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    binding_status: BindingStatus
    managed_curve_uid: str | None = None
    binding_source: Literal["auto_resolved", "user_explicit", "system"] = "user_explicit"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str | None = None
    user_override: bool = False
    updated_by: str = "api"


# ---------------------------------------------------------------------------
# Profile and revision reads
# ---------------------------------------------------------------------------

@router.get("/profiles", response_model=list[SharedCanvasProfile])
def list_profiles(
    include_archived: bool = False,
    svc: SharedCanvasProfileService = Depends(_get_profile_svc),
) -> list[SharedCanvasProfile]:
    return svc.list_profiles(include_archived=include_archived)


@router.get("/profiles/{profile_uid}", response_model=SharedCanvasProfile)
def get_profile(
    profile_uid: str,
    svc: SharedCanvasProfileService = Depends(_get_profile_svc),
) -> SharedCanvasProfile:
    try:
        return svc.get_profile(profile_uid)
    except SharedCanvasProfileNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/profiles/{profile_uid}/revisions",
    response_model=list[SharedCanvasProfileRevision],
)
def list_revisions(
    profile_uid: str,
    svc: SharedCanvasProfileService = Depends(_get_profile_svc),
) -> list[SharedCanvasProfileRevision]:
    try:
        svc.get_profile(profile_uid)  # 404 if profile absent
    except SharedCanvasProfileNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return svc.list_revisions(profile_uid)


@router.get("/revisions/{profile_revision_uid}", response_model=SharedCanvasProfileRevision)
def get_revision(
    profile_revision_uid: str,
    svc: SharedCanvasProfileService = Depends(_get_profile_svc),
) -> SharedCanvasProfileRevision:
    try:
        return svc.get_revision(profile_revision_uid)
    except SharedCanvasProfileNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

@router.get(
    "/scopes/{scope_type}/{scope_uid}/active-revision",
    response_model=SharedCanvasProfileRevision,
)
def get_active_revision(
    scope_type: str,
    scope_uid: str,
    svc: SharedCanvasProfileService = Depends(_get_profile_svc),
) -> SharedCanvasProfileRevision:
    revision = svc.get_active_revision(scope_type=scope_type, scope_uid=scope_uid)
    if revision is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active profile revision for scope ({scope_type!r}, {scope_uid!r})",
        )
    return revision


@router.post(
    "/scopes/{scope_type}/{scope_uid}/activate",
    response_model=SharedCanvasActivation,
)
def activate_revision(
    scope_type: str,
    scope_uid: str,
    body: ActivateRevisionRequest,
    svc: SharedCanvasProfileService = Depends(_get_profile_svc),
) -> SharedCanvasActivation:
    try:
        return svc.activate_revision(
            body.profile_revision_uid,
            scope_type=scope_type,
            scope_uid=scope_uid,
            activated_by=body.activated_by,
        )
    except SharedCanvasProfileNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SharedCanvasArchivedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Well binding reads and updates
# ---------------------------------------------------------------------------

@router.get(
    "/bindings/{managed_well_uid}/{profile_revision_uid}",
    response_model=WellCanvasBinding,
)
def get_binding(
    managed_well_uid: str,
    profile_revision_uid: str,
    svc: WellBindingService = Depends(_get_binding_svc),
) -> WellCanvasBinding:
    binding = svc.get_binding_for_well_and_revision(managed_well_uid, profile_revision_uid)
    if binding is None:
        raise HTTPException(
            status_code=404,
            detail=f"No binding for well {managed_well_uid!r} "
                   f"and revision {profile_revision_uid!r}",
        )
    return binding


@router.post(
    "/bindings/{managed_well_uid}/{profile_revision_uid}",
    response_model=WellCanvasBinding,
    status_code=201,
)
def create_binding(
    managed_well_uid: str,
    profile_revision_uid: str,
    body: CreateBindingRequest,
    svc: WellBindingService = Depends(_get_binding_svc),
) -> WellCanvasBinding:
    return svc.create_binding(
        managed_well_uid=managed_well_uid,
        profile_uid=body.profile_uid,
        profile_revision_uid=profile_revision_uid,
        profile_revision_number=body.profile_revision_number,
        created_by=body.created_by,
    )


@router.patch(
    "/bindings/{binding_uid}/slots/{slot_uid}",
    response_model=WellCanvasBinding,
)
def update_slot_binding(
    binding_uid: str,
    slot_uid: str,
    body: UpdateSlotRequest,
    svc: WellBindingService = Depends(_get_binding_svc),
) -> WellCanvasBinding:
    try:
        return svc.update_slot_binding(
            binding_uid=binding_uid,
            expected_revision=body.expected_revision,
            slot_uid=slot_uid,
            binding_status=body.binding_status,
            managed_curve_uid=body.managed_curve_uid,
            binding_source=body.binding_source,
            confidence=body.confidence,
            reason=body.reason,
            user_override=body.user_override,
            updated_by=body.updated_by,
        )
    except WellCanvasBindingRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SlotValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CrossWellCurveError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Resolved session
# ---------------------------------------------------------------------------

@router.get(
    "/workspaces/{managed_well_uid}",
    response_model=ResolvedWdvCanvasSession,
)
def get_resolved_session(
    managed_well_uid: str,
    scope_type: str = Query(..., description="Activation scope type"),
    scope_uid: str = Query(..., description="Activation scope UID"),
    svc: CanvasResolutionService = Depends(_get_resolution_svc),
) -> ResolvedWdvCanvasSession:
    """Resolve the active shared canvas for one well.

    Read-only.  Does not mutate profile, binding, or any session store.
    Returns the full resolved DTO with per-slot binding state and scale labels.
    """
    try:
        return svc.resolve(
            managed_well_uid=managed_well_uid,
            scope_type=scope_type,
            scope_uid=scope_uid,
        )
    except MissingActiveProfileError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MissingBindingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StaleBindingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ArchivedProfileResolutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CrossWellCurveError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
