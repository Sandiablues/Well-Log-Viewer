"""Focused tests for the backend-owned WDV policy-unit contract.

UNIT-3A extension: adds tests for the dormant PolicyUnitResolutionResult and
ResolvedDisplayPolicy types defined in policy_unit_resolution.py.
"""

from __future__ import annotations

import math

import pytest

from app.wdv_display.policy_unit_contract import (
    UnitConversionStatus,
    WdvPolicyUnitContract,
)
from app.wdv_display.policy_unit_resolution import (
    PolicyUnitResolutionResult,
    PolicyUnitResolutionStatus,
    ResolvedDisplayPolicy,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("OHM.M", "ohmm"),
        ("ohm_m", "ohmm"),
        ("ohm*m", "ohmm"),
        ("API", "gapi"),
        ("pu", "%"),
        ("fraction", "v/v"),
        ("µs/ft", "us/ft"),
        ("°F", "degf"),
    ],
)
def test_alias_normalization(raw: str, expected: str) -> None:
    assert WdvPolicyUnitContract.normalize_unit(raw) == expected


def test_unknown_and_blank_units_are_not_invented() -> None:
    assert WdvPolicyUnitContract.normalize_unit(None) is None
    assert WdvPolicyUnitContract.normalize_unit("") is None
    assert WdvPolicyUnitContract.normalize_unit("mystery-unit") is None


@pytest.mark.parametrize(
    ("source", "target", "value", "expected"),
    [
        ("%", "v/v", 45.0, 0.45),
        ("v/v", "%", 0.45, 45.0),
        ("in", "mm", 1.0, 25.4),
        ("mm", "in", 25.4, 1.0),
        ("cm", "mm", 1.0, 10.0),
        ("g/cc", "kg/m3", 1.0, 1000.0),
        ("kg/m3", "g/cc", 1000.0, 1.0),
        ("us/ft", "us/m", 100.0, 328.0839895013123),
        ("us/m", "us/ft", 328.0839895013123, 100.0),
        ("psi", "kpa", 1.0, 6.894757293168361),
        ("bar", "kpa", 1.0, 100.0),
        ("degf", "degc", 32.0, 0.0),
        ("degf", "degc", 212.0, 100.0),
        ("degc", "degf", 100.0, 212.0),
    ],
)
def test_supported_conversions(
    source: str,
    target: str,
    value: float,
    expected: float,
) -> None:
    result = WdvPolicyUnitContract.convert_value(
        value,
        source_unit=source,
        target_unit=target,
    )
    assert result.status is UnitConversionStatus.RESOLVED
    assert result.value == pytest.approx(expected, rel=1e-12, abs=1e-12)


@pytest.mark.parametrize("unit", ["gapi", "mv", "ohmm", "b/e", "md", "rpm"])
def test_identity_units_are_supported(unit: str) -> None:
    result = WdvPolicyUnitContract.convert_value(
        12.5,
        source_unit=unit,
        target_unit=unit,
    )
    assert result.status is UnitConversionStatus.RESOLVED
    assert result.value == 12.5


def test_incompatible_dimensions_are_explicit() -> None:
    result = WdvPolicyUnitContract.convert_value(
        45.0,
        source_unit="%",
        target_unit="us/ft",
    )
    assert result.status is UnitConversionStatus.INCOMPATIBLE_DIMENSIONS
    assert result.value is None


def test_unknown_source_and_target_are_distinct() -> None:
    source_unknown = WdvPolicyUnitContract.convert_value(
        1.0,
        source_unit="unknown",
        target_unit="mm",
    )
    target_unknown = WdvPolicyUnitContract.convert_value(
        1.0,
        source_unit="mm",
        target_unit="unknown",
    )
    assert source_unknown.status is UnitConversionStatus.UNKNOWN_SOURCE_UNIT
    assert target_unknown.status is UnitConversionStatus.UNKNOWN_TARGET_UNIT


def test_non_finite_values_are_rejected() -> None:
    for value in (float("nan"), float("inf"), float("-inf")):
        result = WdvPolicyUnitContract.convert_value(
            value,
            source_unit="mm",
            target_unit="in",
        )
        assert result.status is UnitConversionStatus.NON_FINITE_VALUE


def test_bounds_conversion_preserves_reversed_order() -> None:
    result = WdvPolicyUnitContract.convert_bounds(
        45.0,
        -15.0,
        source_unit="%",
        target_unit="v/v",
    )
    assert result.status is UnitConversionStatus.RESOLVED
    assert result.minimum == pytest.approx(0.45)
    assert result.maximum == pytest.approx(-0.15)




