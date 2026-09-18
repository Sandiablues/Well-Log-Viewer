"""
MDE-1: Bundle invariant validation.

Validates that a built bundle satisfies the mde.bundle.v1 contract.

No SBLT imports. No SSI imports. No MSI imports. No file I/O.
"""

from __future__ import annotations

from typing import Any

from .mde_models import (
    SCHEMA_VERSION,
    VALID_EVIDENCE_SOURCE_TYPES,
    VALID_REVIEW_CLASSIFICATIONS,
)


class MDEValidationError(Exception):
    """Raised when a bundle fails contract invariants."""


def validate_bundle_invariants(bundle: dict[str, Any]) -> None:
    """
    Enforce MDE bundle contract invariants.

    Raises MDEValidationError if any invariant is violated.
    """
    # --- Schema version ---
    sv = bundle.get("schema_version")
    if sv != SCHEMA_VERSION:
        raise MDEValidationError(
            f"MDE invariant: schema_version={sv!r} expected={SCHEMA_VERSION!r}"
        )

    # --- Required top-level keys ---
    required_keys = {
        "schema_version", "bundle_id", "created_at", "workflow",
        "dataset_context", "submitted_metadata", "candidate_metadata",
        "evidence_records", "qaqc_findings", "field_review",
        "review_summary", "approved_canonical_metadata", "approval",
    }
    missing = required_keys - set(bundle.keys())
    if missing:
        raise MDEValidationError(f"MDE invariant: missing top-level keys: {sorted(missing)}")

    # --- Workflow block ---
    workflow = bundle.get("workflow") or {}
    for wk in ("workflow_type", "workflow_session_id", "workflow_row_id", "intake_mode"):
        if wk not in workflow:
            raise MDEValidationError(f"MDE invariant: workflow missing key {wk!r}")

    # --- Evidence records ---
    evidence_records = bundle.get("evidence_records", [])
    if not isinstance(evidence_records, list):
        raise MDEValidationError("MDE invariant: evidence_records must be a list")
    for i, ev in enumerate(evidence_records):
        for ek in ("evidence_id", "field", "source_type", "observed_value", "confidence", "comparison"):
            if ek not in ev:
                raise MDEValidationError(
                    f"MDE invariant: evidence_records[{i}] missing key {ek!r}"
                )

    # --- QAQC findings ---
    qaqc_findings = bundle.get("qaqc_findings", [])
    if not isinstance(qaqc_findings, list):
        raise MDEValidationError("MDE invariant: qaqc_findings must be a list")
    for i, f in enumerate(qaqc_findings):
        for fk in ("finding_id", "severity", "code", "field", "message", "source"):
            if fk not in f:
                raise MDEValidationError(
                    f"MDE invariant: qaqc_findings[{i}] missing key {fk!r}"
                )

    # --- Field review ---
    field_review = bundle.get("field_review", {})
    if not isinstance(field_review, dict):
        raise MDEValidationError("MDE invariant: field_review must be a dict")
    for field, fr in field_review.items():
        cls = fr.get("classification")
        if cls not in VALID_REVIEW_CLASSIFICATIONS:
            raise MDEValidationError(
                f"MDE invariant: field_review[{field!r}] unknown classification {cls!r}"
            )
        for frk in ("field", "classification", "requires_user_review", "bulk_action_eligible"):
            if frk not in fr:
                raise MDEValidationError(
                    f"MDE invariant: field_review[{field!r}] missing key {frk!r}"
                )

    # --- Review summary ---
    review_summary = bundle.get("review_summary") or {}
    if "total_fields" not in review_summary:
        raise MDEValidationError("MDE invariant: review_summary missing total_fields")
    if review_summary["total_fields"] != len(field_review):
        raise MDEValidationError(
            f"MDE invariant: review_summary.total_fields={review_summary['total_fields']} "
            f"!= len(field_review)={len(field_review)}"
        )
    if "requires_user_review" not in review_summary:
        raise MDEValidationError("MDE invariant: review_summary missing requires_user_review")
    if "approval_blocked" not in review_summary:
        raise MDEValidationError("MDE invariant: review_summary missing approval_blocked")

    # --- Approval ---
    approval = bundle.get("approval") or {}
    for ak in ("approval_status", "approved_for_loading", "approved_for_registration"):
        if ak not in approval:
            raise MDEValidationError(f"MDE invariant: approval missing key {ak!r}")
