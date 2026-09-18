"""
SBLT-8: Approval Gate.

Pure-computation module.  No file reads.  No SEG-Y reads.  No MSI.
No Managed Data.  No conversion/indexing.  No frontend.  Session-local only.

Takes a session with SBLT-7 review decision outputs and produces:
  - per-row:   approval_gate  (added to each row)
  - per-row:   approved_canonical_metadata  (copy of draft; None for non-approved rows)
  - session:   approval_package

Ownership: backend SBLT service — SBLT-8 only.

Architecture guarantees:
  - Does NOT modify row.status, row.actions, row.metadata_evidence, or any prior
    SBLT field.
  - can_register is always False.
  - can_convert is always False.
  - approved_canonical_metadata is only populated for rows with gate_status=approved.
  - session.approval_package.session_loading_readiness.can_continue_to_loading_handoff
    is True only when at least one row is approved — this is readiness for SBLT-9,
    NOT operational conversion/registration/MSI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Schema version constants
# ---------------------------------------------------------------------------

APPROVAL_PACKAGE_SCHEMA_VERSION = "sblt.approval_package.v1"
ROW_APPROVAL_GATE_SCHEMA_VERSION = "sblt.row_approval_gate.v1"
SOURCE_REVIEW_DECISION_PACKAGE_SCHEMA = "sblt.review_decision_package.v1"

# ---------------------------------------------------------------------------
# Gate status vocabulary
# ---------------------------------------------------------------------------

GATE_STATUS_APPROVED = "approved"
GATE_STATUS_HELD = "held"
GATE_STATUS_REJECTED = "rejected"
GATE_STATUS_BLOCKED = "blocked"

# Mirrors SBLT-7 readiness vocabulary (local constants, no import from review_decisions)
_READINESS_DRAFT_APPROVED = "draft_approved"
_READINESS_HELD = "held"
_READINESS_REJECTED = "rejected"
_READINESS_BLOCKED = "blocked"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gate_status_for_row(row: dict[str, Any]) -> str:
    """
    Determine the approval_gate status for a single row.

    Priority order (highest first):
      1. held     — approval_readiness.status == "held"
      2. rejected — approval_readiness.status == "rejected"
      3. blocked  — any of:
           - approval_readiness.status == "blocked"
           - approval_readiness.can_proceed_to_approval is False
           - approved_canonical_metadata_draft is empty / missing
      4. approved — all of:
           - approval_readiness.status == "draft_approved"
           - approval_readiness.can_proceed_to_approval is True
           - approved_canonical_metadata_draft is non-empty

    No other status values are possible.
    """
    readiness: dict = row.get("approval_readiness") or {}
    readiness_status = str(readiness.get("status") or "").strip()
    can_proceed = bool(readiness.get("can_proceed_to_approval", False))
    draft = row.get("approved_canonical_metadata_draft")
    has_draft = bool(draft)

    if readiness_status == _READINESS_HELD:
        return GATE_STATUS_HELD

    if readiness_status == _READINESS_REJECTED:
        return GATE_STATUS_REJECTED

    # Blocked conditions — any one is sufficient.
    if not can_proceed:
        return GATE_STATUS_BLOCKED
    if readiness_status != _READINESS_DRAFT_APPROVED:
        return GATE_STATUS_BLOCKED
    if not has_draft:
        return GATE_STATUS_BLOCKED

    return GATE_STATUS_APPROVED


def _build_gate_reasons(gate_status: str, row: dict[str, Any]) -> list[str]:
    """Return a human-readable list of reasons for the gate decision."""
    readiness: dict = row.get("approval_readiness") or {}

    if gate_status == GATE_STATUS_APPROVED:
        return ["All required review fields resolved. Row approved for loading preparation."]

    if gate_status == GATE_STATUS_HELD:
        return ["Row held by reviewer. Cannot proceed to approval."]

    if gate_status == GATE_STATUS_REJECTED:
        return ["Row rejected by reviewer. Cannot proceed to approval."]

    # blocked — enumerate all contributing reasons.
    reasons: list[str] = []
    readiness_status = str(readiness.get("status") or "")
    can_proceed = bool(readiness.get("can_proceed_to_approval", False))
    draft = row.get("approved_canonical_metadata_draft")

    if readiness_status == _READINESS_BLOCKED:
        reasons.append(f"Row approval_readiness.status is '{_READINESS_BLOCKED}'.")
    if not can_proceed:
        reasons.append("approval_readiness.can_proceed_to_approval is False.")
    unresolved = readiness.get("unresolved_blockers") or []
    if unresolved:
        reasons.append(f"Unresolved blocking fields: {', '.join(sorted(unresolved))}.")
    if not draft:
        reasons.append("approved_canonical_metadata_draft is empty or missing.")

    if not reasons:
        reasons.append("Row does not meet approval criteria.")

    return reasons


def _build_row_approval_gate(
    gate_status: str,
    row: dict[str, Any],
    approved_at: str,
) -> dict[str, Any]:
    """
    Build the row.approval_gate dict conforming to sblt.row_approval_gate.v1.

    approved_at is only set for rows with gate_status == approved.
    """
    reasons = _build_gate_reasons(gate_status, row)
    can_continue = gate_status == GATE_STATUS_APPROVED
    return {
        "schema_version": ROW_APPROVAL_GATE_SCHEMA_VERSION,
        "status": gate_status,
        "can_continue_to_loading_handoff": can_continue,
        "reasons": reasons,
        "approved_at": approved_at if can_continue else None,
        "source_review_decision_package": SOURCE_REVIEW_DECISION_PACKAGE_SCHEMA,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_approval_gate(
    session: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Run the SBLT-8 approval gate over an entire session.

    Reads:
      - row.approval_readiness          (from SBLT-7)
      - row.approved_canonical_metadata_draft  (from SBLT-7)

    Produces (per row):
      - row.approval_gate               (new in SBLT-8)
      - row.approved_canonical_metadata (new in SBLT-8; None for non-approved rows)

    Produces (session level):
      - approval_package  conforming to sblt.approval_package.v1

    Does NOT modify:
      - row.status
      - row.actions
      - row.metadata_evidence
      - row.review_decisions
      - row.approved_canonical_metadata_draft
      - row.approval_readiness
      - any other SBLT-1..7 field

    Returns:
        (updated_rows, approval_package)
    """
    session_id = str(session.get("session_id") or "")
    rows: list[dict[str, Any]] = list(session.get("rows") or [])
    now = _utc_now()

    approved_row_ids: list[str] = []
    held_row_ids: list[str] = []
    rejected_row_ids: list[str] = []
    blocked_row_ids: list[str] = []
    rows_with_missing_canonical_metadata = 0

    updated_rows: list[dict[str, Any]] = []

    for row in rows:
        row_id = str(row.get("row_id") or "")
        gate_status = _gate_status_for_row(row)
        approval_gate = _build_row_approval_gate(gate_status, row, now)

        if gate_status == GATE_STATUS_APPROVED:
            # Promote draft to approved canonical metadata.
            draft = row.get("approved_canonical_metadata_draft") or {}
            approved_canonical_metadata: dict[str, Any] | None = dict(draft)
            approved_row_ids.append(row_id)
        else:
            approved_canonical_metadata = None
            if gate_status == GATE_STATUS_HELD:
                held_row_ids.append(row_id)
            elif gate_status == GATE_STATUS_REJECTED:
                rejected_row_ids.append(row_id)
            elif gate_status == GATE_STATUS_BLOCKED:
                blocked_row_ids.append(row_id)
                # Track rows that were blocked solely due to missing canonical metadata
                # (i.e., readiness says can_proceed but draft is empty — unusual edge case).
                draft = row.get("approved_canonical_metadata_draft")
                readiness = row.get("approval_readiness") or {}
                if not draft and bool(readiness.get("can_proceed_to_approval", False)):
                    rows_with_missing_canonical_metadata += 1

        # Use make_approval_gate_row from sblt_models to build the updated row.
        from .sblt_models import make_approval_gate_row
        updated_rows.append(
            make_approval_gate_row(
                row,
                approval_gate=approval_gate,
                approved_canonical_metadata=approved_canonical_metadata,
            )
        )

    total_rows = len(updated_rows)
    has_approved = len(approved_row_ids) > 0

    approval_package: dict[str, Any] = {
        "schema_version": APPROVAL_PACKAGE_SCHEMA_VERSION,
        "session_id": session_id,
        "created_at": now,
        "source_session_status": str(session.get("status") or ""),
        "summary": {
            "total_rows": total_rows,
            "approved_rows": len(approved_row_ids),
            "held_rows": len(held_row_ids),
            "rejected_rows": len(rejected_row_ids),
            "blocked_rows": len(blocked_row_ids),
            "approval_ready_rows": len(approved_row_ids),
            "rows_with_missing_canonical_metadata": rows_with_missing_canonical_metadata,
        },
        "approved_rows": approved_row_ids,
        "held_rows": held_row_ids,
        "rejected_rows": rejected_row_ids,
        "blocked_rows": blocked_row_ids,
        "session_loading_readiness": {
            "has_approved_rows": has_approved,
            "can_continue_to_loading_handoff": has_approved,
            "can_register": False,   # Never True in SBLT-8.
            "can_convert": False,    # Never True in SBLT-8.
        },
    }

    return updated_rows, approval_package