# Block 3A — Focused test additions for test_wdv_policy_unit_contract.py
# These tests are appended to the existing file by b3a_add_tests.command.
# ---------------------------------------------------------------------------
# BLOCK-3A: Identity alias completion — G/C3 and US/F
# ---------------------------------------------------------------------------
# Two alias entries were added to WdvPolicyUnitContract._ALIASES:
#   "g/c3": "g/cc"   — LAS density abbreviation
#   "us/f": "us/ft"  — LAS sonic abbreviation
# These tests prove:
#   Group 1 — New aliases normalize correctly
#   Group 2 — Existing aliases are unaffected (regression)
#   Group 3 — Near-miss tokens are still rejected
#   Group 4 — Canonical _UNITS set is unchanged
#   Group 5 — End-to-end identity resolution chain for RHOZ, DTCO, DTSM controls
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Group 1 — New alias normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Density: G/C3 LAS abbreviation
        ("G/C3",   "g/cc"),
        ("g/c3",   "g/cc"),
        ("G/c3",   "g/cc"),  # mixed case
        (" G/C3 ", "g/cc"),  # whitespace stripped
        # Sonic: US/F LAS abbreviation
        ("US/F",   "us/ft"),
        ("us/f",   "us/ft"),
        ("Us/F",   "us/ft"),  # mixed case
        (" US/F ", "us/ft"),  # whitespace stripped
    ],
)
def test_block3a_new_alias_normalization(raw: str, expected: str) -> None:
    """New LAS abbreviation aliases must resolve to their canonical units."""
    assert WdvPolicyUnitContract.normalize_unit(raw) == expected


# ---------------------------------------------------------------------------
# Group 2 — Existing aliases unaffected (regression)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Density family — existing aliases
        ("G/CC",    "g/cc"),
        ("g/cm3",   "g/cc"),
        ("g/cm^3",  "g/cc"),
        ("GCC",     "g/cc"),
        # Sonic family — existing aliases
        ("US/FT",   "us/ft"),
        ("µs/ft",   "us/ft"),
        ("usec/ft", "us/ft"),
    ],
)
def test_block3a_existing_aliases_unchanged(raw: str, expected: str) -> None:
    """Existing aliases must still resolve correctly after adding the new entries."""
    assert WdvPolicyUnitContract.normalize_unit(raw) == expected


# ---------------------------------------------------------------------------
# Group 3 — Near-miss rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "G/C4",          # near-miss density — must not match g/c3
        "US/M",          # valid unit, but a different canonical (us/m), not us/ft
        "mystery-unit",  # unknown
        "",              # empty
        None,            # None
    ],
)
def test_block3a_near_miss_not_matched_as_new_aliases(raw: object) -> None:
    """Near-miss and unknown tokens must not be pulled in by the new alias entries."""
    result = WdvPolicyUnitContract.normalize_unit(raw)
    # G/C4 must return None; US/M returns "us/m" (existing, not us/ft)
    if raw == "US/M":
        assert result == "us/m"  # existing alias unaffected
    elif raw == "G/C4":
        assert result is None
    else:
        assert result is None


def test_block3a_g_c4_strictly_rejected() -> None:
    """G/C4 is a near-miss for G/C3 and must return None."""
    assert WdvPolicyUnitContract.normalize_unit("G/C4") is None


def test_block3a_unknown_unit_returns_none() -> None:
    """An unknown unit string must still return None."""
    assert WdvPolicyUnitContract.normalize_unit("mystery-unit") is None


# ---------------------------------------------------------------------------
# Group 4 — Canonical _UNITS set protection
# ---------------------------------------------------------------------------


def test_block3a_g_cc_remains_in_units() -> None:
    """g/cc must remain a canonical unit in _UNITS."""
    assert "g/cc" in WdvPolicyUnitContract._UNITS


def test_block3a_us_ft_remains_in_units() -> None:
    """us/ft must remain a canonical unit in _UNITS."""
    assert "us/ft" in WdvPolicyUnitContract._UNITS


def test_block3a_g_c3_not_added_to_units() -> None:
    """g/c3 is an alias key only — must NOT appear in _UNITS."""
    assert "g/c3" not in WdvPolicyUnitContract._UNITS


