"""C2 focused tests — PolicyValueUnitMigrationService (Defect A pre-step).

10 scenarios using temporary storage only.  The live managed_knowledge.json
is never read or written by these tests.

  1.  dry_run does not modify the file on disk.
  2.  dry_run result reports changed_count=1, dry_run=True, correct structure.
  3.  apply sets policy_value_unit='%' on the neutron record.
  4.  apply is idempotent: second run yields unchanged_count=1, changed_count=0.
  5.  record not found → not_found_count=1, changed_count=0, no error raised.
  6.  non-APPROVED record raises PolicyUnitMigrationError.
  7.  apply increments the record's version number.
  8.  apply appends a governance_history entry with the correct action token.
  9.  changes persist on disk: reloading after apply shows policy_value_unit='%'.
 10.  change report carries correct before/after values.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.knowledge.managed_storage import ManagedStorage
from app.knowledge.policy_value_unit_migration import (
    PolicyUnitMigrationError,
    PolicyUnitMigrationResult,
    PolicyValueUnitMigrationService,
)

# The record_id the migration targets — must match _POLICY_UNIT_MIGRATIONS entry.
_NEUTRON_RECORD_ID = "wlv_approved_kr_refs_1_scale_default_neutron_porosity"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_kr(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps({"version": "1", "records": records}, indent=2),
        encoding="utf-8",
    )


def _neutron_record(
    *,
    policy_value_unit: str | None = None,
    status: str = "approved",
    version: int = 1,
) -> dict[str, Any]:
    """Minimal approved template_scale_default for the neutron porosity family."""
    record: dict[str, Any] = {
        "record_id": _NEUTRON_RECORD_ID,
        "record_type": "template_scale_default",
        "status": status,
        "runtime_eligible": True,
        "version": version,
        "curve_family": "neutron_porosity",
        "scale_type": "linear",
        "scale_min": 45.0,
        "scale_max": -15.0,
        "display_direction": "reversed",
        "governance_history": [],
    }
    if policy_value_unit is not None:
        record["policy_value_unit"] = policy_value_unit
    return record


def _service(kr_path: Path) -> PolicyValueUnitMigrationService:
    return PolicyValueUnitMigrationService(storage=ManagedStorage(path=kr_path))


# ---------------------------------------------------------------------------
# Test 1 — dry_run does not modify the file
# ---------------------------------------------------------------------------


def test_dry_run_does_not_write_file(tmp_path: Path) -> None:
    """dry_run=True must leave the KR file byte-for-byte unchanged."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [_neutron_record()])
    original_bytes = kr_path.read_bytes()

    _service(kr_path).run(dry_run=True)

    assert kr_path.read_bytes() == original_bytes, (
        "dry_run must not modify the KR file on disk"
    )


# ---------------------------------------------------------------------------
# Test 2 — dry_run result structure
# ---------------------------------------------------------------------------


def test_dry_run_result_structure(tmp_path: Path) -> None:
    """dry_run=True must return a PolicyUnitMigrationResult with the expected shape."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [_neutron_record()])

    result = _service(kr_path).run(dry_run=True)

    assert isinstance(result, PolicyUnitMigrationResult)
    assert result.dry_run is True
    assert result.changed_count == 1
    assert result.unchanged_count == 0
    assert result.not_found_count == 0
    assert len(result.changes) == 1


# ---------------------------------------------------------------------------
# Test 3 — apply sets policy_value_unit
# ---------------------------------------------------------------------------


def test_apply_sets_policy_value_unit(tmp_path: Path) -> None:
    """dry_run=False must write policy_value_unit='%' to the neutron record."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [_neutron_record()])

    result = _service(kr_path).run(dry_run=False)

    assert result.dry_run is False
    assert result.changed_count == 1
    assert result.unchanged_count == 0

    # Verify the written value by reloading.
    records, _ = ManagedStorage(path=kr_path).load()
    neutron = next(
        (r for r in records if getattr(r, "record_id", None) == _NEUTRON_RECORD_ID),
        None,
    )
    assert neutron is not None
    assert getattr(neutron, "policy_value_unit", None) == "%"


# ---------------------------------------------------------------------------
# Test 4 — apply is idempotent
# ---------------------------------------------------------------------------


