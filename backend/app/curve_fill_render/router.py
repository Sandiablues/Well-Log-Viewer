from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .models import CurveFillRenderPackage
from .service import CurveFillRenderPackageService

router = APIRouter(
    prefix="/api/wlv/v2/wdv/curve-fill-render-packages",
    tags=["wlv-wdv-curve-fill-render-package"],
)


def get_service() -> CurveFillRenderPackageService:
    return CurveFillRenderPackageService()


@router.get("/{managed_well_uid}", response_model=CurveFillRenderPackage)
def get_curve_fill_render_package(
    managed_well_uid: str,
    service: CurveFillRenderPackageService = Depends(get_service),
) -> CurveFillRenderPackage:
    try:
        return service.get_render_package(managed_well_uid)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
