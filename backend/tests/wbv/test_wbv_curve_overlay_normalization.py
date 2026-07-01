from app.wbv.models import WbvCurveOverlayNormalizationContract, WbvCurveOverlayNormalizationItem
from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedWellRecord,
    ManagedWmdpState,
)
from app.wbv.service import WbvService


class _Repository:
    def __init__(self, record: ManagedWellRecord) -> None:
        self.record = record

    def get_record(self, managed_well_id: str) -> ManagedWellRecord:
        assert managed_well_id == self.record.managed_well_id
        return self.record


class _Samples:
    def get_curve_samples(self, **_: object) -> dict[str, object]:
        return {
            "value_min": -999.0,
            "value_max": 9999.0,
            "robust_value_min": 10.0,
            "robust_value_max": 90.0,
            "value_p05": 20.0,
            "value_p95": 80.0,
            "sample_count": 5,
            "value_unit": "gAPI",
            "samples": [(0.0, -999.0), (1.0, 20.0), (2.0, 50.0), (3.0, 80.0), (4.0, 9999.0)],
        }


def _record() -> ManagedWellRecord:
    item = ManagedProductGroupItem(
        product_id="curve-gr",
        display_name="Gamma Ray",
        curve_name="GR",
        curve_type="curve",
        curve_unit="gAPI",
        curve_description="Gamma Ray",
        curve_family="Gamma Ray",
        run_interval="300.5–6076 ft",
        run_number="1",
        run_date="2025-01-02",
        classification_source="managed_knowledge",
        classification_confidence="high",
        review_required=False,
        source_id="forge-las",
        wmdp_state=ManagedWmdpState.STAGED_IN_WMDP,
    )
    return ManagedWellRecord(
        managed_well_id="managed-well:forge",
        well_id="forge",
        well_name="Forge",
        product_groups=[ManagedProductGroup(group_key="openhole", group_label="Openhole", items=[item])],
    )


def test_curve_overlay_product_inventory_groups_managed_curves() -> None:
    service = WbvService(repository=_Repository(_record()))
    contract = service.get_curve_overlay_products("managed-well:forge")
    assert len(contract.products) == 1
    assert contract.products[0].curve_product_id == "forge-las"
    assert contract.products[0].curve_count == 1
    curve = contract.products[0].curves[0]
    assert curve.curve_product_id == "curve-gr"
    assert curve.description == "Gamma Ray"
    assert curve.curve_family == "Gamma Ray"
    assert curve.run_interval == "300.5–6076 ft"
    assert curve.run_number == "1"
    assert curve.run_date == "2025-01-02"
    assert curve.classification_source == "managed_knowledge"
    assert curve.classification_confidence == "high"
    assert curve.review_required is False
    assert curve.source_display_name == "Managed curve product"


def test_curve_overlay_normalization_consumes_backend_contract_without_local_percentile_fallback() -> None:
    from app.curve_display.contract_service import BackendCurveDisplayContract

    service = WbvService(repository=_Repository(_record()))
    service.curve_sample_service = _Samples()

    class _BackendContractService:
        def resolve(self, **_: object) -> BackendCurveDisplayContract:
            return BackendCurveDisplayContract(
                managed_well_uid=None,
                managed_curve_uid=None,
                minimum=0.0,
                maximum=200.0,
                scale_type="linear",
                direction="normal",
                clamp=True,
                range_source="backend_test_contract",
                policy_revision="revision-1",
                provenance={"authority": "backend_curve_display_contract"},
                requires_review=False,
            )

    service.curve_display_contract_service = _BackendContractService()
    contract = service.normalize_curve_overlays("managed-well:forge", ["curve-gr"])
    curve = contract.curves[0]
    assert curve.display_min == 0.0
    assert curve.display_max == 200.0
    assert curve.range_source == "backend_test_contract"
    assert curve.policy_revision == "revision-1"
    assert curve.provenance["authority"] == "backend_curve_display_contract"
    assert curve.below_range_count == 1
    assert curve.above_range_count == 1
    assert curve.clipped_fraction == 0.4


def test_curve_overlay_product_inventory_excludes_deviation_survey_source() -> None:
    curve_item = ManagedProductGroupItem(
        product_id="curve-gr",
        display_name="Gamma Ray",
        curve_name="GR",
        curve_type="curve",
        source_id="forge-las",
        wmdp_state=ManagedWmdpState.STAGED_IN_WMDP,
    )
    survey_md = ManagedProductGroupItem(
        product_id="survey-md",
        display_name="Survey MD",
        curve_name="MD",
        curve_type="curve",
        source_id="forge-survey",
        display_layer_type="deviation_survey",
        wmdp_state=ManagedWmdpState.STAGED_IN_WMDP,
    )
    survey_inc = ManagedProductGroupItem(
        product_id="survey-inc",
        display_name="Survey inclination",
        curve_name="INC",
        curve_type="curve",
        source_id="forge-survey",
        wmdp_state=ManagedWmdpState.STAGED_IN_WMDP,
    )
    record = ManagedWellRecord(
        managed_well_id="managed-well:forge",
        well_id="forge",
        well_name="Forge",
        product_groups=[
            ManagedProductGroup(
                group_key="mixed",
                group_label="Mixed",
                items=[curve_item, survey_md, survey_inc],
            )
        ],
    )
    contract = WbvService(repository=_Repository(record)).get_curve_overlay_products("managed-well:forge")
    assert [product.curve_product_id for product in contract.products] == ["forge-las"]


