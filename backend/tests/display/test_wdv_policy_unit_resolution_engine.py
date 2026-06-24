"""UNIT-3C tests — dormant policy-unit conversion engine.

Tests the new ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution()
classmethod introduced in UNIT-3C.  This method is dormant: it is never called
from the active resolve() path and has no observable runtime effect.

Coverage:
  D1  — exact identity (same canonical unit token)
  D2  — exact conversion (compatible units, different tokens)
  D3  — exact: missing policy_value_unit (None on record)
  D4  — exact: unknown policy_value_unit (unrecognized string)
  D5  — exact: missing curve_unit (item.curve_unit is None)
  D6  — exact: unknown curve_unit (unrecognized string)
  D7  — exact: incompatible units (different physical dimensions)
  D8  — exact-policy terminal when family also exists
  D9  — family fallback only when no exact rule exists
  D10 — no exact and no family → policy=None, unit_resolution=None
  D11 — policy_revision argument propagated into typed result
  D12 — policy record ID and version provenance from exact rule
  D13 — policy record ID and version provenance from family record
  D14 — runtime resolve() behavior unchanged after UNIT-3C
  D15 — WdvCurveDisplayPolicyService.resolve() never calls dormant method
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.inventory.models import ManagedProductGroupItem
from app.knowledge.managed_storage import ManagedStorage
from app.wdv_display.kr_family_policy_resolver import ManagedKrFamilyDisplayPolicyResolver
from app.wdv_display.policy_service import (
    WdvCurveDisplayPolicyService,
    _clear_display_policy_revision_cache_for_tests,
)
from app.wdv_display.policy_unit_resolution import PolicyUnitResolutionStatus


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


def _write_kr(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps({"version": "1", "records": records}, indent=2),
        encoding="utf-8",
    )


def _approved(extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "approved",
        "runtime_eligible": True,
        "version": 1,
        **extra,
    }


def _display_rule(
    record_id: str,
    canonical_curve_id: str,
    *,
    preferred_track_family: str = "resistivity",
    scale_type: str = "log",
    display_min: float = 0.2,
    display_max: float = 2000.0,
    reverse_scale: bool = False,
    policy_value_unit: str | None = None,
    version: int = 1,
) -> dict[str, Any]:
    rec: dict[str, Any] = _approved({
        "record_id": record_id,
        "record_type": "display_rule",
        "canonical_curve_id": canonical_curve_id,
        "preferred_track_family": preferred_track_family,
        "scale_type": scale_type,
        "display_min": display_min,
        "display_max": display_max,
        "reverse_scale": reverse_scale,
    })
    rec["version"] = version
    if policy_value_unit is not None:
        rec["policy_value_unit"] = policy_value_unit
    # Omitting policy_value_unit key altogether mirrors a record with no unit
    # field (equivalent to None on DisplayRuleRecord).
    return rec


def _template_scale_default(
    record_id: str,
    curve_family: str,
    *,
    scale_type: str = "linear",
    scale_min: float = 0.0,
    scale_max: float = 150.0,
    policy_value_unit: str | None = None,
    version: int = 1,
) -> dict[str, Any]:
    rec: dict[str, Any] = _approved({
        "record_id": record_id,
        "record_type": "template_scale_default",
        "curve_family": curve_family,
        "scale_type": scale_type,
        "scale_min": scale_min,
        "scale_max": scale_max,
        "display_direction": "normal",
    })
    rec["version"] = version
    if policy_value_unit is not None:
        rec["policy_value_unit"] = policy_value_unit
    return rec


def _alias(record_id: str, alias: str, canonical_curve_id: str) -> dict[str, Any]:
    return _approved({
        "record_id": record_id,
        "record_type": "alias",
        "alias": alias,
        "canonical_curve_id": canonical_curve_id,
    })


def _curve_definition(
    record_id: str,
    canonical_curve_id: str,
    family: str,
    *,
    product_group: str = "open_hole_logs",
) -> dict[str, Any]:
    return _approved({
        "record_id": record_id,
        "record_type": "curve_definition",
        "canonical_curve_id": canonical_curve_id,
        "display_name": canonical_curve_id,
        "family": family,
        "product_group": product_group,
    })


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


# ---------------------------------------------------------------------------
# D1 — Exact identity: same canonical unit token
# ---------------------------------------------------------------------------

def test_d1_exact_identity(tmp_path: Path) -> None:
    """Exact rule with policy_value_unit == curve_unit → IDENTITY, bounds usable."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _display_rule(
            "dr_res", "resistivity_at90",
            scale_type="log", display_min=0.2, display_max=2000.0,
            policy_value_unit="ohmm",
        ),
    ])
    storage = ManagedStorage(path=kr_path)
    item = _item(curve_unit="ohmm")

    result = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(
        item, storage=storage, policy_revision="rev-abc"
    )

    assert result.policy is not None
    assert result.policy["source"] == "managed_knowledge_curve_rule"
    assert result.unit_resolution is not None
    ur = result.unit_resolution
    assert ur.status is PolicyUnitResolutionStatus.IDENTITY
    assert ur.resolved_bounds_usable is True
    assert ur.conversion_applied is False
    assert ur.resolved_min == pytest.approx(0.2)
    assert ur.resolved_max == pytest.approx(2000.0)
    assert ur.canonical_policy_unit == "ohmm"
    assert ur.canonical_curve_unit == "ohmm"
    assert ur.unresolved_reason is None


