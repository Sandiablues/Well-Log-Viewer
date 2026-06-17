"""Backend-authoritative Source Intake registration readiness contract.

This module classifies readiness with structured codes. It does not own the
legacy human-readable registration rejection wording; registration.py maps
these codes back to the established public diagnostic contract.
"""
from __future__ import annotations

from .identity_gate import clean_identity_value
from .models import (
    SourceFileCandidate,
    SourceIntakeCandidateRole,
    SourceIntakeParseStatus,
    SourceIntakeQaqcStatus,
    SourceIntakeReadinessBlockCategory,
    SourceIntakeReadinessBlockReason,
    SourceIntakeResolutionState,
)
from .resolution_service import is_ingestible

_USABLE_PARSE = {
    SourceIntakeParseStatus.PARSED,
    SourceIntakeParseStatus.PARSED_WITH_WARNINGS,
}
_USABLE_QAQC = {
    SourceIntakeQaqcStatus.PASS,
    SourceIntakeQaqcStatus.WARNING,
    SourceIntakeQaqcStatus.REVIEW_REQUIRED,
}
_SUPPORTED_ROLES = {
    SourceIntakeCandidateRole.WELL_LOG_CANDIDATE,
    SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE,
}


def _canonical_well_name(candidate: SourceFileCandidate) -> str | None:
    values: list[object | None] = []
    if candidate.resolved_metadata is not None:
        values.append(candidate.resolved_metadata.well_name.value)
    if candidate.parsed_metadata is not None:
        values.append(candidate.parsed_metadata.well_header.well_name)
    values.append(candidate.managed_well_name)
    for value in values:
        cleaned = clean_identity_value(value)
        if cleaned:
            return cleaned
    return None


