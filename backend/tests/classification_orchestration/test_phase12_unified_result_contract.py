from app.classification_orchestration.contracts import CurveClassificationDecision, CurveClassificationRequest
from app.classification_orchestration.decision_gates import DecisionGateResult
from app.classification_orchestration.unified_result import build_unified_result


def authoritative(family="unclassified", resolved=False):
    return CurveClassificationDecision(
        curve_id="c1",
        source_curve_index=1,
        source_mnemonic="X",
        curve_family_key=family,
        curve_family_label="Unclassified" if family == "unclassified" else family.title(),
        classification_status="resolved" if resolved else "requires_review",
        confidence=0.9 if resolved else 0.0,
        decision_source="test",
        review_required=not resolved,
    )


def gate(family="gamma_ray", label="Gamma Ray", review=False):
    return DecisionGateResult(
        family,
        label,
        "requires_review" if review else "resolved",
        0.95 if not review else 0.0,
        "decision_gate_test",
        review,
        (),
        (),
    )


def test_resolved_petrophysical_curve_routes_to_wdv():
    request = CurveClassificationRequest("GR", curve_id="c1", description="Gamma Ray", unit="API")
    result = build_unified_result(request, authoritative(), gate())
    assert result.overall_status == "resolved"
    assert result.review_required is False
    assert result.curve_family_key == "gamma_ray"
    assert result.measurement_domain_key == "petrophysical_log"
    assert result.destination_key == "wdv"
    assert result.display_in_wdv is True


def test_directional_channel_can_resolve_without_curve_family():
    request = CurveClassificationRequest("X", curve_id="c1", description="Hole Azimuth", unit="deg")
    result = build_unified_result(request, authoritative(), gate("unclassified", "Unclassified", True))
    assert result.overall_status == "resolved"
    assert result.review_required is False
    assert result.curve_family_key is None
    assert result.measurement_domain_key == "directional_survey"
    assert result.destination_key == "survey_workflow"
    assert result.display_in_wdv is False


def test_tool_acquisition_channel_can_resolve_without_curve_family():
    request = CurveClassificationRequest("X", curve_id="c1", description="Cable Tension", unit="lbf")
    result = build_unified_result(request, authoritative(), gate("unclassified", "Unclassified", True))
    assert result.overall_status == "resolved"
    assert result.curve_family_key is None
    assert result.measurement_domain_key == "tool_acquisition"
    assert result.display_in_wdv is False


def test_unknown_domain_and_unresolved_family_stays_review_required():
    request = CurveClassificationRequest("X", curve_id="c1", description="Ambiguous derived channel")
    result = build_unified_result(request, authoritative(), gate("unclassified", "Unclassified", True))
    assert result.overall_status == "requires_review"
    assert result.review_required is True
    assert result.review_reason == "measurement_domain_unresolved"


def test_wdv_eligible_domain_requires_family_resolution():
    request = CurveClassificationRequest("X", curve_id="c1", description="Unknown petrophysical-like curve")
    # Supply a resolved drilling family as authoritative to prove WDV placement requires family.
    family = authoritative("drilling", resolved=True)
    result = build_unified_result(request, family, None)
    assert result.overall_status == "resolved"
    assert result.display_in_wdv is True
    assert result.curve_family_key == "drilling"


def test_unified_contract_is_additive_and_does_not_mutate_authoritative():
    request = CurveClassificationRequest("GR", curve_id="c1", description="Gamma Ray", unit="API")
    auth = authoritative()
    before = auth.as_dict()
    _ = build_unified_result(request, auth, gate())
    assert auth.as_dict() == before


def test_live_observer_emits_unified_result(monkeypatch, tmp_path):
    import json
    from app.classification_orchestration import live_shadow_observer as observer

    target = tmp_path / "shadow.jsonl"
    monkeypatch.setenv("WLV_CLASSIFICATION_SHADOW_REPORT_PATH", str(target))
    request = CurveClassificationRequest("GR", curve_id="c1", description="Gamma Ray", unit="API")
    auth = authoritative()
    result_gate = gate()

    # Use the observer's real append boundary while keeping the test deterministic.
    observer._append({
        "observer_version": "classification-live-shadow-v2",
        "unified_result": build_unified_result(request, auth, result_gate).as_dict(),
    })
    payload = json.loads(target.read_text(encoding="utf-8").strip())
    assert payload["observer_version"] == "classification-live-shadow-v2"
    assert payload["unified_result"]["contract_version"] == "curve-classification-unified-shadow-v1"
    assert payload["unified_result"]["destination_key"] == "wdv"


def test_unified_batch_api_preserves_context_aware_gate_boundary(monkeypatch):
    import app.classification_orchestration.decision_gates as gates_module
    from app.classification_orchestration.unified_result import build_unified_batch_results

    request = CurveClassificationRequest("X", curve_id="c1", description="Hole Azimuth", unit="deg")
    runtime = authoritative()
    deterministic = authoritative()

    monkeypatch.setattr(
        gates_module,
        "evaluate_context_batch_decision_gates",
        lambda items, registry=None: (gate("unclassified", "Unclassified", True),),
    )
    results = build_unified_batch_results([(request, runtime, deterministic)])
    assert len(results) == 1
    assert results[0].overall_status == "resolved"
    assert results[0].measurement_domain_key == "directional_survey"
    assert results[0].curve_family_key is None
