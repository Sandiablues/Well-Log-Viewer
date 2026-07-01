from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.curve_fill.models import CurveFillResolveRequest
from app.curve_fill.service import CurveFillResolutionService


def _conditional(samples, **overrides):
    payload = {
        "fill_mode": "conditional",
        "operand_a": {
            "type": "curve",
            "managed_well_uid": "well-1",
            "curve_uid": "curve-a",
            "depth_domain_uid": "md-1",
            "unit": "ohm.m",
        },
        "operand_b": {
            "type": "curve",
            "managed_well_uid": "well-1",
            "curve_uid": "curve-b",
            "depth_domain_uid": "md-1",
            "unit": "ohm.m",
        },
        "condition": "a_greater_than_b",
        "comparison_basis": "engineering_value",
        "style": {"fill": "#d8b85a", "opacity": 0.55},
        "depth_unit": "ft",
        "samples": samples,
    }
    payload.update(overrides)
    return CurveFillResolveRequest.model_validate(payload)


def test_interpolates_exact_crossings_and_returns_only_true_lobe():
    request = _conditional([
        {"depth": 1000, "a_value": 8, "b_value": 10, "a_track_position": .2, "b_track_position": .4},
        {"depth": 1010, "a_value": 12, "b_value": 10, "a_track_position": .6, "b_track_position": .4},
        {"depth": 1020, "a_value": 14, "b_value": 10, "a_track_position": .8, "b_track_position": .4},
        {"depth": 1030, "a_value": 6, "b_value": 10, "a_track_position": .1, "b_track_position": .4},
    ])
    response = CurveFillResolutionService().resolve(request)
    assert len(response.segments) == 1
    segment = response.segments[0]
    assert segment.top_depth == pytest.approx(1005.0)
    assert segment.base_depth == pytest.approx(1025.0)
    assert segment.vertices[0].a_track_position == pytest.approx(segment.vertices[0].b_track_position)
    assert segment.vertices[-1].a_track_position == pytest.approx(0.45)
    assert segment.vertices[-1].b_track_position == pytest.approx(0.4)


def test_null_gap_terminates_and_does_not_bridge():
    request = _conditional([
        {"depth": 1000, "a_value": 12, "b_value": 10, "a_track_position": .6, "b_track_position": .4},
        {"depth": 1010, "a_value": 13, "b_value": 10, "a_track_position": .7, "b_track_position": .4},
        {"depth": 1020, "a_value": None, "b_value": 10, "a_track_position": None, "b_track_position": .4},
        {"depth": 1030, "a_value": 14, "b_value": 10, "a_track_position": .8, "b_track_position": .4},
        {"depth": 1040, "a_value": 15, "b_value": 10, "a_track_position": .9, "b_track_position": .4},
    ])
    response = CurveFillResolutionService().resolve(request)
    assert [(s.top_depth, s.base_depth) for s in response.segments] == [(1000.0, 1010.0), (1030.0, 1040.0)]


def test_deadband_and_minimum_interval_filter_noise():
    request = _conditional([
        {"depth": 1000, "a_value": 10.0, "b_value": 10, "a_track_position": .5, "b_track_position": .5},
        {"depth": 1001, "a_value": 10.1, "b_value": 10, "a_track_position": .51, "b_track_position": .5},
        {"depth": 1002, "a_value": 10.0, "b_value": 10, "a_track_position": .5, "b_track_position": .5},
    ], deadband=0.2, minimum_interval=0.5)
    assert CurveFillResolutionService().resolve(request).segments == ()


def test_rejects_cross_well_and_incompatible_units():
    with pytest.raises(ValidationError, match="same managed well"):
        _conditional([], operand_b={
            "type": "curve", "managed_well_uid": "well-2", "curve_uid": "b",
            "depth_domain_uid": "md-1", "unit": "ohm.m",
        })
    with pytest.raises(ValidationError, match="compatible units"):
        _conditional([], operand_b={
            "type": "curve", "managed_well_uid": "well-1", "curve_uid": "b",
            "depth_domain_uid": "md-1", "unit": "in",
        })


def test_crossover_requires_versioned_policy_and_uses_normalized_order():
    request = CurveFillResolveRequest.model_validate({
        "fill_mode": "crossover",
        "operand_a": {"type": "curve", "managed_well_uid": "well-1", "curve_uid": "rhob", "depth_domain_uid": "md-1", "unit": "g/cc"},
        "operand_b": {"type": "curve", "managed_well_uid": "well-1", "curve_uid": "nphi", "depth_domain_uid": "md-1", "unit": "v/v"},
        "comparison_basis": "normalized_track_position",
        "overlay_policy_id": "density-neutron-overlay-v1",
        "overlay_policy_revision": "approved-2026-07-01",
        "style": {"fill": "#f0cf4c", "opacity": .55},
        "deadband": .005,
        "depth_unit": "ft",
        "samples": [
            {"depth": 1000, "a_value": 2.4, "b_value": .25, "a_track_position": .4, "b_track_position": .5},
            {"depth": 1010, "a_value": 2.2, "b_value": .15, "a_track_position": .7, "b_track_position": .5},
            {"depth": 1020, "a_value": 2.5, "b_value": .30, "a_track_position": .3, "b_track_position": .5},
        ],
    })
    response = CurveFillResolutionService().resolve(request)
    assert len(response.segments) == 1
    assert response.segments[0].top_depth == pytest.approx(1003.3333333)
    assert response.segments[0].base_depth == pytest.approx(1015.0)
