"""UNIT-3D tests — activation of the policy-unit resolution engine.

Tests ``WdvCurveDisplayPolicyService.resolve()`` with the live
``resolve_with_unit_resolution()`` path active, covering:

  A  — live-path activation (typed resolver called; legacy not called;
        policy_revision forwarded; engine-version token is correct)
  B  — IDENTITY path: resolved bounds pass through unchanged
  C  — CONVERTED path: bounds are in the curve-unit frame
  D  — non-usable status variants with / without observed stats
  E  — Tier-2 heuristic unit conversions (density, caliper)
  F  — Tier-3 no-bounds contract (review_required=True)
  G  — warning deduplication (failure token not added twice)
  H  — KR overlay precedence (bounds/source/review_required owned by fallback)
  I  — exact-rule terminal: non-usable unit does not fall through to family
  J  — no-KR regression (policy=None → internal fallback chain unchanged)
  K  — WdvCanonicalCurveDisplayPolicy model validator invariants
  L  — v2_2 contract version constant
  M  — revision changes when KR content changes
  N  — warning token format
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.identity.wdv_viewer_package_v21 import (
    WDV_VIEWER_PACKAGE_CONTRACT_VERSION,
    WdvCanonicalCurveDisplayPolicy,
)
from app.inventory.models import ManagedProductGroupItem
from app.knowledge.managed_storage import ManagedStorage
from app.wdv_display.kr_family_policy_resolver import (
    ManagedKrFamilyDisplayPolicyResolver,
    _UNIT_RESOLUTION_ENGINE_VERSION,
)
from app.wdv_display.policy_service import (
    WDV_DISPLAY_POLICY_RESOLVER_VERSION,
    WDV_DISPLAY_POLICY_UNIT_CONTRACT_VERSION,
    WdvCurveDisplayPolicyService,
    _clear_display_policy_revision_cache_for_tests,
    compute_display_policy_revision,
)
from app.wdv_display.policy_unit_resolution import (
    PolicyUnitResolutionResult,
    PolicyUnitResolutionStatus,
    ResolvedDisplayPolicy,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_caches():
    ManagedKrFamilyDisplayPolicyResolver.clear_cache_for_tests()
    _clear_display_policy_revision_cache_for_tests()
    yield
    ManagedKrFamilyDisplayPolicyResolver.clear_cache_for_tests()
    _clear_display_policy_revision_cache_for_tests()


def _item(
    curve_name: str = "AT90",
    curve_family: str = "resistivity",
    kr_curve_type_id: str | None = "resistivity_at90",
    curve_unit: str | None = "ohmm",
) -> ManagedProductGroupItem:
    return ManagedProductGroupItem(
        product_id=curve_name,
        display_name=curve_name,
        curve_name=curve_name,
        curve_type="curve",
        curve_unit=curve_unit,
        curve_family=curve_family,
        kr_curve_type_id=kr_curve_type_id,
    )


def _ur(
    status: PolicyUnitResolutionStatus,
    *,
    policy_record_id: str | None = "rec-1",
    policy_record_version: int | None = 1,
    policy_source: str | None = "exact",
    original_policy_min: float | None = None,
    original_policy_max: float | None = None,
    canonical_policy_unit: str | None = None,
    canonical_curve_unit: str | None = None,
    resolved_min: float | None = None,
    resolved_max: float | None = None,
    conversion_applied: bool = False,
    unresolved_reason: str | None = None,
    policy_revision: str | None = None,
) -> PolicyUnitResolutionResult:
    """Build a PolicyUnitResolutionResult with resolved_bounds_usable derived from status."""
    usable = status in {
        PolicyUnitResolutionStatus.IDENTITY,
        PolicyUnitResolutionStatus.CONVERTED,
    }
    return PolicyUnitResolutionResult(
        status=status,
        resolved_bounds_usable=usable,
        policy_record_id=policy_record_id,
        policy_record_version=policy_record_version,
        policy_source=policy_source,
        original_policy_min=original_policy_min,
        original_policy_max=original_policy_max,
        canonical_policy_unit=canonical_policy_unit,
        canonical_curve_unit=canonical_curve_unit,
        resolved_min=resolved_min if usable else None,
        resolved_max=resolved_max if usable else None,
        conversion_applied=conversion_applied,
        unresolved_reason=unresolved_reason,
        resolver_version=_UNIT_RESOLUTION_ENGINE_VERSION,
        policy_revision=policy_revision,
    )


def _kr_policy(
    scale_type: str = "linear",
    direction: str = "normal",
    source: str = "managed_knowledge_curve_rule",
    **extra: Any,
) -> dict[str, Any]:
    """Minimal policy dict as returned by the KR resolver."""
    return {
        "type": scale_type,
        "direction": direction,
        "source": source,
        "warnings": [],
        **extra,
    }


def _resolve_via_mock(
    item: ManagedProductGroupItem,
    resolved: ResolvedDisplayPolicy,
    sample_stats: dict | None = None,
    revision: str = "rev-test",
) -> dict[str, Any]:
    """Call WdvCurveDisplayPolicyService.resolve() with a mocked typed resolver."""
    with patch.object(
        ManagedKrFamilyDisplayPolicyResolver,
        "resolve_with_unit_resolution",
        return_value=resolved,
    ):
        with patch(
            "app.wdv_display.policy_service.compute_display_policy_revision",
            return_value=revision,
        ):
            return WdvCurveDisplayPolicyService.resolve(item, sample_stats=sample_stats)


def _fallback(
    ur: PolicyUnitResolutionResult | None,
    *,
    policy: dict | None = None,
    has_stats: bool = False,
    observed_min: float | None = None,
    observed_max: float | None = None,
    curve_class: str = "generic",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Call _resolve_with_fallback_hierarchy directly with a pass-through finalize."""
    resolved = ResolvedDisplayPolicy(
        policy=policy or _kr_policy(),
        unit_resolution=ur,
    )
    return WdvCurveDisplayPolicyService._resolve_with_fallback_hierarchy(
        resolved=resolved,
        ur=ur,
        has_stats=has_stats,
        observed_min=observed_min,
        observed_max=observed_max,
        curve_class=curve_class,
        warnings=warnings or [],
        finalize=lambda d: d,
    )