# ---------------------------------------------------------------------------
# D2 — Exact conversion: compatible units, different tokens
# ---------------------------------------------------------------------------

def test_d2_exact_conversion(tmp_path: Path) -> None:
    """policy_value_unit=g/cc, curve_unit=kg/m3 → CONVERTED, bounds scaled."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _display_rule(
            "dr_den", "bulk_density",
            scale_type="linear", display_min=2.1, display_max=2.8,
            policy_value_unit="g/cc",
        ),
    ])
    storage = ManagedStorage(path=kr_path)
    item = _item(
        curve_name="RHOB", curve_family="density",
        kr_curve_type_id="bulk_density", curve_unit="kg/m3",
    )

    result = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(
        item, storage=storage
    )

    assert result.unit_resolution is not None
    ur = result.unit_resolution
    assert ur.status is PolicyUnitResolutionStatus.CONVERTED
    assert ur.resolved_bounds_usable is True
    assert ur.conversion_applied is True
    # g/cc × 1000 → kg/m3
    assert ur.resolved_min == pytest.approx(2100.0)
    assert ur.resolved_max == pytest.approx(2800.0)
    assert ur.canonical_policy_unit == "g/cc"
    assert ur.canonical_curve_unit == "kg/m3"
    assert ur.original_policy_min == pytest.approx(2.1)
    assert ur.original_policy_max == pytest.approx(2.8)


# ---------------------------------------------------------------------------
# D3 — Exact: missing policy_value_unit (field absent from record)
# ---------------------------------------------------------------------------

def test_d3_exact_missing_policy_unit(tmp_path: Path) -> None:
    """Exact rule with no policy_value_unit field → MISSING_POLICY_UNIT."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        # No policy_value_unit key in the record.
        _display_rule("dr_res", "resistivity_at90", policy_value_unit=None),
    ])
    storage = ManagedStorage(path=kr_path)
    # Omit policy_value_unit from the _display_rule fixture by not passing it —
    # the record dict has no "policy_value_unit" key, which means
    # DisplayRuleRecord.policy_value_unit defaults to None.
    item = _item(curve_unit="ohmm")

    result = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(
        item, storage=storage
    )

    assert result.unit_resolution is not None
    ur = result.unit_resolution
    assert ur.status is PolicyUnitResolutionStatus.MISSING_POLICY_UNIT
    assert ur.resolved_bounds_usable is False
    assert ur.resolved_min is None
    assert ur.resolved_max is None
    assert ur.policy_source == "exact"


# ---------------------------------------------------------------------------
# D4 — Exact: unknown policy_value_unit (unrecognized string)
# ---------------------------------------------------------------------------

