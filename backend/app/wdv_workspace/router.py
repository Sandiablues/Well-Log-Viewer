"""Canonical WDV workspace aggregate API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.inventory.canonical_identity_resolver import CanonicalIdentityResolutionError
from app.inventory.repository import ManagedWellNotFoundError

from .models import WdvCanonicalWorkspace, WdvWorkspaceInvariantError
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
