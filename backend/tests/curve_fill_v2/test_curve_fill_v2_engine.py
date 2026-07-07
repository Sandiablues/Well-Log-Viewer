from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import pytest

from app.curve_fill_v2.models import CurveFillRule, CurveSeries, CurveTransform
from app.curve_fill_v2.service import CurveFillResolutionError, CurveFillResolutionService

FIXTURES = Path(__file__).parent / "fixtures"
WELL_UID = "019ee477-40ae-781d-86f6-05d2465bcb7d"


def _series(name: str) -> CurveSeries:
    raw = json.loads((FIXTURES / f"{name}.json").read_text())
    return CurveSeries(
        managed_well_uid=raw["managed_well_uid"],
        managed_curve_uid=raw["managed_curve_uid"],
        sample_revision=raw["sample_revision"] or "fixture",
        depth_unit=raw["depth_unit"],
        value_unit=raw["value_unit"],
        samples=tuple((float(d), float(v)) for d, v in raw["samples"]),
    )


def _transform(series: CurveSeries, *, minimum: float, maximum: float, scale_type="linear", direction="normal", width=220) -> CurveTransform:
    return CurveTransform(
        assignment_uid=f"assignment-{series.managed_curve_uid}",
        managed_curve_uid=series.managed_curve_uid,
        transform_revision="proof-v1",
        track_width_px=width,
        horizontal_padding_px=10,
        scale_min=minimum,
        scale_max=maximum,
        scale_type=scale_type,
        scale_direction=direction,
    )


def _conditional(a: CurveSeries, b: CurveSeries, comparison="greater_than") -> CurveFillRule:
    return CurveFillRule.model_validate({
        "rule_uid": "rule-af90-af10",
        "managed_well_uid": WELL_UID,
        "track_uid": "track-resistivity",
        "order": 0,
        "rule_type": "conditional",
        "curve_a_uid": a.managed_curve_uid,
        "curve_b_uid": b.managed_curve_uid,
        "comparison": comparison,
        "deadband": 0.0,
        "minimum_interval": 0.0,
        "style": {"color": "#d8b85a", "opacity": 0.55},
    })


def test_exact_crossing_interpolation_and_pixel_edge_coincidence() -> None:
    a = CurveSeries(
        managed_well_uid=WELL_UID,
        managed_curve_uid="a",
        sample_revision="1",
        depth_unit="ft",
        value_unit="ohm.m",
        samples=((1000, 8), (1010, 12), (1020, 14), (1030, 6)),
    )
    b = CurveSeries(
        managed_well_uid=WELL_UID,
        managed_curve_uid="b",
        sample_revision="1",
        depth_unit="ft",
        value_unit="ohm.m",
        samples=((1000, 10), (1010, 10), (1020, 10), (1030, 10)),
    )
    ta = _transform(a, minimum=0, maximum=20)
    tb = _transform(b, minimum=0, maximum=20)
    response = CurveFillResolutionService().resolve(rule=_conditional(a, b), series_a=a, transform_a=ta, series_b=b, transform_b=tb)
    assert len(response.polygons) == 1
    polygon = response.polygons[0]
    assert polygon.top_depth == pytest.approx(1005.0)
    assert polygon.base_depth == pytest.approx(1025.0)
    assert polygon.vertices[0].x_a_px == pytest.approx(polygon.vertices[0].x_b_px)
    assert polygon.vertices[-1].x_a_px == pytest.approx(polygon.vertices[-1].x_b_px)


def test_null_gap_is_not_bridged() -> None:
    a = CurveSeries(managed_well_uid=WELL_UID, managed_curve_uid="a", sample_revision="1", depth_unit="ft", value_unit="x", samples=((1000, 12), (1010, 13), (1030, 14), (1040, 15)))
    b = CurveSeries(managed_well_uid=WELL_UID, managed_curve_uid="b", sample_revision="1", depth_unit="ft", value_unit="x", samples=((1000, 10), (1010, 10), (1020, 10), (1030, 10), (1040, 10)))
    response = CurveFillResolutionService().resolve(rule=_conditional(a, b), series_a=a, transform_a=_transform(a, minimum=0, maximum=20), series_b=b, transform_b=_transform(b, minimum=0, maximum=20))
    assert [(p.top_depth, p.base_depth) for p in response.polygons] == [(1000.0, 1010.0), (1030.0, 1040.0)]