def test_curve_overlay_render_package_maps_samples_to_shared_lane(monkeypatch) -> None:
    record = _record()
    record.metadata["wbv_display_layer_configuration_v1"] = [
        {
            "layer_type": "curve_overlays",
            "visible": True,
            "selected_item_ids": ["curve-gr"],
            "source_type": "wmd",
            "curve_settings": [
                {
                    "curve_product_id": "curve-gr",
                    "display_order": 2,
                    "scale": {"source": "manual", "minimum": 20.0, "maximum": 80.0},
                    "appearance": {
                        "radial_lane": 1,
                        "radial_width": 1.25,
                        "color": "#ffcc00",
                        "fill_mode": "to_baseline",
                        "fill_side": "positive",
                    },
                }
            ],
        }
    ]
    service = WbvService(repository=_Repository(record))
    service.curve_sample_service = _Samples()
    monkeypatch.setattr(
        "app.curve_display.contract_service.WdvCurveDisplayPolicyService.resolve",
        lambda *_args, **_kwargs: {
            "type": "linear",
            "min": 20.0,
            "max": 80.0,
            "direction": "normal",
            "source": "managed_knowledge_curve_rule",
        },
    )
    package = service.get_curve_overlay_render_package("managed-well:forge")
    assert len(package.curves) == 1
    curve = package.curves[0]
    assert curve.radial_lane == 1
    assert curve.display_order == 2
    assert curve.color == "#ffcc00"
    assert curve.fill_mode == "to_baseline"
    assert [sample.normalized for sample in curve.samples] == [0.0, 0.0, 0.5, 1.0, 1.0]


def test_curve_overlay_render_package_carries_between_curves_target(monkeypatch) -> None:
    record = _record()
    second = ManagedProductGroupItem(
        product_id="curve-rhob",
        display_name="Bulk Density",
        curve_name="RHOB",
        curve_type="curve",
        source_id="forge-las",
        wmdp_state=ManagedWmdpState.STAGED_IN_WMDP,
    )
    record.product_groups[0].items.append(second)
    record.metadata["wbv_display_layer_configuration_v1"] = [
        {
            "layer_type": "curve_overlays",
            "visible": True,
            "selected_item_ids": ["curve-gr", "curve-rhob"],
            "curve_settings": [
                {
                    "curve_product_id": "curve-gr",
                    "appearance": {
                        "radial_lane": 0,
                        "fill_mode": "between_curves",
                        "fill_target_curve_product_id": "curve-rhob",
                    },
                },
                {
                    "curve_product_id": "curve-rhob",
                    "appearance": {"radial_lane": 0},
                },
            ],
        }
    ]
    service = WbvService(repository=_Repository(record))
    service.curve_sample_service = _Samples()
    monkeypatch.setattr(
        "app.curve_display.contract_service.WdvCurveDisplayPolicyService.resolve",
        lambda *_args, **_kwargs: {
            "type": "linear",
            "min": 20.0,
            "max": 80.0,
            "direction": "normal",
            "source": "managed_knowledge_curve_rule",
        },
    )
    package = service.get_curve_overlay_render_package("managed-well:forge")
    source = next(curve for curve in package.curves if curve.curve_product_id == "curve-gr")
    assert source.fill_mode == "between_curves"
    assert source.fill_target_curve_product_id == "curve-rhob"


def test_curve_direction_manual_override_is_independent_of_range_source(monkeypatch) -> None:
    record = _record()
    record.metadata["wbv_display_layer_configuration_v1"] = [
        {
            "layer_type": "curve_overlays",
            "visible": True,
            "selected_item_ids": ["curve-gr"],
            "curve_settings": [
                {
                    "curve_product_id": "curve-gr",
                    "scale": {
                        "source": "backend_default",
                        "direction": "reversed",
                        "direction_source": "manual",
                    },
                    "appearance": {"radial_lane": 0},
                }
            ],
        }
    ]
    service = WbvService(repository=_Repository(record))
    service.curve_sample_service = _Samples()
    monkeypatch.setattr(
        "app.curve_display.contract_service.WdvCurveDisplayPolicyService.resolve",
        lambda *_args, **_kwargs: {
            "type": "linear",
            "min": 20.0,
            "max": 80.0,
            "direction": "normal",
            "source": "managed_knowledge_curve_rule",
        },
    )
    package = service.get_curve_overlay_render_package("managed-well:forge")
    assert [sample.normalized for sample in package.curves[0].samples] == [1.0, 1.0, 0.5, 0.0, 0.0]


