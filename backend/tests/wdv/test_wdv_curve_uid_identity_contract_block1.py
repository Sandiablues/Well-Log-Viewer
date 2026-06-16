from __future__ import annotations

from app.inventory.models import ManagedProductGroupItem, ManagedWellRecord
from app.inventory.service import ManagedWellInventoryService
from app.wdv_session.models import WdvSessionCurveAssignmentState
from app.wdv_templates.models import WdvLoadedCurveRecommendationInput, WdvRecommendedCurveResponse
from app.wdv_templates.recommendation_service import WdvTemplateRecommendationService


def test_managed_product_item_carries_backend_identity_contract_fields():
    item = ManagedProductGroupItem(
        product_id="product:nphi:a",
        curve_uid="wlv_curve:nphi_a",
        well_uid="managed-well:forge",
        source_uid="source:las:a",
        kr_curve_type_id="neutron_porosity",
        observed_mnemonic="NPHI",
        normalized_mnemonic="NPHI",
        display_name="NPHI",
        curve_name="NPHI",
        curve_type="Neutron Porosity",
    )

    payload = item.model_dump(mode="json")

    assert payload["curve_uid"] == "wlv_curve:nphi_a"
    assert payload["kr_curve_type_id"] == "neutron_porosity"
    assert payload["observed_mnemonic"] == "NPHI"
    assert payload["normalized_mnemonic"] == "NPHI"


def test_wdv_curve_contract_exports_uid_and_kr_type_without_ui_behavior_change():
    service = ManagedWellInventoryService()
    record = ManagedWellRecord(
        managed_well_id="managed-well:forge",
        well_id="forge",
        well_name="FORGE",
    )
    item = ManagedProductGroupItem(
        product_id="product:nphi:a",
        curve_uid="wlv_curve:nphi_a",
        well_uid="managed-well:forge",
        source_uid="source:las:a",
        kr_curve_type_id="neutron_porosity",
        observed_mnemonic="NPHI",
        normalized_mnemonic="NPHI",
        display_name="NPHI",
        curve_name="NPHI",
        curve_type="Neutron Porosity",
        curve_unit="v/v",
        curve_family="neutron_porosity",
        review_required=False,
    )

    contract = service._wdv_curve_contract_from_product_item(record, item)

    assert contract["product_id"] == "product:nphi:a"
    assert contract["curve_uid"] == "wlv_curve:nphi_a"
    assert contract["well_uid"] == "managed-well:forge"
    assert contract["source_uid"] == "source:las:a"
    assert contract["kr_curve_type_id"] == "neutron_porosity"
    assert contract["observed_mnemonic"] == "NPHI"
    assert contract["normalized_mnemonic"] == "NPHI"
    assert contract["mnemonic"] == "NPHI"


def test_template_loaded_curve_contract_accepts_identity_aliases():
    item = WdvLoadedCurveRecommendationInput.model_validate(
        {
            "productId": "product:gr:a",
            "curveUid": "wlv_curve:gr_a",
            "wellUid": "managed-well:forge",
            "sourceUid": "source:las:a",
            "krCurveTypeId": "gamma_ray",
            "observedMnemonic": "ECGR",
            "normalizedMnemonic": "ECGR",
            "curveId": "ECGR",
            "mnemonic": "ECGR",
        }
    )

    assert item.product_id == "product:gr:a"
    assert item.curve_uid == "wlv_curve:gr_a"
    assert item.kr_curve_type_id == "gamma_ray"
    assert item.observed_mnemonic == "ECGR"
    assert item.normalized_mnemonic == "ECGR"


def test_recommended_curve_response_preserves_identity_fields():
    response = WdvRecommendedCurveResponse(
        product_id="product:rt:a",
        curve_uid="wlv_curve:rt_a",
        well_uid="managed-well:forge",
        source_uid="source:las:a",
        kr_curve_type_id="resistivity",
        observed_mnemonic="AORT",
        normalized_mnemonic="AORT",
        curve_id="AORT",
        mnemonic="AORT",
        display_name="AORT",
        selection_reason="selected",
    )

    payload = response.model_dump(mode="json")
    assert payload["curve_uid"] == "wlv_curve:rt_a"
    assert payload["kr_curve_type_id"] == "resistivity"


def test_session_assignment_contract_accepts_identity_fields_but_keeps_curve_id():
    assignment = WdvSessionCurveAssignmentState.model_validate(
        {
            "assignmentId": "assignment:1",
            "curveUid": "wlv_curve:nphi_a",
            "krCurveTypeId": "neutron_porosity",
            "observedMnemonic": "NPHI",
            "normalizedMnemonic": "NPHI",
            "curveId": "NPHI",
            "productId": "product:nphi:a",
            "mnemonic": "NPHI",
        }
    )

    assert assignment.curve_uid == "wlv_curve:nphi_a"
    assert assignment.kr_curve_type_id == "neutron_porosity"
    assert assignment.curve_id == "NPHI"


def test_recommendation_payload_normalization_preserves_uid_in_candidate_response():
    class FakeRepo:
        def list_records(self, record_type=None):
            return []

    service = WdvTemplateRecommendationService(repository=FakeRepo())
    candidates = service._curves_from_payload(
        [
            {
                "product_id": "product:gr:a",
                "curve_uid": "wlv_curve:gr_a",
                "well_uid": "managed-well:forge",
                "source_uid": "source:las:a",
                "kr_curve_type_id": "gamma_ray",
                "observed_mnemonic": "ECGR",
                "normalized_mnemonic": "ECGR",
                "curve_id": "ECGR",
                "mnemonic": "ECGR",
                "curve_family": "gamma_ray",
            }
        ]
    )
    response = service._curve_response(candidates[0], "selected")

    assert response.curve_uid == "wlv_curve:gr_a"
    assert response.well_uid == "managed-well:forge"
    assert response.source_uid == "source:las:a"
    assert response.kr_curve_type_id == "gamma_ray"
    assert response.observed_mnemonic == "ECGR"
    assert response.normalized_mnemonic == "ECGR"
