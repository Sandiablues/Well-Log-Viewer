"""
SBLT-7: Review Decision Applicator and Canonical Metadata Draft Builder.

Converts user-supplied review decisions and system-derived safe defaults into:
  - row.review_decisions                  — per-field decision record
  - row.approved_canonical_metadata_draft — draft canonical values for all resolved fields
  - row.approval_readiness                — per-row readiness status and blocker summary
  - session.review_decision_package       — session-level summary of decisions applied

Architecture rules (enforced here):
  - Backend-only.  No file reads.  No SEG-Y reads.  No folder scans.
  - MDE-driven: reads metadata_evidence.field_review, submitted_metadata, candidate_metadata.
  - Does NOT modify MDE bundles — metadata_evidence is read-only in this module.
  - Review decisions are stored separately from metadata_evidence (non-destructive).
  - Canonical metadata draft is derived only from explicit decisions and safe auto-defaults.
  - can_register remains False.
  - approved_for_loading remains False.
  - Does NOT approve session for conversion or loading.
  - Does NOT register MSI records.
  - Does NOT query MSI, Managed Data, or Source Intake.
  - Does NOT read SEG-Y files or trace data.
  - Does NOT build geometry.
  - Session-scope only — no cross-session operations.

No SBLT session service imports.  No MDE builder imports.  No file I/O.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

REVIEW_DECISION_PACKAGE_SCHEMA_VERSION = "sblt.review_decision_package.v1"

# ---------------------------------------------------------------------------
# Decision type constants (user-supplied)
# ---------------------------------------------------------------------------

DECISION_ACCEPT_AUTO_ACCEPTED = "accept_auto_accepted"
"""User confirms a field that was already auto-accepted from a high-authority source."""

DECISION_ACCEPT_CANDIDATE = "accept_candidate"
"""User accepts a suggested candidate value (e.g. from textual header or AI suggestion)."""

DECISION_RESOLVE_CONFLICT = "resolve_conflict"
"""User resolves a conflict between submitted and candidate values; may supply override."""

DECISION_SUPPLY_VALUE = "supply_value"
"""User supplies a value for a field that is missing from submitted metadata."""

DECISION_DEFER = "defer"
"""User explicitly defers a field; value is NOT included in the canonical draft."""

VALID_USER_DECISION_TYPES: frozenset = frozenset({
    DECISION_ACCEPT_AUTO_ACCEPTED,
    DECISION_ACCEPT_CANDIDATE,
    DECISION_RESOLVE_CONFLICT,
    DECISION_SUPPLY_VALUE,
    DECISION_DEFER,
})

# ---------------------------------------------------------------------------
# System-applied decision types (not user-supplied)
# ---------------------------------------------------------------------------

DECISION_SYS_NO_ACTION = "system_no_action"
"""System auto-resolved: field classification is no_action_required; submitted value used."""

DECISION_SYS_AUTO_ACCEPTED = "system_auto_accepted"
"""System auto-resolved: field classification is auto_accepted; candidate value used."""

# ---------------------------------------------------------------------------
# Decision source constants
# ---------------------------------------------------------------------------

DECISION_SOURCE_USER = "user"
DECISION_SOURCE_SYSTEM_BULK = "system_bulk"
DECISION_SOURCE_SYSTEM_AUTO = "system_auto"

# ---------------------------------------------------------------------------
# Row action constants
# ---------------------------------------------------------------------------

ROW_ACTION_PROCEED = "proceed"
"""Row proceeds toward approval (default)."""

ROW_ACTION_HOLD = "hold"
"""Row is held from this batch; decisions preserved, approval blocked."""

ROW_ACTION_REJECT = "reject"
"""Row is rejected from this batch; decisions preserved, approval blocked."""

VALID_ROW_ACTIONS: frozenset = frozenset({
    ROW_ACTION_PROCEED,
    ROW_ACTION_HOLD,
    ROW_ACTION_REJECT,
})

# ---------------------------------------------------------------------------
# Approval readiness status constants
# ---------------------------------------------------------------------------

READINESS_DRAFT_APPROVED = "draft_approved"
"""No blocking unresolved fields; row is eligible for approval gate."""

READINESS_BLOCKED = "blocked"
"""One or more blocking fields remain unresolved; row cannot proceed."""

READINESS_HELD = "held"
"""Row action is hold; approval is suspended for this batch."""

READINESS_REJECTED = "rejected"
"""Row action is reject; row is excluded from this batch."""

# ---------------------------------------------------------------------------
# MDE field_review classification mirrors
# (mirrors mde_models constants to avoid cross-package import)
# ---------------------------------------------------------------------------

_CLS_NO_ACTION = "no_action_required"
_CLS_AUTO_ACCEPTED = "auto_accepted"
_CLS_SUGGESTED_REVIEW = "suggested_review"
_CLS_MISSING_REQUIRED = "missing_required"
_CLS_MISSING_RECOMMENDED = "missing_recommended"
_CLS_CONFLICT = "conflict"
_CLS_MANUAL_REQUIRED = "manual_required"
_CLS_POLICY_REVIEW = "policy_review_required"
_CLS_BLOCKED = "blocked"

# Classifications that block approval_readiness if no decision is applied.
_BLOCKING_CLASSIFICATIONS: frozenset = frozenset({
    _CLS_MISSING_REQUIRED,
    _CLS_CONFLICT,
    _CLS_MANUAL_REQUIRED,
    _CLS_POLICY_REVIEW,
    _CLS_BLOCKED,
})

# Classifications that are informational / non-blocking.
_NONBLOCKING_REVIEW_CLASSIFICATIONS: frozenset = frozenset({
    _CLS_MISSING_RECOMMENDED,
    _CLS_SUGGESTED_REVIEW,
})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_field_decision(
    *,
    field: str,
    decision: str,
    decided_value: Any,
    decided_value_source: str | None,
    decision_source: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """
    Build a single field decision record.

    decided_value_source describes where the decided_value came from:
      "submitted"  — taken from submitted metadata
      "candidate"  — taken from candidate/evidence metadata
      "supplied"   — explicitly supplied by the user in this request
      None         — deferred (no value in canonical draft)
    """
    return {
        "field": field,
        "decision": decision,
        "decided_value": decided_value,
        "decided_value_source": decided_value_source,
        "decision_source": decision_source,
        "notes": notes,
        "resolved_at": _utc_now(),
    }


def _auto_apply_system_decisions(field_review: dict[str, Any]) -> dict[str, Any]:
    """
    Auto-apply system decisions for fields that need no user input.

    no_action_required — submitted value is trusted; auto-resolved.
    auto_accepted      — safe technical value from high-authority source; auto-resolved.

    Returns a dict of field → field_decision_record for all auto-resolvable fields.
    Does NOT mutate field_review.
    """
    decisions: dict[str, Any] = {}

    for field, fr_entry in sorted(field_review.items()):
        cls = str(fr_entry.get("classification") or "")

        if cls == _CLS_NO_ACTION:
            submitted_value = fr_entry.get("submitted_value")
            decisions[field] = _make_field_decision(
                field=field,
                decision=DECISION_SYS_NO_ACTION,
                decided_value=submitted_value,
                decided_value_source="submitted",
                decision_source=DECISION_SOURCE_SYSTEM_AUTO,
            )

        elif cls == _CLS_AUTO_ACCEPTED:
            candidate_value = fr_entry.get("candidate_value")
            decisions[field] = _make_field_decision(
                field=field,
                decision=DECISION_SYS_AUTO_ACCEPTED,
                decided_value=candidate_value,
                decided_value_source="candidate",
                decision_source=DECISION_SOURCE_SYSTEM_AUTO,
            )

    return decisions


def _apply_explicit_field_decision(
    *,
    field: str,
    fr_entry: dict[str, Any],
    decision_type: str,
    supplied_value: Any,
    decision_source: str,
    notes: str | None,
) -> dict[str, Any] | None:
    """
    Apply a single explicit field decision.

    Returns a field_decision_record dict, or None if decision_type is unrecognised.

    Decision semantics:
      accept_auto_accepted — use the candidate_value already auto-accepted
      accept_candidate     — use the candidate_value from the MDE bundle
      resolve_conflict     — use supplied_value if provided, else fall back to submitted_value
      supply_value         — use supplied_value (caller must provide a non-None value)
      defer                — no value; field is explicitly deferred
    """
    submitted_value = fr_entry.get("submitted_value")
    candidate_value = fr_entry.get("candidate_value")

    if decision_type == DECISION_DEFER:
        return _make_field_decision(
            field=field,
            decision=DECISION_DEFER,
            decided_value=None,
            decided_value_source=None,
            decision_source=decision_source,
            notes=notes,
        )

    if decision_type == DECISION_ACCEPT_AUTO_ACCEPTED:
        # Accept the candidate that was auto-accepted; fall back to submitted if no candidate.
        value = candidate_value if candidate_value is not None else submitted_value
        return _make_field_decision(
            field=field,
            decision=DECISION_ACCEPT_AUTO_ACCEPTED,
            decided_value=value,
            decided_value_source="candidate",
            decision_source=decision_source,
            notes=notes,
        )

    if decision_type == DECISION_ACCEPT_CANDIDATE:
        return _make_field_decision(
            field=field,
            decision=DECISION_ACCEPT_CANDIDATE,
            decided_value=candidate_value,
            decided_value_source="candidate",
            decision_source=decision_source,
            notes=notes,
        )

    if decision_type == DECISION_RESOLVE_CONFLICT:
        # Explicit supplied_value wins; fall back to submitted if none provided.
        if supplied_value is not None:
            value = supplied_value
            value_source = "supplied"
        else:
            value = submitted_value
            value_source = "submitted"
        return _make_field_decision(
            field=field,
            decision=DECISION_RESOLVE_CONFLICT,
            decided_value=value,
            decided_value_source=value_source,
            decision_source=decision_source,
            notes=notes,
        )

    if decision_type == DECISION_SUPPLY_VALUE:
        return _make_field_decision(
            field=field,
            decision=DECISION_SUPPLY_VALUE,
            decided_value=supplied_value,
            decided_value_source="supplied" if supplied_value is not None else None,
            decision_source=decision_source,
            notes=notes,
        )

    # Unrecognised decision_type — skip silently.
    return None


def _build_canonical_draft(merged_decisions: dict[str, Any]) -> dict[str, Any]:
    """
    Build the approved canonical metadata draft from the merged decisions.

    Includes only fields that:
      - Have a non-None decided_value, AND
      - Decision type is not DECISION_DEFER.

    Deferred fields are deliberately excluded.
    Fields whose decided_value is None (e.g. supply_value with None) are excluded.
    """
    draft: dict[str, Any] = {}
    for field, decision_record in sorted(merged_decisions.items()):
        decision_type = str(decision_record.get("decision") or "")
        if decision_type == DECISION_DEFER:
            continue
        decided_value = decision_record.get("decided_value")
        if decided_value is not None:
            draft[field] = decided_value
    return draft


def _compute_approval_readiness(
    *,
    row_status: str,
    field_review: dict[str, Any],
    merged_decisions: dict[str, Any],
    row_action: str,
) -> dict[str, Any]:
    """
    Compute per-row approval readiness after decisions are applied.

    Readiness rules:
      - If row_action = hold   → READINESS_HELD,     can_proceed = False.
      - If row_action = reject → READINESS_REJECTED,  can_proceed = False.
      - If row_status = blocked OR any blocking field has no decision
                                → READINESS_BLOCKED,  can_proceed = False.
      - Otherwise              → READINESS_DRAFT_APPROVED, can_proceed = True.

    Blocking unresolved = fields whose MDE classification is in _BLOCKING_CLASSIFICATIONS
    and for which no decision was applied.

    Non-blocking unresolved = fields whose classification is in
    _NONBLOCKING_REVIEW_CLASSIFICATIONS and for which no decision was applied.
    These are advisory and do NOT block can_proceed_to_approval.
    """
    # Row-level action gates take priority.
    if row_action == ROW_ACTION_HOLD:
        return {
            "status": READINESS_HELD,
            "row_action": row_action,
            "can_proceed_to_approval": False,
            "unresolved_blockers": [],
            "unresolved_review_items": [],
            "draft_approved_fields": [],
            "deferred_fields": [],
        }

    if row_action == ROW_ACTION_REJECT:
        return {
            "status": READINESS_REJECTED,
            "row_action": row_action,
            "can_proceed_to_approval": False,
            "unresolved_blockers": [],
            "unresolved_review_items": [],
            "draft_approved_fields": [],
            "deferred_fields": [],
        }

    # row_action == "proceed" — evaluate field-level resolution.
    unresolved_blockers: list[str] = []
    unresolved_review_items: list[str] = []
    draft_approved_fields: list[str] = []
    deferred_fields: list[str] = []

    for field, fr_entry in sorted(field_review.items()):
        cls = str(fr_entry.get("classification") or "")
        decision_record = merged_decisions.get(field)

        if decision_record is not None:
            decision_type = str(decision_record.get("decision") or "")
            if decision_type == DECISION_DEFER:
                deferred_fields.append(field)
            elif decision_record.get("decided_value") is not None:
                draft_approved_fields.append(field)
            # DECISION_SYS_NO_ACTION / DECISION_SYS_AUTO_ACCEPTED with None value are
            # unusual (e.g. submitted_value=None on no_action_required) — omit from draft.
        else:
            # No decision was applied to this field.
            if cls in _BLOCKING_CLASSIFICATIONS:
                unresolved_blockers.append(field)
            elif cls in _NONBLOCKING_REVIEW_CLASSIFICATIONS:
                unresolved_review_items.append(field)
            # _CLS_NO_ACTION and _CLS_AUTO_ACCEPTED without system decision:
            # should not occur since _auto_apply_system_decisions covers those.

    # Capture deferred decisions for fields absent from field_review (e.g. fields
    # the user deferred that MDE never classified — they won't appear in the loop above).
    already_seen = (
        set(unresolved_blockers)
        | set(unresolved_review_items)
        | set(draft_approved_fields)
        | set(deferred_fields)
    )
    for field, decision_record in sorted(merged_decisions.items()):
        if field in already_seen:
            continue
        if str(decision_record.get("decision") or "") == DECISION_DEFER:
            deferred_fields.append(field)

    # Row-level blocked status always blocks regardless of field decisions.
    has_row_blocker = (row_status == "blocked")

    can_proceed = (not has_row_blocker) and (len(unresolved_blockers) == 0)

    readiness_status = (
        READINESS_BLOCKED if (has_row_blocker or len(unresolved_blockers) > 0)
        else READINESS_DRAFT_APPROVED
    )

    return {
        "status": readiness_status,
        "row_action": row_action,
        "can_proceed_to_approval": can_proceed,
        "unresolved_blockers": unresolved_blockers,
        "unresolved_review_items": unresolved_review_items,
        "draft_approved_fields": draft_approved_fields,
        "deferred_fields": deferred_fields,
    }


# ---------------------------------------------------------------------------
# Per-row decision applicator
# ---------------------------------------------------------------------------

def _apply_row_decisions(
    row: dict[str, Any],
    row_decision_input: dict[str, Any] | None,
    bulk_accept_auto_accepted: bool,
    bulk_accept_suggestions: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """
    Apply decisions to a single row.

    Decision precedence (highest wins):
      1. Explicit per-field decisions in row_decision_input.field_decisions
      2. Bulk session options (bulk_accept_auto_accepted, bulk_accept_suggestions)
      3. System auto-decisions (no_action_required, auto_accepted)

    Returns:
        (review_decisions, approved_canonical_metadata_draft, approval_readiness)

    Does NOT modify the row or its metadata_evidence in-place.
    """
    mde: dict = row.get("metadata_evidence") or {}
    field_review: dict = mde.get("field_review") or {}

    # --- Step 1: System auto-decisions (lowest precedence baseline) ---
    merged_decisions: dict[str, Any] = _auto_apply_system_decisions(field_review)

    row_action = ROW_ACTION_PROCEED
    explicit_field_decisions_input: list[dict] = []

    if row_decision_input:
        raw_action = str(row_decision_input.get("row_action") or ROW_ACTION_PROCEED).strip().lower()
        if raw_action in VALID_ROW_ACTIONS:
            row_action = raw_action
        explicit_field_decisions_input = list(row_decision_input.get("field_decisions") or [])

    # --- Step 2: Bulk options (override system auto where applicable) ---
    if bulk_accept_auto_accepted:
        for field, fr_entry in sorted(field_review.items()):
            cls = str(fr_entry.get("classification") or "")
            if cls == _CLS_AUTO_ACCEPTED:
                candidate_value = fr_entry.get("candidate_value")
                merged_decisions[field] = _make_field_decision(
                    field=field,
                    decision=DECISION_ACCEPT_AUTO_ACCEPTED,
                    decided_value=candidate_value,
                    decided_value_source="candidate",
                    decision_source=DECISION_SOURCE_SYSTEM_BULK,
                )

    if bulk_accept_suggestions:
        for field, fr_entry in sorted(field_review.items()):
            cls = str(fr_entry.get("classification") or "")
            if cls == _CLS_SUGGESTED_REVIEW:
                candidate_value = fr_entry.get("candidate_value")
                if candidate_value is not None:
                    merged_decisions[field] = _make_field_decision(
                        field=field,
                        decision=DECISION_ACCEPT_CANDIDATE,
                        decided_value=candidate_value,
                        decided_value_source="candidate",
                        decision_source=DECISION_SOURCE_SYSTEM_BULK,
                    )

    # --- Step 3: Explicit per-field decisions (highest precedence) ---
    for fd in explicit_field_decisions_input:
        field = str(fd.get("field") or "").strip()
        if not field:
            continue
        decision_type = str(fd.get("decision") or "").strip()
        if decision_type not in VALID_USER_DECISION_TYPES:
            # Unknown decision type — skip silently.
            continue
        supplied_value = fd.get("supplied_value")
        raw_notes = fd.get("notes")
        notes = str(raw_notes).strip() if raw_notes is not None else None
        if not notes:
            notes = None

        fr_entry = field_review.get(field) or {}
        resolved = _apply_explicit_field_decision(
            field=field,
            fr_entry=fr_entry,
            decision_type=decision_type,
            supplied_value=supplied_value,
            decision_source=DECISION_SOURCE_USER,
            notes=notes,
        )
        if resolved is not None:
            merged_decisions[field] = resolved

    # --- Step 4: Build canonical draft ---
    canonical_draft = _build_canonical_draft(merged_decisions)

    # --- Step 5: Compute approval readiness ---
    readiness = _compute_approval_readiness(
        row_status=str(row.get("status") or "blocked"),
        field_review=field_review,
        merged_decisions=merged_decisions,
        row_action=row_action,
    )

    return merged_decisions, canonical_draft, readiness


# ---------------------------------------------------------------------------
# Session-level review decision package builder
# ---------------------------------------------------------------------------

def build_review_decision_package(
    session_id: str,
    updated_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Build the session-level review decision package summary.

    Aggregates per-row review_decisions and approval_readiness into a single
    session-scoped summary dict.

    Does NOT modify any rows.  Pure aggregation.
    """
    total_rows = len(updated_rows)
    rows_with_decisions_applied = 0
    rows_draft_approved = 0
    rows_held = 0
    rows_rejected = 0
    rows_blocked_unresolvable = 0
    total_fields_resolved = 0
    total_fields_deferred = 0
    total_fields_unresolved_blocking = 0
    total_fields_unresolved_review = 0

    row_readiness_list: list[dict[str, Any]] = []

    for row in updated_rows:
        review_decisions: dict = row.get("review_decisions") or {}
        readiness: dict = row.get("approval_readiness") or {}

        if review_decisions:
            rows_with_decisions_applied += 1

        status = str(readiness.get("status") or "")
        if status == READINESS_DRAFT_APPROVED:
            rows_draft_approved += 1
        elif status == READINESS_HELD:
            rows_held += 1
        elif status == READINESS_REJECTED:
            rows_rejected += 1
        elif status == READINESS_BLOCKED:
            rows_blocked_unresolvable += 1

        total_fields_resolved += len(readiness.get("draft_approved_fields") or [])
        total_fields_deferred += len(readiness.get("deferred_fields") or [])
        total_fields_unresolved_blocking += len(readiness.get("unresolved_blockers") or [])
        total_fields_unresolved_review += len(readiness.get("unresolved_review_items") or [])

        row_readiness_list.append({
            "row_id": str(row.get("row_id") or ""),
            "source_row_number": int(row.get("source_row_number") or 0),
            "approval_readiness": readiness,
        })

    can_proceed_to_approval_gate: bool = (
        rows_blocked_unresolvable == 0
        and rows_held == 0
        and rows_rejected == 0
        and total_rows > 0
    )

    return {
        "schema_version": REVIEW_DECISION_PACKAGE_SCHEMA_VERSION,
        "session_id": session_id,
        "created_at": _utc_now(),
        "summary": {
            "total_rows": total_rows,
            "rows_with_decisions_applied": rows_with_decisions_applied,
            "rows_draft_approved": rows_draft_approved,
            "rows_held": rows_held,
            "rows_rejected": rows_rejected,
            "rows_blocked_unresolvable": rows_blocked_unresolvable,
            "total_fields_resolved": total_fields_resolved,
            "total_fields_deferred": total_fields_deferred,
            "total_fields_unresolved_blocking": total_fields_unresolved_blocking,
            "total_fields_unresolved_review": total_fields_unresolved_review,
        },
        "row_readiness": row_readiness_list,
        "session_approval_readiness": {
            "all_rows_draft_approved": (
                rows_draft_approved == total_rows and total_rows > 0
            ),
            "any_rows_held": rows_held > 0,
            "any_rows_rejected": rows_rejected > 0,
            "any_rows_blocked": rows_blocked_unresolvable > 0,
            "can_proceed_to_approval_gate": can_proceed_to_approval_gate,
        },
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def apply_review_decisions_to_session(
    session: dict[str, Any],
    row_decisions_input: list[dict[str, Any]],
    bulk_accept_auto_accepted: bool = False,
    bulk_accept_suggestions: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Apply review decisions to all rows in the given SBLT session.

    For rows NOT present in row_decisions_input, only system auto-decisions
    are applied (no_action_required → system_no_action, auto_accepted →
    system_auto_accepted).

    For rows present in row_decisions_input, explicit field decisions are merged
    with system auto-decisions using the precedence order:
      explicit > bulk > system_auto.

    Parameters
    ----------
    session:
        Full SBLT session dict (must be in review_package_built or
        review_decisions_applied state — enforced by the caller).
    row_decisions_input:
        List of per-row decision dicts:
        {
          "row_id": str,
          "row_action": "proceed" | "hold" | "reject",   # default: "proceed"
          "field_decisions": [
            {
              "field": str,
              "decision": str,               # one of VALID_USER_DECISION_TYPES
              "supplied_value": Any | None,
              "notes": str | None,
            }
          ]
        }
    bulk_accept_auto_accepted:
        If True, all auto_accepted fields across all rows are confirmed via
        system_bulk decision (user-confirmed bulk action).
    bulk_accept_suggestions:
        If True, all suggested_review fields with a non-None candidate_value
        across all rows are accepted via system_bulk decision.

    Returns
    -------
    (updated_rows, review_decision_package)

    updated_rows — list of row dicts with review_decisions,
                   approved_canonical_metadata_draft, and approval_readiness added.
                   The original metadata_evidence and all prior fields are preserved.

    review_decision_package — session-level summary dict.

    Architecture guarantees:
      - Does NOT modify session or any row in-place.
      - Does NOT modify MDE bundles.
      - can_register remains False.
      - approved_for_loading remains False.
    """
    session_id: str = str(session.get("session_id") or "")
    rows: list[dict] = list(session.get("rows") or [])

    # Build a lookup map from row_id → row decision input for O(1) access.
    row_decision_map: dict[str, dict[str, Any]] = {}
    for rd in (row_decisions_input or []):
        row_id = str(rd.get("row_id") or "").strip()
        if row_id:
            row_decision_map[row_id] = rd

    updated_rows: list[dict[str, Any]] = []

    for row in rows:
        row_id = str(row.get("row_id") or "")
        row_decision_input = row_decision_map.get(row_id)

        review_decisions, canonical_draft, readiness = _apply_row_decisions(
            row=row,
            row_decision_input=row_decision_input,
            bulk_accept_auto_accepted=bulk_accept_auto_accepted,
            bulk_accept_suggestions=bulk_accept_suggestions,
        )

        # Build the updated row: preserve all prior fields, add SBLT-7 outputs.
        updated_row: dict[str, Any] = {
            **row,
            "review_decisions": review_decisions,
            "approved_canonical_metadata_draft": canonical_draft,
            "approval_readiness": readiness,
        }
        updated_rows.append(updated_row)

    # Build the session-level decision package.
    decision_package = build_review_decision_package(session_id, updated_rows)

    return updated_rows, decision_package
