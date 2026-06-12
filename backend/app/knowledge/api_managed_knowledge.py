"""WLV Managed Knowledge Repository API routes (KR-2 + KR-3).

KR-2 read-only endpoints (unchanged):
  GET  /api/wlv/knowledge/managed/health
  GET  /api/wlv/knowledge/managed/schema
  GET  /api/wlv/knowledge/managed/status-summary

KR-3 import/staging endpoints (new):
  POST /api/wlv/knowledge/managed/import/preview
  POST /api/wlv/knowledge/managed/import/stage

The ``/preview`` endpoint validates a payload and returns a projected
candidate record count WITHOUT persisting anything.

The ``/stage`` endpoint validates a payload and, if valid, creates
candidate managed records in the in-memory repository.  Staged records
are NOT production-eligible and do NOT affect KR-1 endpoints.

No approval / promotion endpoint is added in KR-3.
KR-1 endpoints (/api/wlv/knowledge/*) are NOT touched by this module.

FastAPI dependency injection is used for the managed repository so that
tests can inject isolated ManagedKRRepository instances for KR-3 import
tests without affecting the global singleton.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .import_models import ImportPayload
from .import_staging_service import stage_import_payload
from .import_validation_service import validate_import_payload
from .managed_models import KR2_VERSION, KR3_VERSION
from .managed_repository import ManagedKRRepository

router = APIRouter(prefix="/api/wlv/knowledge/managed", tags=["wlv-knowledge-managed"])

# Module-level singleton — the single in-memory managed repository instance.
# Tests may override via FastAPI's dependency_overrides mechanism.
_managed_repository: ManagedKRRepository = ManagedKRRepository()


# ---------------------------------------------------------------------------
# Dependency provider
# ---------------------------------------------------------------------------


def get_managed_repository() -> ManagedKRRepository:
    """Return the active managed repository.

    Override in tests via::

        app.dependency_overrides[get_managed_repository] = lambda: fresh_repo
    """
    return _managed_repository


# ---------------------------------------------------------------------------
# KR-2 response models (unchanged)
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
# KR-3 response models
# ---------------------------------------------------------------------------


class ValidationIssueResponse(BaseModel):
    """A single validation error or warning."""

    code: str
    message: str
    path: str
    severity: str


class ImportPreviewResponse(BaseModel):
    """Response for POST /import/preview.

    Returned for both valid and invalid payloads.
    HTTP 200 is used for semantic validation failures; HTTP 400 is reserved
    for malformed / unparseable payloads (handled by FastAPI/Pydantic).
    """

    valid: bool
    mode: str = "preview"
    staged: bool = False
    kr_version: str = KR3_VERSION
    error_count: int
    warning_count: int
    candidate_record_count: int
    evidence_record_count: int
    record_type_counts: dict[str, int]
    errors: list[ValidationIssueResponse]
    warnings: list[ValidationIssueResponse]


class ImportStageResponse(BaseModel):
    """Response for POST /import/stage.

    On validation failure: valid=False, staged=False, errors populated.
    On success: valid=True, staged=True, import_batch_id and record_ids populated.
    """

    valid: bool
    mode: str = "stage"
    staged: bool
    kr_version: str = KR3_VERSION
    error_count: int
    warning_count: int
    import_batch_id: str | None = None
    candidate_record_count: int
    evidence_record_count: int
    record_type_counts: dict[str, int]
    record_ids: list[str]
    errors: list[ValidationIssueResponse]
    warnings: list[ValidationIssueResponse]


# ---------------------------------------------------------------------------
# KR-2 read-only GET routes (unchanged)
# ---------------------------------------------------------------------------


@router.get(
    "/health",
    response_model=ManagedKrHealthResponse,
    summary="Managed KR health and record counts",
)
def managed_knowledge_health(
    repo: ManagedKRRepository = Depends(get_managed_repository),
) -> ManagedKrHealthResponse:
    """Return health status and record-count summary for the managed KR.

    Includes per-status and per-record-type breakdowns.
    This endpoint is safe to call at any time with no side effects.
    """
    data = repo.get_health()
    return ManagedKrHealthResponse(**data)


@router.get(
    "/schema",
    response_model=ManagedKrSchemaResponse,
    summary="Managed KR record type schema and governance status definitions",
)
def managed_knowledge_schema(
    repo: ManagedKRRepository = Depends(get_managed_repository),
) -> ManagedKrSchemaResponse:
    """Return schema metadata for all managed KR record types."""
    data = repo.get_schema()
    return ManagedKrSchemaResponse(**data)


@router.get(
    "/status-summary",
    response_model=ManagedKrStatusSummaryResponse,
    summary="Managed KR governance status breakdown by record type",
)
def managed_knowledge_status_summary(
    repo: ManagedKRRepository = Depends(get_managed_repository),
) -> ManagedKrStatusSummaryResponse:
    """Return a detailed governance status summary broken down by record type."""
    data = repo.get_status_summary_response()
    return ManagedKrStatusSummaryResponse(**data)


# ---------------------------------------------------------------------------
# KR-3 import / staging POST routes
# ---------------------------------------------------------------------------


def _issues_to_response(issues: list) -> list[ValidationIssueResponse]:
    """Convert ValidationIssue dataclass instances to response models."""
    return [
        ValidationIssueResponse(
            code=issue.code,
            message=issue.message,
            path=issue.path,
            severity=issue.severity,
        )
        for issue in issues
    ]


@router.post(
    "/import/preview",
    response_model=ImportPreviewResponse,
    summary="Validate a KR import payload without staging (dry-run preview)",
    status_code=200,
)
def import_preview(
    payload: ImportPayload,
    repo: ManagedKRRepository = Depends(get_managed_repository),
) -> ImportPreviewResponse:
    """Validate a structured import payload and return a candidate record preview.

    This endpoint is SIDE-EFFECT FREE.  It runs the full validation pass
    and returns projected record counts, errors, and warnings.  Nothing is
    staged or persisted.

    Use this to check an import payload before committing it via /stage.

    HTTP 200 is returned for both valid and semantically-invalid payloads.
    HTTP 422 is returned by FastAPI for malformed/unparseable JSON.

    Returns:
        ImportPreviewResponse with valid=True/False, projected counts, and
        full error/warning lists.
    """
    result = validate_import_payload(payload, repo)
    return ImportPreviewResponse(
        valid=result.valid,
        error_count=result.error_count,
        warning_count=result.warning_count,
        candidate_record_count=result.candidate_record_count,
        evidence_record_count=result.evidence_record_count,
        record_type_counts=result.record_type_counts,
        errors=_issues_to_response(result.errors),
        warnings=_issues_to_response(result.warnings),
    )


@router.post(
    "/import/stage",
    response_model=ImportStageResponse,
    summary="Validate and stage a KR import payload as candidate records",
    status_code=200,
)
def import_stage(
    payload: ImportPayload,
    repo: ManagedKRRepository = Depends(get_managed_repository),
) -> ImportStageResponse:
    """Validate an import payload; if valid, stage it as candidate managed records.

    Staged records have status=candidate and are NOT production-eligible.
    They will NOT appear in KR-1 production endpoints or be consumed by the
    classifier layer.

    If validation fails, the repository is NOT mutated.  Errors are returned
    in the response body with staged=False.

    No approval or promotion endpoint is added in KR-3; staged candidate
    records remain as candidates until a future KR-4 review block.

    HTTP 200 is returned for both valid and invalid payloads (semantic
    validation failure is not a protocol error).
    HTTP 422 is returned by FastAPI for malformed/unparseable JSON.

    Returns:
        ImportStageResponse with staged=True/False, import_batch_id,
        record_ids, and full error/warning lists.
    """
    result = validate_import_payload(payload, repo)

    if not result.valid:
        return ImportStageResponse(
            valid=False,
            staged=False,
            import_batch_id=None,
            error_count=result.error_count,
            warning_count=result.warning_count,
            candidate_record_count=result.candidate_record_count,
            evidence_record_count=result.evidence_record_count,
            record_type_counts=result.record_type_counts,
            record_ids=[],
            errors=_issues_to_response(result.errors),
            warnings=_issues_to_response(result.warnings),
        )

    staging = stage_import_payload(payload, repo)

    return ImportStageResponse(
        valid=True,
        staged=True,
        import_batch_id=staging.import_batch_id,
        error_count=0,
        warning_count=result.warning_count,
        candidate_record_count=staging.candidate_record_count,
        evidence_record_count=staging.evidence_record_count,
        record_type_counts=staging.record_type_counts,
        record_ids=staging.record_ids,
        errors=[],
        warnings=_issues_to_response(result.warnings),
    )
