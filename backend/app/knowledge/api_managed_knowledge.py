"""WLV Managed Knowledge Repository read-only API routes (KR-2).

Exposes introspection-only endpoints for the managed KR layer:
  /api/wlv/knowledge/managed/health
  /api/wlv/knowledge/managed/schema
  /api/wlv/knowledge/managed/status-summary

These endpoints are strictly read-only.  No write, approval, or import
endpoints are exposed in KR-2; those are deferred to future KR blocks.

KR-1 endpoints (/api/wlv/knowledge/*) are NOT touched by this module.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .managed_models import KR2_VERSION
from .managed_repository import ManagedKRRepository

router = APIRouter(prefix="/api/wlv/knowledge/managed", tags=["wlv-knowledge-managed"])
_managed_repository = ManagedKRRepository()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ManagedKrHealthResponse(BaseModel):
    """Response contract for /api/wlv/knowledge/managed/health."""

    service: str
    status: str
    mode: str
    kr_version: str
    total_record_count: int
    governed_record_count: int
    evidence_record_count: int
    status_summary: dict[str, int]
    type_summary: dict[str, int]


class ManagedKrSchemaResponse(BaseModel):
    """Response contract for /api/wlv/knowledge/managed/schema."""

    kr_version: str
    record_types: list[dict[str, Any]]
    governance_statuses: dict[str, Any]
    notes: list[str]


class ManagedKrStatusSummaryResponse(BaseModel):
    """Response contract for /api/wlv/knowledge/managed/status-summary."""

    kr_version: str
    total_governed_records: int
    production_eligible_count: int
    seed_count: int
    candidate_count: int
    approved_count: int
    deprecated_count: int
    rejected_count: int
    status_by_type: dict[str, Any]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    response_model=ManagedKrHealthResponse,
    summary="Managed KR health and record counts",
)
def managed_knowledge_health() -> ManagedKrHealthResponse:
    """Return health status and record-count summary for the managed KR.

    Includes per-status and per-record-type breakdowns.
    This endpoint is safe to call at any time with no side effects.
    """
    data = _managed_repository.get_health()
    return ManagedKrHealthResponse(**data)


@router.get(
    "/schema",
    response_model=ManagedKrSchemaResponse,
    summary="Managed KR record type schema and governance status definitions",
)
def managed_knowledge_schema() -> ManagedKrSchemaResponse:
    """Return schema metadata for all managed KR record types.

    Describes:
    - each record type, its purpose, and whether it is governed
    - each governance status value, its production-eligibility, and valid transitions
    - operational notes for future KR management UI consumers
    """
    data = _managed_repository.get_schema()
    return ManagedKrSchemaResponse(**data)


@router.get(
    "/status-summary",
    response_model=ManagedKrStatusSummaryResponse,
    summary="Managed KR governance status breakdown by record type",
)
def managed_knowledge_status_summary() -> ManagedKrStatusSummaryResponse:
    """Return a detailed governance status summary broken down by record type.

    Useful for KR management tooling and monitoring dashboards.
    Candidate records are counted but clearly separated from
    production-eligible (seed + approved) records.
    """
    data = _managed_repository.get_status_summary_response()
    return ManagedKrStatusSummaryResponse(**data)
