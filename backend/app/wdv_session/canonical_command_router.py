"""Canonical backend-owned WDV session command API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.identity.wdv_contract_v2 import WdvCanonicalSession
from app.inventory.canonical_identity_resolver import CanonicalIdentityResolutionError
from app.inventory.repository import ManagedWellNotFoundError
from app.wdv_session.canonical_command_service import (
    CanonicalWdvCommandError,
    CanonicalWdvCommandService,
)
from app.wdv_session.canonical_commands import (
    AddCurveAssignmentCommand,
    BootstrapCurveAssignmentCommand,
    CreateConfiguredTrackCommand,
    CreateTrackCommand,
    ClearCanvasCommand,
    RemoveCurveAssignmentCommand,
    RemoveTrackCommand,
    MoveCurveAssignmentCommand,
    ReorderCurveAssignmentsCommand,
    ReorderTracksCommand,
    ResetCurveTrackWidthsCommand,
    SelectTrackCommand,
    UpdateCurveAssignmentCommand,
    UpdateTrackCommand,
)
from app.wdv_session.canonical_service import (
    CanonicalSessionCommandReplayConflict,
    CanonicalSessionRevisionConflict,
)
from app.wdv_workspace.models import WdvWorkspaceInvariantError

router = APIRouter(
    prefix="/api/wlv/v2/wdv/session-commands",
    tags=["wlv-wdv-canonical-session-commands"],
)


def get_service() -> CanonicalWdvCommandService:
    return CanonicalWdvCommandService()


def _translate(call):
    try:
        return call()
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CanonicalSessionRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CanonicalSessionCommandReplayConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (
        CanonicalWdvCommandError,
        CanonicalIdentityResolutionError,
        WdvWorkspaceInvariantError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{managed_well_uid}/tracks", response_model=WdvCanonicalSession)
def create_track(
    managed_well_uid: str,
    command: CreateTrackCommand,
    service: CanonicalWdvCommandService = Depends(get_service),
) -> WdvCanonicalSession:
    return _translate(lambda: service.create_track(managed_well_uid, command))


@router.post(
    "/{managed_well_uid}/tracks/configured",
    response_model=WdvCanonicalSession,
)
def create_configured_track(
    managed_well_uid: str,
    command: CreateConfiguredTrackCommand,
    service: CanonicalWdvCommandService = Depends(get_service),
) -> WdvCanonicalSession:
    return _translate(
        lambda: service.create_configured_track(managed_well_uid, command)
    )


@router.post(
    "/{managed_well_uid}/tracks/reset-curve-widths",
    response_model=WdvCanonicalSession,
)
def reset_curve_track_widths(
    managed_well_uid: str,
    command: ResetCurveTrackWidthsCommand,
    service: CanonicalWdvCommandService = Depends(get_service),
) -> WdvCanonicalSession:
    return _translate(
        lambda: service.reset_curve_track_widths(managed_well_uid, command)
    )



@router.post(
    "/{managed_well_uid}/tracks/clear",
    response_model=WdvCanonicalSession,
)
def clear_canvas(
    managed_well_uid: str,
    command: ClearCanvasCommand,
    service: CanonicalWdvCommandService = Depends(get_service),
) -> WdvCanonicalSession:
    return _translate(lambda: service.clear_canvas(managed_well_uid, command))


@router.post("/{managed_well_uid}/tracks/remove", response_model=WdvCanonicalSession)
def remove_track(
    managed_well_uid: str,
    command: RemoveTrackCommand,
    service: CanonicalWdvCommandService = Depends(get_service),
) -> WdvCanonicalSession:
    return _translate(lambda: service.remove_track(managed_well_uid, command))


@router.post(
    "/{managed_well_uid}/assignments/bootstrap",
    response_model=WdvCanonicalSession,
)
def bootstrap_assignment(
    managed_well_uid: str,
    command: BootstrapCurveAssignmentCommand,
    service: CanonicalWdvCommandService = Depends(get_service),
) -> WdvCanonicalSession:
    return _translate(
        lambda: service.bootstrap_assignment(managed_well_uid, command)
    )


@router.post("/{managed_well_uid}/assignments", response_model=WdvCanonicalSession)
def add_assignment(
    managed_well_uid: str,
    command: AddCurveAssignmentCommand,
    service: CanonicalWdvCommandService = Depends(get_service),
) -> WdvCanonicalSession:
    return _translate(lambda: service.add_assignment(managed_well_uid, command))


@router.post("/{managed_well_uid}/assignments/remove", response_model=WdvCanonicalSession)
def remove_assignment(
    managed_well_uid: str,
    command: RemoveCurveAssignmentCommand,
    service: CanonicalWdvCommandService = Depends(get_service),
) -> WdvCanonicalSession:
    return _translate(lambda: service.remove_assignment(managed_well_uid, command))


@router.post("/{managed_well_uid}/assignments/reorder", response_model=WdvCanonicalSession)
def reorder_assignments(
    managed_well_uid: str,
    command: ReorderCurveAssignmentsCommand,
    service: CanonicalWdvCommandService = Depends(get_service),
) -> WdvCanonicalSession:
    return _translate(lambda: service.reorder_assignments(managed_well_uid, command))


@router.post("/{managed_well_uid}/selection", response_model=WdvCanonicalSession)
def select_track(
    managed_well_uid: str,
    command: SelectTrackCommand,
    service: CanonicalWdvCommandService = Depends(get_service),
) -> WdvCanonicalSession:
    return _translate(lambda: service.select_track(managed_well_uid, command))


@router.post("/{managed_well_uid}/tracks/update", response_model=WdvCanonicalSession)
def update_track(
    managed_well_uid: str,
    command: UpdateTrackCommand,
    service: CanonicalWdvCommandService = Depends(get_service),
) -> WdvCanonicalSession:
    return _translate(lambda: service.update_track(managed_well_uid, command))


@router.post("/{managed_well_uid}/tracks/reorder", response_model=WdvCanonicalSession)
def reorder_tracks(
    managed_well_uid: str,
    command: ReorderTracksCommand,
    service: CanonicalWdvCommandService = Depends(get_service),
) -> WdvCanonicalSession:
    return _translate(lambda: service.reorder_tracks(managed_well_uid, command))


@router.post("/{managed_well_uid}/assignments/update", response_model=WdvCanonicalSession)
def update_assignment(
    managed_well_uid: str,
    command: UpdateCurveAssignmentCommand,
    service: CanonicalWdvCommandService = Depends(get_service),
) -> WdvCanonicalSession:
    return _translate(
        lambda: service.update_assignment(managed_well_uid, command)
    )


@router.post("/{managed_well_uid}/assignments/move", response_model=WdvCanonicalSession)
def move_assignment(
    managed_well_uid: str,
    command: MoveCurveAssignmentCommand,
    service: CanonicalWdvCommandService = Depends(get_service),
) -> WdvCanonicalSession:
    return _translate(lambda: service.move_assignment(managed_well_uid, command))