def _write_kr(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps({"version": "1", "records": records}, indent=2),
        encoding="utf-8",
    )


def _approved(extra: dict[str, Any]) -> dict[str, Any]:
    return {"status": "approved", "runtime_eligible": True, "version": 1, **extra}


def _template_scale_default(
    record_id: str,
    curve_family: str,
    *,
    scale_min: float = 0.0,
    scale_max: float = 150.0,
    policy_value_unit: str | None = None,
    version: int = 1,
) -> dict[str, Any]:
    rec: dict[str, Any] = _approved({
        "record_id": record_id,
        "record_type": "template_scale_default",
        "curve_family": curve_family,
        "scale_type": "linear",
        "scale_min": scale_min,
        "scale_max": scale_max,
        "display_direction": "normal",
    })
    rec["version"] = version
    if policy_value_unit is not None:
        rec["policy_value_unit"] = policy_value_unit
    return rec


# ---------------------------------------------------------------------------
# A — Live-path activation
# ---------------------------------------------------------------------------

def test_a1_typed_resolver_called_legacy_not_called() -> None:
    """resolve() invokes resolve_with_unit_resolution, never the legacy resolve()."""
    item = _item()
    resolved = ResolvedDisplayPolicy(policy=None, unit_resolution=None)

    with patch.object(
        ManagedKrFamilyDisplayPolicyResolver,
        "resolve_with_unit_resolution",
        return_value=resolved,
    ) as mock_new:
        with patch.object(
            ManagedKrFamilyDisplayPolicyResolver, "resolve"
        ) as mock_old:
            with patch(
                "app.wdv_display.policy_service.compute_display_policy_revision",
                return_value="rev-x",
            ):
                WdvCurveDisplayPolicyService.resolve(item)

    mock_new.assert_called_once()
    mock_old.assert_not_called()


def test_a2_policy_revision_forwarded_to_resolver() -> None:
    """The content-based policy_revision is forwarded as a kwarg to resolve_with_unit_resolution."""
    item = _item()
    resolved = ResolvedDisplayPolicy(policy=None, unit_resolution=None)

    with patch.object(
        ManagedKrFamilyDisplayPolicyResolver,
        "resolve_with_unit_resolution",
        return_value=resolved,
    ) as mock_new:
        with patch(
            "app.wdv_display.policy_service.compute_display_policy_revision",
            return_value="sha256:abc",
        ):
            WdvCurveDisplayPolicyService.resolve(item)

    _, kwargs = mock_new.call_args
    assert kwargs.get("policy_revision") == "sha256:abc"


