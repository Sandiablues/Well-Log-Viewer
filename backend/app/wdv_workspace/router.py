"""Canonical WDV workspace aggregate API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.inventory.canonical_identity_resolver import CanonicalIdentityResolutionError
from app.inventory.repository import ManagedWellNotFoundError
from app.wdv_session.canonical_service import (
    CanonicalSessionRevisionConflict,
    CanonicalViewRevisionConflict,
)
from app.wdv_session.view_contract import project_canonical_session_view

from .models import (
    WdvCanonicalWorkspace,
    WdvWorkspaceInvariantError,
    WdvSaveWorkspaceSnapshotRequest,
    WdvPersistCommittedViewRequest,
    WdvRestoreWorkspaceSnapshotRequest,
    WdvCommitViewStateRequest,
)
from .service import CanonicalWdvWorkspaceService

router = APIRouter(
    prefix="/api/wlv/v2/wdv/workspaces",
    tags=["wlv-wdv-canonical-workspace"],
)


def get_service() -> CanonicalWdvWorkspaceService:
    return CanonicalWdvWorkspaceService()


@router.get("/{managed_well_uid}", response_model=WdvCanonicalWorkspace)
def get_workspace(
    managed_well_uid: str,
    service: CanonicalWdvWorkspaceService = Depends(get_service),
) -> WdvCanonicalWorkspace:
    try:
        return service.get_workspace(managed_well_uid)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        CanonicalIdentityResolutionError,
        WdvWorkspaceInvariantError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc



@router.get("/{managed_well_uid}/committed-view-state")
def get_committed_view_state(
    managed_well_uid: str,
    service: CanonicalWdvWorkspaceService = Depends(get_service),
):
    try:
        return service.get_committed_view_state(managed_well_uid)
    except (
        CanonicalIdentityResolutionError,
        WdvWorkspaceInvariantError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{managed_well_uid}/committed-view-state")
def commit_view_state(
    managed_well_uid: str,
    request: WdvCommitViewStateRequest,
    service: CanonicalWdvWorkspaceService = Depends(get_service),
):
    try:
        return service.commit_view_state(
            managed_well_uid,
            expected_session_revision=request.expected_session_revision,
            expected_view_revision=request.expected_view_revision,
            view_state=request.view_state,
        )
    except (CanonicalSessionRevisionConflict, CanonicalViewRevisionConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (
        CanonicalIdentityResolutionError,
        WdvWorkspaceInvariantError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{managed_well_uid}/recovery-state")
def get_recovery_state(
    managed_well_uid: str,
    service: CanonicalWdvWorkspaceService = Depends(get_service),
):
    try:
        return service.get_recovery_state(managed_well_uid)
    except (
        CanonicalIdentityResolutionError,
        WdvWorkspaceInvariantError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{managed_well_uid}/recovery-state")
def save_recovery_state(
    managed_well_uid: str,
    request: WdvPersistCommittedViewRequest,
    service: CanonicalWdvWorkspaceService = Depends(get_service),
):
    try:
        return service.save_recovery_state_from_committed_view(
            managed_well_uid,
            expected_revision=request.expected_revision,
            expected_view_revision=request.expected_view_revision,
        )
    except (CanonicalSessionRevisionConflict, CanonicalViewRevisionConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (
        CanonicalIdentityResolutionError,
        WdvWorkspaceInvariantError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{managed_well_uid}/saved-snapshot")
def get_saved_snapshot(
    managed_well_uid: str,
    service: CanonicalWdvWorkspaceService = Depends(get_service),
):
    try:
        return service.get_snapshot(managed_well_uid)
    except (
        CanonicalIdentityResolutionError,
        WdvWorkspaceInvariantError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{managed_well_uid}/saved-snapshot")
def save_snapshot(
    managed_well_uid: str,
    request: WdvPersistCommittedViewRequest,
    service: CanonicalWdvWorkspaceService = Depends(get_service),
):
    try:
        return service.save_snapshot_from_committed_view(
            managed_well_uid,
            expected_revision=request.expected_revision,
            expected_view_revision=request.expected_view_revision,
        )
    except (CanonicalSessionRevisionConflict, CanonicalViewRevisionConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (
        CanonicalIdentityResolutionError,
        WdvWorkspaceInvariantError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{managed_well_uid}/saved-snapshot/restore")
def restore_snapshot(
    managed_well_uid: str,
    request: WdvRestoreWorkspaceSnapshotRequest,
    service: CanonicalWdvWorkspaceService = Depends(get_service),
):
    try:
        result = service.restore_snapshot(
            managed_well_uid,
            expected_revision=request.expected_revision,
        )
        return {
            **result,
            "session": project_canonical_session_view(result["session"]),
        }
    except CanonicalSessionRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (
        CanonicalIdentityResolutionError,
        WdvWorkspaceInvariantError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

