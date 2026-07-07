from app.identity import new_uuid7_str
from pathlib import Path

from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedWellRecord,
    ManagedWdvState,
    ManagedWmdpState,
    WmdReferenceType,
    WmdWorkingState,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.inventory.wmd_lifecycle_service import WmdLifecycleService


def _record() -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id="managed-well:test",
        managed_well_uid=new_uuid7_str(),
        managed_wellbore_uid=new_uuid7_str(),
        well_id="test",
        well_name="Test",
        wmdp_state=ManagedWmdpState.STAGED_IN_WMDP,
        product_groups=[
            ManagedProductGroup(
                group_key="openhole",
                group_label="Openhole",
                items=[
                    ManagedProductGroupItem(
                        product_id="curve:test:gr",
                        display_name="GR",
                        curve_name="GR",
                        curve_type="Gamma Ray",
                    )
                ],
            )
        ],
    )


def test_reference_bindings_are_idempotent_uuidv7_and_project_in_use():
    lifecycle = WmdLifecycleService()
    record = _record()
    first = lifecycle.acquire_reference(record, WmdReferenceType.WBV, "wbv:test")
    second = lifecycle.acquire_reference(record, WmdReferenceType.WBV, "wbv:test")
    assert first.reference_uid == second.reference_uid
    assert len(record.wmd_references) == 1
    projected = lifecycle.project_record(record)
    assert projected.wmd_working_state == WmdWorkingState.IN_USE
    assert projected.wmd_retention_reason == "referenced_by_wbv"


def test_wdv_load_and_unload_acquire_and_release_explicit_references(tmp_path: Path):
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repo)
    repo.upsert_record(_record())

    loaded = service.load_managed_well_to_wdv("managed-well:test")
    assert loaded.record.wdv_state == ManagedWdvState.LOADED_TO_WDV
    assert {ref.reference_type for ref in loaded.record.wmd_references} == {
        WmdReferenceType.WMD,
        WmdReferenceType.WDV,
    }
    loaded_item = loaded.record.product_groups[0].items[0]
    assert {ref.reference_type for ref in loaded_item.wmd_references} == {
        WmdReferenceType.WMD,
        WmdReferenceType.WDV,
    }

    unloaded = service.unload_managed_well_from_wdv("managed-well:test")
    assert unloaded.record.wdv_state == ManagedWdvState.NOT_LOADED
    assert {ref.reference_type for ref in unloaded.record.wmd_references} == {
        WmdReferenceType.WMD,
    }
    assert {ref.reference_type for ref in unloaded.record.product_groups[0].items[0].wmd_references} == {
        WmdReferenceType.WMD,
    }


def test_remove_from_wmd_releases_wmd_and_wdv_but_preserves_other_consumers(tmp_path: Path):
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repo)
    repo.upsert_record(_record())
    service.load_managed_well_to_wdv("managed-well:test")
    service.acquire_wmd_consumer_reference(
        "managed-well:test", WmdReferenceType.SAVED_WORKSPACE, "workspace:test"
    )

    removed = service.remove_managed_data_from_mdp(managed_well_ids=["managed-well:test"])
    record = removed.records[0]
    assert record.wmdp_state == ManagedWmdpState.REMOVED_FROM_WMDP
    assert {ref.reference_type for ref in record.wmd_references} == {
        WmdReferenceType.SAVED_WORKSPACE,
    }
    assert record.wmd_working_state == WmdWorkingState.IN_USE
    assert record.wmd_cleanup_eligible is False


def test_explicit_export_reference_can_be_released(tmp_path: Path):
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repo)
    repo.upsert_record(_record())
    service.acquire_wmd_consumer_reference(
        "managed-well:test", WmdReferenceType.EXPORT, "export:test"
    )
    saved = service.release_wmd_consumer_reference(
        "managed-well:test", WmdReferenceType.EXPORT, "export:test"
    )
    assert all(ref.reference_type != WmdReferenceType.EXPORT for ref in saved.wmd_references)
