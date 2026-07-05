import math
import pytest

from app.source_intake.depth_units import (
    UnsupportedDepthUnitError,
    depth_unit_conversion,
    require_depth_unit_conversion,
)


@pytest.mark.parametrize(
    ("raw", "factor", "unit"),
    [
        ("m", 1.0, "m"),
        ("metres", 1.0, "m"),
        ("0.1 m", 0.1, "m"),
        ("1e-1*m", 0.1, "m"),
        ("1/10 m", 0.1, "m"),
        ("cm", 0.01, "m"),
        ("10 mm", 0.01, "m"),
        ("km", 1000.0, "m"),
        ("ft", 1.0, "ft"),
        ("feet", 1.0, "ft"),
        ("0.01 ft", 0.01, "ft"),
        ("in", 1.0 / 12.0, "ft"),
        ("0.1 in", 1.0 / 120.0, "ft"),
        ("1/10 inch", 1.0 / 120.0, "ft"),
        ("yd", 3.0, "ft"),
    ],
)
def test_supported_depth_unit_matrix(raw, factor, unit):
    value = depth_unit_conversion(raw)
    assert value.supported
    assert value.status == "supported"
    assert value.factor == pytest.approx(factor)
    assert value.normalized_unit == unit


def test_metres_remain_metres():
    value = require_depth_unit_conversion("m")
    assert value.convert(197.0) == pytest.approx(197.0)
    assert value.normalized_unit == "m"


def test_scaled_inches_normalize_to_feet_generically():
    value = require_depth_unit_conversion("0.1 in")
    assert value.convert(74760) == pytest.approx(623.0)
    assert value.convert(1494120) == pytest.approx(12451.0)
    assert value.normalized_unit == "ft"


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (None, "missing_depth_unit"),
        ("", "missing_depth_unit"),
        ("furlong", "unknown_depth_unit"),
        ("m/10", "malformed_depth_unit"),
        ("0 m", "nonpositive_depth_scale"),
        ("-0.1 ft", "nonpositive_depth_scale"),
        ("1/0 in", "invalid_depth_scale"),
        ("depth", "unknown_depth_unit"),
    ],
)
def test_unknown_or_ambiguous_units_are_not_guessed(raw, reason):
    value = depth_unit_conversion(raw)
    assert not value.supported
    assert value.factor is None
    assert value.normalized_unit is None
    assert value.reason == reason
    with pytest.raises(UnsupportedDepthUnitError):
        require_depth_unit_conversion(raw)


def test_case_spacing_and_unicode_multiplication_are_normalized():
    value = require_depth_unit_conversion("  0.1 × IN  ")
    assert value.factor == pytest.approx(1.0 / 120.0)
    assert value.normalized_unit == "ft"