def test_block3a_us_f_not_added_to_units() -> None:
    """us/f is an alias key only — must NOT appear in _UNITS."""
    assert "us/f" not in WdvPolicyUnitContract._UNITS


def test_block3a_aliases_count_increased_by_exactly_two() -> None:
    """_ALIASES must contain exactly 2 more entries than before (64 → 66)."""
    assert len(WdvPolicyUnitContract._ALIASES) == 66


# ---------------------------------------------------------------------------
# Group 5 — End-to-end identity resolution chain
#
# Proves that after the alias is added, curve_unit="G/C3" normalizes to the
# same canonical value as policy_unit="g/cc" → IDENTITY resolution path.
# Similarly for US/F and DTSM/DTCO → us/ft → sonic family.
#
# The resolver's IDENTITY branch fires when:
#   canonical_policy_unit == canonical_curve_unit (both not None)
# We prove this directly from the normalize_unit output.
# ---------------------------------------------------------------------------


def test_block3a_rhoz_g_c3_alias_reaches_identity_path() -> None:
    """
    RHOZ: curve_unit='G/C3', policy_unit='g/cc'.
    After the alias edit, both normalize to 'g/cc' → IDENTITY branch.
    """
    canonical_curve = WdvPolicyUnitContract.normalize_unit("G/C3")
    canonical_policy = WdvPolicyUnitContract.normalize_unit("g/cc")
    # Neither must be None (which would trigger UNKNOWN_CURVE_UNIT)
    assert canonical_curve is not None, "G/C3 must not produce UNKNOWN_CURVE_UNIT"
    assert canonical_policy is not None
    # Both must be the same value → IDENTITY branch
    assert canonical_curve == canonical_policy, (
        f"G/C3 canonical ({canonical_curve!r}) != g/cc canonical ({canonical_policy!r}); "
        "IDENTITY path requires equal canonical units"
    )
    # Explicit: both must be g/cc
    assert canonical_curve == "g/cc"


def test_block3a_dtco_us_f_alias_reaches_identity_path() -> None:
    """
    DTCO: curve_unit='US/F', policy_unit='us/ft'.
    After the alias edit, both normalize to 'us/ft' → IDENTITY branch.
    """
    canonical_curve = WdvPolicyUnitContract.normalize_unit("US/F")
    canonical_policy = WdvPolicyUnitContract.normalize_unit("us/ft")
    assert canonical_curve is not None, "US/F must not produce UNKNOWN_CURVE_UNIT"
    assert canonical_policy is not None
    assert canonical_curve == canonical_policy, (
        f"US/F canonical ({canonical_curve!r}) != us/ft canonical ({canonical_policy!r}); "
        "IDENTITY path requires equal canonical units"
    )
    assert canonical_curve == "us/ft"


def test_block3a_dtsm_us_f_alias_reaches_identity_path() -> None:
    """
    DTSM: curve_unit='US/F', policy_unit='us/ft'.
    Same alias as DTCO — both normalize to 'us/ft' → IDENTITY branch.
    """
    canonical_curve = WdvPolicyUnitContract.normalize_unit("US/F")
    canonical_policy = WdvPolicyUnitContract.normalize_unit("us/ft")
    assert canonical_curve is not None, "US/F must not produce UNKNOWN_CURVE_UNIT for DTSM"
    assert canonical_curve == canonical_policy
    assert canonical_curve == "us/ft"


def test_block3a_gr_normalization_unchanged() -> None:
    """GR uses GAPI — must normalize correctly and be unaffected by the edit."""
    assert WdvPolicyUnitContract.normalize_unit("GAPI") == "gapi"
    assert WdvPolicyUnitContract.normalize_unit("API") == "gapi"


def test_block3a_nphi_normalization_unchanged() -> None:
    """NPHI uses V/V — must normalize correctly and be unaffected by the edit."""
    assert WdvPolicyUnitContract.normalize_unit("V/V") == "v/v"
    assert WdvPolicyUnitContract.normalize_unit("fraction") == "v/v"


def test_block3a_sp_normalization_unchanged() -> None:
    """SP uses MV — must normalize correctly and be unaffected by the edit."""
    assert WdvPolicyUnitContract.normalize_unit("MV") == "mv"
    assert WdvPolicyUnitContract.normalize_unit("millivolt") == "mv"


