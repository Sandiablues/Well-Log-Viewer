"""
SBLT-1 through SBLT-6: FastAPI router for the Seismic Bulk Loading Tool.

Routes:
    POST /api/sblt/sessions                                     — create a session
    GET  /api/sblt/sessions/{session_id}                        — retrieve a session
    POST /api/sblt/sessions/{session_id}/validate               — SBLT-2 schema validation
    POST /api/sblt/sessions/{session_id}/normalize              — SBLT-3 row normalization
    POST /api/sblt/sessions/{session_id}/validate-paths         — SBLT-4 path validation
    POST /api/sblt/sessions/{session_id}/extract-segy-header-evidence — SBLT-5
    POST /api/sblt/sessions/{session_id}/build-review-package   — SBLT-6

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
