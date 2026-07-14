import copy
import os

import pytest

from app.classification_orchestration.authority_router import NewIngestionClassificationAuthorityRouter
from app.classification_orchestration.classification_snapshot import (
    create_classification_snapshot,
    restore_classification_snapshot,
    verify_classification_snapshot,
)
from app.classification_orchestration.contracts import (
    CurveClassificationDecision,
    CurveClassificationRequest,
)
from app.classification_orchestration.cutover_policy import (
    ClassificationAuthorityPolicy,
    ClassificationCutoverScope,
)
from app.classification_orchestration.downstream_parity import (
    project_unified_result,
    verify_stage_parity,
)
from app.classification_orchestration.feature_flags import (
    ClassificationEngineMode,
    ClassificationOrchestrationPolicy,
)
from app.classification_orchestration.unified_result import UnifiedCurveClassificationResult


def legacy():
    return CurveClassificationDecision(
        curve_id="curve-1",
        source_curve_index=1,
        source_mnemonic="X",
        curve_family_key="density",
        curve_family_label="Density",
        classification_status="resolved",
        confidence=0.8,
        decision_source="legacy",
        review_required=False,
    )


def unified(*, review=False):
    return UnifiedCurveClassificationResult(
        curve_id="curve-1",
        source_curve_index=1,
        source_mnemonic="X",
        curve_family_key=None if review else "density",
        curve_family_label=None if review else "Density",
        family_status="requires_review" if review else "resolved",
        family_confidence=0.0 if review else 0.95,
        family_decision_source="gate",
        measurement_domain_key="petrophysical_log",
        measurement_domain_label="Petrophysical Log",
        destination_key="wdv",
        destination_owner="WDV",
        display_in_wdv=True,
        domain_status="resolved",
        domain_confidence=0.95,
        domain_decision_source="domain",
        overall_status="requires_review" if review else "resolved",
        review_required=review,
        review_reason="wdv_destination_requires_resolved_curve_family" if review else None,
    )


def policy(mode, scope):
    return ClassificationAuthorityPolicy(
        engine_policy=ClassificationOrchestrationPolicy(mode=mode),
        cutover_scope=scope,
    )


def request(lifecycle):
    return CurveClassificationRequest(
        source_mnemonic="X",
        curve_id="curve-1",
        context={"ingestion_lifecycle": lifecycle},
    )


def test_default_environment_scope_is_disabled(monkeypatch):
    monkeypatch.delenv("WLV_CLASSIFICATION_ENGINE", raising=False)
    monkeypatch.delenv("WLV_CLASSIFICATION_CUTOVER_SCOPE", raising=False)
    p = ClassificationAuthorityPolicy.from_environment()
    assert p.cutover_scope is ClassificationCutoverScope.DISABLED
    assert not p.permits_new_ingestion_authority()


def test_orchestrated_engine_without_scope_cannot_cut_over():
    router = NewIngestionClassificationAuthorityRouter(
        policy(ClassificationEngineMode.ORCHESTRATED, ClassificationCutoverScope.DISABLED)
    )
    result = router.route(request=request("new_ingestion"), legacy_decision=legacy(), build_unified=unified)
    assert result.authoritative_kind == "legacy"
    assert result.blocked_reason == "cutover_not_enabled"


def test_new_ingestion_requires_both_authority_controls():
    router = NewIngestionClassificationAuthorityRouter(
        policy(ClassificationEngineMode.ORCHESTRATED, ClassificationCutoverScope.NEW_INGESTION)
    )
    result = router.route(request=request("new_ingestion"), legacy_decision=legacy(), build_unified=unified)
    assert result.authoritative_kind == "orchestrated"
    assert result.cutover_eligible is True


@pytest.mark.parametrize("lifecycle", ["existing_managed", "reclassification", "", "unknown"])
def test_existing_or_non_new_data_can_never_cut_over(lifecycle):
    router = NewIngestionClassificationAuthorityRouter(
        policy(ClassificationEngineMode.ORCHESTRATED, ClassificationCutoverScope.NEW_INGESTION)
    )
    called = {"value": False}
    def builder():
        called["value"] = True
        return unified()
    result = router.route(request=request(lifecycle), legacy_decision=legacy(), build_unified=builder)
    assert result.authoritative_kind == "legacy"
    assert result.blocked_reason == "not_new_ingestion"
    assert called["value"] is False


