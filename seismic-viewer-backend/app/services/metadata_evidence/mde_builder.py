"""
MDE-1: Metadata Evidence bundle builder.

Entry point: build_metadata_evidence_bundle(...)

Accepts plain dicts from SBLT or SSI — does not import either.
No SBLT imports. No SSI imports. No MSI imports. No file I/O. No SEG-Y reads.
"""

from __future__ import annotations

from typing import Any

from .mde_models import (
    INTAKE_MODE_METADATA_RICH,
    INTAKE_MODE_METADATA_SPARSE,
    INTAKE_MODE_MIXED,
    INTAKE_MODE_UNKNOWN,
    SCHEMA_VERSION,
    SUBMITTED_SOURCE_LOADSHEET,
    WORKFLOW_UNKNOWN,
    _generate_bundle_id,
    _utc_now,
    make_approval,
    make_candidate_field,
    make_dataset_context,
    make_evidence_record,
    make_review_summary,
    make_submitted_field,
    make_submitted_field_absent,
)
from .mde_review_classifier import classify_field

# ---------------------------------------------------------------------------
# Intake mode detection
# ---------------------------------------------------------------------------

# Key identity fields used to score intake richness.
# source_reference is handled separately (it's in dataset_context, not submitted_metadata).
_IDENTITY_FIELDS = ("survey_name", "record_type")
_LINE_VOLUME_FIELDS = ("line_name", "volume_name")


def detect_intake_mode(
    submitted_metadata: dict[str, Any],
    dataset_context: dict[str, Any] | None = None,
) -> str:
    """
    Classify intake mode based on submitted metadata coverage.

    Scoring:
        1 point — source_reference present and non-empty
        1 point — survey_name present
        1 point — record_type present
        1 point — line_name OR volume_name present

    4 points → metadata_rich
    0–1 points → metadata_sparse
    2–3 points → mixed
    0 with no source_reference → unknown
    """
    score = 0

    # Source reference check
    source_ref = (dataset_context or {}).get("source_reference") or {}
    source_val = str(source_ref.get("source_reference_value") or "").strip()
    has_source = bool(source_val)
    if has_source:
        score += 1

    # Identity field checks
    for f in _IDENTITY_FIELDS:
        entry = submitted_metadata.get(f)
        if entry and entry.get("present", False) and entry.get("value"):
            score += 1

    # Line or volume
    has_line_vol = any(
        submitted_metadata.get(f, {}).get("present", False)
        and submitted_metadata.get(f, {}).get("value")
        for f in _LINE_VOLUME_FIELDS
    )
    if has_line_vol:
        score += 1

    if not has_source:
        return INTAKE_MODE_UNKNOWN
    if score == 4:
        return INTAKE_MODE_METADATA_RICH
    if score <= 1:
        return INTAKE_MODE_METADATA_SPARSE
    return INTAKE_MODE_MIXED


# ---------------------------------------------------------------------------
# Submitted metadata normalisation
# ---------------------------------------------------------------------------


