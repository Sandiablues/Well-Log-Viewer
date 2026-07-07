"""Canonical WDV viewer-package API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.identity.wdv_viewer_package_v21 import WdvCanonicalViewerPackage
from app.inventory.canonical_identity_resolver import CanonicalIdentityResolutionError
from app.inventory.repository import ManagedWellNotFoundError
from app.wells.canonical_viewer_package_service import CanonicalViewerPackageService
from app.wells.canonical_wdv_metadata_contract import (
    CanonicalWdvMetadataService,
    WdvMetadataContract,
)

router = APIRouter(
    prefix="/api/wlv/v2/viewer-packages",
    tags=["wlv-canonical-viewer-package"],
)


def get_service() -> CanonicalViewerPackageService:
    return CanonicalViewerPackageService()


@router.get("/{managed_well_uid}", response_model=WdvCanonicalViewerPackage)
def get_viewer_package(
    managed_well_uid: str,
    service: CanonicalViewerPackageService = Depends(get_service),
) -> WdvCanonicalViewerPackage:
    try:
        return service.generate(managed_well_uid)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (CanonicalIdentityResolutionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/{managed_well_uid}/metadata",
    response_model=WdvMetadataContract,
)
def get_wdv_metadata(
    managed_well_uid: str,
) -> WdvMetadataContract:
    return CanonicalWdvMetadataService().get(managed_well_uid)