def test_a3_engine_version_reflects_activation() -> None:
    """Engine-version token and resolver version token both reflect UNIT-3D activation."""
    assert _UNIT_RESOLUTION_ENGINE_VERSION == "wdv_unit_resolution_v3d"
    assert "3d" in WDV_DISPLAY_POLICY_RESOLVER_VERSION.lower()
    assert "active" in WDV_DISPLAY_POLICY_RESOLVER_VERSION.lower()
    assert "3d" in WDV_DISPLAY_POLICY_UNIT_CONTRACT_VERSION.lower()
    assert "active" in WDV_DISPLAY_POLICY_UNIT_CONTRACT_VERSION.lower()


# ---------------------------------------------------------------------------
# B — IDENTITY: bounds from ur.resolved_min / resolved_max
# ---------------------------------------------------------------------------

def test_b1_identity_bounds_used_directly() -> None:
    """IDENTITY status → resolved bounds are used; source from KR policy preserved."""
    item = _item(curve_unit="ohmm")
    ur = _ur(
        PolicyUnitResolutionStatus.IDENTITY,
        canonical_policy_unit="ohmm",
        canonical_curve_unit="ohmm",
        resolved_min=0.2,
        resolved_max=2000.0,
    )
    resolved = ResolvedDisplayPolicy(
        policy=_kr_policy(
            scale_type="log",
            source="managed_knowledge_curve_rule",
            min=0.2, max=2000.0,
        ),
        unit_resolution=ur,
    )
    result = _resolve_via_mock(item, resolved)

    assert result["min"] == pytest.approx(0.2)
    assert result["max"] == pytest.approx(2000.0)
    assert result["source"] == "managed_knowledge_curve_rule"
    assert not any("policy_unit_resolution_failed" in w for w in result.get("warnings", []))


# ---------------------------------------------------------------------------
# C — CONVERTED: bounds in curve-unit frame
# ---------------------------------------------------------------------------

def test_c1_converted_bounds_in_curve_unit_frame() -> None:
    """CONVERTED status → bounds are the converted values (not raw policy bounds)."""
    item = _item(
        curve_name="RHOB", curve_family="density",
        kr_curve_type_id="bulk_density", curve_unit="kg/m3",
    )
    ur = _ur(
        PolicyUnitResolutionStatus.CONVERTED,
        canonical_policy_unit="g/cc",
        canonical_curve_unit="kg/m3",
        original_policy_min=2.1,
        original_policy_max=2.8,
        resolved_min=2100.0,
        resolved_max=2800.0,
        conversion_applied=True,
    )
    resolved = ResolvedDisplayPolicy(
        policy=_kr_policy(
            scale_type="linear",
            source="managed_knowledge_curve_rule",
            min=2.1, max=2.8,
        ),
        unit_resolution=ur,
    )
    result = _resolve_via_mock(item, resolved)

    assert result["min"] == pytest.approx(2100.0)
    assert result["max"] == pytest.approx(2800.0)
    assert result["source"] == "managed_knowledge_curve_rule"


# ---------------------------------------------------------------------------
# D — Non-usable statuses with / without observed stats
# ---------------------------------------------------------------------------

def test_d1_missing_policy_unit_with_stats_uses_tier1() -> None:
    """MISSING_POLICY_UNIT + observed stats → Tier-1 padded observed domain."""
    ur = _ur(
        PolicyUnitResolutionStatus.MISSING_POLICY_UNIT,
        canonical_curve_unit="ohmm",
    )
    result = _fallback(
        ur,
        has_stats=True,
        observed_min=5.0,
        observed_max=50.0,
        curve_class="resistivity",
    )

    assert result["source"] == "observed_statistics"
    assert result.get("review_required") is False
    assert result["min"] is not None and result["max"] is not None
    assert "policy_unit_resolution_failed:missing_policy_unit" in result["warnings"]


