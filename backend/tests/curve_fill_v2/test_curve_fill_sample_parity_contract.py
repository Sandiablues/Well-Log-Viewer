from app.curve_fill_v2.geometry_service import ResolveCurveFillGeometryCommand
from app.curve_fill_v2.workflow_service import HydrateCurveFillRulesCommand


def test_curve_fill_backend_defaults_match_visible_wdv_sample_limit() -> None:
    assert HydrateCurveFillRulesCommand(expected_revision=0).max_samples == 12000
    assert ResolveCurveFillGeometryCommand(expected_revision=0, rule_uid="rule-1").max_samples == 12000