def test_d4_exact_unknown_policy_unit(tmp_path: Path) -> None:
    """Exact rule with policy_value_unit='gobbledygook' → UNKNOWN_POLICY_UNIT."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _display_rule(
            "dr_res", "resistivity_at90",
            policy_value_unit="gobbledygook",
        ),
    ])
    storage = ManagedStorage(path=kr_path)
    item = _item(curve_unit="ohmm")

    result = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(
        item, storage=storage
    )

    ur = result.unit_resolution
    assert ur is not None
    assert ur.status is PolicyUnitResolutionStatus.UNKNOWN_POLICY_UNIT
    assert ur.resolved_bounds_usable is False
    assert ur.canonical_policy_unit is None
    assert ur.policy_source == "exact"


# ---------------------------------------------------------------------------
# D5 — Exact: missing curve_unit (item.curve_unit is None)
# ---------------------------------------------------------------------------

def test_d5_exact_missing_curve_unit(tmp_path: Path) -> None:
    """item.curve_unit is None → MISSING_CURVE_UNIT."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _display_rule(
            "dr_res", "resistivity_at90",
            policy_value_unit="ohmm",
        ),
    ])
    storage = ManagedStorage(path=kr_path)
    item = _item(curve_unit=None)

    result = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(
        item, storage=storage
    )

    ur = result.unit_resolution
    assert ur is not None
    assert ur.status is PolicyUnitResolutionStatus.MISSING_CURVE_UNIT
    assert ur.resolved_bounds_usable is False
    assert ur.canonical_curve_unit is None
    assert ur.policy_source == "exact"


# ---------------------------------------------------------------------------
# D6 — Exact: unknown curve_unit (unrecognized string)
# ---------------------------------------------------------------------------

def test_d6_exact_unknown_curve_unit(tmp_path: Path) -> None:
    """item.curve_unit is an unrecognized string → UNKNOWN_CURVE_UNIT."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _display_rule(
            "dr_res", "resistivity_at90",
            policy_value_unit="ohmm",
        ),
    ])
    storage = ManagedStorage(path=kr_path)
    item = _item(curve_unit="notathing")

    result = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(
        item, storage=storage
    )

    ur = result.unit_resolution
    assert ur is not None
    assert ur.status is PolicyUnitResolutionStatus.UNKNOWN_CURVE_UNIT
    assert ur.resolved_bounds_usable is False
    assert ur.canonical_curve_unit is None
    assert ur.policy_source == "exact"


# ---------------------------------------------------------------------------
# D7 — Exact: incompatible units (different physical dimensions)
# ---------------------------------------------------------------------------

def test_d7_exact_incompatible_units(tmp_path: Path) -> None:
    """policy_value_unit=ohmm, curve_unit=gapi → INCOMPATIBLE."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _display_rule(
            "dr_res", "resistivity_at90",
            scale_type="log", display_min=0.2, display_max=2000.0,
            policy_value_unit="ohmm",
        ),
    ])
    storage = ManagedStorage(path=kr_path)
    item = _item(curve_unit="gapi")

    result = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(
        item, storage=storage
    )

    ur = result.unit_resolution
    assert ur is not None
    assert ur.status is PolicyUnitResolutionStatus.INCOMPATIBLE
    assert ur.resolved_bounds_usable is False
    assert ur.canonical_policy_unit == "ohmm"
    assert ur.canonical_curve_unit == "gapi"
    assert ur.policy_source == "exact"


# ---------------------------------------------------------------------------
# D8 — Exact-policy terminal: family present but must not be used
# ---------------------------------------------------------------------------