def test_review_required_unified_result_does_not_become_authoritative():
    router = NewIngestionClassificationAuthorityRouter(
        policy(ClassificationEngineMode.ORCHESTRATED, ClassificationCutoverScope.NEW_INGESTION)
    )
    result = router.route(
        request=request("new_ingestion"),
        legacy_decision=legacy(),
        build_unified=lambda: unified(review=True),
    )
    assert result.authoritative_kind == "legacy"
    assert result.blocked_reason == "unified_result_requires_review"


def test_orchestrated_error_falls_back_to_legacy():
    router = NewIngestionClassificationAuthorityRouter(
        policy(ClassificationEngineMode.ORCHESTRATED, ClassificationCutoverScope.NEW_INGESTION)
    )
    def boom():
        raise RuntimeError("forced")
    result = router.route(request=request("new_ingestion"), legacy_decision=legacy(), build_unified=boom)
    assert result.authoritative_kind == "legacy"
    assert result.used_legacy_fallback is True
    assert "RuntimeError" in result.routing_error


def test_snapshot_round_trip_restores_exact_classification_state():
    records = [
        {
            "managed_curve_uid": "019a",
            "curve_family": "Density",
            "classification_confidence": 0.91,
            "classification_source": "legacy",
            "review_required": False,
            "unrelated": "preserve",
        },
        {
            "managed_curve_uid": "019b",
            "curve_family": "Gamma Ray",
            "classification_confidence": 0.88,
            "classification_source": "runtime",
            "review_required": False,
        },
    ]
    original = copy.deepcopy(records)
    snapshot = create_classification_snapshot(records)
    assert verify_classification_snapshot(snapshot)

    records[0]["curve_family"] = "Broken"
    records[0]["classification_confidence"] = 0.01
    records[0]["new_field"] = "not snapshot-owned"
    records[1].pop("curve_family")

    restore_classification_snapshot(records, snapshot)

    for before, after in zip(original, records):
        for field in snapshot.fields:
            assert after.get(field) == before.get(field)
    assert records[0]["unrelated"] == "preserve"
    assert records[0]["new_field"] == "not snapshot-owned"


def test_snapshot_detects_duplicate_identity():
    with pytest.raises(ValueError, match="Duplicate snapshot identity"):
        create_classification_snapshot([
            {"managed_curve_uid": "same"},
            {"managed_curve_uid": "same"},
        ])


def test_snapshot_checksum_blocks_tampered_restore():
    records = [{"managed_curve_uid": "019a", "curve_family": "Density"}]
    snapshot = create_classification_snapshot(records)
    tampered = type(snapshot)(
        identity_field=snapshot.identity_field,
        fields=snapshot.fields,
        records=({"managed_curve_uid": "019a", "curve_family": "Gamma Ray"},),
        checksum_sha256=snapshot.checksum_sha256,
    )
    assert not verify_classification_snapshot(tampered)
    with pytest.raises(ValueError, match="checksum mismatch"):
        restore_classification_snapshot(records, tampered)


def test_quick_view_wsi_mwd_wdv_projection_parity_passes():
    projection = project_unified_result(unified())
    payloads = {stage: [projection] for stage in ("quick_view", "wsi", "mwd", "wdv")}
    assert verify_stage_parity(payloads) == ()


def test_downstream_parity_detects_family_drift():
    projection = project_unified_result(unified())
    drift = type(projection)(
        curve_identity=projection.curve_identity,
        curve_family_key="gamma_ray",
        curve_family_label="Gamma Ray",
        measurement_domain_key=projection.measurement_domain_key,
        destination_key=projection.destination_key,
        display_in_wdv=projection.display_in_wdv,
        review_required=projection.review_required,
    )
    errors = verify_stage_parity({
        "quick_view": [projection],
        "wsi": [projection],
        "mwd": [projection],
        "wdv": [drift],
    })
    assert len(errors) == 1
    assert "classification_projection_mismatch" in errors[0]


def test_downstream_parity_detects_missing_curve_identity():
    projection = project_unified_result(unified())
    errors = verify_stage_parity({
        "quick_view": [projection],
        "wsi": [projection],
        "mwd": [projection],
        "wdv": [],
    })
    assert any("identity_set_mismatch" in item for item in errors)
