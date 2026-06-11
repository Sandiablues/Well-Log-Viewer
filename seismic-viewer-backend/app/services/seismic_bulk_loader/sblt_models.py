"""
SBLT-1 / SBLT-2: Model constants and builder helpers for the SBLT session contract.

Ownership: backend SBLT service.

This module defines:
- Schema version constants.
- Status vocabulary.
- Builder functions that return plain dicts conforming to the sblt.session.v1 contract.

No Pydantic models are defined here; the session state is stored and returned as
plain JSON-serialisable dicts. FastAPI serialises them directly.

MSI dataset_id and representation_id are NOT defined here — those belong to SBLT-8.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "sblt.session.v1"

# Session-level status values.
SESSION_STATUS_PARSED = "parsed"
SESSION_STATUS_SCHEMA_INVALID = "schema_invalid"
SESSION_STATUS_VALIDATED = "validated"
SESSION_STATUS_NORMALIZED = "normalized"
SESSION_STATUS_PATHS_VALIDATED = "paths_validated"
SESSION_STATUS_SEGY_HEADER_EVIDENCE_EXTRACTED = "segy_header_evidence_extracted"
SESSION_STATUS_REVIEW_PACKAGE_BUILT = "review_package_built"
SESSION_STATUS_REVIEW_REQUIRED = "review_required"
SESSION_STATUS_REVIEW_DECISIONS_APPLIED = "review_decisions_applied"
SESSION_STATUS_APPROVED_FOR_LOADING_PREP = "approved_for_loading_prep"  # SBLT-8
SESSION_STATUS_LOADING_HANDOFF_PREPARED = "loading_handoff_prepared"   # SBLT-9
SESSION_STATUS_APPROVED = "approved"
SESSION_STATUS_REGISTERED = "registered"
SESSION_STATUS_FAILED = "failed"

VALID_SESSION_STATUSES = {
    SESSION_STATUS_PARSED,
    SESSION_STATUS_SCHEMA_INVALID,
    SESSION_STATUS_VALIDATED,
    SESSION_STATUS_NORMALIZED,
    SESSION_STATUS_PATHS_VALIDATED,
    SESSION_STATUS_SEGY_HEADER_EVIDENCE_EXTRACTED,
    SESSION_STATUS_REVIEW_PACKAGE_BUILT,
    SESSION_STATUS_REVIEW_REQUIRED,
    SESSION_STATUS_REVIEW_DECISIONS_APPLIED,
    SESSION_STATUS_APPROVED_FOR_LOADING_PREP,
    SESSION_STATUS_LOADING_HANDOFF_PREPARED,
    SESSION_STATUS_APPROVED,
    SESSION_STATUS_REGISTERED,
    SESSION_STATUS_FAILED,
}

# Row-level status values.
ROW_STATUS_PARSED = "parsed"
ROW_STATUS_READY = "ready"
ROW_STATUS_WARNING = "warning"
ROW_STATUS_REVIEW_REQUIRED = "review_required"
ROW_STATUS_BLOCKED = "blocked"
ROW_STATUS_DUPLICATE = "duplicate"
ROW_STATUS_APPROVED = "approved"
ROW_STATUS_REGISTERED = "registered"
ROW_STATUS_FAILED = "failed"

VALID_ROW_STATUSES = {
    ROW_STATUS_PARSED,
    ROW_STATUS_READY,
    ROW_STATUS_WARNING,
    ROW_STATUS_REVIEW_REQUIRED,
    ROW_STATUS_BLOCKED,
    ROW_STATUS_DUPLICATE,
    ROW_STATUS_APPROVED,
    ROW_STATUS_REGISTERED,
    ROW_STATUS_FAILED,
}

# Supported loadsheet formats.
FORMAT_CSV = "csv"
FORMAT_XLSX = "xlsx"
SUPPORTED_FORMATS = {FORMAT_CSV}  # XLSX requires openpyxl — see sblt_loadsheet_parser.py


def make_row_actions(
    *,
    can_validate: bool = True,
    can_approve: bool = False,
    can_register: bool = False,
    requires_review: bool = False,
) -> dict[str, Any]:
    return {
        "can_validate": can_validate,
        "can_approve": can_approve,
        "can_register": can_register,
        "requires_review": requires_review,
    }


def make_parsed_row(
    *,
    row_id: str,
    source_row_number: int,
    source_values: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a single row payload in SBLT-1 parsed state.

    SBLT-1 scope: preserve original column names and values only.
    No column canonicalisation, metadata normalisation, or file validation.
    canonical_fields is empty dict at this stage; populated by SBLT-2 validate.
    """
    return {
        "row_id": row_id,
        "source_row_number": source_row_number,
        "status": ROW_STATUS_PARSED,
        "record_type": "unknown",
        "source_values": source_values,
        "canonical_fields": {},
        "normalized_metadata": {},
        "identity_hints": {},
        "path_validation": {},
        "validation": {},
        "qaqc_flags": [],
        "actions": make_row_actions(
            can_validate=True,
            can_approve=False,
            can_register=False,
            requires_review=False,
        ),
    }


