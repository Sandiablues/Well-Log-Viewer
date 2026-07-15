"""Small backend-owned human-gated Source Intake readiness contract."""

from __future__ import annotations

from .identity_gate import clean_identity_value
from .models import (
    SourceFileCandidate,
    SourceIntakeCandidateRole,
    SourceIntakeParseStatus,
    SourceIntakeQaqcStatus,
    SourceIntakeReadinessState,
    SourceIntakeResolutionState,
    SourceIntakeHumanDecision,
    SourceIntakeWellAssignmentMode,
)
from .resolution_service import is_wmd_eligible


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



def _has_existing_well_assignment(candidate: SourceFileCandidate) -> bool:
    decision = candidate.current_decision
    return bool(
        decision
        and decision.decision == SourceIntakeHumanDecision.ASSIGN
        and decision.assignment_mode
        == SourceIntakeWellAssignmentMode.EXISTING_WELL
        and decision.assignment_target
    )


def evaluate_wmd_availability_readiness(
    candidate: SourceFileCandidate,
) -> SourceFileCandidate:
    """Set one current readiness state.

    QAQC findings remain available for review and export but do not block MWD
    promotion unless they prevent the system from establishing the minimum
    viewing contract: what the data is, which well it belongs to, and whether
    it can be viewed. Technical failure, unsupported data, missing required
    payload, unresolved well association, or unresolved depth normalization
    required for viewing may block progression.
    """
    if (
        candidate.is_available_to_wmd
        or candidate.resolution_state == SourceIntakeResolutionState.REGISTERED
    ):
        candidate.readiness_state = SourceIntakeReadinessState.REGISTERED
        candidate.readiness_issues = []
        candidate.available_human_actions = []
        return candidate

    if candidate.resolution_state == SourceIntakeResolutionState.EXCLUDED:
        candidate.readiness_state = SourceIntakeReadinessState.EXCLUDED
        candidate.readiness_issues = ["Candidate is excluded from ingestion."]
        candidate.available_human_actions = ["clear_decision"]
        return candidate

    if candidate.resolution_state == SourceIntakeResolutionState.DUPLICATE:
        candidate.readiness_state = SourceIntakeReadinessState.BLOCKED
        candidate.readiness_issues = [
            "Candidate is an exact-content duplicate."
        ]
        candidate.available_human_actions = []
        return candidate

    hard_issues: list[str] = []

    if candidate.candidate_role not in _SUPPORTED_ROLES:
        hard_issues.append(
            "Candidate role is not supported for WMD availability: "
            f"{candidate.candidate_role.value}."
        )

    if candidate.parser_status not in _USABLE_PARSE:
        hard_issues.append(
            "Candidate parser status is not usable: "
            f"{candidate.parser_status.value}."
        )

    if candidate.resolution_state == SourceIntakeResolutionState.HARD_FAILED:
        hard_issues.append(
            "Candidate has a non-overridable technical failure."
        )

    if (
        candidate.qaqc_status.status not in _USABLE_QAQC
        or candidate.qaqc_status.failure_count > 0
    ):
        hard_issues.append(
            "Candidate QAQC contains a blocking technical failure."
        )

    if candidate.candidate_role == SourceIntakeCandidateRole.WELL_LOG_CANDIDATE:
        if candidate.parsed_metadata is None:
            hard_issues.append("Candidate has no parsed LAS metadata.")

    if (
        candidate.candidate_role
        == SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE
    ):
        if candidate.geometry_preview is None:
            hard_issues.append(
                "Geometry candidate has no parsed deviation-survey preview."
            )
        elif not candidate.geometry_preview.stations_preview:
            hard_issues.append(
                "Geometry candidate has no station payload to make available."
            )

    if hard_issues:
        candidate.readiness_state = SourceIntakeReadinessState.BLOCKED
        candidate.readiness_issues = list(dict.fromkeys(hard_issues))
        candidate.available_human_actions = []
        return candidate

    review_issues: list[str] = []

    depth_contract = candidate.depth_normalization
    if depth_contract is not None and getattr(depth_contract.status, "value", depth_contract.status) == "review_required":
        review_issues.append("A human must choose the normalized depth unit: metres or feet.")

    if (
        candidate.candidate_role == SourceIntakeCandidateRole.WELL_LOG_CANDIDATE
        and not _canonical_well_name(candidate)
        and not _has_existing_well_assignment(candidate)
    ):
        review_issues.append(
            "A human must assign or confirm the destination well."
        )

    if review_issues:
        candidate.readiness_state = SourceIntakeReadinessState.REVIEW_REQUIRED
        candidate.readiness_issues = list(dict.fromkeys(review_issues))
        candidate.available_human_actions = [
            "accept",
            "correct",
            "assign",
            "exclude",
        ]
        return candidate

    candidate.readiness_state = SourceIntakeReadinessState.READY
    candidate.readiness_issues = []
    candidate.available_human_actions = []
    return candidate


def evaluate_registration_readiness(
    candidate: SourceFileCandidate,
) -> SourceFileCandidate:
    """Compatibility alias for the former registration-oriented contract."""
    return evaluate_wmd_availability_readiness(candidate)
