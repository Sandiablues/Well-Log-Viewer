from __future__ import annotations

from app.inventory.models import ManagedProductGroupItem
from app.wdv_display.kr_family_policy_resolver import (
    ManagedKrFamilyDisplayPolicyResolver,
)
from app.wdv_display.policy_service import WdvCurveDisplayPolicyService


def item(
    name: str,
    *,
    unit: str = "",
    family: str = "Unclassified",
    kr_curve_type_id: str | None = None,
) -> ManagedProductGroupItem:
    return ManagedProductGroupItem(
        product_id=f"product-{name}",
        display_name=name,
        curve_name=name,
        observed_mnemonic=name,
        normalized_mnemonic=name,
        curve_type="curve",
        curve_unit=unit,
        curve_family=family,
        kr_curve_type_id=kr_curve_type_id,
        selectable=True,
    )


def test_at30_resolves_through_alias_definition_to_kr_resistivity_family() -> None:
    ManagedKrFamilyDisplayPolicyResolver.clear_cache_for_tests()
    policy = WdvCurveDisplayPolicyService.resolve(
        item("AT30", unit="ohm.m", family="Resistivity"),
        {
            "observed_min": -4.1,
            "observed_max": 68.9,
            "observed_p05": -3.76,
            "observed_p95": 62.47,
        },
    )
    assert policy["source"] == "managed_knowledge_family_default"
    assert policy["curve_family"] == "resistivity"
    assert policy["policy_record_id"] == "wlv_approved_kr_refs_1_scale_default_resistivity"
    assert policy["type"] == "log"
    assert policy["min"] == 0.2
    assert policy["max"] == 2000.0
    assert policy["min"] > 0
    assert policy["lattice"] == "logarithmic"


def test_gamma_family_uses_updated_kr_default() -> None:
    ManagedKrFamilyDisplayPolicyResolver.clear_cache_for_tests()
    policy = WdvCurveDisplayPolicyService.resolve(
        item("GR", unit="API", family="Gamma Ray"),
        {},
    )
    assert policy["source"] == "managed_knowledge_family_default"
    assert policy["curve_family"] == "gamma_ray"
    assert policy["min"] == 0.0
    assert policy["max"] == 150.0
    assert policy["type"] == "linear"


def test_kr_family_policy_is_not_replaced_by_observed_statistics() -> None:
    ManagedKrFamilyDisplayPolicyResolver.clear_cache_for_tests()
    policy = WdvCurveDisplayPolicyService.resolve(
        item("AT90", unit="ohm.m", family="resistivity"),
        {
            "observed_min": -2.0,
            "observed_max": 35.0,
            "observed_p05": -1.8,
            "observed_p95": 35.2,
        },
    )
    assert policy["source"] == "managed_knowledge_family_default"
    assert policy["min"] == 0.2
    assert policy["max"] == 2000.0


def test_unknown_family_uses_controlled_internal_fallback() -> None:
    ManagedKrFamilyDisplayPolicyResolver.clear_cache_for_tests()
    policy = WdvCurveDisplayPolicyService.resolve(
        item("UNKNOWN_CURVE", family="Unclassified"),
        {},
    )
    assert policy["source"] == "internal_fallback"
    assert policy["type"] == "linear"
    assert policy["min"] == 0.0
    assert policy["max"] == 150.0