def test_transform_matches_wdv_linear_reverse_anchor_offset_and_clip() -> None:
    s = CurveSeries(managed_well_uid=WELL_UID, managed_curve_uid="a", sample_revision="1", depth_unit="ft", value_unit="x", samples=((1, 1), (2, 2)))
    t = CurveTransform(assignment_uid="x", managed_curve_uid="a", transform_revision="1", track_width_px=200, horizontal_padding_px=10, scale_min=0, scale_max=100, scale_direction="reversed", position_anchor="right", horizontal_offset_pct=5, clip_to_track=True)
    service = CurveFillResolutionService()
    assert service.value_to_x(100, t) == pytest.approx(10 + 0 * 180 + 0.18 * 180 + 0.05 * 180)
    assert service.value_to_x(-999, t) == pytest.approx(190.0)


def test_logarithmic_transform() -> None:
    s = CurveSeries(managed_well_uid=WELL_UID, managed_curve_uid="a", sample_revision="1", depth_unit="ft", value_unit="ohm.m", samples=((1, 1), (2, 10)))
    t = _transform(s, minimum=0.2, maximum=2000, scale_type="logarithmic", width=220)
    x = CurveFillResolutionService.value_to_x(20, t)
    assert x == pytest.approx(110.0)
    assert CurveFillResolutionService.value_to_x(-1, t) is None


def test_real_forge_af90_greater_than_af10_under_log_transform() -> None:
    af90, af10 = _series("af90"), _series("af10")
    service = CurveFillResolutionService()
    started = perf_counter()
    result = service.resolve(
        rule=_conditional(af90, af10),
        series_a=af90,
        transform_a=_transform(af90, minimum=0.2, maximum=2000, scale_type="logarithmic"),
        series_b=af10,
        transform_b=_transform(af10, minimum=0.2, maximum=2000, scale_type="logarithmic"),
    )
    elapsed_ms = (perf_counter() - started) * 1000
    assert result.polygons
    assert all(p.base_depth > p.top_depth for p in result.polygons)
    assert elapsed_ms < 150.0
    assert not result.warnings


def test_real_forge_density_neutron_governed_crossover() -> None:
    rhoz, nphi = _series("rhoz"), _series("nphi")
    rule = CurveFillRule.model_validate({
        "rule_uid": "rule-density-neutron",
        "managed_well_uid": WELL_UID,
        "track_uid": "track-density-neutron",
        "order": 0,
        "rule_type": "crossover",
        "curve_a_uid": rhoz.managed_curve_uid,
        "curve_b_uid": nphi.managed_curve_uid,
        "overlay_policy_uid": "density-neutron-overlay-v1",
        "overlay_policy_revision": "approved-2026-07-01",
        "deadband": 0.5,
        "style": {"color": "#f0cf4c", "opacity": 0.55},
    })
    result = CurveFillResolutionService().resolve(
        rule=rule,
        series_a=rhoz,
        transform_a=_transform(rhoz, minimum=1.95, maximum=2.95),
        series_b=nphi,
        transform_b=_transform(nphi, minimum=-0.15, maximum=0.45, direction="reversed"),
    )
    assert result.polygons
    assert all(10 <= v.x_a_px <= 210 and 10 <= v.x_b_px <= 210 for p in result.polygons for v in p.vertices)


def test_boundary_fill_and_deterministic_dependency_key() -> None:
    a = _series("af90")
    rule = CurveFillRule.model_validate({
        "rule_uid": "rule-boundary",
        "managed_well_uid": WELL_UID,
        "track_uid": "track-resistivity",
        "order": 1,
        "rule_type": "to_boundary",
        "curve_a_uid": a.managed_curve_uid,
        "boundary": "right",
        "style": {"color": "#336699", "opacity": 0.3},
    })
    transform = _transform(a, minimum=0.2, maximum=2000, scale_type="logarithmic")
    service = CurveFillResolutionService()
    first = service.resolve(rule=rule, series_a=a, transform_a=transform)
    second = service.resolve(rule=rule, series_a=a, transform_a=transform)
    assert first.dependency_key == second.dependency_key
    assert first.geometry_revision == second.geometry_revision
    assert first.polygons[0].vertices[0].x_b_px == pytest.approx(210.0)


