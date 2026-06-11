"""
SBLT-1 through SBLT-7: FastAPI router for the Seismic Bulk Loading Tool.

Routes:
    POST /api/sblt/sessions                                          — create a session
    GET  /api/sblt/sessions/{session_id}                             — retrieve a session
    POST /api/sblt/sessions/{session_id}/validate                    — SBLT-2 schema validation
    POST /api/sblt/sessions/{session_id}/normalize                   — SBLT-3 row normalization
    POST /api/sblt/sessions/{session_id}/validate-paths              — SBLT-4 path validation
    POST /api/sblt/sessions/{session_id}/extract-segy-header-evidence — SBLT-5
    POST /api/sblt/sessions/{session_id}/build-review-package        — SBLT-6
    POST /api/sblt/sessions/{session_id}/apply-review-decisions      — SBLT-7

Ownership: backend SBLT service.
Frontend: not involved.
MSI: not touched.
Source Intake: not touched.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.seismic_bulk_loader.sblt_session_service import (
    SBLTNotFoundError,
    SBLTValidationError,
    create_session_from_loadsheet,
    get_session,
    validate_session,
    normalize_session,
    validate_session_paths,
    extract_segy_header_evidence,
    build_review_package,
    apply_review_decisions,
)


router = APIRouter(prefix="/api/sblt", tags=["sblt"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CreateSessionRequest(BaseModel):
    # Optional at the Pydantic level so a missing or null field produces a
    # controlled SBLTValidationError (HTTP 400) rather than a FastAPI 422.
    # The service validates that the value is non-empty.
    loadsheet_path: str | None = None
    base_path: str | None = None
    profile: str = "default"


class FieldDecisionInput(BaseModel):
    """A single per-field review decision within a row decision input."""
    field: str
    decision: str                   # One of VALID_USER_DECISION_TYPES from sblt_review_decisions
    supplied_value: Any | None = None
    notes: str | None = None


class RowDecisionInput(BaseModel):
    """Per-row review decision input for SBLT-7."""
    row_id: str
    row_action: str = "proceed"     # "proceed" | "hold" | "reject"
    field_decisions: list[FieldDecisionInput] = []


class ApplyReviewDecisionsRequest(BaseModel):
    """
    Request body for POST /api/sblt/sessions/{session_id}/apply-review-decisions.

    row_decisions           — explicit per-row and per-field decisions.
                              Rows not listed receive system auto-decisions only.
    bulk_accept_auto_accepted — if True, confirm all auto_accepted fields
                              across all rows via system_bulk decision.
    bulk_accept_suggestions   — if True, accept all suggested_review candidates
                              across all rows via system_bulk decision.
    """
    row_decisions: list[RowDecisionInput] = []
    bulk_accept_auto_accepted: bool = False
    bulk_accept_suggestions: bool = False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/sessions")
def create_sblt_session(request: CreateSessionRequest) -> dict[str, Any]:
    """
    Create an SBLT session from a prepared loadsheet path.

    The loadsheet_path must be an absolute path to an existing .csv file
    (or .xlsx if openpyxl is installed).

    Returns the full session payload conforming to sblt.session.v1.
    """
    try:
        session = create_session_from_loadsheet(
            loadsheet_path=request.loadsheet_path,
            base_path=request.base_path,
            profile=request.profile,
        )
    except SBLTValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"SBLT session creation failed unexpectedly: {exc}",
        ) from exc

    return session


@router.post("/sessions/{session_id}/validate")
def validate_sblt_session(session_id: str) -> dict[str, Any]:
    """
    Run SBLT-2 schema validation on an existing parsed session.

    Maps source column names to canonical SBLT fields, validates required /
    conditional / recommended fields, assigns row statuses, updates summary
    counts, persists the updated session, and returns it.

    Returns 404 if the session does not exist.
    Returns 500 if the stored session fails invariant checks.
    """
    try:
        session = validate_session(session_id)
    except SBLTNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SBLTValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"SBLT schema validation failed unexpectedly: {exc}",
        ) from exc

    return session


@router.post("/sessions/{session_id}/normalize")
def normalize_sblt_session(session_id: str) -> dict[str, Any]:
    """
    Run SBLT-3 row normalization on an existing validated SBLT session.

    Normalizes display text, builds key forms, constructs normalized_metadata
    and identity_hints for each row, appends normalization-stage QAQC flags
    (preserving all SBLT-2 flags), updates row statuses, persists the updated
    session, and returns it.

    Session must be in 'validated' or 'normalized' state.
    Returns 400 if the session is in an incompatible state.
    Returns 404 if the session does not exist.
    Returns 500 on invariant failure or unexpected error.
    """
    try:
        session = normalize_session(session_id)
    except SBLTNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SBLTValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"SBLT row normalization failed unexpectedly: {exc}",
        ) from exc

    return session


@router.post("/sessions/{session_id}/validate-paths")
def validate_sblt_session_paths(session_id: str) -> dict[str, Any]:
    """
    Run SBLT-4 file/path reference validation on an existing normalized session.

    Validates the SEG-Y path and supporting document paths referenced in each
    row's normalized_metadata.  Adds a path_validation block to each row,
    appends structured QAQC flags, and updates row statuses.

    Session must be in 'normalized' or 'paths_validated' state.
    Returns 400 if the session has not been normalized yet.
    Returns 404 if the session does not exist.
    Returns 500 on invariant failure or unexpected error.
    """
    try:
        session = validate_session_paths(session_id)
    except SBLTNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SBLTValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"SBLT path validation failed unexpectedly: {exc}",
        ) from exc

    return session


@router.post("/sessions/{session_id}/extract-segy-header-evidence")
def extract_sblt_segy_header_evidence(session_id: str) -> dict[str, Any]:
    """
    Run SBLT-5 SEG-Y header evidence extraction on a paths-validated session.

    For each row with a valid, readable SEG-Y path from path_validation:
      - Reads fixed SEG-Y headers (textual + binary only; no trace data).
      - Builds MDE candidate observations from header fields.
      - Attaches the resulting MDE bundle to each row as metadata_evidence.
      - Updates row status per evidence / review / blocker rules.

    Session must be in 'paths_validated' or 'segy_header_evidence_extracted' state.
    Returns 400 if the session is in an incompatible state.
    Returns 404 if the session does not exist.
    Returns 500 on invariant failure or unexpected error.
    """
    try:
        session = extract_segy_header_evidence(session_id)
    except SBLTNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SBLTValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"SBLT SEG-Y header evidence extraction failed unexpectedly: {exc}",
        ) from exc

    return session


@router.post("/sessions/{session_id}/build-review-package")
def build_sblt_review_package(session_id: str) -> dict[str, Any]:
    """
    Run SBLT-6 review exception packaging on a segy_header_evidence_extracted session.

    Builds a session-level review_package dict that:
      - Classifies every row as ready, review_required, or blocked.
      - Lists per-field exceptions (conflicts, missing required, suggested candidates).
      - Lists auto-accepted fields (informational; no user action required).
      - Detects session-local duplicate risk groups (3 types: dataset_key, source
        reference, line/volume identity).
      - Provides session-level bulk action hints.
      - Produces a session-level blocking_reasons list and status flags.

    Architecture guarantees:
      - Does NOT approve rows.
      - Does NOT register MSI records.
      - Does NOT trigger conversion or indexing.
      - Does NOT query MSI, Managed Data, or Source Intake.
      - Duplicate detection is session-local ONLY.
      - can_register remains False.

    Session must be in 'segy_header_evidence_extracted' or 'review_package_built' state.
    Returns 400 if the session is in an incompatible state.
    Returns 404 if the session does not exist.
    Returns 500 on invariant failure or unexpected error.
    """
    try:
        session = build_review_package(session_id)
    except SBLTNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SBLTValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"SBLT review package build failed unexpectedly: {exc}",
        ) from exc

    return session


@router.post("/sessions/{session_id}/apply-review-decisions")
def apply_sblt_review_decisions(
    session_id: str,
    request: ApplyReviewDecisionsRequest,
) -> dict[str, Any]:
    """
    Run SBLT-7 review decision application on a review_package_built session.

    Applies user-supplied review decisions (and optional bulk actions) to the
    session's rows.  For each row, produces:
      - review_decisions                  — per-field decision records
      - approved_canonical_metadata_draft — draft canonical values for resolved fields
      - approval_readiness                — row-level readiness status and blocker summary

    Produces a session-level review_decision_package summary.

    Decision types per field:
      accept_auto_accepted — confirm a field already auto-accepted from high-authority source
      accept_candidate     — accept a suggested candidate value
      resolve_conflict     — resolve a conflict (supply override or use submitted)
      supply_value         — supply a value for a missing field
      defer                — explicitly defer a field (excluded from canonical draft)

    Row actions:
      proceed (default) — row proceeds toward approval gate
      hold              — row is held from this batch (approval blocked)
      reject            — row is rejected from this batch (approval blocked)

    Bulk options:
      bulk_accept_auto_accepted — confirm all auto_accepted fields session-wide
      bulk_accept_suggestions   — accept all suggested_review candidates session-wide

    Architecture guarantees:
      - Does NOT approve rows for loading or registration.
      - Does NOT set can_register = true.
      - Does NOT register MSI records.
      - Does NOT trigger conversion or indexing.
      - Does NOT query MSI, Managed Data, or Source Intake.
      - Does NOT read SEG-Y files or trace data.
      - Does NOT modify MDE bundles.
      - metadata_evidence is read-only.

    Session must be in 'review_package_built' or 'review_decisions_applied' state.
    Returns 400 if the session is in an incompatible state.
    Returns 404 if the session does not exist.
    Returns 500 on invariant failure or unexpected error.
    """
    try:
        # Convert Pydantic models to plain dicts for the service layer.
        row_decisions_input = [
            {
                "row_id": rd.row_id,
                "row_action": rd.row_action,
                "field_decisions": [
                    {
                        "field": fd.field,
                        "decision": fd.decision,
                        "supplied_value": fd.supplied_value,
                        "notes": fd.notes,
                    }
                    for fd in rd.field_decisions
                ],
            }
            for rd in request.row_decisions
        ]
        session = apply_review_decisions(
            session_id=session_id,
            row_decisions_input=row_decisions_input,
            bulk_accept_auto_accepted=request.bulk_accept_auto_accepted,
            bulk_accept_suggestions=request.bulk_accept_suggestions,
        )
    except SBLTNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SBLTValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"SBLT review decision application failed unexpectedly: {exc}",
        ) from exc

    return session


@router.get("/sessions/{session_id}")
def get_sblt_session(session_id: str) -> dict[str, Any]:
    """
    Retrieve a persisted SBLT session by session_id.

    Returns 404 if the session does not exist.
    Returns 500 if the stored session fails invariant checks.
    """
    try:
        session = get_session(session_id)
    except SBLTNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"SBLT session invariant failure: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"SBLT session retrieval failed unexpectedly: {exc}",
        ) from exc

    return session
