"""Tests for simulation-only WDV policy-unit migration preparation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.knowledge.policy_unit_migration_preparation import (
    PolicyUnitMigrationPreparationService,
)


def _policy(record_id: str, *, record_type: str, version: int, unit_field: str, unit_value: str) -> dict:
    record = {
        "record_id": record_id,
        "record_type": record_type,
        "version": version,
        "status": "approved",
        "runtime_eligible": True,
        "scale_type": "linear",
        "policy_value_unit": None,
    }
    if record_type == "display_rule":
        record.update({"display_min": 0.0, "display_max": 100.0, "canonical_curve_id": record_id})
    else:
        record.update({"scale_min": 0.0, "scale_max": 100.0, "curve_family": record_id})
    record[unit_field] = unit_value
    return record


def _write_fixture(tmp_path: Path) -> tuple[Path, Path]:
    records: list[dict] = []
    # Twenty deterministic inventory candidates.
    for index in range(12):
        records.append(
            _policy(
                f"display-{index}",
                record_type="display_rule",
                version=1,
                unit_field="default_unit",
                unit_value="API",
            )
        )
    for index in range(8):
        records.append(
            _policy(
                f"family-{index}",
                record_type="template_scale_default",
                version=2,
                unit_field="unit_family",
                unit_value="api",
            )
        )
    # Eight governed decisions.
    decision_records = []
    decisions = []
    for index in range(8):
        record = _policy(
            f"decision-{index}",
            record_type="template_scale_default",
            version=3,
            unit_field="unit_family",
            unit_value="engineering",
        )
        decision_records.append(record)
        decisions.append(
            {
                "record_id": record["record_id"],
                "expected_record_type": record["record_type"],
                "expected_curve_family": record["curve_family"],
                "expected_scale_type": record["scale_type"],
                "expected_scale_min": record["scale_min"],
                "expected_scale_max": record["scale_max"],
                "expected_policy_value_unit": None,
                "policy_value_unit": "psi",
                "decision_basis": "governed test decision",
                "decision_status": "approved_for_migration",
            }
        )
    records.extend(decision_records)
    unresolved = _policy(
        "spinner-unresolved",
        record_type="template_scale_default",
        version=4,
        unit_field="unit_family",
        unit_value="engineering",
    )
    records.append(unresolved)
    # Five non-line/incomplete exclusions.
    for index, scale_type in enumerate(
        ["image_track", "event_track", "tadpole_track", "waveform_track"]
    ):
        item = _policy(
            f"excluded-{index}",
            record_type="template_scale_default",
            version=1,
            unit_field="unit_family",
            unit_value="engineering",
        )
        item["scale_type"] = scale_type
        records.append(item)
    incomplete = _policy(
        "excluded-incomplete",
        record_type="template_scale_default",
        version=1,
        unit_field="unit_family",
        unit_value="api",
    )
    incomplete["scale_max"] = None
    records.append(incomplete)

    document = {"records": records, "evidence": []}
    storage_path = tmp_path / "managed_knowledge.json"
    source_bytes = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    storage_path.write_bytes(source_bytes)
    manifest = {
        "schema_version": "wlv-policy-unit-decisions-v1",
        "source_kr_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "decisions": decisions,
        "unresolved": [
            {
                "record_id": unresolved["record_id"],
                "expected_record_type": unresolved["record_type"],
                "expected_curve_family": unresolved["curve_family"],
                "expected_scale_type": unresolved["scale_type"],
                "expected_scale_min": unresolved["scale_min"],
                "expected_scale_max": unresolved["scale_max"],
                "expected_policy_value_unit": None,
                "reason": "requires domain review",
                "decision_status": "requires_domain_review",
            }
        ],
    }
    decision_path = tmp_path / "decisions.json"
    decision_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return storage_path, decision_path


def test_preparation_is_read_only_and_produces_guarded_28_entry_manifest(tmp_path: Path) -> None:
    storage_path, decision_path = _write_fixture(tmp_path)
    before = storage_path.read_bytes()
    result = PolicyUnitMigrationPreparationService(
        storage_path=storage_path,
        decision_path=decision_path,
    ).prepare()
    assert storage_path.read_bytes() == before
    manifest = result["manifest"]
    assert manifest["entry_count"] == 28
    assert manifest["unresolved_record_ids"] == ["spinner-unresolved"]
    assert all(entry["expected_current_policy_value_unit"] is None for entry in manifest["entries"])
    assert all(isinstance(entry["expected_record_version"], int) for entry in manifest["entries"])
    assert {entry["source_kind"] for entry in manifest["entries"]} == {
        "deterministic_inventory",
        "governed_decision",
    }


def test_simulated_inventory_meets_activation_prerequisite_counts(tmp_path: Path) -> None:
    storage_path, decision_path = _write_fixture(tmp_path)
    result = PolicyUnitMigrationPreparationService(
        storage_path=storage_path,
        decision_path=decision_path,
    ).prepare()
    assert result["simulation"]["inventory_status_counts_after"] == {
        "ambiguous_review_required": 1,
        "explicit_supported": 28,
        "explicit_unknown_unit": 0,
        "inferable_supported": 0,
        "non_numeric_or_non_line": 5,
    }


def test_simulation_increments_only_migrated_record_versions(tmp_path: Path) -> None:
    storage_path, decision_path = _write_fixture(tmp_path)
    source = json.loads(storage_path.read_text())
    result = PolicyUnitMigrationPreparationService(
        storage_path=storage_path,
        decision_path=decision_path,
    ).prepare()
    before = {record["record_id"]: record for record in source["records"]}
    after = {record["record_id"]: record for record in result["simulated_document"]["records"]}
    migrated_ids = {entry["record_id"] for entry in result["manifest"]["entries"]}
    for record_id, record in after.items():
        if record_id in migrated_ids:
            assert record["version"] == before[record_id]["version"] + 1
            assert record["policy_value_unit"] is not None
        else:
            assert record == before[record_id]


def test_source_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    storage_path, decision_path = _write_fixture(tmp_path)
    manifest = json.loads(decision_path.read_text())
    manifest["source_kr_sha256"] = "0" * 64
    decision_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="source KR hash"):
        PolicyUnitMigrationPreparationService(
            storage_path=storage_path,
            decision_path=decision_path,
        ).prepare()


def test_changed_record_version_is_rejected(tmp_path: Path) -> None:
    storage_path, decision_path = _write_fixture(tmp_path)
    document = json.loads(storage_path.read_text())
    document["records"][0]["version"] = "bad"
    changed = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    storage_path.write_bytes(changed)
    manifest = json.loads(decision_path.read_text())
    manifest["source_kr_sha256"] = hashlib.sha256(changed).hexdigest()
    decision_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="record version is not an integer"):
        PolicyUnitMigrationPreparationService(
            storage_path=storage_path,
            decision_path=decision_path,
        ).prepare()
