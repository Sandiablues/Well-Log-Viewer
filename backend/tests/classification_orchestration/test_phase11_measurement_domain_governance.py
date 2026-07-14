from app.classification_orchestration.contracts import CurveClassificationRequest, CurveClassificationDecision
from app.classification_orchestration.domain_governance import MeasurementDomainResolver


def decision(family="density", review=False):
    return CurveClassificationDecision(
        curve_id="x", source_curve_index=0, source_mnemonic="X",
        curve_family_key=family, curve_family_label=family.title(),
        classification_status="requires_review" if review else "resolved",
        confidence=.9, decision_source="test", review_required=review,
    )


def test_resolved_petrophysical_family_routes_to_wdv():
    out = MeasurementDomainResolver().resolve(CurveClassificationRequest("X"), decision("density"))
    assert out.measurement_domain_key == "petrophysical_log"
    assert out.display_in_wdv is True


def test_drilling_family_routes_to_operational_domain():
    out = MeasurementDomainResolver().resolve(CurveClassificationRequest("X"), decision("drilling"))
    assert out.measurement_domain_key == "drilling_operational"


def test_directional_semantics_route_outside_wdv():
    req = CurveClassificationRequest("X", description="Hole Azimuth Relative to True North", unit="DEG")
    out = MeasurementDomainResolver().resolve(req)
    assert out.measurement_domain_key == "directional_survey"
    assert out.destination_key == "survey_workflow"
    assert out.display_in_wdv is False


def test_tool_acquisition_semantics_route_outside_wdv():
    req = CurveClassificationRequest("X", description="Cable Tension", unit="LBF")
    out = MeasurementDomainResolver().resolve(req)
    assert out.measurement_domain_key == "tool_acquisition"
    assert out.display_in_wdv is False


def test_unknown_domain_is_not_forced():
    req = CurveClassificationRequest("X", description="Opaque Vendor Measurement")
    out = MeasurementDomainResolver().resolve(req)
    assert out.measurement_domain_key == "unknown"
    assert out.status == "requires_review"
    assert out.display_in_wdv is False


def test_review_required_curve_family_does_not_force_petrophysical_domain():
    out = MeasurementDomainResolver().resolve(
        CurveClassificationRequest("X", description="Hole Deviation from Gravity"),
        decision("density", review=True),
    )
    assert out.measurement_domain_key == "directional_survey"
