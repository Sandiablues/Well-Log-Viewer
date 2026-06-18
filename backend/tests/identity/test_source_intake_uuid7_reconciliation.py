from pathlib import Path

from app.identity import is_uuid7
from app.inventory.models import (
    ManagedInventorySnapshot,
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.identity_reconciliation import reconcile_managed_record_identity


def _incoming_record() -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id="managed-well:wlv-intake-name-test-well-123",
        well_id="wlv-intake-name-test-well-123",
        well_name="Test Well",
        wellbore_id="test-well-main",
        source_references=[
            ManagedSourceReference(
                source_id="occ:abc123",
                source_kind=ManagedSourceKind.LAS,
                display_name="test.las",
                file_name="test.las",
                checksum="sha256:content",
            )
        ],
        product_groups=[
            ManagedProductGroup(
                group_key="resistivity",
                group_label="Resistivity",
                items=[
                    ManagedProductGroupItem(
                        product_id="source-intake-curve:occ:abc123:1:rt",
                        curve_uid="wlv_curve:legacysha1",
                        display_name="RT",
                        curve_name="RT",
                        curve_type="Deep resistivity",
                        source_id="occ:abc123",
                    )
                ],
            )
        ],
    )


def _all_ids(record: ManagedWellRecord) -> tuple[str, ...]:
    source = record.source_references[0]
    product = record.product_groups[0].items[0]
    return (
        record.managed_well_uid,
        record.managed_wellbore_uid,
        source.managed_source_uid,
        source.source_occurrence_uid,
        product.managed_product_uid,
        product.managed_curve_uid,
        product.managed_wellbore_uid,
        product.managed_source_uid,
    )


def test_first_registration_assigns_canonical_uuid7_identity(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    incoming = _incoming_record()
    saved = reconcile_managed_record_identity(incoming)
    action, saved = repository.upsert_record(saved)

    assert action == "created"
    assert all(value and is_uuid7(value) for value in _all_ids(saved))
    assert saved.product_groups[0].items[0].managed_wellbore_uid == saved.managed_wellbore_uid
    assert (
        saved.product_groups[0].items[0].managed_source_uid
        == saved.source_references[0].managed_source_uid
    )


def test_repeated_registration_reuses_every_canonical_identity(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    first = reconcile_managed_record_identity(_incoming_record())
    _first_action, first = repository.upsert_record(first)
    second = reconcile_managed_record_identity(
        _incoming_record(),
        existing=repository.get_record(first.managed_well_id),
    )
    second_action, second = repository.upsert_record(second)

    assert second_action == "updated"
    assert _all_ids(second) == _all_ids(first)
    assert second.identity_assignment == first.identity_assignment
    assert second.source_references[0].identity_assignment == first.source_references[0].identity_assignment
    assert (
        second.product_groups[0].items[0].identity_assignment
        == first.product_groups[0].items[0].identity_assignment
    )


def test_legacy_aliases_are_preserved_once(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    first = reconcile_managed_record_identity(_incoming_record())
    repository.upsert_record(first)
    second = reconcile_managed_record_identity(
        _incoming_record(),
        existing=repository.get_record(first.managed_well_id),
    )
    _action, second = repository.upsert_record(second)

    well_aliases = {(alias.scheme, alias.value) for alias in second.legacy_ids}
    source_aliases = {
        (alias.scheme, alias.value) for alias in second.source_references[0].legacy_ids
    }
    product_aliases = {
        (alias.scheme, alias.value)
        for alias in second.product_groups[0].items[0].legacy_ids
    }

    assert ("managed_well_id_v1", second.managed_well_id) in well_aliases
    assert ("managed_source_reference_source_id_v1", "occ:abc123") in source_aliases
    assert (
        "managed_product_product_id_v1",
        "source-intake-curve:occ:abc123:1:rt",
    ) in product_aliases
    assert ("wlv_curve_sha1_v1", "wlv_curve:legacysha1") in product_aliases
    assert len(product_aliases) == len(second.product_groups[0].items[0].legacy_ids)


def test_repository_upsert_preserves_uuid7_snapshot_schema(tmp_path: Path) -> None:
    path = tmp_path / "managed_wells.json"
    repository = ManagedWellInventoryRepository(path)
    repository.write_snapshot(
        ManagedInventorySnapshot(
            schema_version="wlv_managed_inventory_v3_uuid7",
            records=[],
        )
    )
    saved = reconcile_managed_record_identity(_incoming_record())
    repository.upsert_record(saved)

    assert repository.snapshot().schema_version == "wlv_managed_inventory_v3_uuid7"


def test_existing_migrated_identity_wins_over_new_incoming_record(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    first = reconcile_managed_record_identity(_incoming_record())
    repository.upsert_record(first)
    incoming = _incoming_record().model_copy(
        update={
            "well_name": "Corrected Test Well Name",
        }
    )
    corrected = reconcile_managed_record_identity(
        incoming,
        existing=repository.get_record(first.managed_well_id),
    )
    _action, corrected = repository.upsert_record(corrected)

    assert corrected.well_name == "Corrected Test Well Name"
    assert _all_ids(corrected) == _all_ids(first)
