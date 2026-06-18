from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.identity import new_uuid7_str
from app.inventory.identity_migration import (
    MIGRATION_NAME,
    UUID7_INVENTORY_SCHEMA_VERSION,
    ManagedInventoryIdentityMigrationError,
    ManagedInventoryIdentityMigrationService,
)
from app.inventory.models import (
    ManagedInventorySnapshot,
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
    ViewerPackageReference,
)
from app.inventory.repository import ManagedWellInventoryRepository


def _snapshot() -> ManagedInventorySnapshot:
    return ManagedInventorySnapshot(
        records=[
            ManagedWellRecord(
                managed_well_id="managed-well:w-1",
                well_id="w-1",
                well_name="Well One",
                wellbore_id="wb-1",
                source_references=[
                    ManagedSourceReference(
                        source_id="occ:source-1",
                        source_kind=ManagedSourceKind.LAS,
                        display_name="well-one.las",
                    )
                ],
                viewer_packages=[
                    ViewerPackageReference(
                        viewer_package_id="vp-1",
                        viewer_package_version="1",
                        dataset_id="dataset-1",
                        representation_id="rep-1",
                        well_id="w-1",
                        endpoint="/viewer/vp-1",
                    )
                ],
                product_groups=[
                    ManagedProductGroup(
                        group_key="openhole",
                        group_label="Openhole",
                        items=[
                            ManagedProductGroupItem(
                                product_id="product-1",
                                curve_uid="wlv_curve:legacy-1",
                                source_uid="occ:source-1",
                                display_name="GR",
                                curve_name="GR",
                                curve_type="gamma_ray",
                            )
                        ],
                    )
                ],
            )
        ]
    )


def _repo(tmp_path: Path) -> ManagedWellInventoryRepository:
    repo = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    repo.write_snapshot(_snapshot())
    return repo


def test_dry_run_assigns_in_memory_only_and_creates_no_backup(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = repo.storage_path.read_bytes()

    result = ManagedInventoryIdentityMigrationService(repo).migrate(dry_run=True)

    assert result.ok is True
    assert result.dry_run is True
    assert result.changed is True
    assert result.identities_assigned > 0
    assert result.records_written == 0
    assert result.backup_path is None
    assert repo.storage_path.read_bytes() == before
    assert not list(tmp_path.glob("*.bak"))


def test_migration_assigns_uuid7_aliases_and_relationships(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    result = ManagedInventoryIdentityMigrationService(repo).migrate()
    migrated = repo.snapshot()
    record = migrated.records[0]
    source = record.source_references[0]
    package = record.viewer_packages[0]
    product = record.product_groups[0].items[0]

    assert result.ok is True
    assert result.migration == MIGRATION_NAME
    assert result.changed is True
    assert result.records_written == 1
    assert result.backup_path is not None
    assert Path(result.backup_path).exists()
    assert migrated.schema_version == UUID7_INVENTORY_SCHEMA_VERSION

    for uid in (
        record.managed_well_uid,
        record.managed_wellbore_uid,
        source.managed_source_uid,
        source.source_occurrence_uid,
        package.viewer_package_uid,
        package.representation_uid,
        product.managed_product_uid,
        product.managed_curve_uid,
    ):
        assert uid is not None
        assert uid.split("-")[2].startswith("7")

    assert product.managed_wellbore_uid == record.managed_wellbore_uid
    assert product.managed_source_uid == source.managed_source_uid
    assert any(a.scheme == "managed_well_id" for a in record.legacy_ids)
    assert any(a.scheme == "wlv_curve_sha1_v1" for a in product.legacy_ids)
    assert record.identity_assignment is not None
    assert record.identity_assignment.assignment_source == MIGRATION_NAME


def test_second_run_is_idempotent_and_creates_no_new_backup(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    service = ManagedInventoryIdentityMigrationService(repo)

    first = service.migrate()
    first_payload = repo.storage_path.read_bytes()
    backups_after_first = sorted(tmp_path.glob("*.bak"))
    second = service.migrate()

    assert first.changed is True
    assert second.changed is False
    assert second.identities_assigned == 0
    assert second.aliases_added == 0
    assert second.records_written == 0
    assert second.backup_path is None
    assert repo.storage_path.read_bytes() == first_payload
    assert sorted(tmp_path.glob("*.bak")) == backups_after_first


def test_existing_uuid7_values_are_preserved(tmp_path: Path) -> None:
    snapshot = _snapshot()
    record = snapshot.records[0]
    existing = new_uuid7_str()
    record.managed_well_uid = existing
    repo = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    repo.write_snapshot(snapshot)

    ManagedInventoryIdentityMigrationService(repo).migrate()

    assert repo.snapshot().records[0].managed_well_uid == existing


def test_same_legacy_source_resolves_to_same_managed_source_uid(tmp_path: Path) -> None:
    snapshot = _snapshot()
    second = snapshot.records[0].model_copy(deep=True)
    second.managed_well_id = "managed-well:w-2"
    second.well_id = "w-2"
    second.well_name = "Well Two"
    second.wellbore_id = "wb-2"
    second.viewer_packages = []
    second.product_groups[0].items[0].product_id = "product-2"
    second.product_groups[0].items[0].curve_uid = "wlv_curve:legacy-2"
    snapshot.records.append(second)
    repo = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    repo.write_snapshot(snapshot)

    ManagedInventoryIdentityMigrationService(repo).migrate()
    migrated = repo.snapshot()

    assert (
        migrated.records[0].source_references[0].managed_source_uid
        == migrated.records[1].source_references[0].managed_source_uid
    )


def test_write_failure_restores_original_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path)
    original = repo.storage_path.read_bytes()
    real_snapshot = repo.snapshot
    calls = 0

    def invalid_after_write():
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_snapshot()
        raise RuntimeError("simulated post-write read failure")

    monkeypatch.setattr(repo, "snapshot", invalid_after_write)

    with pytest.raises(ManagedInventoryIdentityMigrationError):
        ManagedInventoryIdentityMigrationService(repo).migrate()

    assert repo.storage_path.read_bytes() == original
    assert list(tmp_path.glob("*.bak"))


def test_duplicate_existing_product_uid_is_rejected_without_writing(tmp_path: Path) -> None:
    snapshot = _snapshot()
    duplicate = snapshot.records[0].product_groups[0].items[0].model_copy(deep=True)
    duplicate.product_id = "product-2"
    shared_uid = new_uuid7_str()
    snapshot.records[0].product_groups[0].items[0].managed_product_uid = shared_uid
    duplicate.managed_product_uid = shared_uid
    snapshot.records[0].product_groups[0].items.append(duplicate)
    repo = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    repo.write_snapshot(snapshot)
    before = repo.storage_path.read_bytes()

    with pytest.raises(ManagedInventoryIdentityMigrationError, match="Duplicate managed_product_uid"):
        ManagedInventoryIdentityMigrationService(repo).migrate()

    assert repo.storage_path.read_bytes() == before
    assert not list(tmp_path.glob("*.bak"))
