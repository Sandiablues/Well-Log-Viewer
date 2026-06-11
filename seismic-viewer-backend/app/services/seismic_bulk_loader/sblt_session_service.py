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
    SESSION_STATUS_VALIDATED,
    SESSION_STATUS_NORMALIZED,
    SESSION_STATUS_PATHS_VALIDATED,
    SESSION_STATUS_SEGY_HEADER_EVIDENCE_EXTRACTED,
    SESSION_STATUS_FAILED,
    make_parsed_row,
    make_validated_row,
    make_normalized_row,
    make_path_validated_row,
    make_segy_header_evidence_row,
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


def validate_session(session_id: str) -> dict[str, Any]:
    """
    Run SBLT-2 schema validation on an existing SBLT session.

    Loads the session, maps source column names to canonical SBLT fields,
    validates required/conditional/recommended fields, assigns row statuses,
    updates the summary, persists the updated session, and returns it.

    SBLT-2 scope:
    - Schema / column alias validation only.
    - source_values on every row are preserved unchanged.
    - No file/path existence check.
    - No SEG-Y header inspection.
    - No MSI interaction.

    Raises SBLTNotFoundError if the session does not exist.
    Raises SBLTValidationError if the session fails invariants.
    """
    from .sblt_column_mapper import map_columns
    from .sblt_schema_validator import validate_row_schema

    # Load and invariant-check the existing session.
    session = get_session(session_id)

    existing_rows: list[dict[str, Any]] = session.get("rows", [])
    validated_rows: list[dict[str, Any]] = []

    for row in existing_rows:
        source_values: dict[str, str] = row.get("source_values", {})

        # Map source column names → canonical field names + detect duplicates.
        mapping = map_columns(source_values)

        # Validate canonical fields → canonical_fields dict, validation block,
        # QAQC flags, and row status.
        canonical_fields, validation, qaqc_flags, status = validate_row_schema(mapping)

        # Build updated row (source_values preserved unchanged).
        validated_rows.append(
            make_validated_row(
                row,
                canonical_fields=canonical_fields,
                validation=validation,
                qaqc_flags=qaqc_flags,
                status=status,
            )
        )

    # Rebuild session with validated rows and updated status.
    now = _utc_now()
    updated_session = make_session(
        session_id=session["session_id"],
        status=SESSION_STATUS_VALIDATED,
        source=session["source"],
        rows=validated_rows,
        created_at=session["created_at"],
        updated_at=now,
    )

    # Enforce invariants before saving.
    _validate_session_invariants(updated_session)
    _save_session(updated_session)

    return updated_session


def normalize_session(session_id: str) -> dict[str, Any]:
    """
    Run SBLT-3 row normalization on an existing SBLT validated session.

    Loads the session, normalizes display text, builds key forms, constructs
    normalized_metadata and identity_hints for each row, appends normalization-
    stage QAQC flags (preserving all SBLT-2 flags), updates row statuses,
    persists the updated session, and returns it.

    SBLT-3 scope:
    - String-level normalization from canonical_fields only.
    - No filesystem access (no file/path existence check).
    - No SEG-Y header inspection.
    - No duplicate detection.
    - No MSI interaction.

    Status invariants:
    - blocked rows stay blocked.
    - review_required rows stay review_required.
    - ready rows may become review_required if dataset_key cannot be built.

    Raises SBLTValidationError if the session is not in validated or normalized state.
    Raises SBLTNotFoundError if the session does not exist.
    """
    from .sblt_row_normalizer import normalize_row

    session = get_session(session_id)

    current_status = session.get("status")
    if current_status not in (SESSION_STATUS_VALIDATED, SESSION_STATUS_NORMALIZED):
        raise SBLTValidationError(
            f"SBLT session must be in 'validated' or 'normalized' state before normalization. "
            f"Current status: {current_status!r}",
            status_code=400,
        )

    existing_rows: list[dict[str, Any]] = session.get("rows", [])
    normalized_rows: list[dict[str, Any]] = []

    for row in existing_rows:
        normalized_meta, identity_hints, new_qaqc_flags, new_status = normalize_row(row)

        # Merge SBLT-2 flags (preserved) with normalization-stage flags.
        merged_flags = list(row.get("qaqc_flags") or []) + new_qaqc_flags

        normalized_rows.append(
            make_normalized_row(
                row,
                normalized_metadata=normalized_meta,
                identity_hints=identity_hints,
                qaqc_flags=merged_flags,
                status=new_status,
            )
        )

    now = _utc_now()
    updated_session = make_session(
        session_id=session["session_id"],
        status=SESSION_STATUS_NORMALIZED,
        source=session["source"],
        rows=normalized_rows,
        created_at=session["created_at"],
        updated_at=now,
    )

    _validate_session_invariants(updated_session)
    _save_session(updated_session)

    return updated_session