def test_block3a_identity_path_no_numeric_conversion_density() -> None:
    """
    IDENTITY resolution means no numeric conversion: factor=1, offset=0.
    g/cc → g/cc: convert_value(x, source_unit='g/cc', target_unit='g/cc') == x.
    """
    for v in (1.0, 2.65, 0.5, 3.0):
        result = WdvPolicyUnitContract.convert_value(
            v, source_unit="g/cc", target_unit="g/cc"
        )
        assert result.status is UnitConversionStatus.RESOLVED
        assert result.value == pytest.approx(v, rel=1e-12)


def test_block3a_identity_path_no_numeric_conversion_sonic() -> None:
    """
    IDENTITY resolution means no numeric conversion: factor=1, offset=0.
    us/ft → us/ft: convert_value(x, source_unit='us/ft', target_unit='us/ft') == x.
    """
    for v in (40.0, 80.0, 100.0, 140.0):
        result = WdvPolicyUnitContract.convert_value(
            v, source_unit="us/ft", target_unit="us/ft"
        )
        assert result.status is UnitConversionStatus.RESOLVED
        assert result.value == pytest.approx(v, rel=1e-12)


def test_block3a_g_c3_alias_key_format() -> None:
    """
    The alias key for G/C3 is produced by _alias_key: strip+lower+collapse whitespace.
    Verify the key 'g/c3' is present in _ALIASES and maps to 'g/cc'.
    """
    assert WdvPolicyUnitContract._ALIASES.get("g/c3") == "g/cc"


def test_block3a_us_f_alias_key_format() -> None:
    """
    The alias key for US/F is produced by _alias_key: strip+lower+collapse whitespace.
    Verify the key 'us/f' is present in _ALIASES and maps to 'us/ft'.
    """
    assert WdvPolicyUnitContract._ALIASES.get("us/f") == "us/ft"


# ---------------------------------------------------------------------------
# UNIT-3A: PolicyUnitResolutionResult and ResolvedDisplayPolicy contract tests
# ---------------------------------------------------------------------------


_RESOLVER_VERSION = "wdv_display_units_v3_foundation_dormant"


def _make_result(
    *,
    status: PolicyUnitResolutionStatus,
    resolved_bounds_usable: bool,
    resolved_min: float | None = None,
    resolved_max: float | None = None,
    conversion_applied: bool = False,
    canonical_policy_unit: str | None = None,
    canonical_curve_unit: str | None = None,
    unresolved_reason: str | None = None,
    policy_source: str | None = None,
) -> PolicyUnitResolutionResult:
    return PolicyUnitResolutionResult(
        status=status,
        resolved_bounds_usable=resolved_bounds_usable,
        policy_record_id="test_record_id",
        policy_record_version=2,
        policy_source=policy_source,  # type: ignore[arg-type]
        original_policy_min=0.0,
        original_policy_max=150.0,
        canonical_policy_unit=canonical_policy_unit,
        canonical_curve_unit=canonical_curve_unit,
        resolved_min=resolved_min,
        resolved_max=resolved_max,
        conversion_applied=conversion_applied,
        unresolved_reason=unresolved_reason,
        resolver_version=_RESOLVER_VERSION,
        policy_revision="abc123",
    )


def test_resolution_status_identity_marks_bounds_usable() -> None:
    """IDENTITY status must set resolved_bounds_usable=True."""
    result = _make_result(
        status=PolicyUnitResolutionStatus.IDENTITY,
        resolved_bounds_usable=True,
        resolved_min=0.0,
        resolved_max=150.0,
        canonical_policy_unit="gapi",
        canonical_curve_unit="gapi",
    )
    assert result.resolved_bounds_usable is True
    assert result.conversion_applied is False
    assert result.resolved_min == 0.0
    assert result.resolved_max == 150.0


def test_resolution_status_converted_marks_bounds_usable() -> None:
    """CONVERTED status must set resolved_bounds_usable=True and carry converted bounds."""
    result = _make_result(
        status=PolicyUnitResolutionStatus.CONVERTED,
        resolved_bounds_usable=True,
        resolved_min=0.45,
        resolved_max=-0.15,
        conversion_applied=True,
        canonical_policy_unit="%",
        canonical_curve_unit="v/v",
    )
    assert result.resolved_bounds_usable is True
    assert result.conversion_applied is True
    assert result.resolved_min == pytest.approx(0.45)
    assert result.resolved_max == pytest.approx(-0.15)


