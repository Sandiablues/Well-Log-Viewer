import pytest

from app.source_intake.depth_units import depth_unit_conversion
from app.source_intake.dlis_parser import _normalized_depth_range


def test_parser_preserves_metric_depth_domain():
    result = _normalized_depth_range([197.0, 3684.0], depth_unit_conversion("m"))
    assert result == (197.0, 3684.0, "m")


def test_parser_normalizes_scaled_imperial_depth_domain():
    top, base, unit = _normalized_depth_range(
        [74760, 1494120], depth_unit_conversion("0.1 in")
    )
    assert top == pytest.approx(623.0)
    assert base == pytest.approx(12451.0)
    assert unit == "ft"


def test_parser_refuses_unknown_depth_domain():
    assert _normalized_depth_range(
        [100, 200], depth_unit_conversion("vendor-count")
    ) == (None, None, None)