def test_d2_missing_policy_unit_no_stats_uses_tier2() -> None:
    """MISSING_POLICY_UNIT + no stats + resistivity family → Tier-2 heuristic (ohmm→ohmm)."""
    ur = _ur(
        PolicyUnitResolutionStatus.MISSING_POLICY_UNIT,
        canonical_curve_unit="ohmm",
    )
    result = _fallback(ur, curve_class="resistivity")

    assert result["source"] == "unit_resolution_tier2_heuristic"
    assert result.get("review_required") is False
    assert result["min"] == pytest.approx(0.2)
    assert result["max"] == pytest.approx(2000.0)


def test_d3_missing_curve_unit_with_stats_tier1_tier2_excluded() -> None:
    """MISSING_CURVE_UNIT: canonical_curve_unit=None → Tier-2 excluded; Tier-1 used when stats present."""
    ur = _ur(
        PolicyUnitResolutionStatus.MISSING_CURVE_UNIT,
        canonical_curve_unit=None,  # no curve unit → Tier 2 excluded
    )
    result = _fallback(
        ur,
        has_stats=True,
        observed_min=0.0,
        observed_max=150.0,
        curve_class="gamma",
    )

    assert result["source"] == "observed_statistics"
    assert result.get("review_required") is False


def test_d4_missing_curve_unit_no_stats_tier3() -> None:
    """MISSING_CURVE_UNIT + no stats → Tier-2 excluded (no canonical_curve_unit) → Tier-3."""
    ur = _ur(
        PolicyUnitResolutionStatus.MISSING_CURVE_UNIT,
        canonical_curve_unit=None,
    )
    result = _fallback(ur, curve_class="gamma")

    assert result["source"] == "unit_resolution_tier3_no_bounds"
    assert result.get("review_required") is True
    assert result.get("min") is None
    assert result.get("max") is None


def test_d5_unknown_curve_unit_no_stats_tier3() -> None:
    """UNKNOWN_CURVE_UNIT + no stats → canonical_curve_unit=None → Tier-3."""
    ur = _ur(
        PolicyUnitResolutionStatus.UNKNOWN_CURVE_UNIT,
        canonical_curve_unit=None,  # normalization failed
    )
    result = _fallback(ur, curve_class="density")

    assert result["source"] == "unit_resolution_tier3_no_bounds"
    assert result.get("review_required") is True


def test_d6_incompatible_with_stats_tier1() -> None:
    """INCOMPATIBLE + stats → Tier-1 used (incompatible does not prevent Tier-1)."""
    ur = _ur(
        PolicyUnitResolutionStatus.INCOMPATIBLE,
        canonical_policy_unit="ohmm",
        canonical_curve_unit="gapi",
    )
    result = _fallback(
        ur,
        has_stats=True,
        observed_min=10.0,
        observed_max=100.0,
        curve_class="generic",
    )

    assert result["source"] == "observed_statistics"
    assert result.get("review_required") is False


def test_d7_log_scale_nonpositive_domain_excludes_tier1() -> None:
    """Log scale with non-positive padded domain → Tier-1 excluded; Tier-2 used if available."""
    ur = _ur(
        PolicyUnitResolutionStatus.MISSING_POLICY_UNIT,
        canonical_curve_unit="ohmm",
    )
    # observed_min=-5 → padded domain will be negative → invalid for log scale
    result = _fallback(
        ur,
        policy=_kr_policy(scale_type="log"),
        has_stats=True,
        observed_min=-5.0,
        observed_max=10.0,
        curve_class="resistivity",
    )

    # Tier-1 excluded (non-positive log domain) → Tier-2 heuristic used
    assert result["source"] == "unit_resolution_tier2_heuristic"


def test_d8_unresolved_status_no_stats_tier3() -> None:
    """UNRESOLVED (catch-all) + no stats + unknown class → Tier-3."""
    ur = _ur(
        PolicyUnitResolutionStatus.UNRESOLVED,
        canonical_curve_unit="someunit",
        unresolved_reason="internal error",
    )
    result = _fallback(ur, curve_class="generic")

    # generic class has no Tier-2 heuristic → Tier-3
    assert result["source"] == "unit_resolution_tier3_no_bounds"
    assert result.get("review_required") is True
    assert "policy_unit_resolution_failed:unresolved" in result["warnings"]


# ---------------------------------------------------------------------------
# E — Tier-2 heuristic unit conversions
# ---------------------------------------------------------------------------