def test_rejects_cross_well_and_unapproved_crossover_policy() -> None:
    a, b = _series("af90"), _series("af10")
    bad_b = b.model_copy(update={"managed_well_uid": "other-well"})
    with pytest.raises(CurveFillResolutionError, match="different managed well"):
        CurveFillResolutionService().resolve(rule=_conditional(a, b), series_a=a, transform_a=_transform(a, minimum=.2, maximum=2000, scale_type="logarithmic"), series_b=bad_b, transform_b=_transform(b, minimum=.2, maximum=2000, scale_type="logarithmic"))


def test_between_curves_fills_all_shared_valid_intervals_without_comparison() -> None:
    a = CurveSeries(
        managed_well_uid=WELL_UID,
        managed_curve_uid="a-between",
        sample_revision="1",
        depth_unit="ft",
        value_unit="g/cm3",
        samples=((1000, 2.1), (1010, 2.2), (1030, 2.3), (1040, 2.4)),
    )
    b = CurveSeries(
        managed_well_uid=WELL_UID,
        managed_curve_uid="b-between",
        sample_revision="1",
        depth_unit="ft",
        value_unit="v/v",
        samples=((1000, .25), (1010, .20), (1020, .15), (1030, .10), (1040, .05)),
    )
    rule = CurveFillRule.model_validate({
        "rule_uid": "rule-between",
        "managed_well_uid": WELL_UID,
        "track_uid": "track-density-neutron",
        "order": 0,
        "rule_type": "between_curves",
        "curve_a_uid": a.managed_curve_uid,
        "curve_b_uid": b.managed_curve_uid,
        "style": {"color": "#778899", "opacity": 0.4},
    })
    result = CurveFillResolutionService().resolve(
        rule=rule,
        series_a=a,
        transform_a=_transform(a, minimum=1.95, maximum=2.95),
        series_b=b,
        transform_b=_transform(b, minimum=-0.15, maximum=0.45, direction="reversed"),
    )
    assert [(p.top_depth, p.base_depth) for p in result.polygons] == [
        (1000.0, 1010.0),
        (1030.0, 1040.0),
    ]
    assert all(v.x_a_px != v.x_b_px for p in result.polygons for v in p.vertices)


def test_fill_style_requires_backend_owned_pattern_or_raster_identity() -> None:
    from pydantic import ValidationError
    from app.curve_fill_v2.models import FillStyle
    assert FillStyle.model_validate({"appearance":"pattern","color":"#112233","opacity":0.5,"pattern_uid":"hatch-45-v1"}).pattern_uid == "hatch-45-v1"
    with pytest.raises(ValidationError):
        FillStyle.model_validate({"appearance":"raster","color":"#112233","opacity":0.5})

def test_approved_pattern_catalog_is_backend_owned() -> None:
    from app.curve_fill_v2.paint_catalog import pattern_by_uid
    assert pattern_by_uid("dots-v1").label == "Dots"
    with pytest.raises(ValueError):
        pattern_by_uid("frontend-invented-pattern")



def test_conditional_fill_compares_rendered_positions_across_different_value_units() -> None:
    a = CurveSeries(
        managed_well_uid=WELL_UID,
        managed_curve_uid="rhob",
        sample_revision="1",
        depth_unit="ft",
        value_unit="g/cm3",
        samples=((1000.0, 2.0), (1001.0, 2.5), (1002.0, 3.0)),
    )
    b = CurveSeries(
        managed_well_uid=WELL_UID,
        managed_curve_uid="nphi",
        sample_revision="1",
        depth_unit="ft",
        value_unit="v/v",
        samples=((1000.0, 0.45), (1001.0, 0.15), (1002.0, -0.15)),
    )
    rule = _conditional(a, b)
    geometry = CurveFillResolutionService().resolve(
        rule=rule,
        series_a=a,
        transform_a=_transform(a, minimum=1.95, maximum=2.95),
        series_b=b,
        transform_b=_transform(b, minimum=0.45, maximum=-0.15),
    )
    assert geometry.polygons
