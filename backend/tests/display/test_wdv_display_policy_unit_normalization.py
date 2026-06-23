"""UNIT-1 foundation/deactivation integration tests.

The policy-unit service exists and is independently tested, but governed family
policy enforcement remains dormant until UNIT-2 migration and UNIT-3 activation.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.inventory.models import ManagedProductGroupItem
from app.knowledge.managed_storage import ManagedStorage
from app.wdv_display.kr_family_policy_resolver import ManagedKrFamilyDisplayPolicyResolver


def _write_kr(path: Path, records: list[dict]) -> Path:
    path.write_text(json.dumps({"records": records, "evidence": []}))
    return path


def _family_record(*, policy_value_unit: str | None = None) -> dict:
    record = {
        "record_id": "tsd_gamma",
        "record_type": "template_scale_default",
        "version": 1,
        "status": "approved",
        "runtime_eligible": True,
        "curve_family": "gamma_ray",
        "scale_type": "linear",
        "scale_min": 0.0,
        "scale_max": 150.0,
        "display_direction": "normal",
        "governance_history": [],
    }
    if policy_value_unit is not None:
        record["policy_value_unit"] = policy_value_unit
    return record


def _item(unit: str = "gapi") -> ManagedProductGroupItem:
    return ManagedProductGroupItem(
        product_id="GR",
        display_name="Gamma Ray",
        curve_name="GR",
        curve_type="curve",
        curve_unit=unit,
        curve_family="gamma_ray",
        selectable=True,
    )


def test_family_policy_remains_available_before_unit_migration(tmp_path: Path) -> None:
    storage = ManagedStorage(path=_write_kr(tmp_path / "kr.json", [_family_record()]))
    result = ManagedKrFamilyDisplayPolicyResolver.resolve(_item(), storage=storage)
    assert result is not None
    assert result["source"] == "managed_knowledge_family_default"
    assert result["min"] == 0.0
    assert result["max"] == 150.0


def test_policy_value_unit_is_not_enforced_during_foundation_block(tmp_path: Path) -> None:
    storage = ManagedStorage(
        path=_write_kr(tmp_path / "kr.json", [_family_record(policy_value_unit="gapi")])
    )
    result = ManagedKrFamilyDisplayPolicyResolver.resolve(_item("API"), storage=storage)
    assert result is not None
    assert result["max"] == 150.0


def test_missing_family_policy_retains_none_contract(tmp_path: Path) -> None:
    storage = ManagedStorage(path=_write_kr(tmp_path / "kr.json", []))
    result = ManagedKrFamilyDisplayPolicyResolver.resolve(_item(), storage=storage)
    assert result is None