def test_d8_exact_terminal_family_not_used(tmp_path: Path) -> None:
    """Exact rule matches (even with unit failure) → family is never consulted.

    The unit_resolution.policy_source must be 'exact', not 'family'.
    """
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        # Exact rule — no policy_value_unit → MISSING_POLICY_UNIT.
        _display_rule("dr_res", "resistivity_at90", policy_value_unit=None),
        # Family default — would give a usable result if consulted.
        _template_scale_default(
            "tsd_res", "resistivity",
            scale_type="log", scale_min=0.2, scale_max=2000.0,
            policy_value_unit="ohmm",
        ),
        _curve_definition("cd_res", "resistivity_at90", "resistivity"),
    ])
    storage = ManagedStorage(path=kr_path)
    item = _item(curve_unit="ohmm")

    result = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(
        item, storage=storage
    )

    ur = result.unit_resolution
    assert ur is not None
    assert ur.policy_source == "exact"
    assert ur.status is PolicyUnitResolutionStatus.MISSING_POLICY_UNIT
    assert ur.resolved_bounds_usable is False


# ---------------------------------------------------------------------------
# D9 — Family fallback: no exact rule exists
# ---------------------------------------------------------------------------

def test_d9_family_fallback_when_no_exact_rule(tmp_path: Path) -> None:
    """No display_rule exists → family record used, policy_source='family'."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _template_scale_default(
            "tsd_gr", "gamma_ray",
            scale_type="linear", scale_min=0.0, scale_max=150.0,
            policy_value_unit="gapi",
        ),
    ])
    storage = ManagedStorage(path=kr_path)
    item = ManagedProductGroupItem(
        product_id="GR",
        display_name="GR",
        curve_name="GR",
        curve_type="curve",
        curve_unit="gapi",
        curve_family="gamma_ray",
        kr_curve_type_id=None,
    )

    result = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(
        item, storage=storage
    )

    assert result.policy is not None
    assert result.policy["source"] == "managed_knowledge_family_default"
    ur = result.unit_resolution
    assert ur is not None
    assert ur.policy_source == "family"
    assert ur.status is PolicyUnitResolutionStatus.IDENTITY
    assert ur.resolved_bounds_usable is True
    assert ur.resolved_min == pytest.approx(0.0)
    assert ur.resolved_max == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# D10 — No exact and no family → policy=None, unit_resolution=None
# ---------------------------------------------------------------------------

def test_d10_no_exact_no_family(tmp_path: Path) -> None:
    """KR has no matching rule or family → ResolvedDisplayPolicy(None, None)."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [])  # empty KR
    storage = ManagedStorage(path=kr_path)
    item = _item()

    result = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(
        item, storage=storage
    )

    assert result.policy is None
    assert result.unit_resolution is None


# ---------------------------------------------------------------------------
# D11 — policy_revision propagated into typed result
# ---------------------------------------------------------------------------

def test_d11_policy_revision_propagated(tmp_path: Path) -> None:
    """The policy_revision kwarg appears verbatim in PolicyUnitResolutionResult."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _display_rule(
            "dr_res", "resistivity_at90",
            policy_value_unit="ohmm",
        ),
    ])
    storage = ManagedStorage(path=kr_path)
    item = _item(curve_unit="ohmm")
    revision = "sha256:deadbeef"

    result = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(
        item, storage=storage, policy_revision=revision
    )

    ur = result.unit_resolution
    assert ur is not None
    assert ur.policy_revision == revision


# ---------------------------------------------------------------------------
# D12 — Provenance: exact rule record_id and version in typed result
# ---------------------------------------------------------------------------

def test_d12_exact_rule_provenance(tmp_path: Path) -> None:
    """PolicyUnitResolutionResult carries the exact display_rule's record fields."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _display_rule(
            "dr_at90_v7", "resistivity_at90",
            policy_value_unit="ohmm",
            version=7,
        ),
    ])
    storage = ManagedStorage(path=kr_path)
    item = _item(curve_unit="ohmm")

    result = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(
        item, storage=storage
    )

    ur = result.unit_resolution
    assert ur is not None
    assert ur.policy_record_id == "dr_at90_v7"
    assert ur.policy_record_version == 7
    assert ur.policy_source == "exact"


# ---------------------------------------------------------------------------
# D13 — Provenance: family record_id and version in typed result
# ---------------------------------------------------------------------------

