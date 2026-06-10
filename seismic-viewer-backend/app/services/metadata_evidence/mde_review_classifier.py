"""
MDE-1: Per-field review classification logic.

Classifies each metadata field for exception-based, batch-oriented review.

No SBLT imports. No SSI imports. No MSI imports. No file I/O.
"""

from __future__ import annotations

import re
from typing import Any

from .mde_models import (
    CANDIDATE_STATUS_AUTO_ACCEPTED,
    CANDIDATE_STATUS_SUGGESTED,
    COMPARISON_CANDIDATE_FROM_EVIDENCE,
    COMPARISON_CONFLICT,
    COMPARISON_MATCH,
    COMPARISON_MISSING,
    COMPARISON_MISSING_EVIDENCE,
    COMPARISON_NOT_CHECKED,
    REVIEW_AUTO_ACCEPTED,
    REVIEW_CONFLICT,
    REVIEW_MISSING_RECOMMENDED,
    REVIEW_MISSING_REQUIRED,
    REVIEW_NO_ACTION_REQUIRED,
    REVIEW_SUGGESTED_REVIEW,
    SEVERITY_BLOCKER,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    CODE_MDE_AUTO_ACCEPTED,
    CODE_MDE_CANDIDATE_FROM_EVIDENCE,
    CODE_MDE_CONFLICT,
    CODE_MDE_MATCH,
    CODE_MDE_MISSING_RECOMMENDED,
    CODE_MDE_MISSING_REQUIRED,
    CODE_MDE_SUGGESTED_REVIEW,
    make_field_review,
    make_qaqc_finding,
    make_review_summary,
)
from .mde_policy import get_field_policy

# ---------------------------------------------------------------------------
# Value comparison helpers
# ---------------------------------------------------------------------------

_FLOAT_TOLERANCE = 0.001
_COLLAPSE_RE = re.compile(r"[\s\-_/\\.,;:]+")


def _normalize_string(value: Any) -> str:
    """Collapse whitespace and punctuation, lowercase."""
    if value is None:
        return ""
    return _COLLAPSE_RE.sub(" ", str(value).strip()).lower()


def _try_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compare_values(
    field: str,
    submitted_normalized: Any,
    candidate_normalized: Any,
) -> str:
    """
    Deterministic comparison of submitted vs candidate normalized values.

    Returns a COMPARISON_* constant.
    """
    sub_is_none = submitted_normalized is None
    can_is_none = candidate_normalized is None

    if sub_is_none and can_is_none:
        return COMPARISON_MISSING

    if sub_is_none and not can_is_none:
        return COMPARISON_CANDIDATE_FROM_EVIDENCE

    if not sub_is_none and can_is_none:
        return COMPARISON_MISSING_EVIDENCE

    # Both present — try numeric comparison first
    sub_f = _try_float(submitted_normalized)
    can_f = _try_float(candidate_normalized)
    if sub_f is not None and can_f is not None:
        if abs(sub_f - can_f) <= _FLOAT_TOLERANCE:
            return COMPARISON_MATCH
        return COMPARISON_CONFLICT

    # String comparison
    if _normalize_string(submitted_normalized) == _normalize_string(candidate_normalized):
        return COMPARISON_MATCH
    return COMPARISON_CONFLICT


# ---------------------------------------------------------------------------
# Per-field classifier
# ---------------------------------------------------------------------------