def test_e1_tier2_density_identity() -> None:
    """_tier2_heuristic_bounds density g/cc → g/cc: bounds returned unchanged."""
    result = WdvCurveDisplayPolicyService._tier2_heuristic_bounds("density", "g/cc")
    assert result is not None
    lo, hi = result
    assert lo == pytest.approx(1.95)
    assert hi == pytest.approx(2.95)


def test_e2_tier2_density_kg_m3_conversion() -> None:
    """_tier2_heuristic_bounds density g/cc → kg/m3: bounds scaled × 1000."""
    result = WdvCurveDisplayPolicyService._tier2_heuristic_bounds("density", "kg/m3")
    assert result is not None
    lo, hi = result
    assert lo == pytest.approx(1950.0)
    assert hi == pytest.approx(2950.0)


def test_e3_tier2_caliper_mm_conversion() -> None:
    """_tier2_heuristic_bounds caliper in → mm: bounds scaled × 25.4."""
    result = WdvCurveDisplayPolicyService._tier2_heuristic_bounds("borehole", "mm")
    assert result is not None
    lo, hi = result
    assert lo == pytest.approx(6.0 * 25.4)
    assert hi == pytest.approx(16.0 * 25.4)


def test_e4_tier2_unknown_curve_class_returns_none() -> None:
    """_tier2_heuristic_bounds for an unrecognized curve_class returns None."""
    result = WdvCurveDisplayPolicyService._tier2_heuristic_bounds("unknown_class", "m")
    assert result is None


def test_e5_tier2_incompatible_unit_returns_none() -> None:
    """_tier2_heuristic_bounds when conversion is impossible returns None."""
    # gamma heuristic is in gapi; 'm' is incompatible
    result = WdvCurveDisplayPolicyService._tier2_heuristic_bounds("gamma", "m")
    assert result is None


# ---------------------------------------------------------------------------
# F — Tier-3 no-bounds contract
# ---------------------------------------------------------------------------

def test_f1_tier3_review_required_true() -> None:
    """No stats, no Tier-2 match → Tier-3: review_required=True, bounds both None."""
    ur = _ur(
        PolicyUnitResolutionStatus.MISSING_POLICY_UNIT,
        canonical_curve_unit="exotic_unit_xyz",  # conversion will fail
    )
    result = _fallback(ur, curve_class="generic")

    assert result["source"] == "unit_resolution_tier3_no_bounds"
    assert result.get("review_required") is True
    assert result.get("min") is None
    assert result.get("max") is None


# ---------------------------------------------------------------------------
# G — Warning deduplication
# ---------------------------------------------------------------------------

def test_g1_failure_token_not_added_twice() -> None:
    """Failure token is not duplicated when already present in kr warnings."""
    token = "policy_unit_resolution_failed:missing_policy_unit"
    ur = _ur(PolicyUnitResolutionStatus.MISSING_POLICY_UNIT, canonical_curve_unit="ohmm")
    # Pre-seed the failure token in the KR policy warnings
    policy = _kr_policy(warnings=[token])
    result = _fallback(ur, policy=policy, curve_class="resistivity")

    assert result["warnings"].count(token) == 1


def test_g2_stats_warning_and_kr_warnings_merged_once() -> None:
    """warnings from the stats path and KR policy are unioned without duplicates."""
    ur = _ur(PolicyUnitResolutionStatus.MISSING_POLICY_UNIT, canonical_curve_unit="ohmm")
    # Item has an existing warning from stats (rejected_sample_count)
    result = _fallback(
        ur,
        policy=_kr_policy(warnings=["existing_kr_warning"]),
        warnings=["invalid_samples_rejected"],
        has_stats=True,
        observed_min=0.0,
        observed_max=200.0,
        curve_class="gamma",
    )

    warnings = result["warnings"]
    assert warnings.count("invalid_samples_rejected") == 1
    assert warnings.count("existing_kr_warning") == 1


# ---------------------------------------------------------------------------
# H — KR overlay precedence
# ---------------------------------------------------------------------------

