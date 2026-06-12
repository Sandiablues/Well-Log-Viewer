"""KR-2 Governance status definitions and validation helpers.

Defines the canonical governance lifecycle for all managed KR records:

  seed       → bootstrap/default knowledge from Python constants (read-only source)
  candidate  → imported or newly proposed knowledge awaiting review
  approved   → trusted knowledge served to classifier/inventory/display
  rejected   → reviewed and rejected; retained for audit history
  deprecated → formerly valid knowledge retained for backward compatibility

Status transitions are strictly controlled; see VALID_TRANSITIONS.
"""

from __future__ import annotations

from enum import Enum


class GovernanceStatus(str, Enum):
    """Lifecycle status for every managed KR record."""

    SEED = "seed"
    CANDIDATE = "candidate"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


# ---------------------------------------------------------------------------
# Status sets
# ---------------------------------------------------------------------------

#: Statuses whose records are eligible for production use by classifier /
#: inventory / display layers.  Candidate records are NOT production-eligible
#: unless the caller explicitly requests them.
PRODUCTION_STATUSES: frozenset[GovernanceStatus] = frozenset(
    {GovernanceStatus.SEED, GovernanceStatus.APPROVED}
)

#: Terminal statuses — no further transitions are permitted.
TERMINAL_STATUSES: frozenset[GovernanceStatus] = frozenset(
    {GovernanceStatus.REJECTED, GovernanceStatus.DEPRECATED}
)

#: Allowed forward transitions for each status.
VALID_TRANSITIONS: dict[GovernanceStatus, frozenset[GovernanceStatus]] = {
    GovernanceStatus.SEED: frozenset(
        {GovernanceStatus.APPROVED, GovernanceStatus.DEPRECATED}
    ),
    GovernanceStatus.CANDIDATE: frozenset(
        {GovernanceStatus.APPROVED, GovernanceStatus.REJECTED}
    ),
    GovernanceStatus.APPROVED: frozenset(
        {GovernanceStatus.DEPRECATED}
    ),
    GovernanceStatus.REJECTED: frozenset(),
    GovernanceStatus.DEPRECATED: frozenset(),
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def is_valid_transition(
    from_status: GovernanceStatus, to_status: GovernanceStatus
) -> bool:
    """Return True if transitioning from_status → to_status is permitted."""
    return to_status in VALID_TRANSITIONS.get(from_status, frozenset())


def is_production_eligible(status: GovernanceStatus) -> bool:
    """Return True if records with this status may be served to classifiers."""
    return status in PRODUCTION_STATUSES


def validate_status(value: str) -> GovernanceStatus:
    """Parse and validate a status string; raise ValueError on unknown values."""
    try:
        return GovernanceStatus(value)
    except ValueError:
        valid = {s.value for s in GovernanceStatus}
        raise ValueError(
            f"Invalid governance status {value!r}. Valid values: {sorted(valid)}"
        )
