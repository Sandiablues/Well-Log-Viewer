"""HTTP command/query boundary for WDV-to-WBV publication."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.wbv.models import WbvCurveOverlayRenderContract

from .models import (
    WbvOverlayPackage,
    WbvOverlayPackageList,
    WbvPackageLifecycleRequest,
    WbvPublishAsNewRequest,
    WbvPublishPreview,
    WbvPublishPreviewRequest,
    WbvPresentationOverridesUpdateRequest,
    WbvUpdateExistingRequest,
    WbvUpdateExistingResult,
    WbvUpdatePreview,
)
from .repository import WbvOverlayPackageNotFound
from .service import WbvOverlayPublicationService

router = APIRouter(prefix="/api/wlv/wbv/publications", tags=["wlv-wbv-publications"])
_service = WbvOverlayPublicationService()


def get_service():
    return _service


class WbvPackageActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool


@router.post("/wells/{managed_well_uid}/preview", response_model=WbvPublishPreview)
def preview_publication(managed_well_uid: str, request: WbvPublishPreviewRequest, service=Depends(get_service)):
    try:
        return service.preview(managed_well_uid, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/wells/{managed_well_uid}/packages", response_model=WbvOverlayPackage, status_code=201)
def publish_as_new(managed_well_uid: str, request: WbvPublishAsNewRequest, service=Depends(get_service)):
    try:
        return service.publish_as_new(managed_well_uid, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/wells/{managed_well_uid}/packages", response_model=WbvOverlayPackageList)
def list_packages(
    managed_well_uid: str,
    include_archived: bool = Query(default=False),
    service=Depends(get_service),
):
    try:
        return service.list_packages(managed_well_uid, include_archived=include_archived)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/wells/{managed_well_uid}/packages/{package_uid}", response_model=WbvOverlayPackage)
def get_package(managed_well_uid: str, package_uid: str, service=Depends(get_service)):
    try:
        return service.get_package(managed_well_uid, package_uid)
    except WbvOverlayPackageNotFound as exc:
        raise HTTPException(status_code=404, detail=f"WBV overlay package not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/wells/{managed_well_uid}/packages/{package_uid}/update-preview",
    response_model=WbvUpdatePreview,
)
def preview_package_update(managed_well_uid: str, package_uid: str, service=Depends(get_service)):
    try:
        return service.preview_update(managed_well_uid, package_uid)
    except WbvOverlayPackageNotFound as exc:
        raise HTTPException(status_code=404, detail=f"WBV overlay package not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put(
    "/wells/{managed_well_uid}/packages/{package_uid}",
    response_model=WbvUpdateExistingResult,
)
def update_existing_package(
    managed_well_uid: str,
    package_uid: str,
    request: WbvUpdateExistingRequest,
    service=Depends(get_service),
):
    try:
        return service.update_existing(managed_well_uid, package_uid, request)
    except WbvOverlayPackageNotFound as exc:
        raise HTTPException(status_code=404, detail=f"WBV overlay package not found: {exc.args[0]}") from exc
    except ValueError as exc:
        message = str(exc)
        status = 409 if message.startswith("Stale package revision") else 422
        raise HTTPException(status_code=status, detail=message) from exc


@router.put("/wells/{managed_well_uid}/packages/{package_uid}/active", response_model=WbvOverlayPackage)
def set_package_active(managed_well_uid: str, package_uid: str, request: WbvPackageActivationRequest, service=Depends(get_service)):
    try:
        return service.set_active(managed_well_uid, package_uid, request.active)
    except WbvOverlayPackageNotFound as exc:
        raise HTTPException(status_code=404, detail=f"WBV overlay package not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put(
    "/wells/{managed_well_uid}/packages/{package_uid}/lifecycle",
    response_model=WbvOverlayPackage,
)
def change_package_lifecycle(
    managed_well_uid: str,
    package_uid: str,
    request: WbvPackageLifecycleRequest,
    service=Depends(get_service),
):
    try:
        return service.change_lifecycle(managed_well_uid, package_uid, request)
    except WbvOverlayPackageNotFound as exc:
        raise HTTPException(status_code=404, detail=f"WBV overlay package not found: {exc.args[0]}") from exc
    except ValueError as exc:
        message = str(exc)
        status = 409 if message.startswith("Stale package revision") else 422
        raise HTTPException(status_code=status, detail=message) from exc


@router.delete(
    "/wells/{managed_well_uid}/packages/{package_uid}",
    status_code=204,
)
def delete_package(
    managed_well_uid: str,
    package_uid: str,
    expected_package_revision: int,
    service=Depends(get_service),
):
    try:
        service.delete_package(
            managed_well_uid,
            package_uid,
            expected_package_revision=expected_package_revision,
        )
    except WbvOverlayPackageNotFound as exc:
        raise HTTPException(status_code=404, detail=f"WBV overlay package not found: {exc.args[0]}") from exc
    except ValueError as exc:
        message = str(exc)
        status = 409 if message.startswith("Stale package revision") else 422
        raise HTTPException(status_code=status, detail=message) from exc
    return None


@router.put(
    "/wells/{managed_well_uid}/packages/{package_uid}/presentation",
    response_model=WbvOverlayPackage,
)
def update_package_presentation(
    managed_well_uid: str,
    package_uid: str,
    request: WbvPresentationOverridesUpdateRequest,
    service=Depends(get_service),
):
    try:
        return service.update_presentation_overrides(managed_well_uid, package_uid, request)
    except WbvOverlayPackageNotFound as exc:
        raise HTTPException(status_code=404, detail=f"WBV overlay package not found: {exc.args[0]}") from exc
    except ValueError as exc:
        message = str(exc)
        status = 409 if message.startswith("Stale package revision") else 422
        raise HTTPException(status_code=status, detail=message) from exc


@router.get(
    "/wells/{managed_well_uid}/packages/{package_uid}/render-package",
    response_model=WbvCurveOverlayRenderContract,
)
def get_published_render_package(managed_well_uid: str, package_uid: str, service=Depends(get_service)):
    try:
        return service.get_render_package(managed_well_uid, package_uid)
    except WbvOverlayPackageNotFound as exc:
        raise HTTPException(status_code=404, detail=f"WBV overlay package not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
