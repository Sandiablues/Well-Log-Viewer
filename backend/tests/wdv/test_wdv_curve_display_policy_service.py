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
    assert policy["max"] == 150.0
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


# ---------------------------------------------------------------------------
# Regression: log-scale governed range must not be overridden by observed stats
#
# Forge 21-31 AT30 had scale_min = -3.7597 stored because the
# _add_visual_variation_diagnostics override fired when the p05-p95 span
# (~66 ohm-m) divided by the 0.2–2000 display span (~1999.8) was < 0.08.
# That replaced the resistivity policy range with padded observed statistics
# that included a negative minimum, breaking logarithmic rendering entirely.
#
# Fix: log-type scales must never have their governed range overwritten by the
# low_visual_variation heuristic.  The linear span ratio is semantically
# invalid for log data and can produce non-positive bounds.
# ---------------------------------------------------------------------------

def _resistivity_item(name: str) -> ManagedProductGroupItem:
    """Create a resistivity ManagedProductGroupItem whose key matches the
    resistivity branch (curve_family='resistivity', unit='ohm.m')."""
    return ManagedProductGroupItem(
        product_id=f"product-{name}",
        display_name=name,
        curve_name=name,
        curve_type="curve",
        curve_unit="ohm.m",
        curve_family="resistivity",
        selectable=True,
    )


# Sample stats that represent Forge 21-31 AT30: narrow observed range that
# historically caused visual_span_ratio < 0.08 and triggered the override.
_FORGE_NARROW_STATS = {
    "observed_min": -4.1,
    "observed_max": 68.9,
    "robust_observed_min": -3.76,
    "robust_observed_max": 62.47,
    "observed_p05": -3.76,
    "observed_p95": 62.47,
    "rejected_sample_count": 0,
}


def test_at30_affected_curve_retains_governed_log_range_with_narrow_stats() -> None:
    """AT30 (affected Forge curve): narrow observed stats must not override the
    resistivity log range.  scale_min must be positive and governed at 0.2."""
    policy = WdvCurveDisplayPolicyService.resolve(
        _resistivity_item("AT30"), _FORGE_NARROW_STATS
    )

    # Classification
    assert policy["curve_class"] == "resistivity"
    assert policy["lattice"] == "logarithmic"
    assert policy["type"] == "log"

    # Governed range must be intact — not replaced by observed stats
    assert policy["min"] == 0.2, (
        f"Expected governed min 0.2 but got {policy['min']!r}; "
        "the low_visual_variation override must not fire for log scales"
    )
    assert policy["max"] == 2000.0, (
        f"Expected governed max 2000.0 but got {policy['max']!r}"
    )

    # min must be strictly positive for log rendering
    assert policy["min"] > 0, (
        f"scale_min={policy['min']} is non-positive; logarithmic rendering "
        "requires min > 0"
    )
    assert policy["max"] > policy["min"]

    # Source must remain the Managed-KR family default — not overridden
    assert policy["source"] == "managed_knowledge_family_default", (
        f"Expected source='managed_knowledge_family_default' but got {policy['source']!r}; "
        "robust_observed_statistics must not be the source for a log scale"
    )


def test_at10_control_curve_retains_governed_log_range() -> None:
    """AT10 (unaffected control): resistivity log range is also governed at
    0.2–2000 regardless of the observed stats passed in."""
    # Use the same narrow stats to prove the fix is symmetric:
    # both AT30 and AT10 must now go through the same code path.
    policy = WdvCurveDisplayPolicyService.resolve(
        _resistivity_item("AT10"), _FORGE_NARROW_STATS
    )

    assert policy["curve_class"] == "resistivity"
    assert policy["lattice"] == "logarithmic"
    assert policy["type"] == "log"
    assert policy["min"] == 0.2
    assert policy["max"] == 2000.0
    assert policy["min"] > 0
    assert policy["source"] == "managed_knowledge_family_default"


def test_at30_and_at10_resolve_identically_with_same_stats() -> None:
    """Affected and control resistivity curves must arrive at the same
    backend-governed scale when given identical observed stats.  This is
    the focused comparison test requested in the regression spec."""
    at30 = WdvCurveDisplayPolicyService.resolve(
        _resistivity_item("AT30"), _FORGE_NARROW_STATS
    )
    at10 = WdvCurveDisplayPolicyService.resolve(
        _resistivity_item("AT10"), _FORGE_NARROW_STATS
    )

    assert at30["min"] == at10["min"] == 0.2
    assert at30["max"] == at10["max"] == 2000.0
    assert at30["lattice"] == at10["lattice"] == "logarithmic"
    assert at30["source"] == at10["source"] == "managed_knowledge_family_default"
    # Neither curve may carry a non-positive min — that would break log rendering
    assert at30["min"] > 0
    assert at10["min"] > 0
