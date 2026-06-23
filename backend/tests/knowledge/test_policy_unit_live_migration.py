from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.knowledge.policy_unit_live_migration import (
    EXPECTED_POST_COUNTS,
    PolicyUnitLiveMigrationError,
    PolicyUnitLiveMigrationService,
)
from app.knowledge.policy_unit_migration_preparation import (
    PolicyUnitMigrationPreparationService,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "policy_units"
PRE_MIGRATION_FIXTURE = FIXTURE_DIR / "pre_migration_policy_records.json"
DECISION_FIXTURE = FIXTURE_DIR / "policy_unit_decisions_fixture_v1.json"
SPINNER_ID = "wlv_approved_kr_refs_1_scale_default_spinner_flow"


def _copy_fixture(tmp_path: Path) -> tuple[Path, Path]:
    storage = tmp_path / "managed_knowledge.json"
    decision_path = tmp_path / "policy_unit_decisions.json"
    storage.write_bytes(PRE_MIGRATION_FIXTURE.read_bytes())
    decision_path.write_bytes(DECISION_FIXTURE.read_bytes())
    return storage, decision_path


def test_canonical_fixture_contract() -> None:
    document = json.loads(PRE_MIGRATION_FIXTURE.read_text(encoding="utf-8"))
    decisions = json.loads(DECISION_FIXTURE.read_text(encoding="utf-8"))
    assert len(document["records"]) == 34
    assert len(decisions["decisions"]) == 8
    assert [item["record_id"] for item in decisions["unresolved"]] == [SPINNER_ID]
    assert decisions["source_kr_sha256"] == hashlib.sha256(PRE_MIGRATION_FIXTURE.read_bytes()).hexdigest()


def test_live_migration_applies_28_entries_and_validates_inventory(tmp_path: Path) -> None:
    storage, decision_path = _copy_fixture(tmp_path)
    backup = tmp_path / "backup.json"
    before = hashlib.sha256(storage.read_bytes()).hexdigest()
    result = PolicyUnitLiveMigrationService(
        storage_path=storage,
        decision_path=decision_path,
        backup_path=backup,
    ).apply()
    assert backup.is_file()
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == before
    assert result["entry_count"] == 28
    assert result["inventory_status_counts_after"] == EXPECTED_POST_COUNTS
    assert result["source_kr_sha256"] == before
    assert result["migrated_kr_sha256"] != before


def test_live_migration_rollback_restores_exact_bytes(tmp_path: Path) -> None:
    storage, decision_path = _copy_fixture(tmp_path)
    original = storage.read_bytes()
    backup = tmp_path / "backup.json"
    service = PolicyUnitLiveMigrationService(
        storage_path=storage,
        decision_path=decision_path,
        backup_path=backup,
    )
    service.apply()
    service.restore_backup()
    assert storage.read_bytes() == original


def test_live_migration_refuses_existing_backup(tmp_path: Path) -> None:
    storage, decision_path = _copy_fixture(tmp_path)
    backup = tmp_path / "backup.json"
    backup.write_text("occupied", encoding="utf-8")
    service = PolicyUnitLiveMigrationService(
        storage_path=storage,
        decision_path=decision_path,
        backup_path=backup,
    )
    with pytest.raises(PolicyUnitLiveMigrationError, match="already exists"):
        service.apply()


def test_live_migration_refuses_changed_record_version(tmp_path: Path) -> None:
    storage, decision_path = _copy_fixture(tmp_path)
    preparation = PolicyUnitMigrationPreparationService(
        storage_path=storage,
        decision_path=decision_path,
    ).prepare()
    target_id = preparation["manifest"]["entries"][0]["record_id"]
    document = json.loads(storage.read_text(encoding="utf-8"))
    next(record for record in document["records"] if record["record_id"] == target_id)["version"] += 1
    storage.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    service = PolicyUnitLiveMigrationService(
        storage_path=storage,
        decision_path=decision_path,
        backup_path=tmp_path / "backup.json",
    )
    with pytest.raises(ValueError):
        service.apply()


def test_live_migration_keeps_spinner_unresolved(tmp_path: Path) -> None:
    storage, decision_path = _copy_fixture(tmp_path)
    PolicyUnitLiveMigrationService(
        storage_path=storage,
        decision_path=decision_path,
        backup_path=tmp_path / "backup.json",
    ).apply()
    document = json.loads(storage.read_text(encoding="utf-8"))
    spinner = next(record for record in document["records"] if record["record_id"] == SPINNER_ID)
    assert spinner.get("policy_value_unit") is None
