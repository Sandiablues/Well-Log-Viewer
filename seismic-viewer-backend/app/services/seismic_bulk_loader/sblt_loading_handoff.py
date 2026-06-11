"""
SBLT-9: Loading / Conversion Handoff Preparation.

Pure-computation module.  No file reads.  No SEG-Y reads.  No MSI.
No Managed Data.  No conversion/indexing.  No job queueing.  No frontend.
Session-local only.

Takes a session with SBLT-8 approval gate outputs and produces:
  - per-row:   loading_handoff  (added to each row)
  - session:   loading_handoff_package

Ownership: backend SBLT service — SBLT-9 only.

Architecture guarantees:
  - Does NOT modify row.status, row.actions, row.metadata_evidence, or any prior
    SBLT field.
  - Does NOT read SEG-Y files, supporting documents, or any filesystem path.
  - Does NOT queue jobs, execute conversion, register MSI, or write artifacts.
  - Does NOT query MSI, Managed Data, or Source Intake.
  - can_register is always False.
  - can_convert is always False.
  - can_expose_to_managed_data is always False.
  - job_request.status is always "prepared" — no backend job id is ever created.
  - can_continue_to_job_queueing is True only when at least one handoff item is
    prepared — this is readiness for SBLT-10 only, NOT operational execution.

Deterministic IDs:
  handoff_item_id : sblt_handoff_{row_id}
  job_request_id  : sblt_jobreq_{row_id}

  row_id already embeds the session_id, preserving full traceability.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Schema version constants
# ---------------------------------------------------------------------------

LOADING_HANDOFF_PACKAGE_SCHEMA_VERSION = "sblt.loading_handoff_package.v1"
ROW_LOADING_HANDOFF_SCHEMA_VERSION = "sblt.row_loading_handoff.v1"

# ---------------------------------------------------------------------------
# Handoff status vocabulary
# ---------------------------------------------------------------------------

HANDOFF_STATUS_PREPARED = "prepared"
HANDOFF_STATUS_SKIPPED  = "skipped"
HANDOFF_STATUS_BLOCKED  = "blocked"

# ---------------------------------------------------------------------------
# Representation and job-type maps
# ---------------------------------------------------------------------------

# Supported record types and their Zarr representation targets.
SUPPORTED_RECORD_TYPES: frozenset[str] = frozenset({"2d_line", "3d_volume"})

REPRESENTATION_MAP: dict[str, str] = {
    "2d_line":   "zarr_section_2d",
    "3d_volume": "zarr_volume",
}

JOB_TYPE_MAP: dict[str, str] = {
    "2d_line":   "segy_to_zarr_2d",
    "3d_volume": "segy_to_zarr_3d",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _segy_path_valid(row: dict[str, Any]) -> tuple[bool, str]:
    """
    Return (is_valid, resolved_path_str) for the row's stored SEG-Y path result.

    Uses path_validation.summary.segy_valid as the primary signal (SBLT-4
    calculates this from exists + is_file + readable).  Falls back to reading
    those flags directly if summary is absent.

    No filesystem check is performed — this is a pure read of stored session data.
    """
    path_val: dict = row.get("path_validation") or {}

    # Primary: use SBLT-4 computed summary flag.
    summary: dict = path_val.get("summary") or {}
    if "segy_valid" in summary:
        is_valid = bool(summary["segy_valid"])
    else:
        # Fallback: compute from segy block (same logic SBLT-4 and SBLT-5 use).
        segy_info: dict = path_val.get("segy") or {}
        is_valid = bool(
            segy_info.get("exists")
            and segy_info.get("is_file")
            and segy_info.get("readable")
        )

    segy_info: dict = path_val.get("segy") or {}
    resolved_path = str(segy_info.get("resolved_path") or "").strip()

    return is_valid, resolved_path


def _get_record_type(row: dict[str, Any]) -> str:
    """
    Return the effective record_type for the row.

    Preference order:
    1. approved_canonical_metadata.record_type  (SBLT-8 approved value)
    2. row.record_type                          (SBLT-2 parsed value)

    Returns "unknown" if neither is present.
    """
    acm: dict = row.get("approved_canonical_metadata") or {}
    rt = str(acm.get("record_type") or "").strip()
    if not rt:
        rt = str(row.get("record_type") or "").strip()
    return rt or "unknown"


def _make_prepared_job_request(
    row_id: str,
    record_type: str,
    created_at: str,
) -> dict[str, Any]:
    """Build a prepared job request record.  Status is always 'prepared'."""
    return {
        "job_request_id": f"sblt_jobreq_{row_id}",
        "job_type": JOB_TYPE_MAP[record_type],
        "status": "prepared",
        "created_at": created_at,
    }


def _make_row_handoff(
    row_id: str,
    *,
    status: str,
    source_segy_path: str | None,
    record_type: str | None,
    requested_representation: str | None,
    job_request: dict[str, Any] | None,
    reasons: list[str],
) -> dict[str, Any]:
    """Build a row.loading_handoff dict conforming to sblt.row_loading_handoff.v1."""
    return {
        "schema_version": ROW_LOADING_HANDOFF_SCHEMA_VERSION,
        "handoff_item_id": f"sblt_handoff_{row_id}",
        "status": status,
        "source_segy_path": source_segy_path,
        "record_type": record_type,
        "requested_representation": requested_representation,
        "approved_canonical_metadata_ref": "row.approved_canonical_metadata",
        "job_request": job_request,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def prepare_loading_handoff(
    session: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Build loading handoff records from an SBLT-8-approved session.

    Reads (per row):
      - row.approval_gate           (from SBLT-8)
      - row.approved_canonical_metadata  (from SBLT-8)
      - row.path_validation         (from SBLT-4)
      - row.record_type             (from SBLT-2/3)

    Produces (per row):
      - row.loading_handoff         (new in SBLT-9)

    Produces (session level):
      - loading_handoff_package     conforming to sblt.loading_handoff_package.v1

    Does NOT modify:
      - row.status
      - row.actions
      - row.metadata_evidence
      - row.review_decisions
      - row.approved_canonical_metadata_draft
      - row.approval_readiness
      - row.approval_gate
      - row.approved_canonical_metadata
      - session.approval_package
      - any other SBLT-1..8 field

    Row classification:
      held / rejected rows     → loading_handoff.status = "skipped"
      blocked rows             → loading_handoff.status = "blocked"
      approved rows (all OK)   → loading_handoff.status = "prepared"
      approved rows (missing   → loading_handoff.status = "blocked"
        SEG-Y / ACM / record_type)

    Returns:
        (updated_rows, loading_handoff_package)
    """
    from .sblt_models import make_loading_handoff_row

    session_id = str(session.get("session_id") or "")
    rows: list[dict[str, Any]] = list(session.get("rows") or [])
    now = _utc_now()

    updated_rows: list[dict[str, Any]] = []
    handoff_item_ids: list[str] = []   # prepared handoff_item_ids
    skipped_row_ids: list[str] = []
    blocked_row_ids: list[str] = []
    approved_rows_seen: int = 0
    job_requests_created: int = 0

    for row in rows:
        row_id = str(row.get("row_id") or "")
        approval_gate: dict = row.get("approval_gate") or {}
        gate_status = str(approval_gate.get("status") or "").strip()
        can_continue = bool(approval_gate.get("can_continue_to_loading_handoff", False))

        # ------------------------------------------------------------------ #
        # SKIPPED: held or rejected at approval gate                          #
        # ------------------------------------------------------------------ #
        if gate_status in ("held", "rejected"):
            lh = _make_row_handoff(
                row_id,
                status=HANDOFF_STATUS_SKIPPED,
                source_segy_path=None,
                record_type=None,
                requested_representation=None,
                job_request=None,
                reasons=[
                    f"Row {gate_status} at approval gate. "
                    "Skipped from loading handoff."
                ],
            )
            skipped_row_ids.append(row_id)
            updated_rows.append(make_loading_handoff_row(row, loading_handoff=lh))
            continue

        # ------------------------------------------------------------------ #
        # APPROVED: validate all handoff requirements                         #
        # ------------------------------------------------------------------ #
        if gate_status == "approved" and can_continue:
            approved_rows_seen += 1
            block_reasons: list[str] = []

            # Requirement 1: approved_canonical_metadata present and non-empty.
            acm = row.get("approved_canonical_metadata")
            if not acm:
                block_reasons.append(
                    "approved_canonical_metadata is absent or empty."
                )

            # Requirement 2: valid source SEG-Y path in stored path_validation.
            segy_valid, resolved_path = _segy_path_valid(row)
            if not segy_valid or not resolved_path:
                block_reasons.append(
                    "Valid source SEG-Y path is absent or not marked accessible "
                    "in path_validation."
                )

            # Requirement 3: supported record_type.
            record_type = _get_record_type(row)
            if record_type not in SUPPORTED_RECORD_TYPES:
                block_reasons.append(
                    f"Unsupported record_type: {record_type!r}. "
                    f"Supported types: {sorted(SUPPORTED_RECORD_TYPES)}."
                )

            if block_reasons:
                # Approved at gate but cannot proceed to handoff — blocked.
                lh = _make_row_handoff(
                    row_id,
                    status=HANDOFF_STATUS_BLOCKED,
                    source_segy_path=resolved_path if resolved_path else None,
                    record_type=record_type if record_type else None,
                    requested_representation=None,
                    job_request=None,
                    reasons=block_reasons,
                )
                blocked_row_ids.append(row_id)
                updated_rows.append(make_loading_handoff_row(row, loading_handoff=lh))
                continue

            # All requirements met — build prepared handoff item.
            requested_representation = REPRESENTATION_MAP[record_type]
            job_request = _make_prepared_job_request(row_id, record_type, now)

            lh = _make_row_handoff(
                row_id,
                status=HANDOFF_STATUS_PREPARED,
                source_segy_path=resolved_path,
                record_type=record_type,
                requested_representation=requested_representation,
                job_request=job_request,
                reasons=[],
            )
            handoff_item_ids.append(f"sblt_handoff_{row_id}")
            job_requests_created += 1
            updated_rows.append(make_loading_handoff_row(row, loading_handoff=lh))
            continue

        # ------------------------------------------------------------------ #
        # BLOCKED: gate status == blocked, or inconsistent gate state          #
        # ------------------------------------------------------------------ #
        block_reasons_gate: list[str] = []
        if gate_status == "blocked":
            block_reasons_gate.append("Row blocked at approval gate.")
        elif not can_continue:
            block_reasons_gate.append(
                "approval_gate.can_continue_to_loading_handoff is False."
            )
        else:
            block_reasons_gate.append(
                f"Inconsistent approval gate state: "
                f"gate_status={gate_status!r}, "
                f"can_continue_to_loading_handoff={can_continue!r}."
            )

        lh = _make_row_handoff(
            row_id,
            status=HANDOFF_STATUS_BLOCKED,
            source_segy_path=None,
            record_type=None,
            requested_representation=None,
            job_request=None,
            reasons=block_reasons_gate,
        )
        blocked_row_ids.append(row_id)
        updated_rows.append(make_loading_handoff_row(row, loading_handoff=lh))

    # ------------------------------------------------------------------ #
    # Build loading_handoff_package                                        #
    # ------------------------------------------------------------------ #
    total_rows = len(rows)
    handoff_items_created = len(handoff_item_ids)
    has_handoff_items = handoff_items_created > 0

    loading_handoff_package: dict[str, Any] = {
        "schema_version": LOADING_HANDOFF_PACKAGE_SCHEMA_VERSION,
        "session_id": session_id,
        "created_at": now,
        "source_session_status": str(session.get("status") or ""),
        "summary": {
            "total_rows": total_rows,
            "approved_rows_seen": approved_rows_seen,
            "handoff_items_created": handoff_items_created,
            "rows_skipped": len(skipped_row_ids),
            "rows_blocked": len(blocked_row_ids),
            "job_requests_created": job_requests_created,
            "job_requests_failed": 0,
        },
        "handoff_items": handoff_item_ids,
        "skipped_rows": skipped_row_ids,
        "blocked_rows": blocked_row_ids,
        "session_handoff_readiness": {
            "has_handoff_items": has_handoff_items,
            "can_continue_to_job_queueing": has_handoff_items,
            "can_register": False,
            "can_expose_to_managed_data": False,
            "can_convert": False,
        },
    }

    return updated_rows, loading_handoff_package
