"""
SBLT-1: Backend-owned SBLT session service.

Ownership: backend SBLT service.

Responsibilities:
- Create an SBLT session from a prepared loadsheet path.
- Persist the session as a single JSON file per session (atomic write).
- Return the session on GET by session_id.
- Enforce session and row invariants on every read and write.

State location:
    seismic-viewer-backend/data/seismic_bulk_loader/sessions/{session_id}.json

SBLT-1 scope:
- Parse loadsheet rows and persist the session.
- No schema validation, metadata normalisation, file validation, SEG-Y
  inspection, duplicate checks, approval, registration, or MSI interaction.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sblt_models import (
    SCHEMA_VERSION,
    FORMAT_CSV,
    FORMAT_XLSX,
    SESSION_STATUS_PARSED,
    SESSION_STATUS_FAILED,
    make_parsed_row,
    make_session,
)
from .sblt_loadsheet_parser import (
    ParseError,
    UnsupportedFormatError,
    parse_loadsheet,
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# seismic-viewer-backend/app/services/seismic_bulk_loader/sblt_session_service.py
# parents[0] = seismic_bulk_loader/
# parents[1] = services/
# parents[2] = app/
# parents[3] = seismic-viewer-backend/
_BACKEND_DIR = Path(__file__).resolve().parents[3]
_SESSIONS_DIR = _BACKEND_DIR / "data" / "seismic_bulk_loader" / "sessions"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_session_id() -> str:
    """
    Generate a stable, human-readable SBLT session ID.

    Format: sblt_YYYYMMDD_HHMMSS_<8 random hex chars>
    Example: sblt_20260610_143022_a3f7c901
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    rand = secrets.token_hex(4)  # 8 hex chars
    return f"sblt_{ts}_{rand}"


def _generate_row_id(session_id: str, source_row_number: int) -> str:
    """
    Generate a stable row ID tied to the session and the source row number.

    Format: {session_id}_row_{source_row_number:04d}
    Example: sblt_20260610_143022_a3f7c901_row_0002
    """
    return f"{session_id}_row_{source_row_number:04d}"


def _detect_format(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".csv":
        return FORMAT_CSV
    if ext in {".xlsx", ".xls"}:
        return FORMAT_XLSX
    return ext.lstrip(".") or "unknown"


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def _ensure_sessions_dir() -> None:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _session_path(session_id: str) -> Path:
    return _SESSIONS_DIR / f"{session_id}.json"


def _save_session(session: dict[str, Any]) -> None:
    """Atomically write a session to disk using a .tmp rename pattern."""
    _ensure_sessions_dir()
    session_id = session["session_id"]
    target = _session_path(session_id)
    tmp = target.with_suffix(".json.tmp")
    payload = json.dumps(session, indent=2, sort_keys=False, ensure_ascii=False) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(target)


def _load_session_raw(session_id: str) -> dict[str, Any] | None:
    """Read a session from disk. Returns None if not found."""
    path = _session_path(session_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


# ---------------------------------------------------------------------------
# Invariant validation
# ---------------------------------------------------------------------------

def _validate_session_invariants(session: dict[str, Any]) -> None:
    """
    Enforce the SBLT session contract invariants.

    Raises ValueError if any invariant is violated.
    """
    schema_version = session.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"SBLT invariant failed: schema_version={schema_version!r} "
            f"expected={SCHEMA_VERSION!r}"
        )

    rows = session.get("rows")
    if not isinstance(rows, list):
        raise ValueError("SBLT invariant failed: rows must be a list.")

    row_count = session.get("row_count")
    if row_count != len(rows):
        raise ValueError(
            f"SBLT invariant failed: row_count={row_count} != len(rows)={len(rows)}"
        )

    summary = session.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("SBLT invariant failed: summary must be a dict.")

    if summary.get("total") != len(rows):
        raise ValueError(
            f"SBLT invariant failed: summary.total={summary.get('total')} "
            f"!= len(rows)={len(rows)}"
        )

    # Validate every row has required fields.
    for i, row in enumerate(rows):
        for field in ("row_id", "source_row_number", "status", "source_values", "actions"):
            if field not in row:
                raise ValueError(
                    f"SBLT invariant failed: row[{i}] missing required field {field!r}"
                )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SBLTSessionError(Exception):
    """Base error for SBLT session service failures."""


class SBLTValidationError(SBLTSessionError):
    """Raised for bad input that should produce a 400 response."""
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class SBLTNotFoundError(SBLTSessionError):
    """Raised when a session is not found (404)."""


def create_session_from_loadsheet(
    loadsheet_path: str,
    base_path: str | None = None,
    profile: str = "default",
) -> dict[str, Any]:
    """
    Create and persist a new SBLT session from a prepared loadsheet.

    Input validation:
    - loadsheet_path must be non-empty.
    - loadsheet_path must be an absolute path.
    - The file must exist.
    - The file extension must be supported.

    SBLT-1 scope:
    - Parse rows and preserve original column names and values.
    - No schema validation, normalisation, file/path validation, or MSI interaction.
    """
    # --- Input validation ---
    clean_path = str(loadsheet_path or "").strip()
    if not clean_path:
        raise SBLTValidationError("loadsheet_path is required.")

    p = Path(clean_path)

    if not p.is_absolute():
        raise SBLTValidationError(
            f"loadsheet_path must be an absolute path. Got: {clean_path!r}"
        )

    if not p.exists():
        raise SBLTValidationError(
            f"Loadsheet file not found: {clean_path!r}",
            status_code=400,
        )

    fmt = _detect_format(p)
    clean_base_path = str(base_path or "").strip() or None
    clean_profile = str(profile or "").strip() or "default"

    # --- Parse the loadsheet ---
    try:
        raw_rows = parse_loadsheet(p)
    except UnsupportedFormatError as exc:
        raise SBLTValidationError(str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise SBLTValidationError(str(exc)) from exc
    except ParseError as exc:
        raise SBLTValidationError(f"Loadsheet parse error: {exc}") from exc

    # --- Build session ---
    now = _utc_now()
    session_id = _generate_session_id()

    rows = [
        make_parsed_row(
            row_id=_generate_row_id(session_id, raw["source_row_number"]),
            source_row_number=raw["source_row_number"],
            source_values=raw["source_values"],
        )
        for raw in raw_rows
    ]

    source = {
        "loadsheet_path": clean_path,
        "base_path": clean_base_path,
        "profile": clean_profile,
        "format": fmt,
    }

    session = make_session(
        session_id=session_id,
        status=SESSION_STATUS_PARSED,
        source=source,
        rows=rows,
        created_at=now,
        updated_at=now,
    )

    # --- Validate invariants before saving ---
    _validate_session_invariants(session)

    # --- Persist ---
    _save_session(session)

    return session


def get_session(session_id: str) -> dict[str, Any]:
    """
    Retrieve a persisted SBLT session by session_id.

    Raises SBLTNotFoundError if the session does not exist.
    Raises ValueError if the stored session fails invariant checks.
    """
    clean_id = str(session_id or "").strip()
    if not clean_id:
        raise SBLTNotFoundError("session_id is required.")

    session = _load_session_raw(clean_id)
    if session is None:
        raise SBLTNotFoundError(f"SBLT session not found: {clean_id!r}")

    # Validate invariants on load to catch any persisted corruption.
    _validate_session_invariants(session)

    return session