def _normalize_submitted_value(value: Any) -> Any:
    """
    Return a normalized form of a submitted value for comparison purposes.
    Converts numeric strings to float where possible. Strips strings.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return s


def _build_submitted_metadata(
    raw_submitted: dict[str, Any],
    source_type: str = SUBMITTED_SOURCE_LOADSHEET,
) -> dict[str, Any]:
    """
    Normalise a flat field→value dict into the submitted_metadata contract shape.

    raw_submitted keys are field names; values are raw submitted values (may be None).
    """
    result: dict[str, Any] = {}
    for field, raw_value in raw_submitted.items():
        stripped = str(raw_value).strip() if raw_value is not None else ""
        is_present = raw_value is not None and stripped != ""
        if is_present:
            normalized = _normalize_submitted_value(raw_value)
            result[field] = make_submitted_field(
                field=field,
                value=raw_value,
                value_normalized=normalized,
                source_type=source_type,
                source_label=f"Submitted field: {field}",
            )
        else:
            result[field] = make_submitted_field_absent(
                field=field,
                source_type=source_type,
                source_label=f"Submitted field: {field}",
            )
    return result


# ---------------------------------------------------------------------------
# Candidate observation processing
# ---------------------------------------------------------------------------


def _process_candidate_observations(
    observations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """
    Convert a list of raw candidate observation dicts into:
        - evidence_records: list of evidence record dicts
        - candidate_metadata: dict[field → candidate_field dict]

    Multiple observations for the same field result in the last one winning
    for the candidate_metadata entry (ordered by priority: high > medium > low > unknown).
    """
    evidence_records: list[dict[str, Any]] = []
    # field → list of (confidence_rank, evidence_record) to pick best candidate
    field_candidates: dict[str, list[tuple[int, dict[str, Any]]]] = {}

    _conf_rank = {"high": 3, "medium": 2, "low": 1, "unknown": 0}

    for obs in observations:
        field = str(obs.get("field") or "").strip()
        if not field:
            continue

        observed_value = obs.get("observed_value")
        normalized_value = _normalize_submitted_value(observed_value)
        source_type = str(obs.get("source_type") or "unknown").strip()
        source_label = str(obs.get("source_label") or "").strip()
        confidence = str(obs.get("confidence") or "unknown").strip()
        raw_detail = obs.get("evidence_detail") or {}
        evidence_detail = {
            "line_number": raw_detail.get("line_number"),
            "byte_range": raw_detail.get("byte_range"),
            "document_id": raw_detail.get("document_id"),
            "header_field": raw_detail.get("header_field"),
            "raw_text": raw_detail.get("raw_text"),
        }

        ev = make_evidence_record(
            field=field,
            source_type=source_type,
            source_label=source_label,
            observed_value=observed_value,
            observed_value_normalized=normalized_value,
            confidence=confidence,
            evidence_detail=evidence_detail,
        )
        evidence_records.append(ev)

        rank = _conf_rank.get(confidence, 0)
        field_candidates.setdefault(field, []).append((rank, ev))

    # Build candidate_metadata: pick highest-confidence evidence per field
    candidate_metadata: dict[str, dict[str, Any]] = {}
    for field, ranked_evs in field_candidates.items():
        ranked_evs.sort(key=lambda x: x[0], reverse=True)
        _rank, best_ev = ranked_evs[0]
        all_ids = [e["evidence_id"] for _r, e in ranked_evs]
        candidate_metadata[field] = make_candidate_field(
            field=field,
            candidate_value=best_ev["observed_value"],
            candidate_value_normalized=best_ev["observed_value_normalized"],
            candidate_source_type=best_ev["source_type"],
            candidate_source_ids=all_ids,
            confidence=best_ev["confidence"],
        )

    return evidence_records, candidate_metadata


# ---------------------------------------------------------------------------
# Main bundle builder
# ---------------------------------------------------------------------------


def build_metadata_evidence_bundle(
    *,
    workflow_type: str = WORKFLOW_UNKNOWN,
    workflow_session_id: str = "",
    workflow_row_id: str = "",
    dataset_context: dict[str, Any] | None = None,
    raw_submitted_metadata: dict[str, Any] | None = None,
    candidate_observations: list[dict[str, Any]] | None = None,
    existing_qaqc_findings: list[dict[str, Any]] | None = None,
    submitted_source_type: str = SUBMITTED_SOURCE_LOADSHEET,
    policy_profile: str = "default",
) -> dict[str, Any]:
    """
    Build a complete MDE bundle from SBLT or SSI inputs.

    Parameters
    ----------
    workflow_type:
        "sblt" | "ssi" | "unknown"
    workflow_session_id:
        The originating session ID (e.g. sblt_... or ssi_...).
    workflow_row_id:
        The originating row ID.
    dataset_context:
        Use make_dataset_context() to build. Contains record_type, dataset_label,
        and source_reference.
    raw_submitted_metadata:
        Flat dict of {field_name: raw_value}. None/empty string values treated as absent.
    candidate_observations:
        List of observation dicts:
        {
          "field": str,
          "observed_value": any,
          "source_type": str,
          "source_label": str,
          "confidence": str,
          "evidence_detail": dict  # optional
        }
    existing_qaqc_findings:
        Pre-existing QAQC findings (e.g. from SBLT path validation) to carry forward.
    submitted_source_type:
        "loadsheet" | "source_intake" | "manual" | "unknown"
    policy_profile:
        Reserved for future policy switching. Currently only "default" is used.

    Returns
    -------
    A complete MDE bundle conforming to mde.bundle.v1.
    """
    bundle_id = _generate_bundle_id()
    now = _utc_now()

    # Normalise inputs
    raw_submitted = raw_submitted_metadata or {}
    observations = candidate_observations or []
    prior_findings = list(existing_qaqc_findings or [])
    ctx = dataset_context or make_dataset_context()

    # --- Step 1: Build submitted_metadata ---
    submitted_metadata = _build_submitted_metadata(raw_submitted, source_type=submitted_source_type)

    # --- Step 2: Process candidate observations → evidence_records + candidate_metadata ---
    evidence_records, candidate_metadata = _process_candidate_observations(observations)

    # --- Step 3: Detect intake mode ---
    intake_mode = detect_intake_mode(submitted_metadata, ctx)

    # --- Step 4: Update evidence comparison fields against submitted ---
    # (evidence records are given their comparison result here)
    field_to_evidence_ids: dict[str, list[str]] = {}
    for ev in evidence_records:
        field_to_evidence_ids.setdefault(ev["field"], []).append(ev["evidence_id"])

    # --- Step 5: Classify every field that appears in either submitted or candidate ---
    all_fields: set[str] = set(submitted_metadata.keys()) | set(candidate_metadata.keys())
    field_review: dict[str, Any] = {}
    new_findings: list[dict[str, Any]] = []

    for field in sorted(all_fields):
        sub_entry = submitted_metadata.get(field, make_submitted_field_absent(field=field))
        cand_entry = candidate_metadata.get(field)
        ev_ids = field_to_evidence_ids.get(field, [])

        fr, findings, comparison = classify_field(
            field=field,
            submitted_entry=sub_entry,
            candidate_entry=cand_entry,
            evidence_ids=ev_ids,
            finding_ids_in=[],
        )
        field_review[field] = fr
        new_findings.extend(findings)

        # Update evidence records with comparison result
        for ev in evidence_records:
            if ev["field"] == field:
                ev["comparison"] = comparison

    # --- Step 6: Build review summary ---
    review_summary = make_review_summary(field_review)

    # --- Step 7: Merge all findings ---
    all_findings = prior_findings + new_findings

    # --- Step 8: Approved canonical metadata starts empty ---
    approved_canonical_metadata: dict[str, Any] = {}

    # --- Step 9: Default approval state ---
    approval = make_approval()

    return {
        "schema_version": SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "created_at": now,
        "workflow": {
            "workflow_type": workflow_type,
            "workflow_session_id": workflow_session_id,
            "workflow_row_id": workflow_row_id,
            "intake_mode": intake_mode,
        },
        "dataset_context": ctx,
        "submitted_metadata": submitted_metadata,
        "candidate_metadata": candidate_metadata,
        "evidence_records": evidence_records,
        "qaqc_findings": all_findings,
        "field_review": field_review,
        "review_summary": review_summary,
        "approved_canonical_metadata": approved_canonical_metadata,
        "approval": approval,
    }
