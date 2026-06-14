"""FastAPI router for KR-backed WDV layout preset recommendations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .models import WdvLayoutPresetListResponse, WdvLayoutPresetRecommendationResponse
from .service import WdvLayoutPresetService

router = APIRouter(prefix="/api/wlv/wdv/layout-presets", tags=["wlv-wdv-layout-presets"])
_service = WdvLayoutPresetService()


def get_layout_preset_service() -> WdvLayoutPresetService:
    """Dependency provider for tests and future service injection."""

    return _service


@router.get(
    "",
    response_model=WdvLayoutPresetListResponse,
    summary="List approved KR-backed WDV layout presets",
)
def list_layout_presets(
    service: WdvLayoutPresetService = Depends(get_layout_preset_service),
) -> WdvLayoutPresetListResponse:
    return service.list_presets()


@router.get(
    "/",
    response_model=WdvLayoutPresetListResponse,
    include_in_schema=False,
)
def list_layout_presets_slash(
    service: WdvLayoutPresetService = Depends(get_layout_preset_service),
) -> WdvLayoutPresetListResponse:
    return service.list_presets()


@router.get(
    "/recommend",
    response_model=WdvLayoutPresetRecommendationResponse,
    summary="Recommend a KR-backed WDV layout preset for one managed well",
)
def recommend_layout_preset(
    well_id: str = Query(..., min_length=1, description="Managed well ID"),
    preset_id: str = Query(
        "basic_triple_combo_openhole",
        min_length=1,
        description="KR template_rule.template_key; compatibility aliases such as triple_combo are accepted.",
    ),
    service: WdvLayoutPresetService = Depends(get_layout_preset_service),
) -> WdvLayoutPresetRecommendationResponse:
    try:
        return service.recommend_preset(managed_well_id=well_id, preset_id=preset_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
