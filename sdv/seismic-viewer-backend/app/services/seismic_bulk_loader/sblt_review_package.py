"""
SBLT-6: MDE Review Exception Packager.

Converts row-level MDE review states into a session-level, batch-oriented
review package that identifies:
  - rows ready to proceed without manual review
  - rows requiring review, with per-field exception details
  - conflicts, missing required, missing recommended, suggested candidates
  - auto-accepted technical fields
  - blocked rows with blocking reasons
  - session-local duplicate risk groups
  - session-level bulk action suggestions

Architecture rules (enforced here):
  - Does NOT approve rows.
  - Does NOT register MSI records.
  - Does NOT trigger conversion or indexing.
  - Does NOT query MSI.
  - Does NOT query Managed Data.
  - Does NOT inspect Source Intake.
  - Does NOT read SEG-Y files or trace data.
  - Does NOT build geometry.
  - Does NOT modify MDE bundles.
  - Duplicate detection is session-local ONLY.
  - Can_register remains False.
  - review_package SUMMARISES metadata_evidence; it does NOT replace it.

No SBLT session service imports.  No MDE builder imports.  No file I/O.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REVIEW_PACKAGE_SCHEMA_VERSION = "sblt.review_package.v1"

# MDE field_review classification constants (mirrors mde_models to avoid import)
_CLS_NO_ACTION = "no_action_required"
_CLS_AUTO_ACCEPTED = "auto_accepted"
_CLS_SUGGESTED_REVIEW = "suggested_review"
_CLS_MISSING_REQUIRED = "missing_required"
_CLS_MISSING_RECOMMENDED = "missing_recommended"
_CLS_CONFLICT = "conflict"
_CLS_MANUAL_REQUIRED = "manual_required"
_CLS_POLICY_REVIEW = "policy_review_required"
_CLS_BLOCKED = "blocked"

# Row status constants
_STATUS_BLOCKED = "blocked"
_STATUS_REVIEW_REQUIRED = "review_required"
_STATUS_READY = "ready"

# Classifications that produce a field_exception entry (require active user attention)
_EXCEPTION_CLASSIFICATIONS: frozenset = frozenset({
    _CLS_CONFLICT,
    _CLS_MISSING_REQUIRED,
    _CLS_SUGGESTED_REVIEW,
    _CLS_MANUAL_REQUIRED,
    _CLS_POLICY_REVIEW,
    _CLS_BLOCKED,
})

# SBLT QAQC flag codes that indicate missing required fields at the schema level
_SBLT_REQUIRED_MISSING_CODES: frozenset = frozenset({
    "MISSING_REQUIRED_FIELD",
    "MISSING_CONDITIONAL_FIELD",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_group_id() -> str:
    return f"dup_{secrets.token_hex(6)}"


def _make_field_exception(field: str, fr_entry: dict[str, Any]) -> dict[str, Any]:
    """
    Build a field exception from an MDE field_review entry.

    All values are read directly from the field_review dict; nothing is
    modified or approved.
    """
    classification = str(fr_entry.get("classification") or "unknown")
    submitted = fr_entry.get("submitted_value")
    candidate = fr_entry.get("candidate_value")
    requires_review = bool(fr_entry.get("requires_user_review", False))
    bulk_eligible = bool(fr_entry.get("bulk_action_eligible", False))
    ev_ids = list(fr_entry.get("related_evidence_ids") or [])
    finding_ids = list(fr_entry.get("related_finding_ids") or [])

    message = (
        f"Field {field!r} has classification {classification!r} and requires attention."
    )

    return {
        "field": field,
        "classification": classification,
        "submitted_value": submitted,
        "candidate_value": candidate,
        "requires_user_review": requires_review,
        "bulk_action_eligible": bulk_eligible,
        "related_evidence_ids": ev_ids,
        "related_finding_ids": finding_ids,
        "message": message,
    }


def _make_sblt_required_field_exception(field: str, flag: dict[str, Any]) -> dict[str, Any]:
    """
    Build a field exception from an SBLT-2 required-field blocker flag.

    Used when a required field is missing at the SBLT schema level and the
    MDE bundle is empty (blocked row).  No approval state is set.
    """
    return {
        "field": field,
        "classification": _CLS_MISSING_REQUIRED,
        "submitted_value": None,
        "candidate_value": None,
        "requires_user_review": True,
        "bulk_action_eligible": False,
        "related_evidence_ids": [],
        "related_finding_ids": [],
        "message": str(flag.get("message") or f"Required field {field!r} is missing."),
    }


# ---------------------------------------------------------------------------
# Row review builder
# ---------------------------------------------------------------------------

def _build_review_row(row: dict[str, Any]) -> dict[str, Any]:
    """
    Build one review-row item from a SBLT session row dict.

    Reads from:
      row.status
      row.record_type
      row.normalized_metadata
      row.path_validation
      row.qaqc_flags
      row.metadata_evidence.field_review
      row.metadata_evidence.review_summary
      row.validation.required_missing
      row.validation.recommended_missing

    Does not modify the row.  Does not approve anything.
    """
    row_id: str = str(row.get("row_id") or "")
    source_row_number: int = int(row.get("source_row_number") or 0)
    row_status: str = str(row.get("status") or _STATUS_BLOCKED)
    record_type: str = str(row.get("record_type") or "unknown")

    nm: dict = row.get("normalized_metadata") or {}
    dataset_label: str = str(nm.get("dataset_label") or "")
    dataset_key: str = str(nm.get("dataset_key") or "")

    # Source reference: prefer resolved SEG-Y path from path_validation.
    path_val: dict = row.get("path_validation") or {}
    segy_pv: dict = path_val.get("segy") or {}
    resolved_path: str = str(segy_pv.get("resolved_path") or "")
    source_reference: str = resolved_path or str(nm.get("segy_path_raw") or "")

    # ------------------------------------------------------------------ #
    # Blocking flags from SBLT operational QAQC                           #
    # ------------------------------------------------------------------ #
    qaqc_flags: list = list(row.get("qaqc_flags") or [])
    blocking_flags: list = [f for f in qaqc_flags if f.get("severity") == "blocker"]

    # ------------------------------------------------------------------ #
    # SBLT-2 schema-level missing fields                                   #
    # ------------------------------------------------------------------ #
    validation: dict = row.get("validation") or {}
    sblt_required_missing: list[str] = list(validation.get("required_missing") or [])
    sblt_recommended_missing: list[str] = list(validation.get("recommended_missing") or [])

    # ------------------------------------------------------------------ #
    # MDE field_review                                                     #
    # ------------------------------------------------------------------ #
    mde: dict = row.get("metadata_evidence") or {}
    field_review: dict = mde.get("field_review") or {}
    mde_review_summary: dict = mde.get("review_summary") or {}

    # ------------------------------------------------------------------ #
    # Classify fields from MDE field_review                                #
    # ------------------------------------------------------------------ #
    field_exceptions: list[dict] = []
    auto_accepted_fields: list[str] = []
    suggested_candidates: list[str] = []
    conflicts: list[str] = []
    missing_required: list[str] = []
    missing_recommended: list[str] = []

    for field, fr_entry in sorted(field_review.items()):
        cls: str = str(fr_entry.get("classification") or "")

        if cls == _CLS_AUTO_ACCEPTED:
            auto_accepted_fields.append(field)
            # auto_accepted does NOT add to field_exceptions

        elif cls == _CLS_SUGGESTED_REVIEW:
            suggested_candidates.append(field)
            field_exceptions.append(_make_field_exception(field, fr_entry))

        elif cls == _CLS_CONFLICT:
            conflicts.append(field)
            field_exceptions.append(_make_field_exception(field, fr_entry))

        elif cls == _CLS_MISSING_REQUIRED:
            missing_required.append(field)
            field_exceptions.append(_make_field_exception(field, fr_entry))

        elif cls == _CLS_MISSING_RECOMMENDED:
            # missing_recommended is informational; does NOT add to field_exceptions
            missing_recommended.append(field)

        elif cls in _EXCEPTION_CLASSIFICATIONS:
            # Catch-all for manual_required, policy_review_required, blocked
            field_exceptions.append(_make_field_exception(field, fr_entry))

    # ------------------------------------------------------------------ #
    # Supplement missing_required from SBLT-2 schema validation           #
    #                                                                      #
    # For blocked rows, the MDE bundle is empty (no field_review entries). #
    # We populate missing_required from the SBLT-2 validation block so    #
    # callers can identify which required fields were absent.              #
    # ------------------------------------------------------------------ #
    sblt_blocker_by_field: dict[str, dict] = {}
    for flag in blocking_flags:
        field_name: str = str(flag.get("field") or "")
        if field_name and flag.get("code") in _SBLT_REQUIRED_MISSING_CODES:
            sblt_blocker_by_field[field_name] = flag

    for field_name in sblt_required_missing:
        if field_name not in missing_required:
            missing_required.append(field_name)
            # Only add a field_exception if not already present from MDE
            if not any(fe["field"] == field_name for fe in field_exceptions):
                flag = sblt_blocker_by_field.get(
                    field_name,
                    {"message": f"Required field {field_name!r} is missing."},
                )
                field_exceptions.append(
                    _make_sblt_required_field_exception(field_name, flag)
                )

    # Supplement missing_recommended from SBLT-2 schema validation
    for field_name in sblt_recommended_missing:
        if field_name not in missing_recommended:
            missing_recommended.append(field_name)

    # ------------------------------------------------------------------ #
    # Determine review_classification                                      #
    # ------------------------------------------------------------------ #
    if row_status == _STATUS_BLOCKED:
        review_classification = _STATUS_BLOCKED
    elif (
        bool(mde_review_summary.get("requires_user_review", False))
        or bool(field_exceptions)
    ):
        review_classification = _STATUS_REVIEW_REQUIRED
    else:
        review_classification = _STATUS_READY

    return {
        "row_id": row_id,
        "source_row_number": source_row_number,
        "row_status": row_status,
        "record_type": record_type,
        "dataset_label": dataset_label,
        "dataset_key": dataset_key,
        "source_reference": source_reference,
        "review_classification": review_classification,
        "field_exceptions": field_exceptions,
        "auto_accepted_fields": auto_accepted_fields,
        "suggested_candidates": suggested_candidates,
        "conflicts": conflicts,
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "blocking_flags": blocking_flags,
        "review_summary": mde_review_summary,
    }


# ---------------------------------------------------------------------------
# Duplicate group detection (session-local only)
# ---------------------------------------------------------------------------

def _detect_duplicate_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Detect session-local duplicate risk groups.

    Three risk types:
      1. dataset_key_duplicate      — same normalized_metadata.dataset_key
      2. source_reference_duplicate — same resolved SEG-Y path
      3. line_or_volume_duplicate   — same survey+line (2D) or survey+volume (3D)

    Does NOT block rows.  Returns warning-severity groups only.
    Session-local only — does NOT query MSI or Managed Data.
    """
    # Maps: match_key → list of {row_id, srn, dataset_label}
    dataset_key_map: dict[str, list[dict]] = {}
    source_ref_map: dict[str, list[dict]] = {}
    identity_map: dict[str, list[dict]] = {}

    for row in rows:
        row_id: str = str(row.get("row_id") or "")
        srn: int = int(row.get("source_row_number") or 0)
        nm: dict = row.get("normalized_metadata") or {}
        record_type: str = str(row.get("record_type") or "unknown")
        dataset_label: str = str(nm.get("dataset_label") or "")

        member = {"row_id": row_id, "srn": srn, "dataset_label": dataset_label}

        # 1. dataset_key duplicate
        dk: str = str(nm.get("dataset_key") or "").strip()
        if dk:
            dataset_key_map.setdefault(dk, []).append(member)

        # 2. source_reference duplicate (resolved SEG-Y path)
        path_val: dict = row.get("path_validation") or {}
        segy_pv: dict = path_val.get("segy") or {}
        resolved: str = str(segy_pv.get("resolved_path") or "").strip()
        if resolved:
            source_ref_map.setdefault(resolved, []).append(member)

        # 3. line_or_volume duplicate
        survey_key: str = str(nm.get("survey_name_normalized") or "").strip()
        if record_type == "2d_line":
            detail_key: str = str(nm.get("line_name_normalized") or "").strip()
            if survey_key and detail_key:
                ident_key = f"2d_line__{survey_key}__{detail_key}"
                identity_map.setdefault(ident_key, []).append(member)
        elif record_type == "3d_volume":
            detail_key = str(nm.get("volume_name_normalized") or "").strip()
            if survey_key and detail_key:
                ident_key = f"3d_volume__{survey_key}__{detail_key}"
                identity_map.setdefault(ident_key, []).append(member)

    groups: list[dict[str, Any]] = []

    for dk, members in sorted(dataset_key_map.items()):
        if len(members) >= 2:
            groups.append({
                "group_id": _gen_group_id(),
                "risk_type": "dataset_key_duplicate",
                "severity": "warning",
                "match_key": dk,
                "row_ids": [m["row_id"] for m in members],
                "source_row_numbers": [m["srn"] for m in members],
                "dataset_labels": [m["dataset_label"] for m in members],
                "message": (
                    f"Multiple rows share dataset_key {dk!r}. "
                    "Possible duplicate submission."
                ),
            })

    for ref, members in sorted(source_ref_map.items()):
        if len(members) >= 2:
            groups.append({
                "group_id": _gen_group_id(),
                "risk_type": "source_reference_duplicate",
                "severity": "warning",
                "match_key": ref,
                "row_ids": [m["row_id"] for m in members],
                "source_row_numbers": [m["srn"] for m in members],
                "dataset_labels": [m["dataset_label"] for m in members],
                "message": (
                    "Multiple rows reference the same resolved SEG-Y path. "
                    "Possible duplicate source file."
                ),
            })

    for ik, members in sorted(identity_map.items()):
        if len(members) >= 2:
            groups.append({
                "group_id": _gen_group_id(),
                "risk_type": "line_or_volume_duplicate",
                "severity": "warning",
                "match_key": ik,
                "row_ids": [m["row_id"] for m in members],
                "source_row_numbers": [m["srn"] for m in members],
                "dataset_labels": [m["dataset_label"] for m in members],
                "message": (
                    "Multiple rows share the same survey/line or survey/volume identity. "
                    "Possible duplicate dataset."
                ),
            })

    return groups