def validate_session_paths(session_id: str) -> dict[str, Any]:
    """
    Run SBLT-4 file/path reference validation on an existing normalized session.

    Loads the session, validates the SEG-Y path and supporting document paths
    referenced in each row's normalized_metadata, appends path-validation-stage
    QAQC flags (preserving all earlier flags), updates row statuses, persists
    the updated session, and returns it.

    SBLT-4 scope:
    - Existence, is_file, and read-permission checks only.
    - SEG-Y extension check (warning; does not block if file is readable).
    - No SEG-Y header/trace data inspection.
    - No supporting document content inspection or classification.
    - No folder scanning or path inference.
    - No duplicate detection.
    - No MSI interaction.

    Status rules:
    - blocked         stays blocked.
    - review_required stays review_required unless SEG-Y blocker → blocked.
    - ready           stays ready if SEG-Y valid, else blocked.
    - Supporting document failures produce warnings only; never block.

    Raises SBLTValidationError (400) if session is not in normalized or
    paths_validated state.
    Raises SBLTNotFoundError (404) if the session does not exist.
    """
    from .sblt_path_validator import validate_row_paths

    session = get_session(session_id)

    current_status = session.get("status")
    if current_status not in (SESSION_STATUS_NORMALIZED, SESSION_STATUS_PATHS_VALIDATED):
        raise SBLTValidationError(
            "SBLT session must be normalized before path validation.",
            status_code=400,
        )

    # base_path from the original session creation request (may be None).
    base_path: str | None = (session.get("source") or {}).get("base_path") or None

    existing_rows: list[dict[str, Any]] = session.get("rows", [])
    path_validated_rows: list[dict[str, Any]] = []

    for row in existing_rows:
        path_validation, new_qaqc_flags, new_status = validate_row_paths(row, base_path)

        # Merge earlier flags (SBLT-2 + SBLT-3) with path-validation-stage flags.
        merged_flags = list(row.get("qaqc_flags") or []) + new_qaqc_flags

        path_validated_rows.append(
            make_path_validated_row(
                row,
                path_validation=path_validation,
                qaqc_flags=merged_flags,
                status=new_status,
            )
        )

    now = _utc_now()
    updated_session = make_session(
        session_id=session["session_id"],
        status=SESSION_STATUS_PATHS_VALIDATED,
        source=session["source"],
        rows=path_validated_rows,
        created_at=session["created_at"],
        updated_at=now,
    )

    _validate_session_invariants(updated_session)
    _save_session(updated_session)

    return updated_session


# ---------------------------------------------------------------------------
# SBLT-5 helpers
# ---------------------------------------------------------------------------

# Fields from normalized_metadata that are actual metadata (not path / key fields).
_MDE_METADATA_FIELDS: frozenset = frozenset({
    "survey_name",
    "line_name",
    "volume_name",
    "record_type",
    "processing_stage",
    "operator",
    "area_or_block",
    "sample_interval_ms",
    "crs_raw",    # exposed as "crs" to MDE
    "datum_raw",  # exposed as "datum" to MDE
})

# Normalise field names that differ between normalized_metadata and MDE policy keys.
_NM_TO_MDE_FIELD: dict = {
    "crs_raw": "crs",
    "datum_raw": "datum",
}


def _build_mde_raw_submitted(normalized_metadata: dict) -> dict:
    """
    Extract a flat {field: value} dict from normalized_metadata for MDE.

    Only real metadata fields are included; path, key, and system fields
    are excluded.  Fields whose value is None or empty string are omitted
    entirely so MDE classifies them as absent rather than receiving an
    explicit None.

    IMPORTANT: the is-absent check uses explicit ``is not None`` plus a
    non-empty-string guard — never a bare truthy test — so that numeric
    values such as 0 or 0.0 are preserved and passed through correctly.
    """
    out: dict = {}
    nm = normalized_metadata if normalized_metadata is not None else {}
    for nm_key in _MDE_METADATA_FIELDS:
        mde_key = _NM_TO_MDE_FIELD.get(nm_key, nm_key)
        raw_val = nm.get(nm_key)
        # Convert empty strings to absent; preserve all other types (int, float,
        # non-empty str) including numeric zero and 0.0.
        if raw_val is not None and isinstance(raw_val, str) and not raw_val.strip():
            raw_val = None
        # Only include the field when a value is actually present.
        if raw_val is not None:
            out[mde_key] = raw_val
    return out


def _sblt5_flag(severity: str, code: str, message: str) -> dict:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "field": None,
        "source": "segy_header_evidence",
    }


