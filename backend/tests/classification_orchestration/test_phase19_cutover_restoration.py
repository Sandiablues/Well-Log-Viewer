from __future__ import annotations

from app.classification_orchestration.cutover_policy import ClassificationCutoverScope
from app.classification_orchestration.feature_flags import ClassificationEngineMode
from app.classification_orchestration.source_intake_bridge import (
    SourceIntakeAuthorityOutcome,
    apply_source_intake_authority_outcome,
    source_intake_authority_policy_from_environment,
)
from app.classification_orchestration.unified_result import (
    UNIFIED_RESULT_CONTRACT_VERSION,
    UnifiedCurveClassificationResult,
)
from app.inventory.models import ManagedProductGroupItem


def _unified(*, family_key: str = "caliper", family_label: str = "Caliper") -> UnifiedCurveClassificationResult:
    return UnifiedCurveClassificationResult(
        curve_id="curve:0",
        source_curve_index=1,
        source_mnemonic="DCAL",
        curve_family_key=family_key,
        curve_family_label=family_label,
        family_status="resolved",
        family_confidence=1.0,
        family_decision_source="decision_gate_consensus",
        measurement_domain_key="open_hole_log",
        measurement_domain_label="Open-hole Log",
        destination_key="wdv",
        destination_owner="WDV",
        display_in_wdv=True,
        domain_status="resolved",
        domain_confidence=1.0,
        domain_decision_source="measurement_domain_resolver",
        overall_status="resolved",
        review_required=False,
        review_reason=None,
    )


def _outcome(unified: UnifiedCurveClassificationResult) -> SourceIntakeAuthorityOutcome:
    return SourceIntakeAuthorityOutcome(
        curve_index=1,
        authoritative_kind="orchestrated",
        legacy_decision=None,  # type: ignore[arg-type]
        unified_result=unified,
        blocked_reason=None,
        used_legacy_fallback=False,
    )


def test_new_ingestion_authority_is_default_when_environment_is_unset(monkeypatch):
    monkeypatch.delenv("WLV_CLASSIFICATION_ENGINE", raising=False)
    monkeypatch.delenv("WLV_CLASSIFICATION_CUTOVER_SCOPE", raising=False)
    policy = source_intake_authority_policy_from_environment()
    assert policy.engine_policy.mode == ClassificationEngineMode.ORCHESTRATED
    assert policy.cutover_scope == ClassificationCutoverScope.NEW_INGESTION
    assert policy.permits_new_ingestion_authority() is True


def test_legacy_environment_override_remains_emergency_fallback(monkeypatch):
    monkeypatch.setenv("WLV_CLASSIFICATION_ENGINE", "legacy")
    monkeypatch.delenv("WLV_CLASSIFICATION_CUTOVER_SCOPE", raising=False)
    policy = source_intake_authority_policy_from_environment()
    assert policy.engine_policy.mode == ClassificationEngineMode.LEGACY
    assert policy.permits_new_ingestion_authority() is False


def test_accepted_runtime_kr_family_and_provenance_are_preserved_while_phase18_routing_is_added():
    runtime_payload = {
        "product_category": "open_hole_logs",
        "product_subgroup_key": "borehole_geometry_imaging",
        "product_subgroup_label": "Borehole Geometry / Imaging",
        "curve_family": "caliper",
        "curve_description": "Caliper",
        "classification_confidence": "high",
        "classification_source": "runtime_alias",
        "classification_reasons": [
            "Runtime KR resolved mnemonic DCAL.",
            "Resolution source: runtime_alias.",
        ],
        "review_required": False,
    }
    payload = apply_source_intake_authority_outcome(runtime_payload, _outcome(_unified()))
    assert payload["curve_family"] == "caliper"
    assert payload["classification_source"] == "runtime_alias"
    assert payload["classification_confidence"] == "high"
    assert payload["classification_reasons"] == runtime_payload["classification_reasons"]
    assert payload["review_required"] is False
    assert payload["product_category"] == "open_hole_logs"
    assert payload["product_subgroup_key"] == "borehole_geometry_imaging"
    assert payload["curve_family_key"] == "caliper"
    assert payload["measurement_domain_key"] == "open_hole_log"
    assert payload["destination_key"] == "wdv"
    assert payload["destination_owner"] == "WDV"
    assert payload["display_in_wdv"] is True
    assert payload["classification_contract_version"] == UNIFIED_RESULT_CONTRACT_VERSION


def test_unresolved_payload_can_receive_accepted_unified_general_family():
    legacy_payload = {
        "product_category": "other_review_required",
        "product_subgroup_key": None,
        "product_subgroup_label": None,
        "curve_family": "Unclassified",
        "curve_description": "Unknown curve",
        "classification_confidence": "low",
        "classification_source": "unclassified",
        "classification_reasons": ["No governed runtime match."],
        "review_required": True,
    }
    payload = apply_source_intake_authority_outcome(
        legacy_payload,
        _outcome(_unified(family_key="sonic", family_label="Sonic")),
    )
    assert payload["curve_family_key"] == "sonic"
    assert payload["curve_family"] == "Sonic"
    assert payload["classification_source"].startswith("orchestrated:")
    assert payload["review_required"] is False


def test_managed_curve_contract_persists_general_family_key_separately_from_subclass_metadata():
    item = ManagedProductGroupItem(
        product_id="p1",
        display_name="DTCO",
        curve_name="DTCO",
        curve_type="Sonic Compressional",
        curve_description="Delta-T Compressional",
        curve_family="Sonic",
        curve_family_key="sonic",
    )
    dumped = item.model_dump(mode="json")
    assert dumped["curve_family_key"] == "sonic"
    assert dumped["curve_family"] == "Sonic"
    assert dumped["curve_type"] == "Sonic Compressional"