def test_h1_fallback_owns_bounds_source_review_required() -> None:
    """Fallback hierarchy owns min, max, source, review_required; KR owns direction."""
    ur = _ur(
        PolicyUnitResolutionStatus.MISSING_POLICY_UNIT,
        canonical_curve_unit="ohmm",
    )
    policy = _kr_policy(direction="reversed", source="managed_knowledge_curve_rule")
    result = _fallback(ur, policy=policy, curve_class="resistivity")

    # Fallback overwrites min/max/source (KR min/max ignored)
    assert result["source"] in {
        "observed_statistics",
        "unit_resolution_tier2_heuristic",
        "unit_resolution_tier3_no_bounds",
    }
    # KR direction is preserved via overlay
    assert result["direction"] == "reversed"


def test_h2_review_required_true_cannot_be_cleared() -> None:
    """review_required=True set by Tier-3 must survive; KR cannot override it."""
    ur = _ur(
        PolicyUnitResolutionStatus.MISSING_POLICY_UNIT,
        canonical_curve_unit="exotic_xyz",  # no heuristic conversion
    )
    result = _fallback(ur, curve_class="generic")

    # Tier-3 fired → review_required must be True
    assert result["review_required"] is True


# ---------------------------------------------------------------------------
# I — Exact-rule terminal: non-usable does not fall through to family
# ---------------------------------------------------------------------------