@pytest.mark.parametrize(
    "status",
    [
        PolicyUnitResolutionStatus.MISSING_POLICY_UNIT,
        PolicyUnitResolutionStatus.UNKNOWN_POLICY_UNIT,
        PolicyUnitResolutionStatus.MISSING_CURVE_UNIT,
        PolicyUnitResolutionStatus.UNKNOWN_CURVE_UNIT,
        PolicyUnitResolutionStatus.INCOMPATIBLE,
        PolicyUnitResolutionStatus.UNRESOLVED,
    ],
)
def test_non_usable_statuses_mark_bounds_not_usable(
    status: PolicyUnitResolutionStatus,
) -> None:
    """All non-usable statuses must set resolved_bounds_usable=False."""
    result = _make_result(
        status=status,
        resolved_bounds_usable=False,
        unresolved_reason=status.value,
    )
    assert result.resolved_bounds_usable is False
    assert result.resolved_min is None
    assert result.resolved_max is None


def test_resolved_bounds_usable_inconsistent_with_status_raises() -> None:
    """resolved_bounds_usable=True with a non-usable status must raise ValueError."""
    with pytest.raises(ValueError, match="inconsistent with status"):
        PolicyUnitResolutionResult(
            status=PolicyUnitResolutionStatus.MISSING_POLICY_UNIT,
            resolved_bounds_usable=True,  # wrong
            policy_record_id="x",
            policy_record_version=1,
            policy_source=None,
            original_policy_min=0.0,
            original_policy_max=150.0,
            canonical_policy_unit=None,
            canonical_curve_unit=None,
            resolved_min=None,
            resolved_max=None,
            conversion_applied=False,
            unresolved_reason="missing",
            resolver_version=_RESOLVER_VERSION,
            policy_revision=None,
        )


def test_non_none_resolved_bounds_when_not_usable_raises() -> None:
    """resolved_min or resolved_max must be None when resolved_bounds_usable is False."""
    with pytest.raises(ValueError, match="resolved_min and resolved_max must be None"):
        PolicyUnitResolutionResult(
            status=PolicyUnitResolutionStatus.MISSING_POLICY_UNIT,
            resolved_bounds_usable=False,
            policy_record_id="x",
            policy_record_version=1,
            policy_source=None,
            original_policy_min=0.0,
            original_policy_max=150.0,
            canonical_policy_unit=None,
            canonical_curve_unit=None,
            resolved_min=0.0,  # must be None
            resolved_max=150.0,  # must be None
            conversion_applied=False,
            unresolved_reason="missing",
            resolver_version=_RESOLVER_VERSION,
            policy_revision=None,
        )


def test_policy_source_literal_values() -> None:
    """policy_source must accept exact, family, and fallback literals."""
    for source in ("exact", "family", "fallback"):
        result = _make_result(
            status=PolicyUnitResolutionStatus.IDENTITY,
            resolved_bounds_usable=True,
            resolved_min=0.0,
            resolved_max=150.0,
            canonical_policy_unit="gapi",
            canonical_curve_unit="gapi",
            policy_source=source,
        )
        assert result.policy_source == source


def test_resolved_display_policy_dormant_unit_resolution_is_none() -> None:
    """ResolvedDisplayPolicy with unit_resolution=None represents dormant mode."""
    rdp = ResolvedDisplayPolicy(
        policy={"display_min": 0.0, "display_max": 150.0},
        unit_resolution=None,
    )
    assert rdp.policy is not None
    assert rdp.unit_resolution is None


def test_resolved_display_policy_no_kr_match() -> None:
    """ResolvedDisplayPolicy with policy=None represents no KR match."""
    rdp = ResolvedDisplayPolicy(policy=None, unit_resolution=None)
    assert rdp.policy is None
    assert rdp.unit_resolution is None


def test_resolved_display_policy_with_usable_resolution() -> None:
    """ResolvedDisplayPolicy carries a fully resolved result when wired."""
    resolution = _make_result(
        status=PolicyUnitResolutionStatus.CONVERTED,
        resolved_bounds_usable=True,
        resolved_min=0.0,
        resolved_max=0.45,
        conversion_applied=True,
        canonical_policy_unit="%",
        canonical_curve_unit="v/v",
    )
    rdp = ResolvedDisplayPolicy(
        policy={"display_min": 0.0, "display_max": 45.0},
        unit_resolution=resolution,
    )
    assert rdp.unit_resolution is not None
    assert rdp.unit_resolution.resolved_bounds_usable is True
    assert rdp.unit_resolution.status is PolicyUnitResolutionStatus.CONVERTED