def make_validated_row(
    existing_row: dict[str, Any],
    *,
    canonical_fields: dict[str, Any],
    validation: dict[str, Any],
    qaqc_flags: list[dict[str, Any]],
    status: str,
) -> dict[str, Any]:
    """
    Build an updated row dict after SBLT-2 schema validation.

    Preserves row_id, source_row_number, and source_values unchanged.
    Updates status, record_type, canonical_fields, validation, qaqc_flags,
    and actions based on the validation result.
    """
    requires_review = status in (ROW_STATUS_REVIEW_REQUIRED, ROW_STATUS_BLOCKED)
    can_approve = status == ROW_STATUS_READY
    normalised_record_type = canonical_fields.get("record_type") or "unknown"
    return {
        **existing_row,
        "status": status,
        "record_type": normalised_record_type,
        "canonical_fields": canonical_fields,
        "validation": validation,
        "qaqc_flags": qaqc_flags,
        "actions": make_row_actions(
            can_validate=True,
            can_approve=can_approve,
            can_register=False,
            requires_review=requires_review,
        ),
    }


def make_normalized_row(
    existing_row: dict[str, Any],
    *,
    normalized_metadata: dict[str, Any],
    identity_hints: dict[str, Any],
    qaqc_flags: list[dict[str, Any]],
    status: str,
) -> dict[str, Any]:
    """
    Build an updated row dict after SBLT-3 row normalization.

    Preserves row_id, source_row_number, source_values, canonical_fields,
    and validation unchanged.
    Updates status, normalized_metadata, identity_hints, qaqc_flags, and actions.
    """
    requires_review = status in (ROW_STATUS_REVIEW_REQUIRED, ROW_STATUS_BLOCKED)
    can_approve = status == ROW_STATUS_READY
    return {
        **existing_row,
        "status": status,
        "normalized_metadata": normalized_metadata,
        "identity_hints": identity_hints,
        "qaqc_flags": qaqc_flags,
        "actions": make_row_actions(
            can_validate=True,
            can_approve=can_approve,
            can_register=False,
            requires_review=requires_review,
        ),
    }


def make_path_validated_row(
    existing_row: dict[str, Any],
    *,
    path_validation: dict[str, Any],
    qaqc_flags: list[dict[str, Any]],
    status: str,
) -> dict[str, Any]:
    """
    Build an updated row dict after SBLT-4 path validation.

    Preserves row_id, source_row_number, source_values, canonical_fields,
    validation, normalized_metadata, and identity_hints unchanged.
    Updates status, path_validation, qaqc_flags, and actions.
    """
    requires_review = status in (ROW_STATUS_REVIEW_REQUIRED, ROW_STATUS_BLOCKED)
    can_approve = status == ROW_STATUS_READY
    return {
        **existing_row,
        "status": status,
        "path_validation": path_validation,
        "qaqc_flags": qaqc_flags,
        "actions": make_row_actions(
            can_validate=True,
            can_approve=can_approve,
            can_register=False,
            requires_review=requires_review,
        ),
    }


def make_segy_header_evidence_row(
    existing_row: dict[str, Any],
    *,
    metadata_evidence: dict[str, Any],
    header_read_summary: dict[str, Any] | None,
    qaqc_flags: list[dict[str, Any]],
    status: str,
) -> dict[str, Any]:
    """
    Build an updated row dict after SBLT-5 SEG-Y header evidence extraction.

    Preserves row_id, source_row_number, source_values, canonical_fields,
    validation, normalized_metadata, identity_hints, and path_validation
    unchanged.  Adds metadata_evidence, optionally adds header_read_summary,
    and updates status, qaqc_flags, and actions.
    """
    requires_review = status in (ROW_STATUS_REVIEW_REQUIRED, ROW_STATUS_BLOCKED)
    can_approve = status == ROW_STATUS_READY
    result: dict[str, Any] = {
        **existing_row,
        "status": status,
        "metadata_evidence": metadata_evidence,
        "qaqc_flags": qaqc_flags,
        "actions": make_row_actions(
            can_validate=True,
            can_approve=can_approve,
            can_register=False,
            requires_review=requires_review,
        ),
    }
    if header_read_summary is not None:
        result["header_read_summary"] = header_read_summary
    return result


def make_review_decided_row(
    existing_row: dict[str, Any],
    *,
    review_decisions: dict[str, Any],
    approved_canonical_metadata_draft: dict[str, Any],
    approval_readiness: dict[str, Any],
) -> dict[str, Any]:
    """
    Build an updated row dict after SBLT-7 review decision application.

    Preserves all fields produced by SBLT-1 through SBLT-6 unchanged, including
    metadata_evidence (read-only in SBLT-7).

    Adds:
      review_decisions                — per-field decision records
      approved_canonical_metadata_draft — draft canonical field values
      approval_readiness              — row-level readiness status

    Row status and actions are NOT changed by SBLT-7.  Earlier pipeline steps
    own those fields.  approval_readiness independently communicates the SBLT-7
    outcome without conflicting with existing row state.
    """
    return {
        **existing_row,
        "review_decisions": review_decisions,
        "approved_canonical_metadata_draft": approved_canonical_metadata_draft,
        "approval_readiness": approval_readiness,
    }