def test_apply_is_idempotent(tmp_path: Path) -> None:
    """Running apply twice must leave changed_count=0 on the second call."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [_neutron_record()])

    _service(kr_path).run(dry_run=False)          # first apply
    result2 = _service(kr_path).run(dry_run=False)  # second apply

    assert result2.changed_count == 0
    assert result2.unchanged_count == 1
    assert result2.not_found_count == 0
    assert result2.changes == []


# ---------------------------------------------------------------------------
# Test 5 — record not found
# ---------------------------------------------------------------------------


def test_record_not_found_reports_not_found(tmp_path: Path) -> None:
    """An empty KR (no matching record) must yield not_found_count=1 without error."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [])  # no records at all

    result = _service(kr_path).run(dry_run=False)

    assert result.not_found_count == 1
    assert result.changed_count == 0
    assert result.changes == []


# ---------------------------------------------------------------------------
# Test 6 — non-APPROVED record raises
# ---------------------------------------------------------------------------


def test_non_approved_record_raises(tmp_path: Path) -> None:
    """A non-APPROVED record (status='candidate') must raise PolicyUnitMigrationError."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [_neutron_record(status="candidate")])

    with pytest.raises(PolicyUnitMigrationError, match="APPROVED"):
        _service(kr_path).run(dry_run=False)


# ---------------------------------------------------------------------------
# Test 7 — apply increments record version
# ---------------------------------------------------------------------------


def test_apply_increments_record_version(tmp_path: Path) -> None:
    """After apply, the record's version must be incremented from its prior value."""
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [_neutron_record(version=1)])

    _service(kr_path).run(dry_run=False)

    records, _ = ManagedStorage(path=kr_path).load()
    neutron = next(
        r for r in records if getattr(r, "record_id", None) == _NEUTRON_RECORD_ID
    )
    assert neutron.version == 2, (
        f"Expected version=2 after migration apply but got {neutron.version}"
    )


# ---------------------------------------------------------------------------
# Test 8 — apply appends governance_history entry
# ---------------------------------------------------------------------------


def test_apply_appends_governance_history_entry(tmp_path: Path) -> None:
    """After apply, governance_history must contain a new entry with
    action='add_policy_value_unit' and by='wlv_policy_value_unit_migration'.
    """
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [_neutron_record()])

    _service(kr_path).run(dry_run=False)

    records, _ = ManagedStorage(path=kr_path).load()
    neutron = next(
        r for r in records if getattr(r, "record_id", None) == _NEUTRON_RECORD_ID
    )
    history = neutron.governance_history
    assert len(history) == 1, f"Expected 1 history entry, got {len(history)}"
    entry = history[0]
    assert entry.get("action") == "add_policy_value_unit"
    assert entry.get("by") == "wlv_policy_value_unit_migration"


# ---------------------------------------------------------------------------
# Test 9 — changes persist: reload after apply shows policy_value_unit
# ---------------------------------------------------------------------------


def test_apply_persists_across_storage_reload(tmp_path: Path) -> None:
    """After apply, a fresh ManagedStorage instance must see policy_value_unit='%'.

    This verifies that ManagedStorage.save() wrote the mutation and that the
    migration did not rely on any in-process cache.
    """
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [_neutron_record()])

    # Apply with one service instance.
    PolicyValueUnitMigrationService(
        storage=ManagedStorage(path=kr_path)
    ).run(dry_run=False)

    # Reload with a completely fresh storage instance — no shared state.
    fresh_records, _ = ManagedStorage(path=kr_path).load()
    neutron = next(
        (r for r in fresh_records if getattr(r, "record_id", None) == _NEUTRON_RECORD_ID),
        None,
    )
    assert neutron is not None, "Neutron record missing after reload"
    assert getattr(neutron, "policy_value_unit", None) == "%", (
        "policy_value_unit must be '%' after reload, not "
        f"{getattr(neutron, 'policy_value_unit', '<missing>')!r}"
    )


# ---------------------------------------------------------------------------
# Test 10 — change report before/after values
# ---------------------------------------------------------------------------


def test_change_report_before_after_values(tmp_path: Path) -> None:
    """The change report must record the correct before and after policy_value_unit."""
    kr_path = tmp_path / "kr.json"
    # Start without policy_value_unit so before should show None.
    _write_kr(kr_path, [_neutron_record(policy_value_unit=None)])

    result = _service(kr_path).run(dry_run=True)

    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.record_id == _NEUTRON_RECORD_ID
    assert change.before == {"policy_value_unit": None}
    assert change.after == {"policy_value_unit": "%"}
    assert change.curve_family == "neutron_porosity"
