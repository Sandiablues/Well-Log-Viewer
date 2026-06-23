"""Focused tests for the backend-owned WDV policy-unit contract."""

from __future__ import annotations

import math

import pytest

from app.wdv_display.policy_unit_contract import (
    UnitConversionStatus,
    WdvPolicyUnitContract,
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
