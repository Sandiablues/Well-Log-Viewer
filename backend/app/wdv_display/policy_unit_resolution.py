"""Typed unit-resolution contract for WDV governed display-policy bounds.

DORMANT — wdv_display_units_v3_foundation_dormant
--------------------------------------------------
This module defines the typed data structures for policy-unit resolution.
The resolver (ManagedKrFamilyDisplayPolicyResolver) does not call these
types yet.  Connection is gated on UNIT-3C after the activation block.

No runtime code imports this module in UNIT-3A.  The types are defined and
tested in isolation so the resolution contract is stable before wiring.

Resolution semantics
--------------------
``PolicyUnitResolutionResult.resolved_bounds_usable`` is True only when
``status`` is ``IDENTITY`` or ``CONVERTED``.  Callers must not apply
``resolved_min`` / ``resolved_max`` to display rendering when this field
is False.

Exact-policy failure is terminal: if a matched exact display_rule record
has an unusable policy_value_unit, the result status reflects that failure
and the resolver does NOT fall through to family-level records.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional


class PolicyUnitResolutionStatus(Enum):
    """Typed outcome of a policy-unit resolution attempt."""

    IDENTITY = "identity"
    """Policy unit and curve unit are the same canonical token.

    No numeric conversion was applied.  Bounds are usable as-is.
    """

    CONVERTED = "converted"
    """Bounds were successfully converted from policy unit to curve unit.

    ``resolved_min`` and ``resolved_max`` are in the curve's unit frame.
    """

    MISSING_POLICY_UNIT = "missing_policy_unit"
    """The matched policy record carries no ``policy_value_unit`` value.

    Bounds are NOT usable.  The resolver does not fall through to a family
    record when an exact-rule match has a missing policy unit.
    """

    UNKNOWN_POLICY_UNIT = "unknown_policy_unit"
    """``policy_value_unit`` is present but not recognized by WdvPolicyUnitContract.

    Bounds are NOT usable.
    """

    MISSING_CURVE_UNIT = "missing_curve_unit"
    """The curve item carries no ``curve_unit`` value.

    Bounds are NOT usable.
    """

    UNKNOWN_CURVE_UNIT = "unknown_curve_unit"
    """``curve_unit`` is present but not recognized by WdvPolicyUnitContract.

    Bounds are NOT usable.
    """

    INCOMPATIBLE = "incompatible"
    """Policy unit and curve unit have incompatible physical dimensions.

    Bounds are NOT usable.
    """

    UNRESOLVED = "unresolved"
    """Resolution failed for a reason not covered by a more specific status.

    Bounds are NOT usable.
    """


#: Statuses under which ``resolved_bounds_usable`` must be True.
_USABLE_STATUSES: frozenset[PolicyUnitResolutionStatus] = frozenset(
    {
        PolicyUnitResolutionStatus.IDENTITY,
        PolicyUnitResolutionStatus.CONVERTED,
    }
)


@dataclass(frozen=True)
class PolicyUnitResolutionResult:
    """Complete record of a single policy-unit resolution attempt.

    All fields are present regardless of outcome so consumers can log or
    display the full resolution trace without conditional attribute access.

    ``resolved_bounds_usable`` is the authoritative gate: callers must
    check this before using ``resolved_min`` / ``resolved_max``.
    """

    # Outcome gate.
    status: PolicyUnitResolutionStatus
    resolved_bounds_usable: bool

    # Policy record provenance.
    policy_record_id: Optional[str]
    policy_record_version: Optional[int]
    policy_source: Optional[Literal["exact", "family", "fallback"]]

    # Raw policy bounds (always in policy-unit frame; None if no KR match).
    original_policy_min: Optional[float]
    original_policy_max: Optional[float]

    # Canonical unit tokens after WdvPolicyUnitContract normalization.
    # None when the unit string was absent or unrecognized.
    canonical_policy_unit: Optional[str]
    canonical_curve_unit: Optional[str]

    # Output bounds in curve-unit frame.
    # None unless resolved_bounds_usable is True.
    resolved_min: Optional[float]
    resolved_max: Optional[float]

    # True when a numeric conversion was applied (CONVERTED status).
    # False for IDENTITY (same canonical token, bounds copied verbatim).
    conversion_applied: bool

    # Human-readable explanation when not usable.
    unresolved_reason: Optional[str]

    # Traceability.
    resolver_version: str
    policy_revision: Optional[str]

    def __post_init__(self) -> None:
        expected_usable = self.status in _USABLE_STATUSES
        if self.resolved_bounds_usable != expected_usable:
            raise ValueError(
                f"resolved_bounds_usable={self.resolved_bounds_usable!r} is "
                f"inconsistent with status={self.status!r}: expected "
                f"{expected_usable!r}"
            )
        if not self.resolved_bounds_usable:
            if self.resolved_min is not None or self.resolved_max is not None:
                raise ValueError(
                    "resolved_min and resolved_max must be None when "
                    "resolved_bounds_usable is False"
                )


@dataclass(frozen=True)
class ResolvedDisplayPolicy:
    """Pair of raw policy dict and typed unit-resolution result.

    ``policy`` is the raw dict returned by
    ``ManagedKrFamilyDisplayPolicyResolver`` (None when no KR rule matched).

    ``unit_resolution`` is None in dormant mode (UNIT-3A through UNIT-3B).
    It will be populated after UNIT-3C wires this contract into the resolver.
    """

    policy: Optional[dict]
    unit_resolution: Optional[PolicyUnitResolutionResult]