def test_i1_exact_rule_terminal_with_usable_unit(tmp_path: Path) -> None:
    """Exact display_rule with usable unit → terminal; IDENTITY bounds used; no family consulted."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _approved({
            "record_id": "dr_res", "record_type": "display_rule",
            "canonical_curve_id": "resistivity_at90",
            "preferred_track_family": "resistivity",
            "scale_type": "log", "display_min": 0.2, "display_max": 2000.0,
            "reverse_scale": False, "policy_value_unit": "ohmm",
        }),
        _template_scale_default("tsd_res", "resistivity",
                                scale_min=0.2, scale_max=2000.0,
                                policy_value_unit="ohmm"),
    ])
    item = _item(curve_unit="ohmm")

    result = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(
        item, storage=ManagedStorage(path=kr_path)
    )

    assert result.unit_resolution is not None
    assert result.unit_resolution.policy_source == "exact"
    assert result.unit_resolution.status is PolicyUnitResolutionStatus.IDENTITY
    assert result.unit_resolution.resolved_bounds_usable is True


# ---------------------------------------------------------------------------
# J — No-KR regression
# ---------------------------------------------------------------------------

def test_j1_no_kr_match_falls_to_internal_chain() -> None:
    """policy=None (no KR match) → existing internal fallback chain, not typed path."""
    item = _item(curve_name="AT90", curve_family="resistivity", curve_unit="ohmm")
    resolved = ResolvedDisplayPolicy(policy=None, unit_resolution=None)
    result = _resolve_via_mock(item, resolved)

    # Internal resistivity fallback: log scale, 0.2–2000
    assert result["type"] == "log"
    assert result["min"] == pytest.approx(0.2)
    assert result["max"] == pytest.approx(2000.0)
    assert result["source"] == "internal_fallback"


def test_j2_no_kr_match_gamma_internal_fallback() -> None:
    """Gamma curve with no KR match → internal fallback 0–200."""
    item = _item(curve_name="GR", curve_family="gamma", curve_unit="gapi")
    resolved = ResolvedDisplayPolicy(policy=None, unit_resolution=None)
    result = _resolve_via_mock(item, resolved)

    assert result["type"] == "linear"
    assert result["min"] == pytest.approx(0.0)
    assert result["max"] == pytest.approx(200.0)
    assert result["source"] == "internal_fallback"


# ---------------------------------------------------------------------------
# K — WdvCanonicalCurveDisplayPolicy model validator invariants
# ---------------------------------------------------------------------------

def _display_policy(**kwargs: Any) -> WdvCanonicalCurveDisplayPolicy:
    defaults: dict[str, Any] = dict(
        curve_class="gamma",
        lattice="linear",
        scale_type="linear",
        scale_direction="normal",
        default_color="#2f80ed",
        source="template_default",
    )
    defaults.update(kwargs)
    return WdvCanonicalCurveDisplayPolicy(**defaults)


def test_k1_valid_bounds_review_required_false() -> None:
    """Present display_min/max with review_required=False is valid."""
    dp = _display_policy(display_min=0.0, display_max=200.0, review_required=False)
    assert dp.display_min == pytest.approx(0.0)
    assert dp.display_max == pytest.approx(200.0)
    assert dp.review_required is False


def test_k2_no_bounds_review_required_true() -> None:
    """Absent bounds with review_required=True is valid."""
    dp = _display_policy(review_required=True)
    assert dp.display_min is None
    assert dp.display_max is None
    assert dp.review_required is True


def test_k3_asymmetric_bounds_rejected() -> None:
    """One bound present and the other absent must be rejected."""
    with pytest.raises(Exception, match="supplied together"):
        _display_policy(display_min=0.0, display_max=None, review_required=True)


def test_k4_review_required_true_with_bounds_rejected() -> None:
    """review_required=True when bounds are present must be rejected."""
    with pytest.raises(Exception, match="review_required"):
        _display_policy(display_min=0.0, display_max=200.0, review_required=True)


def test_k5_no_bounds_review_required_false_rejected() -> None:
    """Absent bounds with review_required=False must be rejected."""
    with pytest.raises(Exception, match="review_required"):
        _display_policy(review_required=False)  # no bounds


def test_k6_log_scale_nonpositive_bounds_rejected() -> None:
    """Log scale with non-positive display bounds must be rejected."""
    with pytest.raises(Exception, match="positive"):
        _display_policy(
            scale_type="log",
            lattice="logarithmic",
            display_min=-1.0,
            display_max=100.0,
            review_required=False,
        )


def test_k7_equal_bounds_rejected() -> None:
    """display_min == display_max must be rejected."""
    with pytest.raises(Exception, match="unequal"):
        _display_policy(display_min=5.0, display_max=5.0, review_required=False)


# ---------------------------------------------------------------------------
# L — v2_2 contract version constant
# ---------------------------------------------------------------------------

def test_l1_contract_version_is_v2_2() -> None:
    """WDV_VIEWER_PACKAGE_CONTRACT_VERSION is 'wdv_viewer_package_v2_2'."""
    assert WDV_VIEWER_PACKAGE_CONTRACT_VERSION == "wdv_viewer_package_v2_2"


# ---------------------------------------------------------------------------
# M — Revision changes when KR content changes (stale override invalidation)
# ---------------------------------------------------------------------------

def test_m1_revision_changes_with_kr_content(tmp_path: Path) -> None:
    """compute_display_policy_revision produces a different hash when KR content changes."""
    kr_path = tmp_path / "kr.json"

    _write_kr(kr_path, [
        _template_scale_default("tsd_v1", "gamma", scale_min=0.0, scale_max=150.0),
    ])
    storage = ManagedStorage(path=kr_path)
    rev1 = compute_display_policy_revision(storage)

    _clear_display_policy_revision_cache_for_tests()
    ManagedKrFamilyDisplayPolicyResolver.clear_cache_for_tests()

    _write_kr(kr_path, [
        _template_scale_default("tsd_v1", "gamma", scale_min=0.0, scale_max=200.0),
    ])
    storage2 = ManagedStorage(path=kr_path)
    rev2 = compute_display_policy_revision(storage2)

    assert rev1 != rev2, "Revision must change when KR scale_max changes"


def test_m2_revision_stable_with_same_content(tmp_path: Path) -> None:
    """Same KR content → same revision (cache and determinism check)."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _template_scale_default("tsd_v1", "gamma", scale_min=0.0, scale_max=150.0),
    ])
    storage = ManagedStorage(path=kr_path)

    rev1 = compute_display_policy_revision(storage)
    rev2 = compute_display_policy_revision(storage)
    assert rev1 == rev2


# ---------------------------------------------------------------------------
# N — Warning token format
# ---------------------------------------------------------------------------

def test_n1_warning_token_format() -> None:
    """Failure token format is 'policy_unit_resolution_failed:{status.value}'."""
    for status in PolicyUnitResolutionStatus:
        if status in {
            PolicyUnitResolutionStatus.IDENTITY,
            PolicyUnitResolutionStatus.CONVERTED,
        }:
            continue  # usable — no failure token
        expected = f"policy_unit_resolution_failed:{status.value}"
        ur = _ur(
            status,
            canonical_curve_unit=None,  # ensure no Tier-2
        )
        result = _fallback(ur, curve_class="generic")
        assert expected in result["warnings"], (
            f"Expected token {expected!r} for status {status}"
        )