def classify_field(
    *,
    field: str,
    submitted_entry: dict[str, Any],
    candidate_entry: dict[str, Any] | None,
    evidence_ids: list[str],
    finding_ids_in: list[str],
    policy: dict | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """
    Classify a single metadata field for review.

    Returns:
        (field_review_dict, new_qaqc_findings, comparison_result)

    Policy defaults to get_field_policy(field) if not supplied.
    """
    if policy is None:
        policy = get_field_policy(field)

    submitted_present: bool = submitted_entry.get("present", False)
    submitted_value = submitted_entry.get("value_normalized") if submitted_present else None

    candidate_value = (
        candidate_entry.get("candidate_value_normalized")
        if candidate_entry is not None
        else None
    )
    candidate_source_type: str = (
        candidate_entry.get("candidate_source_type", "") if candidate_entry else ""
    )

    comparison = compare_values(field, submitted_value, candidate_value)

    new_findings: list[dict[str, Any]] = []
    classification: str
    requires_user_review: bool
    candidate_status: str | None = None

    # --- Determine classification ---

    if comparison == COMPARISON_MISSING:
        # Neither submitted nor candidate
        cls = policy["missing_classification"]
        if cls == REVIEW_MISSING_REQUIRED:
            classification = REVIEW_MISSING_REQUIRED
            requires_user_review = True
            sev = SEVERITY_BLOCKER
            code = CODE_MDE_MISSING_REQUIRED
        else:
            classification = REVIEW_MISSING_RECOMMENDED
            requires_user_review = True
            sev = SEVERITY_WARNING
            code = CODE_MDE_MISSING_RECOMMENDED
        new_findings.append(
            make_qaqc_finding(
                severity=sev,
                code=code,
                field=field,
                message=f"Field '{field}' is absent — no submitted value and no candidate evidence.",
                related_evidence_ids=evidence_ids,
                review_required=requires_user_review,
            )
        )

    elif comparison == COMPARISON_CANDIDATE_FROM_EVIDENCE:
        # Submitted absent, candidate present
        auto_accept_sources = policy.get("auto_accept_sources", [])
        if candidate_source_type in auto_accept_sources:
            classification = REVIEW_AUTO_ACCEPTED
            requires_user_review = False
            candidate_status = CANDIDATE_STATUS_AUTO_ACCEPTED
            new_findings.append(
                make_qaqc_finding(
                    severity=SEVERITY_INFO,
                    code=CODE_MDE_AUTO_ACCEPTED,
                    field=field,
                    message=(
                        f"Field '{field}' auto-accepted from {candidate_source_type!r}. "
                        f"Candidate value: {candidate_value!r}."
                    ),
                    related_evidence_ids=evidence_ids,
                    review_required=False,
                )
            )
        else:
            classification = REVIEW_SUGGESTED_REVIEW
            requires_user_review = True
            candidate_status = CANDIDATE_STATUS_SUGGESTED
            new_findings.append(
                make_qaqc_finding(
                    severity=SEVERITY_INFO,
                    code=CODE_MDE_SUGGESTED_REVIEW,
                    field=field,
                    message=(
                        f"Field '{field}' has a candidate value from {candidate_source_type!r}: "
                        f"{candidate_value!r}. Review required before acceptance."
                    ),
                    related_evidence_ids=evidence_ids,
                    review_required=True,
                )
            )

    elif comparison == COMPARISON_MATCH:
        classification = REVIEW_NO_ACTION_REQUIRED
        requires_user_review = False
        new_findings.append(
            make_qaqc_finding(
                severity=SEVERITY_INFO,
                code=CODE_MDE_MATCH,
                field=field,
                message=(
                    f"Field '{field}' submitted value matches candidate: {submitted_value!r}."
                ),
                related_evidence_ids=evidence_ids,
                review_required=False,
            )
        )

    elif comparison == COMPARISON_CONFLICT:
        classification = REVIEW_CONFLICT
        requires_user_review = True
        new_findings.append(
            make_qaqc_finding(
                severity=SEVERITY_WARNING,
                code=CODE_MDE_CONFLICT,
                field=field,
                message=(
                    f"Field '{field}' conflict: submitted={submitted_value!r} "
                    f"vs candidate={candidate_value!r} "
                    f"from {candidate_source_type!r}."
                ),
                related_evidence_ids=evidence_ids,
                review_required=True,
            )
        )

    else:
        # COMPARISON_MISSING_EVIDENCE or NOT_CHECKED: submitted present, no candidate
        classification = REVIEW_NO_ACTION_REQUIRED
        requires_user_review = False

    # Update candidate status in the candidate entry if supplied
    if candidate_entry is not None and candidate_status is not None:
        candidate_entry["candidate_status"] = candidate_status

    all_finding_ids = list(finding_ids_in) + [f["finding_id"] for f in new_findings]
    bulk_action_eligible = policy.get("bulk_action_eligible", False) and not requires_user_review

    fr = make_field_review(
        field=field,
        classification=classification,
        submitted_value=submitted_value,
        candidate_value=candidate_value,
        requires_user_review=requires_user_review,
        bulk_action_eligible=bulk_action_eligible,
        related_evidence_ids=evidence_ids,
        related_finding_ids=all_finding_ids,
    )

    return fr, new_findings, comparison


# ---------------------------------------------------------------------------
# Convenience re-export
# ---------------------------------------------------------------------------

__all__ = [
    "classify_field",
    "compare_values",
    "make_review_summary",
]