def evaluate_registration_readiness(candidate: SourceFileCandidate) -> SourceFileCandidate:
    """Populate and return the backend-owned registration readiness contract."""
    reasons: list[SourceIntakeReadinessBlockReason] = []
    actions: list[str] = []
    hard_failure_count = 0
    overridable_review_count = 0

    def add(
        code: str,
        category: SourceIntakeReadinessBlockCategory,
        message: str,
        *,
        overridable: bool = False,
    ) -> None:
        nonlocal hard_failure_count, overridable_review_count
        if any(item.code == code for item in reasons):
            return
        reasons.append(
            SourceIntakeReadinessBlockReason(
                code=code,
                category=category,
                message=message,
                overridable=overridable,
            )
        )
        if category == SourceIntakeReadinessBlockCategory.HARD_FAILURE:
            hard_failure_count += 1
        elif category == SourceIntakeReadinessBlockCategory.REVIEW_REQUIRED:
            overridable_review_count += 1

    if candidate.registration_status == "registered" or candidate.resolution_state == SourceIntakeResolutionState.REGISTERED:
        add(
            "already_registered",
            SourceIntakeReadinessBlockCategory.LIFECYCLE,
            "Candidate is already registered to Managed Well Inventory.",
        )

    if candidate.resolution_state == SourceIntakeResolutionState.DUPLICATE:
        add(
            "exact_content_duplicate",
            SourceIntakeReadinessBlockCategory.LIFECYCLE,
            "Candidate is an exact-content duplicate.",
        )

    if candidate.resolution_state == SourceIntakeResolutionState.EXCLUDED:
        add(
            "candidate_excluded",
            SourceIntakeReadinessBlockCategory.LIFECYCLE,
            "Candidate is excluded from ingestion.",
        )
        actions.append("reopen_candidate")

    if candidate.candidate_role not in _SUPPORTED_ROLES:
        add(
            "unsupported_candidate_role",
            SourceIntakeReadinessBlockCategory.HARD_FAILURE,
            f"Candidate role is not registration-supported: {candidate.candidate_role.value}.",
        )

    if candidate.parser_status not in _USABLE_PARSE:
        add(
            "parser_not_usable",
            SourceIntakeReadinessBlockCategory.HARD_FAILURE,
            f"Candidate parser status is not usable: {candidate.parser_status.value}.",
        )

    if candidate.resolution_state == SourceIntakeResolutionState.HARD_FAILED:
        add(
            "hard_failed",
            SourceIntakeReadinessBlockCategory.HARD_FAILURE,
            "Candidate has a non-overridable technical failure.",
        )

    if candidate.qaqc_status.status not in _USABLE_QAQC or candidate.qaqc_status.failure_count > 0:
        add(
            "qaqc_failure",
            SourceIntakeReadinessBlockCategory.HARD_FAILURE,
            "Candidate QAQC contains blocking failures.",
        )

    canonical_well_resolved = bool(_canonical_well_name(candidate))

    if candidate.candidate_role == SourceIntakeCandidateRole.WELL_LOG_CANDIDATE:
        if candidate.parsed_metadata is None:
            add(
                "parsed_metadata_missing",
                SourceIntakeReadinessBlockCategory.HARD_FAILURE,
                "Candidate has no parsed LAS metadata.",
            )
        if not canonical_well_resolved:
            add(
                "canonical_well_unresolved",
                SourceIntakeReadinessBlockCategory.REVIEW_REQUIRED,
                "Candidate must be assigned to a canonical well.",
            )
            actions.extend(
                [
                    "assign_existing_well",
                    "create_new_well",
                    "confirm_suggestion",
                    "manual_correction",
                    "exclude_candidate",
                ]
            )

    if candidate.candidate_role == SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE:
        if candidate.geometry_preview is None:
            add(
                "geometry_preview_missing",
                SourceIntakeReadinessBlockCategory.HARD_FAILURE,
                "Geometry candidate has no parsed deviation-survey preview.",
            )
        elif not candidate.geometry_preview.stations_preview:
            add(
                "geometry_station_payload_missing",
                SourceIntakeReadinessBlockCategory.HARD_FAILURE,
                "Geometry candidate preview has no station payload to register.",
            )

    terminal_codes = {
        "already_registered",
        "exact_content_duplicate",
        "candidate_excluded",
        "hard_failed",
    }
    if not is_ingestible(candidate) and not any(item.code in terminal_codes for item in reasons):
        add(
            "resolution_required",
            SourceIntakeReadinessBlockCategory.REVIEW_REQUIRED,
            "Candidate resolution state requires review before registration.",
        )
        actions.extend(
            [
                "confirm_suggestion",
                "manual_correction",
                "accept_warnings",
                "promote_with_exception",
                "exclude_candidate",
            ]
        )

    if candidate.qaqc_status.non_blocking_warning_count > 0:
        actions.append("accept_warnings")
    if candidate.qaqc_status.review_controlled_count > 0:
        actions.append("promote_with_exception")
    if candidate.resolved_metadata is not None and any(
        getattr(candidate.resolved_metadata, name).value
        for name in ("well_name", "uwi", "operator", "field", "block")
    ):
        actions.append("confirm_suggestion")
    if candidate.resolution_state not in {
        SourceIntakeResolutionState.REGISTERED,
        SourceIntakeResolutionState.EXCLUDED,
        SourceIntakeResolutionState.DUPLICATE,
        SourceIntakeResolutionState.HARD_FAILED,
    }:
        actions.append("manual_correction")

    candidate.registration_block_reasons = reasons
    candidate.available_resolution_actions = list(dict.fromkeys(actions))
    candidate.hard_failure_count = max(
        hard_failure_count,
        candidate.qaqc_status.hard_failure_count,
    )
    candidate.overridable_review_count = max(
        overridable_review_count,
        candidate.qaqc_status.review_controlled_count,
    )
    candidate.non_blocking_warning_count = max(
        candidate.qaqc_status.non_blocking_warning_count,
        0,
    )
    candidate.canonical_well_resolved = canonical_well_resolved
    candidate.registration_eligible = not reasons
    return candidate
