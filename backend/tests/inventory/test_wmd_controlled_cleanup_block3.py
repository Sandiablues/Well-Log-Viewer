from pathlib import Path

from app.identity import new_uuid7_str
from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedWellRecord,
    ManagedWmdpState,
    WmdReferenceType,
    WmdRetentionState,
    WmdWorkingState,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.inventory.wmd_lifecycle_service import WmdLifecycleService


def _record() -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id="managed-well:test",
        managed_well_uid=new_uuid7_str(),
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


def test_removed_record_without_any_reference_is_cleanup_eligible(tmp_path: Path):
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repo)
    repo.upsert_record(_record())

    removed = service.remove_managed_data_from_mdp(
        managed_well_ids=["managed-well:test"]
    ).records[0]

    assert removed.wmd_references == []
    assert removed.wmd_working_state == WmdWorkingState.ELIGIBLE_FOR_CLEANUP
    assert removed.wmd_retention_state == WmdRetentionState.ELIGIBLE_FOR_CLEANUP
    assert removed.wmd_cleanup_eligible is True
    assert removed.wmd_retention_reason == "removed_from_wmd_no_active_references"
    item = removed.product_groups[0].items[0]
    assert item.wmd_references == []
    assert item.wmd_cleanup_eligible is True


def test_saved_workspace_reference_blocks_cleanup_until_released(tmp_path: Path):
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repo)
    repo.upsert_record(_record())
    service.acquire_wmd_consumer_reference(
        "managed-well:test",
        WmdReferenceType.SAVED_WORKSPACE,
        "workspace:test",
    )

    removed = service.remove_managed_data_from_mdp(
        managed_well_ids=["managed-well:test"]
    ).records[0]
    assert removed.wmd_working_state == WmdWorkingState.IN_USE
    assert removed.wmd_cleanup_eligible is False
    assert removed.wmd_retention_reason == "referenced_by_saved_workspace"

    released = service.release_wmd_consumer_reference(
        "managed-well:test",
        WmdReferenceType.SAVED_WORKSPACE,
        "workspace:test",
    )
    assert released.wmd_working_state == WmdWorkingState.ELIGIBLE_FOR_CLEANUP
    assert released.wmd_retention_state == WmdRetentionState.ELIGIBLE_FOR_CLEANUP
    assert released.wmd_cleanup_eligible is True


def test_each_downstream_reference_type_blocks_cleanup():
    lifecycle = WmdLifecycleService()
    for reference_type in (
        WmdReferenceType.WDV,
        WmdReferenceType.WBV,
        WmdReferenceType.EXPORT,
        WmdReferenceType.SAVED_WORKSPACE,
    ):
        record = _record().model_copy(
            update={
                "wmdp_available": False,
                "wmdp_state": ManagedWmdpState.REMOVED_FROM_WMDP,
            }
        )
        lifecycle.acquire_reference(
            record, reference_type, f"owner:{reference_type.value}"
        )
        projected = lifecycle.project_record(record)
        assert projected.wmd_cleanup_eligible is False
        assert projected.wmd_working_state == WmdWorkingState.IN_USE


def test_wmd_reference_also_blocks_cleanup_if_transition_is_incomplete():
    lifecycle = WmdLifecycleService()
    record = _record().model_copy(
        update={
            "wmdp_available": False,
            "wmdp_state": ManagedWmdpState.REMOVED_FROM_WMDP,
        }
    )
    lifecycle.acquire_reference(record, WmdReferenceType.WMD, record.managed_well_id)
    projected = lifecycle.project_record(record)
    assert projected.wmd_cleanup_eligible is False
    assert projected.wmd_retention_reason == "referenced_by_wmd"


def test_partial_product_removal_marks_only_unreferenced_product_eligible(tmp_path: Path):
    record = _record()
    second = ManagedProductGroupItem(
        product_id="curve:test:rhob",
        display_name="RHOB",
        curve_name="RHOB",
        curve_type="Bulk Density",
    )
    record.product_groups[0].items.append(second)
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repo)
    repo.upsert_record(record)
    service.load_managed_well_to_wdv(
        "managed-well:test", product_ids=["curve:test:rhob"]
    )

    result = service.remove_managed_data_from_mdp(
        product_ids=["curve:test:gr"]
    ).records[0]
    items = {
        item.product_id: item
        for group in result.product_groups
        for item in group.items
    }
    assert items["curve:test:gr"].wmd_cleanup_eligible is True
    assert items["curve:test:rhob"].wmd_cleanup_eligible is False
    assert result.wmd_cleanup_eligible is False
    assert result.wmd_working_state == WmdWorkingState.IN_USE
