from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedWellRecord,
    ManagedWdvState,
    ManagedWmdpState,
    WmdRetentionState,
    WmdWorkingState,
)
from app.inventory.wmd_lifecycle_service import WmdLifecycleService


def _record(*, wmdp_available=True, wmdp_state=ManagedWmdpState.STAGED_IN_WMDP, wdv_state=ManagedWdvState.NOT_LOADED):
    item = ManagedProductGroupItem(
        product_id="p1", display_name="GR", curve_name="GR", curve_type="curve",
        wmdp_state=wmdp_state, wdv_state=wdv_state,
    )
    return ManagedWellRecord(
        managed_well_id="managed-well:test", well_id="test", well_name="Test",
        wmdp_available=wmdp_available, wmdp_state=wmdp_state, wdv_state=wdv_state,
        product_groups=[ManagedProductGroup(group_key="openhole", group_label="Openhole", items=[item])],
    )


def test_available_wmd_data_is_active_and_not_cleanup_eligible():
    projected = WmdLifecycleService().project_record(_record())
    assert projected.wmd_working_state == WmdWorkingState.AVAILABLE
    assert projected.wmd_retention_state == WmdRetentionState.ACTIVE
    assert projected.wmd_cleanup_eligible is False
    assert projected.product_groups[0].items[0].wmd_working_state == WmdWorkingState.AVAILABLE


def test_wdv_loaded_data_is_in_use():
    projected = WmdLifecycleService().project_record(_record(wdv_state=ManagedWdvState.LOADED_TO_WDV))
    assert projected.wmd_working_state == WmdWorkingState.IN_USE
    assert projected.wmd_retention_reason == "referenced_by_wdv"
    assert projected.product_groups[0].items[0].wmd_working_state == WmdWorkingState.IN_USE


def test_removed_wmd_data_without_references_is_cleanup_eligible():
    projected = WmdLifecycleService().project_record(_record(
        wmdp_available=False, wmdp_state=ManagedWmdpState.REMOVED_FROM_WMDP
    ))
    assert projected.wmd_working_state == WmdWorkingState.ELIGIBLE_FOR_CLEANUP
    assert projected.wmd_retention_state == WmdRetentionState.ELIGIBLE_FOR_CLEANUP
    assert projected.wmd_cleanup_eligible is True
    assert projected.wmd_retention_reason == "removed_from_wmd_no_active_references"
