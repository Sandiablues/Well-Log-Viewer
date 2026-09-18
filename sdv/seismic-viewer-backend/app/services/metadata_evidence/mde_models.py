"""
MDE-1: Shared Metadata / Evidence / QAQC / Review contract — model constants and builder helpers.

Schema version: mde.bundle.v1

Ownership: shared backend service (app/services/metadata_evidence/).

This module is INDEPENDENT of SBLT and SSI.
- No seismic_bulk_loader imports.
- No source_intake imports.
- No MSI imports.
- No frontend.
- No file I/O.

SBLT and SSI consume this package. This package does not depend on SBLT or SSI.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "mde.bundle.v1"

# ---------------------------------------------------------------------------
# Workflow types
# ---------------------------------------------------------------------------

WORKFLOW_SBLT = "sblt"
WORKFLOW_SSI = "ssi"
WORKFLOW_UNKNOWN = "unknown"

VALID_WORKFLOW_TYPES = {WORKFLOW_SBLT, WORKFLOW_SSI, WORKFLOW_UNKNOWN}

# ---------------------------------------------------------------------------
# Intake modes
# ---------------------------------------------------------------------------

INTAKE_MODE_METADATA_RICH = "metadata_rich"
INTAKE_MODE_METADATA_SPARSE = "metadata_sparse"
INTAKE_MODE_MIXED = "mixed"
INTAKE_MODE_UNKNOWN = "unknown"

# ---------------------------------------------------------------------------
# Source reference types / statuses
# ---------------------------------------------------------------------------

SOURCE_REF_LOCAL_PATH = "local_path"
SOURCE_REF_URL = "url"
SOURCE_REF_OBJECT_STORE_URI = "object_store_uri"
SOURCE_REF_UNKNOWN = "unknown"

SOURCE_STATUS_SUBMITTED = "submitted"
SOURCE_STATUS_VALIDATED = "validated"
SOURCE_STATUS_STAGED = "staged"
SOURCE_STATUS_UNAVAILABLE = "unavailable"
SOURCE_STATUS_UNKNOWN = "unknown"

# ---------------------------------------------------------------------------
# Submitted metadata source types
# ---------------------------------------------------------------------------

SUBMITTED_SOURCE_LOADSHEET = "loadsheet"
SUBMITTED_SOURCE_SOURCE_INTAKE = "source_intake"
SUBMITTED_SOURCE_MANUAL = "manual"
SUBMITTED_SOURCE_UNKNOWN = "unknown"

# ---------------------------------------------------------------------------
# Evidence source types
# ---------------------------------------------------------------------------

EVIDENCE_SOURCE_LOADSHEET = "loadsheet"
EVIDENCE_SOURCE_SEGY_BINARY_HEADER = "segy_binary_header"
EVIDENCE_SOURCE_SEGY_TEXTUAL_HEADER = "segy_textual_header"
EVIDENCE_SOURCE_FILENAME = "filename"
EVIDENCE_SOURCE_FOLDER_PATH = "folder_path"
EVIDENCE_SOURCE_SUPPORTING_DOCUMENT = "supporting_document"
EVIDENCE_SOURCE_MANUAL = "manual"
EVIDENCE_SOURCE_AI_SUGGESTION = "ai_suggestion"
EVIDENCE_SOURCE_SOURCE_INTAKE = "source_intake"
EVIDENCE_SOURCE_UNKNOWN = "unknown"

VALID_EVIDENCE_SOURCE_TYPES = {
    EVIDENCE_SOURCE_LOADSHEET,
    EVIDENCE_SOURCE_SEGY_BINARY_HEADER,
    EVIDENCE_SOURCE_SEGY_TEXTUAL_HEADER,
    EVIDENCE_SOURCE_FILENAME,
    EVIDENCE_SOURCE_FOLDER_PATH,
    EVIDENCE_SOURCE_SUPPORTING_DOCUMENT,
    EVIDENCE_SOURCE_MANUAL,
    EVIDENCE_SOURCE_AI_SUGGESTION,
    EVIDENCE_SOURCE_SOURCE_INTAKE,
    EVIDENCE_SOURCE_UNKNOWN,
}

# ---------------------------------------------------------------------------
# Confidence levels
# ---------------------------------------------------------------------------

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_UNKNOWN = "unknown"

VALID_CONFIDENCE_LEVELS = {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW, CONFIDENCE_UNKNOWN}

# ---------------------------------------------------------------------------
# Comparison results
# ---------------------------------------------------------------------------

COMPARISON_MATCH = "match"
COMPARISON_CONFLICT = "conflict"
COMPARISON_CANDIDATE_FROM_EVIDENCE = "candidate_from_evidence"
COMPARISON_MISSING = "missing"
COMPARISON_NOT_CHECKED = "not_checked"
COMPARISON_NOT_APPLICABLE = "not_applicable"
COMPARISON_MISSING_EVIDENCE = "missing_evidence"

VALID_COMPARISONS = {
    COMPARISON_MATCH,
    COMPARISON_CONFLICT,
    COMPARISON_CANDIDATE_FROM_EVIDENCE,
    COMPARISON_MISSING,
    COMPARISON_NOT_CHECKED,
    COMPARISON_NOT_APPLICABLE,
    COMPARISON_MISSING_EVIDENCE,
}

# ---------------------------------------------------------------------------
# Candidate statuses
# ---------------------------------------------------------------------------

CANDIDATE_STATUS_SUGGESTED = "suggested"
CANDIDATE_STATUS_AUTO_ACCEPTED = "auto_accepted"
CANDIDATE_STATUS_REJECTED = "rejected"
CANDIDATE_STATUS_SUPERSEDED = "superseded"

# ---------------------------------------------------------------------------
# Review classifications
# ---------------------------------------------------------------------------

REVIEW_NO_ACTION_REQUIRED = "no_action_required"
REVIEW_AUTO_ACCEPTED = "auto_accepted"
REVIEW_SUGGESTED_REVIEW = "suggested_review"
REVIEW_MISSING_REQUIRED = "missing_required"
REVIEW_MISSING_RECOMMENDED = "missing_recommended"
REVIEW_CONFLICT = "conflict"
REVIEW_MANUAL_REQUIRED = "manual_required"
REVIEW_POLICY_REVIEW_REQUIRED = "policy_review_required"
REVIEW_BLOCKED = "blocked"

VALID_REVIEW_CLASSIFICATIONS = {
    REVIEW_NO_ACTION_REQUIRED,
    REVIEW_AUTO_ACCEPTED,
    REVIEW_SUGGESTED_REVIEW,
    REVIEW_MISSING_REQUIRED,
    REVIEW_MISSING_RECOMMENDED,
    REVIEW_CONFLICT,
    REVIEW_MANUAL_REQUIRED,
    REVIEW_POLICY_REVIEW_REQUIRED,
    REVIEW_BLOCKED,
}

# ---------------------------------------------------------------------------
# Approval statuses
# ---------------------------------------------------------------------------

APPROVAL_NOT_REVIEWED = "not_reviewed"
APPROVAL_PARTIALLY_REVIEWED = "partially_reviewed"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"
APPROVAL_DEFERRED = "deferred"

# ---------------------------------------------------------------------------
# QAQC severity levels
# ---------------------------------------------------------------------------

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_BLOCKER = "blocker"

# ---------------------------------------------------------------------------
# MDE QAQC finding codes
# ---------------------------------------------------------------------------

CODE_MDE_MATCH = "MDE_MATCH"
CODE_MDE_CONFLICT = "MDE_CONFLICT"
CODE_MDE_CANDIDATE_FROM_EVIDENCE = "MDE_CANDIDATE_FROM_EVIDENCE"
CODE_MDE_AUTO_ACCEPTED = "MDE_AUTO_ACCEPTED"
CODE_MDE_SUGGESTED_REVIEW = "MDE_SUGGESTED_REVIEW"
CODE_MDE_MISSING_REQUIRED = "MDE_MISSING_REQUIRED"
CODE_MDE_MISSING_RECOMMENDED = "MDE_MISSING_RECOMMENDED"

# ---------------------------------------------------------------------------
# ID generators
# ---------------------------------------------------------------------------


def _generate_bundle_id() -> str:
    return f"mde_{secrets.token_hex(8)}"


def _generate_evidence_id() -> str:
    return f"ev_{secrets.token_hex(6)}"


def _generate_finding_id() -> str:
    return f"qaqc_{secrets.token_hex(6)}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Submitted metadata builders
# ---------------------------------------------------------------------------


def make_submitted_field(
    *,
    field: str,
    value: Any,
    value_normalized: Any = None,
    source_type: str = SUBMITTED_SOURCE_LOADSHEET,
    source_label: str = "",
) -> dict[str, Any]:
    """Build a submitted metadata field entry where a value is present."""
    return {
        "field": field,
        "value": value,
        "value_normalized": value_normalized if value_normalized is not None else value,
        "source_type": source_type,
        "source_label": source_label,
        "present": True,
    }


def make_submitted_field_absent(
    *,
    field: str,
    source_type: str = SUBMITTED_SOURCE_LOADSHEET,
    source_label: str = "",
) -> dict[str, Any]:
    """Build a submitted metadata field entry where no value was submitted."""
    return {
        "field": field,
        "value": None,
        "value_normalized": None,
        "source_type": source_type,
        "source_label": source_label,
        "present": False,
    }


# ---------------------------------------------------------------------------
# Candidate metadata builder
# ---------------------------------------------------------------------------


def make_candidate_field(
    *,
    field: str,
    candidate_value: Any,
    candidate_value_normalized: Any = None,
    candidate_source_type: str,
    candidate_source_ids: list[str],
    confidence: str = CONFIDENCE_UNKNOWN,
    candidate_status: str = CANDIDATE_STATUS_SUGGESTED,
) -> dict[str, Any]:
    """Build a candidate metadata field entry from evidence."""
    return {
        "field": field,
        "candidate_value": candidate_value,
        "candidate_value_normalized": (
            candidate_value_normalized
            if candidate_value_normalized is not None
            else candidate_value
        ),
        "candidate_source_type": candidate_source_type,
        "candidate_source_ids": candidate_source_ids,
        "confidence": confidence,
        "candidate_status": candidate_status,
    }


# ---------------------------------------------------------------------------
# Evidence record builder
# ---------------------------------------------------------------------------


def make_evidence_record(
    *,
    field: str,
    source_type: str,
    source_label: str = "",
    observed_value: Any,
    observed_value_normalized: Any = None,
    confidence: str = CONFIDENCE_UNKNOWN,
    supports_value: Any = None,
    comparison: str = COMPARISON_NOT_CHECKED,
    evidence_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build an evidence record.

    evidence_id is generated here and is stable for this record's lifetime.
    """
    return {
        "evidence_id": _generate_evidence_id(),
        "field": field,
        "source_type": source_type,
        "source_label": source_label,
        "observed_value": observed_value,
        "observed_value_normalized": (
            observed_value_normalized
            if observed_value_normalized is not None
            else observed_value
        ),
        "confidence": confidence,
        "supports_value": supports_value if supports_value is not None else observed_value,
        "comparison": comparison,
        "evidence_detail": evidence_detail or _empty_evidence_detail(),
    }


