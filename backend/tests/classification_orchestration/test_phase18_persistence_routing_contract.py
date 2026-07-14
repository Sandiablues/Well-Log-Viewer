from types import SimpleNamespace

from app.classification_orchestration.source_intake_bridge import (
    apply_source_intake_authority_outcome,
    build_source_intake_authority_outcomes,
)
from app.classification_orchestration.cutover_policy import (
    ClassificationAuthorityPolicy,
    ClassificationCutoverScope,
)
from app.classification_orchestration.feature_flags import (
    ClassificationEngineMode,
    ClassificationOrchestrationPolicy,
)
from app.inventory.models import ManagedProductGroupItem
from app.inventory.service import ManagedWellInventoryService


def enabled_policy():
    return ClassificationAuthorityPolicy(
        engine_policy=ClassificationOrchestrationPolicy(
            mode=ClassificationEngineMode.ORCHESTRATED
        ),
        cutover_scope=ClassificationCutoverScope.NEW_INGESTION,
    )


def test_managed_curve_defaults_preserve_existing_wdv_behavior():
    item = ManagedProductGroupItem(
        product_id="p",
        display_name="X",
        curve_name="X",
        curve_type="X",
    )
    assert item.display_in_wdv is True
    assert item.measurement_domain_key is None
    assert ManagedWellInventoryService._is_wdv_loadable_product(item) is True


def test_explicit_non_wdv_route_is_not_wdv_loadable():
    item = ManagedProductGroupItem(
        product_id="p",
        display_name="HAZI",
        curve_name="HAZI",
        curve_type="Hole Azimuth",
        measurement_domain_key="directional_survey",
        destination_key="survey_wbv",
        destination_owner="Survey/WBV",
        display_in_wdv=False,
    )
    assert ManagedWellInventoryService._is_wdv_loadable_product(item) is False


def test_resolved_non_wdv_domain_is_persistable_authority():
    headers = [SimpleNamespace(mnemonic="HAZI", unit="DEG", description="Hole Azimuth")]
    outcomes = build_source_intake_authority_outcomes(
        curve_headers=headers,
        context_terms=("phase18",),
        source_kind="LAS",
        source_uid="phase18",
        policy=enabled_policy(),
    )
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.authoritative_kind == "orchestrated"
    assert outcome.unified_result is not None
    assert outcome.unified_result.display_in_wdv is False

    payload = apply_source_intake_authority_outcome(
        {
            "curve_family": "Unclassified",
            "classification_confidence": "low",
            "classification_source": "legacy",
            "classification_reasons": [],
            "review_required": True,
        },
        outcome,
    )
    assert payload["measurement_domain_key"] == "directional_survey"
    assert payload["display_in_wdv"] is False
    assert str(payload["classification_source"]).startswith("orchestrated:")
    assert payload["review_required"] is False
