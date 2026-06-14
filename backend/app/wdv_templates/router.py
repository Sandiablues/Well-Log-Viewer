"""API routes for approved KR-backed WDV template contracts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.inventory.repository import ManagedWellNotFoundError
from backend.app.knowledge.api_managed_knowledge import get_managed_repository
from backend.app.knowledge.managed_repository import ManagedKRRepository

from .models import (
    WdvTemplateDetailEnvelope,
    WdvTemplateListResponse,
    WdvTemplateRecommendationEnvelope,
    WdvTemplateRecommendationRequest,
    WdvTemplateReferenceSummaryResponse,
)
from .recommendation_service import WdvTemplateRecommendationService
from .service import WdvTemplateNotFoundError, WdvTemplateService

router = APIRouter(prefix="/api/wlv/wdv/templates", tags=["wlv-wdv-templates"])


def get_wdv_template_service(
    repo: ManagedKRRepository = Depends(get_managed_repository),
) -> WdvTemplateService:
    """Return the backend-owned WDV template service."""
    return WdvTemplateService(repository=repo)


def get_wdv_template_recommendation_service(
    repo: ManagedKRRepository = Depends(get_managed_repository),
) -> WdvTemplateRecommendationService:
    """Return the backend-owned WDV template recommendation service."""
    return WdvTemplateRecommendationService(repository=repo)


@router.get("", response_model=WdvTemplateListResponse)
def list_wdv_templates(
    service: WdvTemplateService = Depends(get_wdv_template_service),
) -> WdvTemplateListResponse:
    """List approved KR-backed WDV preview templates."""
    return service.list_templates()


@router.get("/reference-summary", response_model=WdvTemplateReferenceSummaryResponse)
def wdv_template_reference_summary(
    service: WdvTemplateService = Depends(get_wdv_template_service),
) -> WdvTemplateReferenceSummaryResponse:
    """Return approved KR record counts and source references for WDV templates."""
    return service.reference_summary()


@router.post("/recommendations/evaluate", response_model=WdvTemplateRecommendationEnvelope)
def evaluate_wdv_template_recommendations(
    request: WdvTemplateRecommendationRequest,
    service: WdvTemplateRecommendationService = Depends(get_wdv_template_recommendation_service),
) -> WdvTemplateRecommendationEnvelope:
    """Rank approved KR templates against supplied WDV-loaded curve items.

    This returns a recommendation contract only. It does not apply templates or
    mutate WDV state.
    """
    return service.recommend_from_request(request)


@router.get("/recommendations/{managed_well_id}", response_model=WdvTemplateRecommendationEnvelope)
def recommend_wdv_templates_for_managed_well(
    managed_well_id: str,
    workflow_context: str | None = Query(default=None),
    include_ineligible: bool = Query(default=True),
    service: WdvTemplateRecommendationService = Depends(get_wdv_template_recommendation_service),
) -> WdvTemplateRecommendationEnvelope:
    """Rank approved KR templates against the currently loaded managed well package.

    This route reads the backend-owned WDV viewer-package contract for the
    managed well and returns recommendation data only. It does not apply a
    template, populate tracks, or mutate inventory/WDV state.
    """
    try:
        return service.recommend_for_managed_well(
            managed_well_id,
            workflow_context=workflow_context,
            include_ineligible=include_ineligible,
        )
    except ManagedWellNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "managed_well_not_found", "managed_well_id": managed_well_id},
        ) from exc


@router.get("/{template_key}", response_model=WdvTemplateDetailEnvelope)
def get_wdv_template(
    template_key: str,
    service: WdvTemplateService = Depends(get_wdv_template_service),
) -> WdvTemplateDetailEnvelope:
    """Return the full approved KR-backed contract for one WDV template."""
    try:
        return service.get_template(template_key)
    except WdvTemplateNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "wdv_template_not_found", "template_key": template_key},
        ) from exc