def _empty_evidence_detail() -> dict[str, Any]:
    return {
        "line_number": None,
        "byte_range": None,
        "document_id": None,
        "header_field": None,
        "raw_text": None,
    }


# ---------------------------------------------------------------------------
# QAQC finding builder
# ---------------------------------------------------------------------------


def make_qaqc_finding(
    *,
    severity: str,
    code: str,
    field: str,
    message: str,
    source: str = "mde",
    related_evidence_ids: list[str] | None = None,
    review_required: bool = False,
) -> dict[str, Any]:
    """Build a structured QAQC finding."""
    return {
        "finding_id": _generate_finding_id(),
        "severity": severity,
        "code": code,
        "field": field,
        "message": message,
        "source": source,
        "related_evidence_ids": related_evidence_ids or [],
        "review_required": review_required,
    }


# ---------------------------------------------------------------------------
# Field review builder
# ---------------------------------------------------------------------------


def make_field_review(
    *,
    field: str,
    classification: str,
    submitted_value: Any = None,
    candidate_value: Any = None,
    requires_user_review: bool,
    bulk_action_eligible: bool = False,
    related_evidence_ids: list[str] | None = None,
    related_finding_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build a field review entry."""
    return {
        "field": field,
        "classification": classification,
        "submitted_value": submitted_value,
        "candidate_value": candidate_value,
        "approved_value": None,
        "decision": "none",
        "decision_source": "system",
        "requires_user_review": requires_user_review,
        "bulk_action_eligible": bulk_action_eligible,
        "related_evidence_ids": related_evidence_ids or [],
        "related_finding_ids": related_finding_ids or [],
    }


# ---------------------------------------------------------------------------
# Review summary builder
# ---------------------------------------------------------------------------


def make_review_summary(field_review: dict[str, Any]) -> dict[str, Any]:
    """
    Compute batch-oriented review summary from field_review dict.

    Invariant: counts reconcile with field_review classifications.
    """
    counts: dict[str, int] = {
        "total_fields": len(field_review),
        "no_action_required_count": 0,
        "auto_accepted_count": 0,
        "suggested_review_count": 0,
        "missing_required_count": 0,
        "missing_recommended_count": 0,
        "conflict_count": 0,
        "manual_required_count": 0,
        "policy_review_required_count": 0,
        "blocked_count": 0,
    }

    cls_map = {
        REVIEW_NO_ACTION_REQUIRED: "no_action_required_count",
        REVIEW_AUTO_ACCEPTED: "auto_accepted_count",
        REVIEW_SUGGESTED_REVIEW: "suggested_review_count",
        REVIEW_MISSING_REQUIRED: "missing_required_count",
        REVIEW_MISSING_RECOMMENDED: "missing_recommended_count",
        REVIEW_CONFLICT: "conflict_count",
        REVIEW_MANUAL_REQUIRED: "manual_required_count",
        REVIEW_POLICY_REVIEW_REQUIRED: "policy_review_required_count",
        REVIEW_BLOCKED: "blocked_count",
    }

    for fr in field_review.values():
        cls = fr.get("classification", "")
        key = cls_map.get(cls)
        if key:
            counts[key] += 1

    requires_user_review = any(
        fr.get("requires_user_review", False) for fr in field_review.values()
    )
    approval_blocked = (
        counts["missing_required_count"] > 0 or counts["blocked_count"] > 0
    )

    bulk_actions: list[str] = []
    if counts["auto_accepted_count"] > 0:
        bulk_actions.append("bulk_confirm_auto_accepted")
    if counts["suggested_review_count"] > 0:
        bulk_actions.append("bulk_accept_suggestions")
    if counts["conflict_count"] > 0:
        bulk_actions.append("bulk_review_conflicts")

    return {
        **counts,
        "requires_user_review": requires_user_review,
        "approval_blocked": approval_blocked,
        "bulk_actions_available": bulk_actions,
    }


# ---------------------------------------------------------------------------
# Approval state builder
# ---------------------------------------------------------------------------


def make_approval() -> dict[str, Any]:
    """Build the default (not_reviewed) approval state."""
    return {
        "approval_status": APPROVAL_NOT_REVIEWED,
        "approved_for_loading": False,
        "approved_for_registration": False,
        "approved_by": None,
        "approved_at": None,
        "approval_notes": None,
    }


# ---------------------------------------------------------------------------
# Source reference builder
# ---------------------------------------------------------------------------


def make_source_reference(
    *,
    source_reference_type: str = SOURCE_REF_UNKNOWN,
    source_reference_value: str = "",
    resolved_reference: str = "",
    source_status: str = SOURCE_STATUS_UNKNOWN,
) -> dict[str, Any]:
    return {
        "source_reference_type": source_reference_type,
        "source_reference_value": source_reference_value,
        "resolved_reference": resolved_reference,
        "source_status": source_status,
    }


# ---------------------------------------------------------------------------
# Dataset context builder
# ---------------------------------------------------------------------------


def make_dataset_context(
    *,
    record_type: str = "unknown",
    dataset_label: str = "",
    source_reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "record_type": record_type,
        "dataset_label": dataset_label,
        "source_reference": source_reference or make_source_reference(),
    }
