"""API route for deterministic backend-owned curve-fill geometry."""

from fastapi import APIRouter

from .models import CurveFillResolveRequest, CurveFillResolveResponse
from .service import CurveFillResolutionService

router = APIRouter(prefix="/api/wlv/wdv/curve-fill", tags=["wlv-curve-fill"])
_service = CurveFillResolutionService()


@router.post("/resolve", response_model=CurveFillResolveResponse)
def resolve_curve_fill(request: CurveFillResolveRequest) -> CurveFillResolveResponse:
    return _service.resolve(request)
