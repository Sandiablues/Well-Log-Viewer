from __future__ import annotations

import pytest

from app.classification_orchestration.contracts import CurveClassificationDecision, CurveClassificationRequest
from app.classification_orchestration.differential import compare_classifications
from app.classification_orchestration.family_registry import CanonicalCurveFamilyRegistry
from app.classification_orchestration.feature_flags import ClassificationEngineMode, ClassificationOrchestrationPolicy
from app.classification_orchestration.orchestrator import CurveClassificationOrchestrator


class StubEngine:
    def __init__(self, decision=None, error=None):
        self.decision = decision
        self.error = error
        self.calls = 0

    def classify_curve(self, request):
        self.calls += 1
        if self.error:
            raise self.error
        return self.decision


def decision(family_key="gamma_ray", label="Gamma Ray", status="resolved", review=False, source="stub"):
    return CurveClassificationDecision(
        curve_id="curve-1",
        source_curve_index=1,
        source_mnemonic="GR",
        curve_family_key=family_key,
        curve_family_label=label,
        classification_status=status,
        confidence=0.95,
        decision_source=source,
        review_required=review,
    )


def request():
    return CurveClassificationRequest(source_mnemonic="GR", curve_id="curve-1", unit="API", description="Gamma Ray")


def test_default_policy_is_shadow(monkeypatch):
    monkeypatch.delenv("WLV_CLASSIFICATION_ENGINE", raising=False)
    assert ClassificationOrchestrationPolicy.from_environment().mode is ClassificationEngineMode.SHADOW


def test_invalid_feature_flag_is_rejected(monkeypatch):
    monkeypatch.setenv("WLV_CLASSIFICATION_ENGINE", "guess")
    with pytest.raises(ValueError):
        ClassificationOrchestrationPolicy.from_environment()


def test_legacy_mode_never_calls_orchestrated_engine():
    legacy = StubEngine(decision())
    shadow = StubEngine(decision(source="shadow"))
    result = CurveClassificationOrchestrator(
        legacy_engine=legacy,
        orchestrated_engine=shadow,
        policy=ClassificationOrchestrationPolicy(mode=ClassificationEngineMode.LEGACY),
    ).classify_curve(request())
    assert result.authoritative.decision_source == "stub"
    assert shadow.calls == 0
    assert result.shadow is None


def test_shadow_mode_keeps_legacy_authoritative():
    legacy = StubEngine(decision(source="legacy"))
    shadow = StubEngine(decision(source="shadow"))
    result = CurveClassificationOrchestrator(
        legacy_engine=legacy,
        orchestrated_engine=shadow,
        policy=ClassificationOrchestrationPolicy(mode=ClassificationEngineMode.SHADOW),
    ).classify_curve(request())
    assert result.authoritative.decision_source == "legacy"
    assert result.shadow.decision_source == "shadow"
    assert result.differential.agreement is True


def test_orchestrated_mode_can_make_shadow_authoritative():
    legacy = StubEngine(decision(source="legacy"))
    shadow = StubEngine(decision(family_key="density", label="Density", source="shadow"))
    result = CurveClassificationOrchestrator(
        legacy_engine=legacy,
        orchestrated_engine=shadow,
        policy=ClassificationOrchestrationPolicy(mode=ClassificationEngineMode.ORCHESTRATED),
    ).classify_curve(request())
    assert result.authoritative.curve_family_key == "density"
    assert result.differential.classification == "material_conflict"


def test_orchestrator_exception_falls_back_to_legacy():
    legacy = StubEngine(decision(source="legacy"))
    shadow = StubEngine(error=RuntimeError("forced failure"))
    result = CurveClassificationOrchestrator(
        legacy_engine=legacy,
        orchestrated_engine=shadow,
        policy=ClassificationOrchestrationPolicy(mode=ClassificationEngineMode.ORCHESTRATED),
    ).classify_curve(request())
    assert result.authoritative.decision_source == "legacy"
    assert result.used_legacy_fallback is True
    assert "forced failure" in result.orchestration_error


def test_fallback_can_be_disabled():
    legacy = StubEngine(decision(source="legacy"))
    shadow = StubEngine(error=RuntimeError("forced failure"))
    orchestrator = CurveClassificationOrchestrator(
        legacy_engine=legacy,
        orchestrated_engine=shadow,
        policy=ClassificationOrchestrationPolicy(
            mode=ClassificationEngineMode.ORCHESTRATED,
            fallback_to_legacy_on_error=False,
        ),
    )
    with pytest.raises(RuntimeError, match="forced failure"):
        orchestrator.classify_curve(request())


def test_family_registry_uses_existing_backend_vocabulary_and_normalizes_nomenclature():
    registry = CanonicalCurveFamilyRegistry.from_existing_backend_vocabulary()
    assert registry.require("Gamma Ray").family_key == "gamma_ray"
    assert registry.require("gamma_ray").display_label == "Gamma Ray"
    assert registry.require("GAMMA RAY").family_key == "gamma_ray"
    assert registry.require("sonic shear").family_key == "sonic_shear"


def test_family_registry_rejects_unregistered_free_text():
    registry = CanonicalCurveFamilyRegistry.from_existing_backend_vocabulary()
    with pytest.raises(ValueError, match="Unregistered curve family"):
        registry.require("made up family")


def test_differential_labels_newly_classified():
    legacy = decision(family_key="unclassified", label="Unclassified", status="requires_review", review=True)
    shadow = decision(family_key="nmr", label="NMR")
    diff = compare_classifications(legacy, shadow)
    assert diff.agreement is False
    assert diff.classification == "newly_classified"
