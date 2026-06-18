from __future__ import annotations

from app.inventory.models import (
    ManagedInventorySnapshot,
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService


def _legacy_record_without_curve_uids() -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id="managed-well:uid-block2",
        well_id="well-uid-block2",
        well_name="UID Block 2",
        source_references=[
            ManagedSourceReference(
                source_id="source:uid-block2:las",
                source_kind=ManagedSourceKind.LAS,
                display_name="uid-block2.las",
                file_format="LAS",
            )
        ],
        product_groups=[
            ManagedProductGroup(
                group_key="porosity",
                group_label="Porosity",
                items=[
                    ManagedProductGroupItem(
                        product_id="curve:uid-block2:nphi:upper",
                        display_name="NPHI",
                        curve_name="NPHI",
                        curve_type="Neutron Porosity",
                        curve_unit="v/v",
                        product_category="porosity",
                        curve_family="neutron_porosity",
                        run_interval="300.5-6076 ft",
                        run_number="1",
                    ),
                    ManagedProductGroupItem(
                        product_id="curve:uid-block2:nphi:lower",
                        display_name="NPHI",
                        curve_name="NPHI",
                        curve_type="Neutron Porosity",
                        curve_unit="v/v",
                        product_category="porosity",
                        curve_family="neutron_porosity",
                        run_interval="5970.5-8150 ft",
                        run_number="2",
                    ),
                ],
            )
        ],
    )


def _curve_items(record: ManagedWellRecord) -> list[ManagedProductGroupItem]:
    return [item for group in record.product_groups for item in group.items]


def test_metadata_backfill_does_not_manufacture_legacy_curve_uids(tmp_path):
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "managed_wells.json")
    repository.write_snapshot(ManagedInventorySnapshot(records=[_legacy_record_without_curve_uids()]))
    service = ManagedWellInventoryService(repository=repository)

    dry_run = service.backfill_inventory_identity_contract(dry_run=True)
    assert dry_run["product_identity_updates"] == 2
    assert all(item.curve_uid is None for item in _curve_items(repository.get_record("managed-well:uid-block2")))

    result = service.backfill_inventory_identity_contract()
    assert result["records_written"] == 1
    assert result["product_identity_updates"] == 2

    saved = repository.get_record("managed-well:uid-block2")
    items = _curve_items(saved)
    assert all(item.curve_uid is None for item in items)
    assert all(item.managed_curve_uid is None for item in items)
    assert [item.normalized_mnemonic for item in items] == ["NPHI", "NPHI"]
    assert all(item.well_uid == "well-uid-block2" for item in items)
    assert all(item.source_uid == "source:uid-block2:las" for item in items)

    second = service.backfill_inventory_identity_contract()
    assert second["product_identity_updates"] == 0
    assert all(
        item.curve_uid is None
        for item in _curve_items(repository.get_record("managed-well:uid-block2"))
    )


def test_upsert_managed_record_backfills_identity_before_write(tmp_path):
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "managed_wells.json")
    service = ManagedWellInventoryService(repository=repository)

    action, saved = service.upsert_managed_record(_legacy_record_without_curve_uids())

    assert action == "created"
    items = _curve_items(saved)
    assert len({str(item.managed_curve_uid) for item in items}) == 2
    assert all(item.managed_curve_uid is not None for item in items)
    assert all(item.curve_uid is None for item in items)
    assert all(item.observed_mnemonic == "NPHI" for item in items)
    assert all(item.normalized_mnemonic == "NPHI" for item in items)

    persisted = repository.get_record("managed-well:uid-block2")
    assert [item.managed_curve_uid for item in _curve_items(persisted)] == [
        item.managed_curve_uid for item in items
    ]


def test_list_wells_returns_identity_contract_for_legacy_rows_without_mutating_storage(tmp_path):
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "managed_wells.json")
    repository.write_snapshot(ManagedInventorySnapshot(records=[_legacy_record_without_curve_uids()]))
    service = ManagedWellInventoryService(repository=repository)

    listed = service.list_wells()
    listed_items = _curve_items(listed[0])

    assert all(item.curve_uid is None for item in listed_items)
    assert all(item.normalized_mnemonic == "NPHI" for item in listed_items)
    assert all(
        item.curve_uid is None
        for item in _curve_items(repository.get_record("managed-well:uid-block2"))
    )
