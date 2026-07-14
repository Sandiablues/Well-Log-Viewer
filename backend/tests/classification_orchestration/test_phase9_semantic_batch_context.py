from app.classification_orchestration.contracts import CurveClassificationDecision, CurveClassificationRequest
from app.classification_orchestration.decision_gates import evaluate_decision_gates
from app.classification_orchestration.family_registry import CanonicalCurveFamilyRegistry
from app.classification_orchestration.semantic_context import BatchSeriesContextResolver, DescriptionSemanticResolver


def unresolved(mnemonic="X"):
    return CurveClassificationDecision(
        curve_id=None, source_curve_index=0, source_mnemonic=mnemonic,
        curve_family_key="unclassified", curve_family_label="Unclassified",
        classification_status="requires_review", confidence=0.0,
        decision_source="unknown", review_required=True,
    )


def test_description_plus_compatible_unit_resolves_sonic_without_mnemonic_mapping():
    req=CurveClassificationRequest(source_mnemonic="UNSEEN_VENDOR_CODE", description="Delta-T High Frequency - Memory", unit="us/ft")
    result=evaluate_decision_gates(req, unresolved(), unresolved())
    assert result.curve_family_key == "sonic"
    assert result.decision_source == "decision_gate_semantic_unit"
    assert result.review_required is False


def test_description_semantics_rejects_incompatible_unit():
    req=CurveClassificationRequest(source_mnemonic="X", description="Downhole Temperature", unit="ohm.m")
    result=evaluate_decision_gates(req, unresolved(), unresolved())
    assert result.curve_family_key == "unclassified"
    assert result.review_required is True


def test_batch_series_strengthens_repeated_azimuthal_density_candidates():
    registry=CanonicalCurveFamilyRegistry.default()
    semantic=DescriptionSemanticResolver(registry)
    batch=BatchSeriesContextResolver()
    requests=[
        CurveClassificationRequest(source_mnemonic=f"VENDOR_{i}", description=f"Azimuthal Bulk Density - Compensated - Sector {i:02d}", unit="g/cm3", source_uid="source-a", logical_file_id="lf", frame_id="frame")
        for i in range(1,4)
    ]
    support=batch.resolve_batch(requests, semantic)
    assert len(support) == 3
    for i, req in enumerate(requests):
        identity=str(req.source_curve_index or f"ordinal:{i}")
        result=evaluate_decision_gates(req, unresolved(), unresolved(), registry, semantic_resolver=semantic, batch_support=support[identity])
        assert result.curve_family_key == "density"
        assert result.decision_source == "decision_gate_batch_series_semantic"
        assert result.review_required is False


def test_single_series_candidate_does_not_auto_accept_when_below_semantic_threshold():
    req=CurveClassificationRequest(source_mnemonic="X", description="Resistivity Attenuation - Corrected", unit="ohm.m")
    result=evaluate_decision_gates(req, unresolved(), unresolved())
    assert result.curve_family_key == "resistivity"
    assert result.decision_source == "decision_gate_semantic_review"
    assert result.review_required is True


def test_hard_runtime_unit_conflict_still_blocks_before_semantic_candidate():
    runtime=CurveClassificationDecision(
        curve_id=None, source_curve_index=0, source_mnemonic="X",
        curve_family_key="resistivity", curve_family_label="Resistivity",
        classification_status="resolved", confidence=.99,
        decision_source="runtime_alias", review_required=False,
        legacy_payload={"default_unit":"ohm.m"},
    )
    req=CurveClassificationRequest(source_mnemonic="X", description="Resistivity Standoff Standard Resolution", unit="IN")
    result=evaluate_decision_gates(req, runtime, unresolved())
    assert result.decision_source == "decision_gate_conflict"
    assert result.curve_family_key == "unclassified"
    assert result.review_required is True


def test_batch_api_applies_series_support_without_changing_single_curve_rule():
    from app.classification_orchestration.decision_gates import evaluate_batch_decision_gates
    registry=CanonicalCurveFamilyRegistry.default()
    items=[]
    for i in range(1,3):
        req=CurveClassificationRequest(source_mnemonic=f"VENDOR_{i}", description=f"Resistivity Phase - Corrected - CRIM - {i}MHz", unit="ohm.m", source_uid="s", logical_file_id="lf", frame_id="f", source_curve_index=i)
        items.append((req, unresolved(), unresolved()))
    results=evaluate_batch_decision_gates(items, registry)
    assert len(results)==2
    assert all(r.curve_family_key=="resistivity" for r in results)
    assert all(r.decision_source=="decision_gate_batch_series_semantic" for r in results)
    assert all(not r.review_required for r in results)
