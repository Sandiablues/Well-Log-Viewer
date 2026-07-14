from types import SimpleNamespace

from app.classification_orchestration.contracts import CurveClassificationDecision
from app.classification_orchestration.cutover_policy import (
    ClassificationAuthorityPolicy,
    ClassificationCutoverScope,
)
from app.classification_orchestration.feature_flags import (
    ClassificationEngineMode,
    ClassificationOrchestrationPolicy,
)
from app.classification_orchestration.source_intake_bridge import (
    SourceIntakeAuthorityOutcome,
    apply_source_intake_authority_outcome,
    build_source_intake_authority_outcomes,
)
from app.classification_orchestration.unified_result import UnifiedCurveClassificationResult


def policy(mode, scope):
    return ClassificationAuthorityPolicy(
        engine_policy=ClassificationOrchestrationPolicy(mode=mode),
        cutover_scope=scope,
    )


def legacy_decision():
    return CurveClassificationDecision(
        curve_id="X",
        source_curve_index=1,
        source_mnemonic="X",
        curve_family_key="unclassified",
        curve_family_label="Unclassified",
        classification_status="requires_review",
        confidence=0.4,
        decision_source="legacy",
        review_required=True,
    )


def unified(*, display_in_wdv=True, review=False):
    return UnifiedCurveClassificationResult(
        curve_id="X",
        source_curve_index=1,
        source_mnemonic="X",
        curve_family_key=None if review or not display_in_wdv else "density",
        curve_family_label=None if review or not display_in_wdv else "Density",
        family_status="requires_review" if review else "resolved",
        family_confidence=0.0 if review else 0.95,
        family_decision_source="decision_gate_exact_runtime_kr",
        measurement_domain_key="tool_acquisition" if not display_in_wdv else "petrophysical_log",
        measurement_domain_label="Tool / Acquisition" if not display_in_wdv else "Petrophysical Log",
        destination_key="acquisition_qaqc" if not display_in_wdv else "wdv",
        destination_owner="Acquisition / QAQC" if not display_in_wdv else "WDV",
        display_in_wdv=display_in_wdv,
        domain_status="resolved",
        domain_confidence=0.95,
        domain_decision_source="domain",
        overall_status="requires_review" if review else "resolved",
        review_required=review,
        review_reason="forced" if review else None,
    )


def test_disabled_policy_is_lazy_and_returns_no_outcomes(monkeypatch):
    # If the bridge tried to instantiate runtime governance, this deliberately
    # invalid curve object would fail later. Disabled mode must return first.
    outcomes = build_source_intake_authority_outcomes(
        curve_headers=[object()],
        context_terms=["x"],
        source_kind="LAS",
        source_uid="source-1",
        policy=policy(ClassificationEngineMode.SHADOW, ClassificationCutoverScope.DISABLED),
    )
    assert outcomes == ()


def test_orchestrated_overlay_changes_only_family_classification_fields():
    legacy = {
        "product_category": "open_hole_logs",
        "product_subgroup_key": "density",
        "product_subgroup_label": "Density",
        "curve_family": "Unclassified",
        "curve_description": "Original",
        "curve_unit": "g/cc",
        "classification_confidence": "low",
        "classification_source": "legacy",
        "classification_reasons": ["legacy reason"],
        "review_required": True,
    }
    outcome = SourceIntakeAuthorityOutcome(
        curve_index=1,
        authoritative_kind="orchestrated",
        legacy_decision=legacy_decision(),
        unified_result=unified(),
        blocked_reason=None,
        used_legacy_fallback=False,
    )
    result = apply_source_intake_authority_outcome(legacy, outcome)
    assert result["curve_family"] == "Density"
    assert result["classification_confidence"] == "high"
    assert result["classification_source"].startswith("orchestrated:")
    assert result["review_required"] is False
    assert result["product_category"] == legacy["product_category"]
    assert result["product_subgroup_key"] == legacy["product_subgroup_key"]
    assert result["curve_unit"] == legacy["curve_unit"]


def test_legacy_outcome_preserves_exact_payload_object():
    legacy = {"curve_family": "Gamma Ray", "classification_reasons": ["x"]}
    outcome = SourceIntakeAuthorityOutcome(
        curve_index=1,
        authoritative_kind="legacy",
        legacy_decision=legacy_decision(),
        unified_result=unified(),
        blocked_reason="cutover_not_enabled",
        used_legacy_fallback=False,
    )
    assert apply_source_intake_authority_outcome(legacy, outcome) is legacy


def test_non_wdv_unified_result_persists_first_class_routing_contract():
    legacy = {"curve_family": "Unclassified", "classification_reasons": []}
    outcome = SourceIntakeAuthorityOutcome(
        curve_index=1,
        authoritative_kind="orchestrated",
        legacy_decision=legacy_decision(),
        unified_result=unified(display_in_wdv=False),
        blocked_reason=None,
        used_legacy_fallback=False,
    )

    payload = apply_source_intake_authority_outcome(legacy, outcome)

    assert payload is not legacy
    assert payload["measurement_domain_key"] == "tool_acquisition"
    assert payload["measurement_domain_label"] == "Tool / Acquisition"
    assert payload["destination_key"] == "acquisition_qaqc"
    assert payload["destination_owner"] == "Acquisition / QAQC"
    assert payload["display_in_wdv"] is False
    assert payload["classification_contract_version"] == "curve-classification-unified-shadow-v1"
    assert str(payload["classification_source"]).startswith("orchestrated:")
    assert payload["review_required"] is False