# ---------------------------------------------------------------------------
# SBLT-5: extract_segy_header_evidence
# ---------------------------------------------------------------------------

def extract_segy_header_evidence(session_id: str) -> dict:
    """
    Run SBLT-5 SEG-Y header evidence extraction on a paths-validated session.

    For each row with a valid, readable SEG-Y path from path_validation:
      - Reads fixed SEG-Y headers (textual + binary only; no trace data).
      - Builds MDE candidate observations from header fields.
      - Calls build_metadata_evidence_bundle() to produce the MDE bundle.
      - Attaches the MDE bundle to the row as metadata_evidence.
      - Updates row status per evidence / review / blocker rules.
      - Appends operational QAQC flags (preserving all prior flags).

    SBLT-5 scope:
      - Fixed headers only.  No trace data.  No geometry.  No approval.
      - No MSI registration.  No conversion/indexing.  No folder scanning.

    Raises SBLTValidationError (400) if session is not in paths_validated
    or segy_header_evidence_extracted state.
    Raises SBLTNotFoundError (404) if the session does not exist.
    """
    from pathlib import Path as _Path

    from app.services.metadata_evidence import build_metadata_evidence_bundle
    from app.services.metadata_evidence.mde_models import (
        WORKFLOW_SBLT,
        SOURCE_REF_LOCAL_PATH,
        SOURCE_STATUS_VALIDATED,
        make_dataset_context,
        make_source_reference,
    )
    from .sblt_segy_header_reader import read_segy_fixed_headers
    from .sblt_segy_header_evidence import build_segy_candidate_observations

    session = get_session(session_id)

    current_status = session.get("status")
    if current_status not in (
        SESSION_STATUS_PATHS_VALIDATED,
        SESSION_STATUS_SEGY_HEADER_EVIDENCE_EXTRACTED,
    ):
        raise SBLTValidationError(
            f"SBLT session must be in 'paths_validated' or "
            f"'segy_header_evidence_extracted' state before SEG-Y header "
            f"evidence extraction.  Current status: {current_status!r}",
            status_code=400,
        )

    existing_rows: list = session.get("rows", [])
    updated_rows: list = []

    for row in existing_rows:
        row_id: str = row.get("row_id", "")
        row_status: str = str(row.get("status") or "blocked")
        nm: dict = row.get("normalized_metadata") or {}
        prior_flags: list = list(row.get("qaqc_flags") or [])
        path_val: dict = row.get("path_validation") or {}

        # ------------------------------------------------------------------ #
        # Determine whether this row has a readable SEG-Y path                #
        # ------------------------------------------------------------------ #
        segy_info: dict = path_val.get("segy") or {}
        segy_readable: bool = bool(
            segy_info.get("exists")
            and segy_info.get("is_file")
            and segy_info.get("readable")
        )
        resolved_path_str: str = str(segy_info.get("resolved_path") or "").strip()

        # ------------------------------------------------------------------ #
        # Rows that are already blocked or have no readable path               #
        # ------------------------------------------------------------------ #
        if row_status == "blocked" or not segy_readable or not resolved_path_str:
            # Attach an empty MDE bundle so the key is always present on
            # rows that have been through this step.
            if "metadata_evidence" not in row:
                raw_submitted = _build_mde_raw_submitted(nm)
                dataset_ctx = make_dataset_context(
                    record_type=nm.get("record_type") or "unknown",
                    dataset_label=nm.get("dataset_label") or "",
                    source_reference=make_source_reference(
                        source_reference_type=SOURCE_REF_LOCAL_PATH,
                        source_reference_value=nm.get("segy_path_raw") or "",
                        resolved_reference=resolved_path_str,
                        source_status=(
                            SOURCE_STATUS_VALIDATED if segy_readable else "unknown"
                        ),
                    ),
                )
                empty_bundle = build_metadata_evidence_bundle(
                    workflow_type=WORKFLOW_SBLT,
                    workflow_session_id=session_id,
                    workflow_row_id=row_id,
                    dataset_context=dataset_ctx,
                    raw_submitted_metadata=raw_submitted,
                    candidate_observations=[],
                    existing_qaqc_findings=[],
                )
                updated_rows.append(make_segy_header_evidence_row(
                    row,
                    metadata_evidence=empty_bundle,
                    header_read_summary=None,
                    qaqc_flags=prior_flags,
                    status=row_status,
                ))
            else:
                updated_rows.append(row)
            continue

        # ------------------------------------------------------------------ #
        # Read fixed SEG-Y headers                                             #
        # ------------------------------------------------------------------ #
        resolved_path = _Path(resolved_path_str)
        header_result = read_segy_fixed_headers(resolved_path)

        new_flags: list = []

        if not header_result["ok"]:
            err_str: str = str(header_result.get("error") or "")
            if "SEGY_HEADER_TOO_SMALL" in err_str:
                code = "SEGY_HEADER_TOO_SMALL"
                msg = (
                    f"SEG-Y file too small for fixed headers "
                    f"(requires {3600} bytes): {resolved_path_str}"
                )
            else:
                code = "SEGY_HEADER_READ_FAILED"
                msg = (
                    f"SEG-Y header read failed for {resolved_path_str!r}: {err_str}"
                )
            new_flags.append(_sblt5_flag("blocker", code, msg))
            merged_flags = prior_flags + new_flags
            new_status = "blocked"

            raw_submitted = _build_mde_raw_submitted(nm)
            dataset_ctx = make_dataset_context(
                record_type=nm.get("record_type") or "unknown",
                dataset_label=nm.get("dataset_label") or "",
                source_reference=make_source_reference(
                    source_reference_type=SOURCE_REF_LOCAL_PATH,
                    source_reference_value=nm.get("segy_path_raw") or "",
                    resolved_reference=resolved_path_str,
                    source_status=SOURCE_STATUS_VALIDATED,
                ),
            )
            mde_bundle = build_metadata_evidence_bundle(
                workflow_type=WORKFLOW_SBLT,
                workflow_session_id=session_id,
                workflow_row_id=row_id,
                dataset_context=dataset_ctx,
                raw_submitted_metadata=raw_submitted,
                candidate_observations=[],
                existing_qaqc_findings=[],
            )
            updated_rows.append(make_segy_header_evidence_row(
                row,
                metadata_evidence=mde_bundle,
                header_read_summary=header_result["header_read_summary"],
                qaqc_flags=merged_flags,
                status=new_status,
            ))
            continue

        # ------------------------------------------------------------------ #
        # Build MDE candidate observations                                     #
        # ------------------------------------------------------------------ #
        new_flags.append(_sblt5_flag(
            "info", "SEGY_BINARY_HEADER_PARSED",
            f"SEG-Y binary header parsed: {resolved_path_str}",
        ))

        candidate_obs = build_segy_candidate_observations(header_result, nm)

        # ------------------------------------------------------------------ #
        # Build MDE bundle                                                     #
        # ------------------------------------------------------------------ #
        raw_submitted = _build_mde_raw_submitted(nm)
        dataset_ctx = make_dataset_context(
            record_type=nm.get("record_type") or "unknown",
            dataset_label=nm.get("dataset_label") or "",
            source_reference=make_source_reference(
                source_reference_type=SOURCE_REF_LOCAL_PATH,
                source_reference_value=nm.get("segy_path_raw") or "",
                resolved_reference=resolved_path_str,
                source_status=SOURCE_STATUS_VALIDATED,
            ),
        )
        mde_bundle = build_metadata_evidence_bundle(
            workflow_type=WORKFLOW_SBLT,
            workflow_session_id=session_id,
            workflow_row_id=row_id,
            dataset_context=dataset_ctx,
            raw_submitted_metadata=raw_submitted,
            candidate_observations=candidate_obs,
            existing_qaqc_findings=[],
        )

        # ------------------------------------------------------------------ #
        # Determine new row status from MDE review summary                     #
        # ------------------------------------------------------------------ #
        review_summary: dict = mde_bundle.get("review_summary") or {}
        mde_requires_review: bool = bool(
            review_summary.get("requires_user_review", False)
        )

        if row_status == "blocked":
            new_status = "blocked"
        elif row_status == "review_required":
            new_status = "review_required"
        elif row_status == "ready":
            new_status = "review_required" if mde_requires_review else "ready"
        else:
            new_status = row_status

        new_flags.append(_sblt5_flag(
            "info", "SEGY_HEADER_EVIDENCE_EXTRACTED",
            f"SEG-Y header evidence extracted for row {row_id!r}.",
        ))

        merged_flags = prior_flags + new_flags

        updated_rows.append(make_segy_header_evidence_row(
            row,
            metadata_evidence=mde_bundle,
            header_read_summary=header_result["header_read_summary"],
            qaqc_flags=merged_flags,
            status=new_status,
        ))

    # ------------------------------------------------------------------ #
    # Rebuild and persist session atomically                               #
    # ------------------------------------------------------------------ #
    now = _utc_now()
    updated_session = make_session(
        session_id=session["session_id"],
        status=SESSION_STATUS_SEGY_HEADER_EVIDENCE_EXTRACTED,
        source=session["source"],
        rows=updated_rows,
        created_at=session["created_at"],
        updated_at=now,
    )

    _validate_session_invariants(updated_session)
    _save_session(updated_session)

    return updated_session
