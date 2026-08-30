from app.curve_fill_v2.models import CurveFillRule, CurveSeries, CurveTransform, FillStyle
from app.curve_fill_v2.service import CurveFillResolutionService

STYLE = FillStyle(color="#d94841", opacity=0.45)
SERIES = CurveSeries(
    managed_well_uid="well",
    managed_curve_uid="gr",
    sample_revision="1",
    depth_unit="m",
    value_unit="API",
    samples=((1000.0, 10.0), (1001.0, 20.0), (1002.0, 40.0)),
)
TRANSFORM = CurveTransform(
    assignment_uid="a-gr",
    managed_curve_uid="gr",
    transform_revision="1",
    track_width_px=160,
    horizontal_padding_px=5,
    scale_min=0.0,
    scale_max=150.0,
)


def test_threshold_below_left_boundary_fills_boundary_to_curve_only():
    rule = CurveFillRule(
        rule_uid="threshold-left",
        managed_well_uid="well",
        track_uid="track",
        order=0,
        rule_type="threshold",
        curve_a_uid="gr",
        comparison="less_than",
        reference_value=25.0,
        boundary="left",
        style=STYLE,
    )
    geometry = CurveFillResolutionService().resolve(
        rule=rule,
        series_a=SERIES,
        transform_a=TRANSFORM,
    )
    assert len(geometry.polygons) == 1
    polygon = geometry.polygons[0]
    assert polygon.top_depth == 1000.0
    assert 1001.0 < polygon.base_depth < 1002.0
    assert all(abs(vertex.x_b_px - 5.0) < 1e-9 for vertex in polygon.vertices)
    # The threshold is a predicate, not the fill anchor. The curve side remains
    # at its rendered X and therefore changes across the qualifying interval.
    assert len({round(vertex.x_a_px, 6) for vertex in polygon.vertices}) > 1


def test_threshold_curve_to_threshold_remains_available_when_boundary_is_null():
    rule = CurveFillRule(
        rule_uid="threshold-value",
        managed_well_uid="well",
        track_uid="track",
        order=0,
        rule_type="threshold",
        curve_a_uid="gr",
        comparison="less_than",
        reference_value=25.0,
        boundary=None,
        style=STYLE,
    )
    geometry = CurveFillResolutionService().resolve(
        rule=rule,
        series_a=SERIES,
        transform_a=TRANSFORM,
    )
    threshold_x = CurveFillResolutionService.value_to_x(25.0, TRANSFORM)
    assert threshold_x is not None
    assert all(abs(vertex.x_b_px - threshold_x) < 1e-9 for vertex in geometry.polygons[0].vertices)


def test_threshold_above_right_boundary_fills_curve_to_right_boundary():
    rule = CurveFillRule(
        rule_uid="threshold-right",
        managed_well_uid="well",
        track_uid="track",
        order=0,
        rule_type="threshold",
        curve_a_uid="gr",
        comparison="greater_than",
        reference_value=25.0,
        boundary="right",
        style=STYLE,
    )
    geometry = CurveFillResolutionService().resolve(
        rule=rule,
        series_a=SERIES,
        transform_a=TRANSFORM,
    )
    assert len(geometry.polygons) == 1
    assert all(abs(vertex.x_b_px - 155.0) < 1e-9 for vertex in geometry.polygons[0].vertices)
