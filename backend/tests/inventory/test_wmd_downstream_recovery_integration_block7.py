from pathlib import Path

import pytest

from app.identity import new_uuid7_str
from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedWellRecord,
    WmdRetentionState,
    WmdSourceRecoveryState,
    WmdWorkingState,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService


def _service(tmp_path: Path, state=WmdSourceRecoveryState.AVAILABLE, cleared=False):
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    item = ManagedProductGroupItem(
        product_id="curve:test:gr",
        managed_product_uid=new_uuid7_str(),
        managed_curve_uid=new_uuid7_str(),
        display_name="GR",
        curve_name="GR",
        curve_type="Gamma Ray",
        wmd_source_recovery_state=state,
        wmd_working_state=WmdWorkingState.CLEARED if cleared else WmdWorkingState.AVAILABLE,
        wmd_retention_state=WmdRetentionState.CLEARED if cleared else WmdRetentionState.ACTIVE,
    )
    record = ManagedWellRecord(
        managed_well_id="managed-well:test",
        managed_well_uid=new_uuid7_str(),
        well_id="test",
        well_name="Test",
        product_groups=[ManagedProductGroup(group_key="openhole", group_label="Openhole", items=[item])],
        metadata={"viewer_package_contract": {"tracks": []}},
        wmd_source_recovery_state=state,
        wmd_working_state=WmdWorkingState.CLEARED if cleared else WmdWorkingState.AVAILABLE,
        wmd_retention_state=WmdRetentionState.CLEARED if cleared else WmdRetentionState.ACTIVE,
        wmd_source_recovery_message="source unavailable" if state != WmdSourceRecoveryState.AVAILABLE else None,
    )
    repo.upsert_record(record)
    return ManagedWellInventoryService(repository=repo)


def test_recovery_contract_blocks_all_downstream_consumers(tmp_path: Path):
    service = _service(tmp_path, WmdSourceRecoveryState.MISSING, cleared=True)
    status = service.get_wmd_downstream_recovery_status("managed-well:test")
    assert status.payload_available is False
    assert status.wdv_load_allowed is False
    assert status.wbv_load_allowed is False
    assert status.export_allowed is False
    assert status.saved_workspace_resume_allowed is False
    assert status.blocked_product_ids == ["curve:test:gr"]


def test_wdv_load_rejects_stale_or_cleared_payload(tmp_path: Path):
    service = _service(tmp_path, WmdSourceRecoveryState.CHANGED, cleared=True)
    with pytest.raises(ValueError, match="downstream payload unavailable"):
        service.load_managed_well_to_wdv("managed-well:test", ["curve:test:gr"])


def test_viewer_package_rejects_stale_payload(tmp_path: Path):
    service = _service(tmp_path, WmdSourceRecoveryState.INACCESSIBLE, cleared=True)
    with pytest.raises(ValueError, match="downstream payload unavailable"):
        service.get_viewer_package_contract("managed-well:test")


def test_available_rebuilt_payload_allows_downstream_resume(tmp_path: Path):
    service = _service(tmp_path)
    status = service.get_wmd_downstream_recovery_status("managed-well:test")
    assert status.payload_available is True
    response = service.load_managed_well_to_wdv("managed-well:test", ["curve:test:gr"])
    assert response.result.loaded_product_ids == ["curve:test:gr"]