# ---------------------------------------------------------------------------
# Session-level review package builder
# ---------------------------------------------------------------------------

def build_review_package_for_session(session: dict[str, Any]) -> dict[str, Any]:
    """
    Build a review package for the given SBLT session dict.

    Args:
        session — a full SBLT session dict (all rows must have metadata_evidence
                  from SBLT-5).

    Returns:
        A review_package dict conforming to sblt.review_package.v1.

    Does NOT modify the session or any rows.
    Does NOT approve rows.
    Does NOT register MSI records.
    """
    session_id: str = str(session.get("session_id") or "")
    source_session_status: str = str(session.get("status") or "")
    rows: list[dict] = list(session.get("rows") or [])

    # ------------------------------------------------------------------ #
    # Build per-row review items                                           #
    # ------------------------------------------------------------------ #
    review_rows: list[dict] = [_build_review_row(row) for row in rows]

    # ------------------------------------------------------------------ #
    # Session-local duplicate detection                                    #
    # ------------------------------------------------------------------ #
    duplicate_groups: list[dict] = _detect_duplicate_groups(rows)

    # ------------------------------------------------------------------ #
    # Compute summary                                                      #
    # ------------------------------------------------------------------ #
    total = len(rows)
    ready_rows = sum(1 for rr in review_rows if rr["review_classification"] == _STATUS_READY)
    review_required_rows = sum(
        1 for rr in review_rows if rr["review_classification"] == _STATUS_REVIEW_REQUIRED
    )
    blocked_rows = sum(
        1 for rr in review_rows if rr["review_classification"] == _STATUS_BLOCKED
    )
    rows_with_conflicts = sum(1 for rr in review_rows if rr["conflicts"])
    rows_with_missing_required = sum(1 for rr in review_rows if rr["missing_required"])
    rows_with_missing_recommended = sum(1 for rr in review_rows if rr["missing_recommended"])
    rows_with_suggested = sum(1 for rr in review_rows if rr["suggested_candidates"])
    rows_with_auto_accepted = sum(1 for rr in review_rows if rr["auto_accepted_fields"])

    dup_risk_row_ids: set[str] = set()
    for grp in duplicate_groups:
        for rid in (grp.get("row_ids") or []):
            dup_risk_row_ids.add(rid)
    dup_group_count = len(duplicate_groups)
    dup_risk_row_count = len(dup_risk_row_ids)

    # ------------------------------------------------------------------ #
    # Session-level bulk action suggestions                                #
    # ------------------------------------------------------------------ #
    bulk_actions: list[str] = []
    if any(rr["auto_accepted_fields"] for rr in review_rows):
        bulk_actions.append("bulk_confirm_auto_accepted")
    if any(rr["suggested_candidates"] for rr in review_rows):
        bulk_actions.append("bulk_accept_suggestions")
    if any(rr["conflicts"] for rr in review_rows):
        bulk_actions.append("bulk_review_conflicts")

    # ------------------------------------------------------------------ #
    # Blocking reasons                                                     #
    # ------------------------------------------------------------------ #
    blocking_reasons: list[str] = []
    if rows_with_missing_required > 0:
        blocking_reasons.append(
            f"{rows_with_missing_required} row(s) have missing required metadata fields."
        )
    if blocked_rows > 0:
        blocking_reasons.append(
            f"{blocked_rows} row(s) are blocked by operational errors "
            "and cannot proceed until resolved."
        )

    # ------------------------------------------------------------------ #
    # Package-level status                                                 #
    # ------------------------------------------------------------------ #
    has_blockers: bool = blocked_rows > 0
    requires_user_review: bool = review_required_rows > 0
    can_continue: bool = not has_blockers and not requires_user_review

    return {
        "schema_version": REVIEW_PACKAGE_SCHEMA_VERSION,
        "session_id": session_id,
        "created_at": _utc_now(),
        "source_session_status": source_session_status,
        "summary": {
            "total_rows": total,
            "ready_rows": ready_rows,
            "review_required_rows": review_required_rows,
            "blocked_rows": blocked_rows,
            "rows_with_conflicts": rows_with_conflicts,
            "rows_with_missing_required": rows_with_missing_required,
            "rows_with_missing_recommended": rows_with_missing_recommended,
            "rows_with_suggested_candidates": rows_with_suggested,
            "rows_with_auto_accepted_fields": rows_with_auto_accepted,
            "duplicate_group_count": dup_group_count,
            "duplicate_risk_row_count": dup_risk_row_count,
        },
        "review_rows": review_rows,
        "duplicate_groups": duplicate_groups,
        "bulk_actions": bulk_actions,
        "blocking_reasons": blocking_reasons,
        "status": {
            "can_continue_to_approval": can_continue,
            "requires_user_review": requires_user_review,
            "has_blockers": has_blockers,
        },
    }
