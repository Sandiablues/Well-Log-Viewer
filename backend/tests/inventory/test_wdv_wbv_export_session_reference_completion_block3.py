from pathlib import Path

import pytest

from app.identity import new_uuid7_str
from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedWdvState,
    ManagedWellRecord,
    WmdReferenceType,
    WmdRetentionState,
    WmdWorkingState,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService


def _record(name: str, *, loaded: bool = True) -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id=f"managed-well:{name}",
        managed_well_uid=new_uuid7_str(),
        well_id=f"well:{name}",
        well_name=name,
        product_groups=[
            ManagedProductGroup(
                group_key="open_hole_logs",
                group_label="Open hole logs",
                items=[
                    ManagedProductGroupItem(
                        product_id=f"product:{name}:gr",
                        managed_product_uid=new_uuid7_str(),
                        managed_curve_uid=new_uuid7_str(),
                        display_name="GR",
                        curve_name="GR",
                        curve_type="Gamma Ray",
                        wdv_state=(ManagedWdvState.LOADED_TO_WDV if loaded else ManagedWdvState.NOT_LOADED),
                    )
                ],
            )
        ],
    )


def _owners(record: ManagedWellRecord, ref_type: WmdReferenceType) -> set[str]:
    owners = {b.owner_id for b in record.wmd_references if b.reference_type == ref_type}
    owners |= {
        b.owner_id
        for group in record.product_groups
        for item in group.items
        for b in item.wmd_references
        if b.reference_type == ref_type
    }
    return owners


def test_export_reference_is_acquired_and_fully_released(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    record = _record("one")
    repo.upsert_record(record)
    service = ManagedWellInventoryService(repository=repo)
    export_uid = new_uuid7_str()

    service.reconcile_export_references(export_uid, {record.managed_well_uid: None})
    assert _owners(repo.get_record(record.managed_well_id), WmdReferenceType.EXPORT) == {export_uid}

    service.release_export_references(export_uid)
    assert _owners(repo.get_record(record.managed_well_id), WmdReferenceType.EXPORT) == set()


def test_export_rejects_cleared_payload_without_stale_binding(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    record = _record("blocked", loaded=False).model_copy(update={
        "wmd_working_state": WmdWorkingState.CLEARED,
        "wmd_retention_state": WmdRetentionState.CLEARED,
    })
    repo.upsert_record(record)
    service = ManagedWellInventoryService(repository=repo)
    export_uid = new_uuid7_str()

    with pytest.raises(ValueError, match="downstream payload unavailable"):
        service.reconcile_export_references(export_uid, {record.managed_well_id: None})
    assert _owners(repo.get_record(record.managed_well_id), WmdReferenceType.EXPORT) == set()


def test_viewer_session_reset_releases_wbv_but_preserves_wdv(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    record = _record("one")
    repo.upsert_record(record)
    service = ManagedWellInventoryService(repository=repo)
    service.acquire_wmd_consumer_reference(record.managed_well_id, WmdReferenceType.WDV, "wdv-workspace:test")
    service.acquire_wmd_consumer_reference(record.managed_well_id, WmdReferenceType.WBV, "wbv-session:test")

    service.reset_viewer_session_references(owner_id="wbv-session:test")
    saved = repo.get_record(record.managed_well_id)
    assert _owners(saved, WmdReferenceType.WBV) == set()
    assert _owners(saved, WmdReferenceType.WDV) == {"wdv-workspace:test"}


def test_stale_reconciliation_only_removes_unlisted_transient_consumers(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    record = _record("one")
    repo.upsert_record(record)
    service = ManagedWellInventoryService(repository=repo)
    service.acquire_wmd_consumer_reference(record.managed_well_id, WmdReferenceType.WDV, "wdv-workspace:test")
    service.acquire_wmd_consumer_reference(record.managed_well_id, WmdReferenceType.EXPORT, "export:stale")
    service.acquire_wmd_consumer_reference(record.managed_well_id, WmdReferenceType.EXPORT, "export:active")
    service.acquire_wmd_consumer_reference(record.managed_well_id, WmdReferenceType.SAVED_WORKSPACE, "workspace:stale")
    service.acquire_wmd_consumer_reference(record.managed_well_id, WmdReferenceType.WBV, "wbv-session:stale")

    service.reconcile_stale_consumer_references(
        active_export_owner_ids={"export:active"},
        active_saved_workspace_owner_ids=set(),
        active_wbv_owner_ids=set(),
    )
    saved = repo.get_record(record.managed_well_id)
    assert _owners(saved, WmdReferenceType.EXPORT) == {"export:active"}
    assert _owners(saved, WmdReferenceType.SAVED_WORKSPACE) == set()
    assert _owners(saved, WmdReferenceType.WBV) == set()
    assert _owners(saved, WmdReferenceType.WDV) == {"wdv-workspace:test"}
