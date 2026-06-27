"""Backend-owned WDV range display formatting."""

from app.wdv_session.assignment_policy_service import format_wdv_range_value


def test_binary_float_artifact_is_suppressed():
    assert format_wdv_range_value(-0.07529999999999999) == "-0.0753"


def test_common_curve_ranges_remain_concise():
    assert format_wdv_range_value(0.0219) == "0.0219"
    assert format_wdv_range_value(0.2) == "0.2"
    assert format_wdv_range_value(120.0) == "120"
    assert format_wdv_range_value(2000.0) == "2000"
    assert format_wdv_range_value(-2000.0) == "-2000"


def test_scientific_notation_is_reserved_for_extreme_values():
    assert format_wdv_range_value(0.000012345) == "1.23e-5"
    assert format_wdv_range_value(12_345_678.0) == "1.23e+7"
