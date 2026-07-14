
from app.classification_orchestration.contracts import CurveClassificationDecision, CurveClassificationRequest
from app.classification_orchestration.decision_gates import evaluate_decision_gates
from app.classification_orchestration.family_registry import CanonicalCurveFamilyRegistry

def d(family_key, family_label, *, payload=None, source="test", confidence=.9):
    return CurveClassificationDecision(
        curve_id=None, source_curve_index=0, source_mnemonic="DTC",
        curve_family_key=family_key, curve_family_label=family_label,
        classification_status="resolved", confidence=confidence,
        decision_source=source, review_required=False,
        legacy_payload=payload or {},
    )

def req(unit="US/F"):
    return CurveClassificationRequest(source_mnemonic="DTC", unit=unit, description="Compressional slowness")

def test_governed_canonical_curve_relationship_collapses_measurement_label_to_family():
    runtime=d("sonic","Sonic",payload={
        "canonical_curve_id":"sonic_compressional",
        "display_name":"Sonic Compressional",
        "family":"Sonic",
    }, source="runtime_standard_mnemonic")
    deterministic=d("sonic_compressional","Sonic Compressional")
    result=evaluate_decision_gates(req(), runtime, deterministic, CanonicalCurveFamilyRegistry.default())
    assert result.curve_family_key == "sonic"
    assert result.curve_family_label == "Sonic"
    assert result.decision_source == "decision_gate_governed_family_consensus"
    assert result.review_required is False

def test_measurement_label_is_not_global_alias_without_runtime_governed_relationship():
    runtime=d("sonic","Sonic",payload={"canonical_curve_id":"different_measurement","family":"Sonic"})
    deterministic=d("sonic_compressional","Sonic Compressional")
    result=evaluate_decision_gates(req(), runtime, deterministic, CanonicalCurveFamilyRegistry.default())
    assert result.decision_source == "decision_gate_conflict"
    assert result.review_required is True

def test_true_family_conflict_remains_blocked():
    runtime=d("resistivity","Resistivity",payload={
        "canonical_curve_id":"deep_resistivity",
        "family":"Resistivity",
    })
    deterministic=d("density","Density")
    result=evaluate_decision_gates(CurveClassificationRequest(source_mnemonic="X",unit="OHM.M"), runtime, deterministic, CanonicalCurveFamilyRegistry.default())
    assert result.decision_source == "decision_gate_conflict"
    assert result.curve_family_key == "unclassified"
    assert result.review_required is True

def test_registry_relationship_accepts_display_name_as_governed_measurement_identity():
    registry=CanonicalCurveFamilyRegistry.default()
    assert registry.governed_measurement_matches_family(
        "Sonic Compressional",
        governed_family_value="Sonic",
        runtime_payload={"display_name":"Sonic Compressional","family":"Sonic"},
    )

def test_registry_relationship_rejects_unrelated_measurement():
    registry=CanonicalCurveFamilyRegistry.default()
    assert not registry.governed_measurement_matches_family(
        "Density",
        governed_family_value="Sonic",
        runtime_payload={"canonical_curve_id":"sonic_compressional","display_name":"Sonic Compressional"},
    )