def make_approval_gate_row(
    existing_row: dict[str, Any],
    *,
    approval_gate: dict[str, Any],
    approved_canonical_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Build an updated row dict after SBLT-8 approval gate processing.

    Preserves all fields produced by SBLT-1 through SBLT-7 unchanged, including
    metadata_evidence (read-only), review_decisions, approved_canonical_metadata_draft,
    and approval_readiness.

    Adds:
      approval_gate                — gate decision, status, reasons, and readiness flags
      approved_canonical_metadata  — copy of approved_canonical_metadata_draft if approved;
                                     None otherwise

    Row status, row actions, and all prior SBLT fields are NOT changed by SBLT-8.
    """
    return {
        **existing_row,
        "approval_gate": approval_gate,
        "approved_canonical_metadata": approved_canonical_metadata,
    }


def make_loading_handoff_row(
    existing_row: dict[str, Any],
    *,
    loading_handoff: dict[str, Any],
) -> dict[str, Any]:
    """
    Build an updated row dict after SBLT-9 loading handoff preparation.

    Preserves all fields produced by SBLT-1 through SBLT-8 unchanged, including
    metadata_evidence (read-only), review_decisions, approved_canonical_metadata_draft,
    approval_readiness, approval_gate, and approved_canonical_metadata.

    Adds:
      loading_handoff  — SBLT-9 handoff record (prepared | skipped | blocked)

    Row status, row actions, and all prior SBLT fields are NOT changed by SBLT-9.
    """
    return {
        **existing_row,
        "loading_handoff": loading_handoff,
    }


def make_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Build the summary block from a list of row dicts.

    Invariants enforced by caller:
    - summary.total == len(rows)
    - summary.parsed == len(rows) for SBLT-1 parsed sessions
    """
    counts: dict[str, int] = {
        "total": 0,
        "parsed": 0,
        "ready": 0,
        "warning": 0,
        "review_required": 0,
        "blocked": 0,
        "duplicate": 0,
        "approved": 0,
        "registered": 0,
        "failed": 0,
    }
    counts["total"] = len(rows)
    for row in rows:
        status = str(row.get("status") or "").strip()
        if status in counts:
            counts[status] += 1
    return counts


def make_session_actions(
    *,
    can_validate: bool,
    can_approve: bool,
    can_register: bool,
) -> dict[str, Any]:
    return {
        "can_validate": can_validate,
        "can_approve": can_approve,
        "can_register": can_register,
    }


def make_session(
    *,
    session_id: str,
    status: str,
    source: dict[str, Any],
    rows: list[dict[str, Any]],
    created_at: str,
    updated_at: str,
) -> dict[str, Any]:
    """
    Build a complete SBLT session dict conforming to sblt.session.v1.

    Invariants:
    - row_count == len(rows)
    - summary.total == len(rows)
    """
    summary = make_summary(rows)
    # Invariant assertion — hard stop if violated.
    assert summary["total"] == len(rows), (
        f"SBLT invariant failed: summary.total={summary['total']} != len(rows)={len(rows)}"
    )
    row_count = len(rows)

    # Session-level actions: computed from status and row states.
    # can_validate: true for parsed and validated sessions that have rows.
    # can_approve:  true only for validated sessions where at least one row
    #               is ready or review_required (SBLT-7 will gate per-row approval).
    # can_register: false until SBLT-8.
    _approvable_statuses = {ROW_STATUS_READY, ROW_STATUS_REVIEW_REQUIRED}
    has_approvable_rows = any(
        r.get("status") in _approvable_statuses for r in rows
    )
    actions = make_session_actions(
        can_validate=(
            status in (
                SESSION_STATUS_PARSED,
                SESSION_STATUS_VALIDATED,
                SESSION_STATUS_NORMALIZED,
                SESSION_STATUS_PATHS_VALIDATED,
                SESSION_STATUS_SEGY_HEADER_EVIDENCE_EXTRACTED,
                SESSION_STATUS_REVIEW_PACKAGE_BUILT,
                SESSION_STATUS_REVIEW_DECISIONS_APPLIED,
                SESSION_STATUS_APPROVED_FOR_LOADING_PREP,
                SESSION_STATUS_LOADING_HANDOFF_PREPARED,
            )
            and row_count > 0
        ),
        can_approve=(
            status in (
                SESSION_STATUS_VALIDATED,
                SESSION_STATUS_NORMALIZED,
                SESSION_STATUS_PATHS_VALIDATED,
                SESSION_STATUS_SEGY_HEADER_EVIDENCE_EXTRACTED,
                SESSION_STATUS_REVIEW_PACKAGE_BUILT,
                SESSION_STATUS_REVIEW_DECISIONS_APPLIED,
            )
            and has_approvable_rows
        ),
        can_register=False,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "status": status,
        "source": source,
        "row_count": row_count,
        "summary": summary,
        "rows": rows,
        "actions": actions,
        "created_at": created_at,
        "updated_at": updated_at,
    }
