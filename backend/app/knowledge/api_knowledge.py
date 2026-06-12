"""WLV Knowledge Repository API routes (KR-1).

Exposes read-only backend-owned knowledge contracts:
  /api/wlv/knowledge/health
  /api/wlv/knowledge/product-groups
  /api/wlv/knowledge/curve-definitions
  /api/wlv/knowledge/display-rules
  /api/wlv/knowledge/templates

Routes are intentionally thin; all logic lives in the repository layer.
"""

from __future__ import annotations

from fastapi import APIRouter

from .models import (
    KrCurveDefinitionsResponse,
    KrDisplayRulesResponse,
    KrHealthResponse,
    KrProductGroupsResponse,
    KrTemplatesResponse,
)
from .repository import KnowledgeRepository

router = APIRouter(prefix="/api/wlv/knowledge", tags=["wlv-knowledge"])
_repository = KnowledgeRepository()


@router.get(
    "/health",
    response_model=KrHealthResponse,
    summary="WLV Knowledge Repository health",
)
def knowledge_health() -> KrHealthResponse:
    return _repository.get_health()


@router.get(
    "/product-groups",
    response_model=KrProductGroupsResponse,
    summary="Backend-owned product groups and ordered subgroups",
)
def knowledge_product_groups() -> KrProductGroupsResponse:
    return _repository.get_product_groups()


@router.get(
    "/curve-definitions",
    response_model=KrCurveDefinitionsResponse,
    summary="Backend-owned canonical curve definitions",
)
def knowledge_curve_definitions() -> KrCurveDefinitionsResponse:
    return _repository.get_curve_definitions()


@router.get(
    "/display-rules",
    response_model=KrDisplayRulesResponse,
    summary="Backend-owned curve display rules",
)
def knowledge_display_rules() -> KrDisplayRulesResponse:
    return _repository.get_display_rules()


@router.get(
    "/templates",
    response_model=KrTemplatesResponse,
    summary="Backend-owned viewer template seeds (KR-1: empty)",
)
def knowledge_templates() -> KrTemplatesResponse:
    return _repository.get_templates()