def test_d13_family_provenance(tmp_path: Path) -> None:
    """PolicyUnitResolutionResult carries the family record's fields when family path used."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _template_scale_default(
            "tsd_gr_v3", "gamma_ray",
            policy_value_unit="gapi",
            version=3,
        ),
    ])
    storage = ManagedStorage(path=kr_path)
    item = ManagedProductGroupItem(
        product_id="GR",
        display_name="GR",
        curve_name="GR",
        curve_type="curve",
        curve_unit="gapi",
        curve_family="gamma_ray",
        kr_curve_type_id=None,
    )

    result = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(
        item, storage=storage
    )

    ur = result.unit_resolution
    assert ur is not None
    assert ur.policy_record_id == "tsd_gr_v3"
    assert ur.policy_record_version == 3
    assert ur.policy_source == "family"


# ---------------------------------------------------------------------------
# D14 — Runtime resolve() is unchanged after UNIT-3C
# ---------------------------------------------------------------------------

def test_d14_runtime_resolve_unchanged(tmp_path: Path) -> None:
    """resolve() returns the same result before and after UNIT-3C additions.

    This test exercises the existing dict-returning path with both exact-rule
    and family-fallback scenarios to confirm no regression.
    """
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _display_rule(
            "dr_res", "resistivity_at90",
            scale_type="log", display_min=0.2, display_max=2000.0,
            policy_value_unit="ohmm",  # new field in KR — must not affect dict shape
        ),
        _template_scale_default(
            "tsd_gr", "gamma_ray",
            scale_type="linear", scale_min=0.0, scale_max=150.0,
            policy_value_unit="gapi",  # new field — must not affect dict shape
        ),
    ])
    storage = ManagedStorage(path=kr_path)

    # Exact match.
    exact_item = _item(curve_unit="ohmm")
    exact_result = ManagedKrFamilyDisplayPolicyResolver.resolve(
        exact_item, storage=storage
    )
    assert exact_result is not None
    assert exact_result["source"] == "managed_knowledge_curve_rule"
    assert exact_result["type"] == "log"
    assert exact_result["min"] == pytest.approx(0.2)
    assert exact_result["max"] == pytest.approx(2000.0)
    assert "unit_resolution" not in exact_result
    assert "policy_value_unit" not in exact_result

    # Family fallback.
    family_item = ManagedProductGroupItem(
        product_id="GR",
        display_name="GR",
        curve_name="GR",
        curve_type="curve",
        curve_unit="gapi",
        curve_family="gamma_ray",
        kr_curve_type_id=None,
    )
    family_result = ManagedKrFamilyDisplayPolicyResolver.resolve(
        family_item, storage=storage
    )
    assert family_result is not None
    assert family_result["source"] == "managed_knowledge_family_default"
    assert family_result["type"] == "linear"
    assert family_result["min"] == pytest.approx(0.0)
    assert family_result["max"] == pytest.approx(150.0)
    assert "unit_resolution" not in family_result
    assert "policy_value_unit" not in family_result


# ---------------------------------------------------------------------------
# D15 — WdvCurveDisplayPolicyService.resolve() never calls the dormant method
# ---------------------------------------------------------------------------

def test_d15_policy_service_does_not_call_dormant_method(tmp_path: Path) -> None:
    """WdvCurveDisplayPolicyService.resolve() must not invoke resolve_with_unit_resolution."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _display_rule(
            "dr_res", "resistivity_at90",
            scale_type="log", display_min=0.2, display_max=2000.0,
            policy_value_unit="ohmm",
        ),
    ])
    storage = ManagedStorage(path=kr_path)
    item = _item(curve_unit="ohmm")

    target = (
        "app.wdv_display.kr_family_policy_resolver"
        ".ManagedKrFamilyDisplayPolicyResolver"
        ".resolve_with_unit_resolution"
    )
    with patch(target) as mock_dormant:
        result = WdvCurveDisplayPolicyService.resolve(item, {})

    mock_dormant.assert_not_called()
    # Active path still returns a usable dict.
    assert result is not None
    assert "type" in result
    assert "min" in result
    assert "max" in result
