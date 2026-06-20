"""Versioned canonical curve-sample API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.identity.wdv_contract_v2 import WdvCurveSampleRequest, WdvCurveSampleResponse
from app.inventory.canonical_curve_sample_service import CanonicalCurveSampleService
from app.inventory.canonical_identity_resolver import CanonicalIdentityResolutionError
from app.inventory.curve_sample_service import CurveSampleServiceError
from app.inventory.repository import ManagedWellNotFoundError

router = APIRouter(prefix="/api/wlv/v2/curve-samples", tags=["wlv-canonical-curve-samples"])


def get_service() -> CanonicalCurveSampleService:
    return CanonicalCurveSampleService()


@router.post("", response_model=WdvCurveSampleResponse)
def get_curve_samples(
    request: WdvCurveSampleRequest,
    service: CanonicalCurveSampleService = Depends(get_service),
) -> WdvCurveSampleResponse:
    try:
        return service.get_curve_samples(request)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (CanonicalIdentityResolutionError, CurveSampleServiceError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
