"""
SBLT-1: FastAPI router for the Seismic Bulk Loading Tool.

Routes:
    POST /api/sblt/sessions    — create a session from a prepared loadsheet path
    GET  /api/sblt/sessions/{session_id} — retrieve a persisted session

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
