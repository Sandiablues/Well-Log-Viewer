"""API routes for approved KR-backed WDV template contracts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.knowledge.api_managed_knowledge import get_managed_repository
from backend.app.knowledge.managed_repository import ManagedKRRepository

from .models import (
    WdvTemplateDetailEnvelope,
    WdvTemplateListResponse,
    WdvTemplateReferenceSummaryResponse,
)
from .service import WdvTemplateNotFoundError, WdvTemplateService

router = APIRouter(prefix="/api/wlv/wdv/templates", tags=["wlv-wdv-templates"])


def get_wdv_template_service(
    repo: ManagedKRRepository = Depends(get_managed_repository),
) -> WdvTemplateService:
    """Return the backend-owned WDV template service."""
    return WdvTemplateService(repository=repo)


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
