"""C2 tests — display-policy precedence and AT30/AO90 guarantee.

Precedence under test:
  1. Approved exact KR display_rule (managed_knowledge_curve_rule)
  2. Approved KR family default (managed_knowledge_family_default)
  3. Controlled internal fallback (internal_fallback)

User WDV overrides are tested in test_wdv_canonical_curve_scale_override.py.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from app.inventory.models import ManagedProductGroupItem
from app.wdv_display.kr_family_policy_resolver import (
    ManagedKrFamilyDisplayPolicyResolver,
)
from app.wdv_display.policy_service import (
    WdvCurveDisplayPolicyService,
    _clear_display_policy_revision_cache_for_tests,
    compute_display_policy_revision,
)
from app.knowledge.managed_storage import ManagedStorage


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_caches():
    """Isolate every test from process-level caches."""
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
    scale_type: str = "log",
    display_min: float = 0.2,
    display_max: float = 2000.0,
    reverse_scale: bool = False,
) -> dict[str, Any]:
    return _approved({
        "record_id": record_id,
        "record_type": "display_rule",
        "canonical_curve_id": canonical_curve_id,
        "preferred_track_family": "resistivity",
        "scale_type": scale_type,
        "display_min": display_min,
        "display_max": display_max,
        "reverse_scale": reverse_scale,
    })


def _template_scale_default(
    record_id: str,
    curve_family: str,
    scale_type: str = "linear",
    scale_min: float = 0.0,
    scale_max: float = 150.0,
) -> dict[str, Any]:
    return _approved({
        "record_id": record_id,
        "record_type": "template_scale_default",
        "curve_family": curve_family,
        "scale_type": scale_type,
        "scale_min": scale_min,
        "scale_max": scale_max,
        "display_direction": "normal",
    })


def _alias(record_id: str, alias: str, canonical_curve_id: str) -> dict[str, Any]:
    return _approved({
        "record_id": record_id,
        "record_type": "alias",
        "alias": alias,
        "normalized_alias": alias.upper(),
        "canonical_curve_id": canonical_curve_id,
    })


def _curve_definition(
    record_id: str,
    canonical_curve_id: str,
    family: str,
) -> dict[str, Any]:
    return _approved({
        "record_id": record_id,
        "record_type": "curve_definition",
        "canonical_curve_id": canonical_curve_id,
        "display_name": canonical_curve_id,
        "family": family,
        "product_group": "open_hole_logs",
    })


def _item(
    curve_name: str = "GR",
    curve_family: str = "gamma_ray",
    curve_type: str = "curve",
    curve_unit: str = "API",
    kr_curve_type_id: str | None = None,
) -> ManagedProductGroupItem:
    return ManagedProductGroupItem(
        product_id=curve_name,
        display_name=curve_name,
        curve_name=curve_name,
        curve_type=curve_type,
        curve_unit=curve_unit,
        curve_family=curve_family,
        kr_curve_type_id=kr_curve_type_id,
    )


# ---------------------------------------------------------------------------
# Test 1 — exact approved curve rule wins over family default
# ---------------------------------------------------------------------------

def test_exact_curve_rule_wins_over_family_default(tmp_path: Path) -> None:
    """An approved display_rule for the exact curve beats the family default."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        # Exact rule: spectral_gamma_ray → linear 0–300
        _display_rule("dr_sgr", "spectral_gamma_ray", "linear", 0.0, 300.0),
        # Family default: gamma_ray → linear 0–150
        _template_scale_default("tsd_gr", "gamma_ray", "linear", 0.0, 150.0),
        # Alias: SGR → spectral_gamma_ray
        _alias("al_sgr", "SGR", "spectral_gamma_ray"),
        # Curve definition: spectral_gamma_ray → family gamma_ray
        _curve_definition("cd_sgr", "spectral_gamma_ray", "gamma_ray"),
    ])
    storage = ManagedStorage(path=kr_path)
    item = _item(curve_name="SGR", curve_family="gamma_ray")

    result = ManagedKrFamilyDisplayPolicyResolver.resolve(item, storage=storage)

    assert result is not None
    assert result["source"] == "managed_knowledge_curve_rule"
    assert result["type"] == "linear"
    assert result["min"] == pytest.approx(0.0)
    assert result["max"] == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# Test 2 — no exact rule falls back to family default
# ---------------------------------------------------------------------------

