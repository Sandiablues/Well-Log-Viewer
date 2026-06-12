"""WLV Managed Knowledge Repository API routes (KR-2 through KR-8).

KR-2 read-only endpoints (unchanged):
  GET  /api/wlv/knowledge/managed/health
  GET  /api/wlv/knowledge/managed/schema
  GET  /api/wlv/knowledge/managed/status-summary

KR-3 import/staging endpoints (unchanged):
  POST /api/wlv/knowledge/managed/import/preview
  POST /api/wlv/knowledge/managed/import/stage

KR-4 governance review endpoints (unchanged):
  GET  /api/wlv/knowledge/managed/records
  GET  /api/wlv/knowledge/managed/records/{record_id}
  POST /api/wlv/knowledge/managed/records/{record_id}/approve
  POST /api/wlv/knowledge/managed/records/{record_id}/reject
  POST /api/wlv/knowledge/managed/records/{record_id}/deprecate
  GET  /api/wlv/knowledge/managed/production-eligible

KR-6 resolution endpoints (unchanged):
  POST /api/wlv/knowledge/resolve/curve
  POST /api/wlv/knowledge/resolve/curves

KR-7 classification endpoint (unchanged):
  POST /api/wlv/knowledge/classify/curves

KR-8 display recommendation endpoint (new):
  POST /api/wlv/knowledge/recommend-display/curves

KR-1 endpoints (/api/wlv/knowledge/*) are NOT touched by this module.

FastAPI dependency injection is used for the managed repository so that
tests can inject isolated ManagedKRRepository instances without affecting
the global singleton.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .governance_service import (
    GovernanceService,
    GovernanceTransitionError,
    RecordNotFoundError,
    _serialize_record,
)
from .import_models import ImportPayload
from .import_staging_service import stage_import_payload
from .import_validation_service import validate_import_payload
from .managed_models import KR2_VERSION, KR3_VERSION, KR4_VERSION, KR5_VERSION
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


# ---------------------------------------------------------------------------
# KR-4 governance dependency
# ---------------------------------------------------------------------------


def get_governance_service(
    repo: ManagedKRRepository = Depends(get_managed_repository),
) -> GovernanceService:
    """Return a GovernanceService wrapping the active managed repository.

    Override in tests via::

        app.dependency_overrides[get_managed_repository] = lambda: fresh_repo
        # get_governance_service derives from get_managed_repository, so
        # overriding the repository is sufficient.
    """
    return GovernanceService(repo)


# ---------------------------------------------------------------------------
# KR-4 response models
# ---------------------------------------------------------------------------


class GovernanceActionRequest(BaseModel):
    """Request body for approve / reject / deprecate actions."""

    actor: str = Field(..., description="Identity of the person or system performing the action")
    reason: Optional[str] = Field(None, description="Reason for the governance action")
    notes: Optional[str] = Field(None, description="Optional free-text reviewer notes")


class GovernanceActionResponse(BaseModel):
    """Response for a successful governance action."""

    ok: bool
    kr_version: str
    record_id: str
    previous_status: str
    new_status: str
    production_eligible: bool
    record: dict[str, Any]


class RecordListResponse(BaseModel):
    """Response for GET /records."""

    kr_version: str
    count: int
    records: list[dict[str, Any]]


class ProductionEligibleResponse(BaseModel):
    """Response for GET /production-eligible."""

    kr_version: str
    count: int
    records: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# KR-4 endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/records",
    response_model=RecordListResponse,
    summary="List managed KR records with optional status/type filtering",
)
def list_managed_records(
    status: Optional[str] = Query(None, description="Filter by governance status"),
    record_type: Optional[str] = Query(None, description="Filter by record type"),
    service: GovernanceService = Depends(get_governance_service),
) -> RecordListResponse:
    """Return governed records.

    Optional query parameters:
    - ``status``: one of seed, candidate, approved, rejected, deprecated
    - ``record_type``: one of curve_definition, alias, display_rule,
      classification_rule, template_rule

    HTTP 422 is returned for unknown status values (via Pydantic/FastAPI).
    """
    from .governance import validate_status

    parsed_status = None
    if status is not None:
        try:
            parsed_status = validate_status(status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    records = service.list_records(status=parsed_status, record_type=record_type)
    return RecordListResponse(
        kr_version=KR4_VERSION,
        count=len(records),
        records=[_serialize_record(r) for r in records],
    )


@router.get(
    "/records/{record_id}",
    response_model=dict,
    summary="Fetch a single managed KR record by ID",
)
def get_managed_record(
    record_id: str,
    service: GovernanceService = Depends(get_governance_service),
) -> dict[str, Any]:
    """Return a single governed record by its record_id.

    HTTP 404 if the record does not exist.
    """
    try:
        record = service.get_record(record_id)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "kr_version": KR4_VERSION,
        "record": _serialize_record(record),
    }


@router.post(
    "/records/{record_id}/approve",
    response_model=GovernanceActionResponse,
    summary="Approve a candidate or seed managed KR record",
)
def approve_managed_record(
    record_id: str,
    body: GovernanceActionRequest,
    service: GovernanceService = Depends(get_governance_service),
) -> GovernanceActionResponse:
    """Approve a candidate or seed record, making it production-eligible.

    Valid transitions: candidate → approved, seed → approved.

    HTTP 404 if the record does not exist.
    HTTP 400 if the transition is not permitted.
    HTTP 422 if the request body is malformed.
    """
    try:
        result = service.approve_record(
            record_id,
            actor=body.actor,
            reason=body.reason,
            notes=body.notes,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GovernanceTransitionError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_transition",
                "record_id": exc.record_id,
                "from_status": exc.from_status.value,
                "to_status": exc.to_status.value,
                "message": str(exc),
            },
        ) from exc
    return GovernanceActionResponse(**result)


@router.post(
    "/records/{record_id}/reject",
    response_model=GovernanceActionResponse,
    summary="Reject a candidate managed KR record",
)
def reject_managed_record(
    record_id: str,
    body: GovernanceActionRequest,
    service: GovernanceService = Depends(get_governance_service),
) -> GovernanceActionResponse:
    """Reject a candidate record.  Rejected records are NOT production-eligible.

    Valid transitions: candidate → rejected.

    HTTP 404 if the record does not exist.
    HTTP 400 if the transition is not permitted.
    HTTP 422 if the request body is malformed.
    """
    reason = body.reason or ""
    try:
        result = service.reject_record(
            record_id,
            actor=body.actor,
            reason=reason,
            notes=body.notes,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GovernanceTransitionError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_transition",
                "record_id": exc.record_id,
                "from_status": exc.from_status.value,
                "to_status": exc.to_status.value,
                "message": str(exc),
            },
        ) from exc
    return GovernanceActionResponse(**result)


@router.post(
    "/records/{record_id}/deprecate",
    response_model=GovernanceActionResponse,
    summary="Deprecate a seed or approved managed KR record",
)
def deprecate_managed_record(
    record_id: str,
    body: GovernanceActionRequest,
    service: GovernanceService = Depends(get_governance_service),
) -> GovernanceActionResponse:
    """Deprecate a seed or approved record.  Deprecated records are NOT production-eligible.

    Valid transitions: seed → deprecated, approved → deprecated.
    candidate → deprecated is NOT permitted.

    HTTP 404 if the record does not exist.
    HTTP 400 if the transition is not permitted.
    HTTP 422 if the request body is malformed.
    """
    reason = body.reason or ""
    try:
        result = service.deprecate_record(
            record_id,
            actor=body.actor,
            reason=reason,
            notes=body.notes,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GovernanceTransitionError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_transition",
                "record_id": exc.record_id,
                "from_status": exc.from_status.value,
                "to_status": exc.to_status.value,
                "message": str(exc),
            },
        ) from exc
    return GovernanceActionResponse(**result)


@router.get(
    "/production-eligible",
    response_model=ProductionEligibleResponse,
    summary="List all production-eligible managed KR records (seed + approved)",
)
def list_production_eligible(
    record_type: Optional[str] = Query(None, description="Filter by record type"),
    service: GovernanceService = Depends(get_governance_service),
) -> ProductionEligibleResponse:
    """Return all records that are production-eligible (status = seed or approved).

    Candidate, rejected, and deprecated records are excluded.

    Optional query parameter:
    - ``record_type``: one of curve_definition, alias, display_rule,
      classification_rule, template_rule
    """
    records = service.list_production_eligible_records(record_type=record_type)
    return ProductionEligibleResponse(
        kr_version=KR4_VERSION,
        count=len(records),
        records=[_serialize_record(r) for r in records],
    )


# ---------------------------------------------------------------------------
# KR-5 storage health endpoint
# ---------------------------------------------------------------------------


class StorageHealthResponse(BaseModel):
    """Response for GET /managed/storage/health (KR-5)."""

    kr_version: str
    storage_enabled: bool
    storage_path: str
    storage_schema_version: str
    persisted_record_count: int
    persisted_evidence_record_count: int


@router.get(
    "/storage/health",
    response_model=StorageHealthResponse,
    summary="KR-5 persistent storage health and record counts",
)
def managed_storage_health(
    repo: ManagedKRRepository = Depends(get_managed_repository),
) -> StorageHealthResponse:
    """Return persistent storage health for the managed KR (KR-5).

    Reports the storage file path, schema version, and count of records
    currently persisted to disk.  Does not include in-memory seed records.
    """
    data = repo.get_storage_health()
    return StorageHealthResponse(**data)


# ---------------------------------------------------------------------------
# KR-6 resolution router (separate prefix: /api/wlv/knowledge)
# ---------------------------------------------------------------------------

from .resolution_service import (  # noqa: E402
    CurveResolveInput,
    CurveResolveResult,
    DisplayRuleResult,
    KnowledgeResolutionService,
    KR6_VERSION,
)

resolve_router = APIRouter(
    prefix="/api/wlv/knowledge",
    tags=["wlv-knowledge-resolution"],
)


# ---------------------------------------------------------------------------
# KR-6 Pydantic request / response models
# ---------------------------------------------------------------------------


class ResolveContextModel(BaseModel):
    """Optional context hints for a resolution request."""

    well_id: Optional[str] = Field(None, description="Well identifier (informational)")
    source: Optional[str] = Field(None, description="Caller / data source identifier")


class CurveResolveRequest(BaseModel):
    """Request body for POST /api/wlv/knowledge/resolve/curve."""

    mnemonic: str = Field(..., description="Curve mnemonic to resolve")
    unit: Optional[str] = Field(None, description="Optional unit hint (supporting evidence only)")
    description: Optional[str] = Field(None, description="Optional description hint")
    context: Optional[ResolveContextModel] = Field(None, description="Optional resolution context")


class DisplayRuleResponse(BaseModel):
    """Display rule sub-object returned when a matching rule exists."""

    scale_type: str
    recommended_min: float
    recommended_max: float
    unit: Optional[str]


class CurveResolveResponse(BaseModel):
    """Response contract for a single mnemonic resolution.

    resolved=True : mnemonic was matched to approved managed knowledge.
    resolved=False: no match; only mnemonic, normalized_mnemonic, and warnings
                    are meaningful.
    """

    kr_version: str
    resolved: bool
    mnemonic: str
    normalized_mnemonic: str
    canonical_curve_id: Optional[str]
    display_name: Optional[str] = None
    family: Optional[str] = None
    product_group: Optional[str] = None
    product_subgroup: Optional[str] = None
    default_unit: Optional[str] = None
    confidence: float
    resolution_source: str
    record_id: Optional[str] = None
    display_rule: Optional[DisplayRuleResponse] = None
    warnings: list[str]


class BatchCurveResolveRequest(BaseModel):
    """Request body for POST /api/wlv/knowledge/resolve/curves."""

    curves: list[CurveResolveRequest] = Field(
        ...,
        description="Ordered list of curve resolution requests",
        min_length=1,
    )


class BatchCurveResolveResponse(BaseModel):
    """Response contract for batch mnemonic resolution."""

    kr_version: str
    count: int
    resolved_count: int
    unresolved_count: int
    results: list[CurveResolveResponse]


# ---------------------------------------------------------------------------
# KR-6 dependency provider
# ---------------------------------------------------------------------------


def get_resolution_service(
    repo: ManagedKRRepository = Depends(get_managed_repository),
) -> KnowledgeResolutionService:
    """Return a KnowledgeResolutionService wrapping the active managed repository.

    Overriding get_managed_repository in tests is sufficient to inject an
    isolated repository into the resolution service.
    """
    return KnowledgeResolutionService(repo)


# ---------------------------------------------------------------------------
# KR-6 helpers
# ---------------------------------------------------------------------------


def _display_rule_to_response(dr: Optional[DisplayRuleResult]) -> Optional[DisplayRuleResponse]:
    if dr is None:
        return None
    return DisplayRuleResponse(
        scale_type=dr.scale_type,
        recommended_min=dr.recommended_min,
        recommended_max=dr.recommended_max,
        unit=dr.unit,
    )


def _result_to_response(result: CurveResolveResult) -> CurveResolveResponse:
    return CurveResolveResponse(
        kr_version=KR6_VERSION,
        resolved=result.resolved,
        mnemonic=result.mnemonic,
        normalized_mnemonic=result.normalized_mnemonic,
        canonical_curve_id=result.canonical_curve_id,
        display_name=result.display_name,
        family=result.family,
        product_group=result.product_group,
        product_subgroup=result.product_subgroup,
        default_unit=result.default_unit,
        confidence=result.confidence,
        resolution_source=result.resolution_source,
        record_id=result.record_id,
        display_rule=_display_rule_to_response(result.display_rule),
        warnings=result.warnings,
    )


def _request_to_input(req: CurveResolveRequest) -> CurveResolveInput:
    ctx: dict = {}
    if req.context is not None:
        ctx = req.context.model_dump()
    return CurveResolveInput(
        mnemonic=req.mnemonic,
        unit=req.unit,
        description=req.description,
        context=ctx,
    )


# ---------------------------------------------------------------------------
# KR-6 endpoints
# ---------------------------------------------------------------------------


@resolve_router.post(
    "/resolve/curve",
    response_model=CurveResolveResponse,
    summary="Resolve a single curve mnemonic to approved managed knowledge (KR-6)",
    status_code=200,
)
def resolve_curve(
    body: CurveResolveRequest,
    service: KnowledgeResolutionService = Depends(get_resolution_service),
) -> CurveResolveResponse:
    """Resolve a single curve mnemonic into a stable backend knowledge contract.

    Uses only production-eligible knowledge (status = seed or approved).
    Candidate, rejected, and deprecated records are always excluded.

    Resolution priority:
      1. Exact approved/seed alias match
      2. Normalized approved/seed alias match
      3. Exact canonical curve ID match

    Returns resolved=True on a match, resolved=False with a warning when no
    approved knowledge matches the input mnemonic.

    This endpoint is offline-capable and side-effect free.
    """
    input_ = _request_to_input(body)
    result = service.resolve_curve(input_)
    return _result_to_response(result)


@resolve_router.post(
    "/resolve/curves",
    response_model=BatchCurveResolveResponse,
    summary="Resolve a batch of curve mnemonics to approved managed knowledge (KR-6)",
    status_code=200,
)
def resolve_curves(
    body: BatchCurveResolveRequest,
    service: KnowledgeResolutionService = Depends(get_resolution_service),
) -> BatchCurveResolveResponse:
    """Resolve a batch of curve mnemonics.

    Input order is strictly preserved in the response.  Each entry is
    independently resolved; one unresolvable mnemonic does not affect others.

    The same exclusion rules apply as the single-curve endpoint:
    candidate, rejected, and deprecated records are never used.

    Returns a batch result with per-entry resolved/unresolved status and
    aggregate counts.
    """
    inputs = [_request_to_input(req) for req in body.curves]
    results = service.resolve_curves(inputs)
    responses = [_result_to_response(r) for r in results]
    resolved_count = sum(1 for r in responses if r.resolved)
    return BatchCurveResolveResponse(
        kr_version=KR6_VERSION,
        count=len(responses),
        resolved_count=resolved_count,
        unresolved_count=len(responses) - resolved_count,
        results=responses,
    )


# ---------------------------------------------------------------------------
# KR-7 classification — imports and models
# ---------------------------------------------------------------------------

from .classification_service import (  # noqa: E402
    ClassificationSource,
    CurveClassificationBatchResult,
    CurveClassificationRequest,
    CurveClassificationResult,
    CurveClassificationService,
    CurveClassifyInput,
    KR7_VERSION,
)


# ---------------------------------------------------------------------------
# KR-7 Pydantic request / response models
# ---------------------------------------------------------------------------


class ClassificationSourceModel(BaseModel):
    """Optional import source context for a classification batch."""

    source_type: str = Field(..., description="Source type (e.g. las_import, dlis_import)")
    source_file: Optional[str] = Field(None, description="Optional source filename")
    import_batch_id: Optional[str] = Field(None, description="Optional import batch ID")


class CurveClassifyRequestItem(BaseModel):
    """A single raw curve to classify within a batch."""

    curve_id: str = Field(..., description="Caller-supplied stable identifier for this curve")
    mnemonic: str = Field(..., description="Curve mnemonic from source file")
    unit: Optional[str] = Field(None, description="Unit from source file (evidence only)")
    description: Optional[str] = Field(None, description="Description from source file (evidence only)")
    source_curve_index: Optional[int] = Field(
        None, description="Zero-based index of the curve in its source file"
    )


class BatchClassifyRequest(BaseModel):
    """Request body for POST /api/wlv/knowledge/classify/curves."""

    well_id: Optional[str] = Field(None, description="Well identifier (informational)")
    source: Optional[ClassificationSourceModel] = Field(
        None, description="Import source context"
    )
    curves: list[CurveClassifyRequestItem] = Field(
        ...,
        description="Ordered list of raw curves to classify",
    )


class DisplayRuleClassifyResponse(BaseModel):
    """Display rule sub-object in a classification result."""

    scale_type: str
    recommended_min: float
    recommended_max: float
    unit: Optional[str]


class CurveClassificationItemResponse(BaseModel):
    """Classification result for a single curve."""

    curve_id: str
    mnemonic: str
    normalized_mnemonic: str
    resolved: bool
    classification_status: str
    source_curve_index: Optional[int]
    canonical_curve_id: Optional[str] = None
    display_name: Optional[str] = None
    family: Optional[str] = None
    product_group: Optional[str] = None
    product_subgroup: Optional[str] = None
    default_unit: Optional[str] = None
    confidence: float
    resolution_source: str
    knowledge_record_id: Optional[str] = None
    display_rule: Optional[DisplayRuleClassifyResponse] = None
    review_required: bool
    warnings: list[str]


class BatchClassifyResponse(BaseModel):
    """Response contract for POST /api/wlv/knowledge/classify/curves."""

    kr_version: str
    well_id: Optional[str]
    source: Optional[ClassificationSourceModel]
    curve_count: int
    classified_count: int
    unclassified_count: int
    review_required_count: int
    classifications: list[CurveClassificationItemResponse]


# ---------------------------------------------------------------------------
# KR-7 dependency provider
# ---------------------------------------------------------------------------


def get_classification_service(
    repo: ManagedKRRepository = Depends(get_managed_repository),
) -> CurveClassificationService:
    """Return a CurveClassificationService backed by the active managed repository.

    Overriding get_managed_repository in tests is sufficient to inject an
    isolated repository into the full service chain.
    """
    resolution_service = KnowledgeResolutionService(repo)
    return CurveClassificationService(resolution_service)


# ---------------------------------------------------------------------------
# KR-7 helpers
# ---------------------------------------------------------------------------


def _display_rule_to_classify_response(
    dr: Optional["DisplayRuleResult"],
) -> Optional[DisplayRuleClassifyResponse]:
    if dr is None:
        return None
    return DisplayRuleClassifyResponse(
        scale_type=dr.scale_type,
        recommended_min=dr.recommended_min,
        recommended_max=dr.recommended_max,
        unit=dr.unit,
    )


def _source_model_to_domain(
    src: Optional[ClassificationSourceModel],
) -> Optional[ClassificationSource]:
    if src is None:
        return None
    return ClassificationSource(
        source_type=src.source_type,
        source_file=src.source_file,
        import_batch_id=src.import_batch_id,
    )


def _domain_source_to_model(
    src: Optional[ClassificationSource],
) -> Optional[ClassificationSourceModel]:
    if src is None:
        return None
    return ClassificationSourceModel(
        source_type=src.source_type,
        source_file=src.source_file,
        import_batch_id=src.import_batch_id,
    )


def _classification_result_to_response(
    result: CurveClassificationResult,
) -> CurveClassificationItemResponse:
    return CurveClassificationItemResponse(
        curve_id=result.curve_id,
        mnemonic=result.mnemonic,
        normalized_mnemonic=result.normalized_mnemonic,
        resolved=result.resolved,
        classification_status=result.classification_status,
        source_curve_index=result.source_curve_index,
        canonical_curve_id=result.canonical_curve_id,
        display_name=result.display_name,
        family=result.family,
        product_group=result.product_group,
        product_subgroup=result.product_subgroup,
        default_unit=result.default_unit,
        confidence=result.confidence,
        resolution_source=result.resolution_source,
        knowledge_record_id=result.knowledge_record_id,
        display_rule=_display_rule_to_classify_response(result.display_rule),
        review_required=result.review_required,
        warnings=result.warnings,
    )


def _batch_result_to_response(
    result: CurveClassificationBatchResult,
) -> BatchClassifyResponse:
    return BatchClassifyResponse(
        kr_version=result.kr_version,
        well_id=result.well_id,
        source=_domain_source_to_model(result.source),
        curve_count=result.curve_count,
        classified_count=result.classified_count,
        unclassified_count=result.unclassified_count,
        review_required_count=result.review_required_count,
        classifications=[
            _classification_result_to_response(c) for c in result.classifications
        ],
    )


# ---------------------------------------------------------------------------
# KR-7 endpoint
# ---------------------------------------------------------------------------


@resolve_router.post(
    "/classify/curves",
    response_model=BatchClassifyResponse,
    summary="Classify a batch of raw imported curves using backend knowledge (KR-7)",
    status_code=200,
)
def classify_curves(
    body: BatchClassifyRequest,
    service: CurveClassificationService = Depends(get_classification_service),
) -> BatchClassifyResponse:
    """Classify a batch of raw imported curves into stable backend-owned identities.

    Accepts raw curve inventory from a well/log import context and returns
    ordered classification results.

    Classification rules:
    - Only production-eligible knowledge (seed + approved) is used.
    - Candidate, rejected, and deprecated records are always excluded.
    - resolved=True  → classification_status="classified"
    - resolved=False → classification_status="unclassified", review_required=True
    - Input order is strictly preserved.
    - Source curve identity (curve_id, source_curve_index) is preserved.

    This endpoint is offline-capable and side-effect free.

    HTTP 200 for both classified and unclassified results.
    HTTP 422 for malformed request bodies.
    """
    domain_curves = [
        CurveClassifyInput(
            curve_id=c.curve_id,
            mnemonic=c.mnemonic,
            unit=c.unit,
            description=c.description,
            source_curve_index=c.source_curve_index,
        )
        for c in body.curves
    ]
    request = CurveClassificationRequest(
        curves=domain_curves,
        well_id=body.well_id,
        source=_source_model_to_domain(body.source),
    )
    result = service.classify_curves(request)
    return _batch_result_to_response(result)


# ---------------------------------------------------------------------------
# KR-8 display recommendation — imports and models
# ---------------------------------------------------------------------------

from .display_recommendation_service import (  # noqa: E402
    CurveDisplayRecommendation,
    CurveRecommendInput,
    DisplayRecommendationBatchResult,
    DisplayRecommendationRequest,
    DisplayRecommendationService,
    KR8_VERSION,
)


# ---------------------------------------------------------------------------
# KR-8 Pydantic request / response models
# ---------------------------------------------------------------------------


class CurveRecommendRequestItem(BaseModel):
    """A single raw curve to receive a display recommendation within a batch."""

    curve_id: str = Field(..., description="Caller-supplied stable identifier for this curve")
    mnemonic: str = Field(..., description="Curve mnemonic from source file")
    unit: Optional[str] = Field(None, description="Unit from source file (evidence only)")
    description: Optional[str] = Field(
        None, description="Description from source file (evidence only)"
    )
    source_curve_index: Optional[int] = Field(
        None, description="Zero-based index of the curve in its source file"
    )


class BatchRecommendRequest(BaseModel):
    """Request body for POST /api/wlv/knowledge/recommend-display/curves."""

    well_id: Optional[str] = Field(None, description="Well identifier (informational)")
    source: Optional[ClassificationSourceModel] = Field(
        None, description="Import source context"
    )
    curves: list[CurveRecommendRequestItem] = Field(
        ...,
        description="Ordered list of raw curves to receive display recommendations",
    )


class CurveRecommendationItemResponse(BaseModel):
    """Display recommendation result for a single curve."""

    curve_id: str
    mnemonic: str
    normalized_mnemonic: str
    canonical_curve_id: Optional[str] = None
    classification_status: str
    recommendation_status: str
    source_curve_index: Optional[int] = None

    # Classification / knowledge fields
    display_name: Optional[str] = None
    product_group: Optional[str] = None
    product_subgroup: Optional[str] = None
    display_family: Optional[str] = None

    # Display rule fields
    scale_type: Optional[str] = None
    recommended_min: Optional[float] = None
    recommended_max: Optional[float] = None
    unit: Optional[str] = None
    preferred_track_group: Optional[str] = None

    review_required: bool
    warnings: list[str]


class BatchRecommendResponse(BaseModel):
    """Response contract for POST /api/wlv/knowledge/recommend-display/curves."""

    kr_version: str
    well_id: Optional[str] = None
    curve_count: int
    recommended_count: int
    unrecommended_count: int
    review_required_count: int
    recommendations: list[CurveRecommendationItemResponse]


# ---------------------------------------------------------------------------
# KR-8 dependency provider
# ---------------------------------------------------------------------------


def get_recommendation_service(
    repo: ManagedKRRepository = Depends(get_managed_repository),
) -> DisplayRecommendationService:
    """Return a DisplayRecommendationService backed by the active managed repository.

    Overriding get_managed_repository in tests is sufficient to inject an
    isolated repository into the full service chain.
    """
    resolution_service = KnowledgeResolutionService(repo)
    classification_service = CurveClassificationService(resolution_service)
    return DisplayRecommendationService(classification_service)


# ---------------------------------------------------------------------------
# KR-8 helpers
# ---------------------------------------------------------------------------


def _recommendation_to_response(
    rec: CurveDisplayRecommendation,
) -> CurveRecommendationItemResponse:
    return CurveRecommendationItemResponse(
        curve_id=rec.curve_id,
        mnemonic=rec.mnemonic,
        normalized_mnemonic=rec.normalized_mnemonic,
        canonical_curve_id=rec.canonical_curve_id,
        classification_status=rec.classification_status,
        recommendation_status=rec.recommendation_status,
        source_curve_index=rec.source_curve_index,
        display_name=rec.display_name,
        product_group=rec.product_group,
        product_subgroup=rec.product_subgroup,
        display_family=rec.display_family,
        scale_type=rec.scale_type,
        recommended_min=rec.recommended_min,
        recommended_max=rec.recommended_max,
        unit=rec.unit,
        preferred_track_group=rec.preferred_track_group,
        review_required=rec.review_required,
        warnings=rec.warnings,
    )


def _batch_recommend_result_to_response(
    result: DisplayRecommendationBatchResult,
) -> BatchRecommendResponse:
    return BatchRecommendResponse(
        kr_version=result.kr_version,
        well_id=result.well_id,
        curve_count=result.curve_count,
        recommended_count=result.recommended_count,
        unrecommended_count=result.unrecommended_count,
        review_required_count=result.review_required_count,
        recommendations=[_recommendation_to_response(r) for r in result.recommendations],
    )


# ---------------------------------------------------------------------------
# KR-8 endpoint
# ---------------------------------------------------------------------------


@resolve_router.post(
    "/recommend-display/curves",
    response_model=BatchRecommendResponse,
    summary="Return backend display recommendations for a batch of curves (KR-8)",
    status_code=200,
)
def recommend_display_curves(
    body: BatchRecommendRequest,
    service: DisplayRecommendationService = Depends(get_recommendation_service),
) -> BatchRecommendResponse:
    """Return backend-owned display recommendations for a batch of raw curves.

    Classifies each curve via KR-7, applies approved/seed display rules, and
    returns ordered display recommendations.

    Recommendation rules:
    - classified + approved/seed display rule found → recommendation_status="recommended"
    - classified + no display rule                  → recommendation_status="review_required"
    - unclassified                                  → recommendation_status="unrecommended",
                                                       review_required=True
    - Only production-eligible records (seed + approved) are used.
    - Candidate, rejected, and deprecated display rules never produce recommendations.
    - Input order is strictly preserved.
    - Source curve identity (curve_id, source_curve_index) is preserved.

    This endpoint is offline-capable and side-effect free.  It does not mutate
    storage, alter WDV state, alter MDP state, or build track templates.

    HTTP 200 for all valid requests (including all-unrecommended results).
    HTTP 422 for malformed request bodies.
    """
    domain_curves = [
        CurveRecommendInput(
            curve_id=c.curve_id,
            mnemonic=c.mnemonic,
            unit=c.unit,
            description=c.description,
            source_curve_index=c.source_curve_index,
        )
        for c in body.curves
    ]
    request = DisplayRecommendationRequest(
        curves=domain_curves,
        well_id=body.well_id,
        source=_source_model_to_domain(body.source),
    )
    result = service.recommend_display(request)
    return _batch_recommend_result_to_response(result)
