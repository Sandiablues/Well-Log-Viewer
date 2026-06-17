from __future__ import annotations

from .models import (
    SourceFileCandidate,
    SourceIntakeFindingClass,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionAuditEvent,
)
from .qaqc import run_source_intake_qaqc, summarize_source_intake_qaqc


_CODE_ALIASES: dict[str, set[str]] = {
    "missing_uwi": {"identity.uwi.missing"},
    "missing_optional_unit": {"curve.unit.missing"},
    "geometry_review": {
        "candidate.role.wellbore_geometry",
        "geometry.preview.warning",
        "geometry.column_mapping.review",
    },
}

_ALL_REVIEW_ALIASES = {"review_required"}
_ALL_WARNING_ALIASES = {"optional_warning"}


def recompute_qaqc_after_resolution(
    candidate: SourceFileCandidate,
    event: SourceIntakeResolutionAuditEvent,
) -> SourceFileCandidate:
    """Replace current QAQC after a human decision; retain no QAQC history."""
    current = run_source_intake_qaqc(candidate)
    checks = list(current.checks)

    if event.action in {
        SourceIntakeResolutionAction.WARNING_ACCEPTED,
        SourceIntakeResolutionAction.PROMOTE_WITH_EXCEPTION,
    }:
        accepted_ids = _accepted_check_ids(checks, event)
        checks = [
            check
            for check in checks
            if (
                check.check_id not in accepted_ids
                or check.finding_class == SourceIntakeFindingClass.HARD_FAILURE
            )
        ]

    candidate.qaqc_status = summarize_source_intake_qaqc(checks)
    candidate.review_required = candidate.qaqc_status.review_required
    return candidate


def _accepted_check_ids(
    checks,
    event: SourceIntakeResolutionAuditEvent,
) -> set[str]:
    accepted: set[str] = set()
    available = {check.check_id for check in checks}

    for code in event.accepted_warning_codes:
        if code in available:
            accepted.add(code)
        accepted.update(_CODE_ALIASES.get(code, set()))

        if code in _ALL_REVIEW_ALIASES:
            accepted.update(
                check.check_id
                for check in checks
                if check.finding_class == SourceIntakeFindingClass.REVIEW_CONTROLLED
            )

        if code in _ALL_WARNING_ALIASES:
            accepted.update(
                check.check_id
                for check in checks
                if check.finding_class
                == SourceIntakeFindingClass.NON_BLOCKING_WARNING
            )

    if event.action == SourceIntakeResolutionAction.PROMOTE_WITH_EXCEPTION:
        accepted.update(
            check.check_id
            for check in checks
            if check.finding_class in {
                SourceIntakeFindingClass.REVIEW_CONTROLLED,
                SourceIntakeFindingClass.NON_BLOCKING_WARNING,
            }
        )

    return accepted & available