def test_no_exact_rule_falls_back_to_family_default(tmp_path: Path) -> None:
    """When no display_rule matches, the family default is used."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        # Family default only — no display_rule for gamma_ray canonical ID
        _template_scale_default("tsd_gr", "gamma_ray", "linear", 0.0, 150.0),
    ])
    storage = ManagedStorage(path=kr_path)
    item = _item(curve_name="GR", curve_family="gamma_ray")

    result = ManagedKrFamilyDisplayPolicyResolver.resolve(item, storage=storage)

    assert result is not None
    assert result["source"] == "managed_knowledge_family_default"
    assert result["type"] == "linear"
    assert result["min"] == pytest.approx(0.0)
    assert result["max"] == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# Test 3 — no exact or family rule falls back to internal fallback
# ---------------------------------------------------------------------------

def test_no_kr_policy_uses_internal_fallback(tmp_path: Path) -> None:
    """When KR has no matching rule or family default, WdvCurveDisplayPolicyService
    returns an internal_fallback result — not None.

    Two assertions:
    1. The resolver returns None when given an explicit empty KR (storage= injection).
    2. WdvCurveDisplayPolicyService falls back to internal_fallback when the
       curve family is absent from the real managed KR.  WdvCurveDisplayPolicyService
       has no storage-injection path; we test the boundary via an invented
       curve name/family that cannot match any real KR record or any keyword
       heuristic, so the service hits the generic terminal fallback.
    """
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [])
    storage = ManagedStorage(path=kr_path)
    # Invented curve: name and family contain no heuristic keywords
    # ("gamma", "resist", "density", "neutron", "sonic", etc.) and will
    # not match any real KR family default.
    item = _item(
        curve_name="XYZ_INVENTED_NOHIT",
        curve_family="xyz_invented_family_not_in_kr",
    )

    # Resolver returns None for the empty test KR
    kr_result = ManagedKrFamilyDisplayPolicyResolver.resolve(item, storage=storage)
    assert kr_result is None

    # Real KR also has no coverage for this invented family → resolver returns
    # None → policy service hits the generic terminal internal_fallback.
    policy = WdvCurveDisplayPolicyService.resolve(item, {})
    assert policy["source"] == "internal_fallback"
    assert policy["min"] is not None
    assert policy["max"] is not None


# ---------------------------------------------------------------------------
# Test 4 — exact-rule provenance fields are correct
# ---------------------------------------------------------------------------

def test_exact_curve_rule_provenance(tmp_path: Path) -> None:
    """Exact rule result carries correct provenance fields."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [
        _display_rule("dr_deep_ind", "deep_induction_resistivity", "log", 0.2, 2000.0),
        _alias("al_ild", "ILD", "deep_induction_resistivity"),
        _curve_definition("cd_ild", "deep_induction_resistivity", "resistivity"),
    ])
    storage = ManagedStorage(path=kr_path)
    item = _item(curve_name="ILD", curve_family="resistivity")

    result = ManagedKrFamilyDisplayPolicyResolver.resolve(item, storage=storage)

    assert result is not None
    assert result["source"] == "managed_knowledge_curve_rule"
    assert result["policy_record_id"] == "dr_deep_ind"
    assert result["canonical_curve_id"] == "deep_induction_resistivity"
    assert result["type"] == "log"
    assert result["min"] == pytest.approx(0.2)
    assert result["max"] == pytest.approx(2000.0)
    assert result["direction"] == "normal"
    assert isinstance(result["warnings"], list)


# ---------------------------------------------------------------------------
# Test 10 — AT30 and AO90 remain 0.2–2000 logarithmic
# ---------------------------------------------------------------------------

def test_at30_and_ao90_resolve_to_resistivity_family_default() -> None:
    """AT30 and AO90 have no exact display_rule (their PWLS canonical IDs
    are not in the curated runtime_eligible=True set).  Both must fall through
    to the resistivity family default and resolve to 0.2–2000 logarithmic."""
    # Use the real managed KR
    at30 = ManagedProductGroupItem(
        product_id="AT30",
        display_name="AT30",
        curve_name="AT30",
        curve_type="curve",
        curve_unit="OHMM",
        curve_family="resistivity",
    )
    ao90 = ManagedProductGroupItem(
        product_id="AO90",
        display_name="AO90",
        curve_name="AO90",
        curve_type="curve",
        curve_unit="OHMM",
        curve_family="resistivity",
    )

    for item in (at30, ao90):
        result = ManagedKrFamilyDisplayPolicyResolver.resolve(item)
        assert result is not None, f"{item.curve_name} resolved to None"
        assert result["source"] == "managed_knowledge_family_default", (
            f"{item.curve_name}: expected family_default, got {result['source']!r}"
        )
        assert result["type"] == "log", (
            f"{item.curve_name}: expected log, got {result['type']!r}"
        )
        assert result["min"] == pytest.approx(0.2), (
            f"{item.curve_name}: expected min=0.2, got {result['min']}"
        )
        assert result["max"] == pytest.approx(2000.0), (
            f"{item.curve_name}: expected max=2000, got {result['max']}"
        )
