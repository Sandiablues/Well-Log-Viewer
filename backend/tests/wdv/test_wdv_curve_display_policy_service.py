from app.inventory.models import ManagedProductGroupItem
from app.wdv_display.policy_service import WdvCurveDisplayPolicyService


def product(name: str, unit: str = "") -> ManagedProductGroupItem:
    return ManagedProductGroupItem(
        product_id=f"product-{name}",
        display_name=name,
        curve_name=name,
        curve_type="curve",
        curve_unit=unit,
        selectable=True,
    )


def test_gamma_policy_is_backend_owned() -> None:
    policy = WdvCurveDisplayPolicyService.resolve(product("GR", "API"), {})
    assert policy["curve_class"] == "gamma"
    assert policy["lattice"] == "linear"
    assert policy["min"] == 0.0
    assert policy["max"] == 200.0
    assert policy["direction"] == "normal"
    assert policy["default_color"]


def test_resistivity_policy_is_logarithmic() -> None:
    policy = WdvCurveDisplayPolicyService.resolve(product("Deep Resistivity", "ohm.m"), {})
    assert policy["curve_class"] == "resistivity"
    assert policy["lattice"] == "logarithmic"
    assert policy["type"] == "log"
    assert policy["min"] == 0.2
    assert policy["max"] == 2000.0


def test_neutron_policy_preserves_reversed_display_semantics() -> None:
    policy = WdvCurveDisplayPolicyService.resolve(product("Neutron Porosity", "v/v"), {})
    assert policy["curve_class"] == "neutron"
    assert policy["direction"] == "reversed"
    assert policy["min"] > policy["max"]