def test_curve_direction_remains_governed_without_manual_override(monkeypatch) -> None:
    record = _record()
    record.metadata["wbv_display_layer_configuration_v1"] = [
        {
            "layer_type": "curve_overlays",
            "visible": True,
            "selected_item_ids": ["curve-gr"],
            "curve_settings": [
                {
                    "curve_product_id": "curve-gr",
                    "scale": {
                        "source": "backend_default",
                        "direction": "reversed",
                        "direction_source": "governed",
                    },
                    "appearance": {"radial_lane": 0},
                }
            ],
        }
    ]
    service = WbvService(repository=_Repository(record))
    service.curve_sample_service = _Samples()
    monkeypatch.setattr(
        "app.curve_display.contract_service.WdvCurveDisplayPolicyService.resolve",
        lambda *_args, **_kwargs: {
            "type": "linear",
            "min": 20.0,
            "max": 80.0,
            "direction": "normal",
            "source": "managed_knowledge_curve_rule",
        },
    )
    package = service.get_curve_overlay_render_package("managed-well:forge")
    assert [sample.normalized for sample in package.curves[0].samples] == [0.0, 0.0, 0.5, 1.0, 1.0]


def test_persisted_wbv_p5_p95_intent_reaches_shared_backend_resolver(monkeypatch) -> None:
    record = _record()
    record.metadata["wbv_display_layer_configuration_v1"] = [
        {
            "layer_type": "curve_overlays",
            "visible": True,
            "selected_item_ids": ["curve-gr"],
            "curve_settings": [
                {
                    "curve_product_id": "curve-gr",
                    "scale": {
                        "source": "robust_p5_p95",
                        "scale_type": "linear",
                        "direction": "normal",
                        "direction_source": "governed",
                    },
                    "appearance": {"track_id": "curve-track-0"},
                }
            ],
        }
    ]
    service = WbvService(repository=_Repository(record))
    service.curve_sample_service = _Samples()
    monkeypatch.setattr(
        "app.curve_display.contract_service.WdvCurveDisplayPolicyService.resolve",
        lambda *_args, **_kwargs: {
            "type": "linear", "min": 0.0, "max": 200.0,
            "direction": "normal", "source": "managed_knowledge_curve_rule",
        },
    )
    contract = service.normalize_curve_overlays("managed-well:forge", ["curve-gr"])
    curve = contract.curves[0]
    assert curve.display_min == 20.0
    assert curve.display_max == 80.0
    assert curve.range_source == "backend_observed_p05_p95"
    assert curve.provenance["policy_scope"] == "backend_persisted_curve_intent"

def test_render_package_uses_backend_contract_metadata_without_local_manual_scale_state(monkeypatch) -> None:
    record = _record()
    record.metadata["wbv_display_layer_configuration_v1"] = [
        {
            "layer_type": "curve_overlays",
            "visible": True,
            "selected_item_ids": ["curve-gr"],
            "curve_settings": [
                {
                    "curve_product_id": "curve-gr",
                    "scale": {"source": "manual", "minimum": 20.0, "maximum": 80.0},
                    "appearance": {"radial_lane": 0},
                }
            ],
        }
    ]
    service = WbvService(repository=_Repository(record))
    service.curve_sample_service = _Samples()
    monkeypatch.setattr(
        service,
        "normalize_curve_overlays",
        lambda *_args, **_kwargs: WbvCurveOverlayNormalizationContract(
            managed_well_id="managed-well:forge",
            curves=[
                WbvCurveOverlayNormalizationItem(
                    curve_product_id="curve-gr",
                    display_name="Gamma Ray",
                    mnemonic="GR",
                    unit="gAPI",
                    display_min=20.0,
                    display_max=80.0,
                    scale_type="linear",
                    display_direction="normal",
                    range_source="backend_manual_override",
                    policy_revision="backend-curve-display-contract-v2",
                    provenance={
                        "authority": "backend_curve_display_contract",
                        "policy_scope": "explicit_manual_override",
                    },
                )
            ],
        ),
    )

    package = service.get_curve_overlay_render_package("managed-well:forge")
    curve = package.curves[0]

    assert curve.range_source == "backend_manual_override"
    assert curve.policy_revision == "backend-curve-display-contract-v2"
    assert curve.provenance == {
        "authority": "backend_curve_display_contract",
        "policy_scope": "explicit_manual_override",
    }

