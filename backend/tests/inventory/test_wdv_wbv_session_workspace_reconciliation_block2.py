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
from app.inventory.wdv_workspace import WdvWorkspaceService


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
                        wdv_state=(
                            ManagedWdvState.LOADED_TO_WDV
                            if loaded
                            else ManagedWdvState.NOT_LOADED
                        ),
                    )
                ],
            )
        ],
    )


def _owners(record: ManagedWellRecord, reference_type: WmdReferenceType) -> set[str]:
    return {
        binding.owner_id
        for binding in record.wmd_references
        if binding.reference_type == reference_type
    }


def _item_owners(record: ManagedWellRecord, reference_type: WmdReferenceType) -> set[str]:
    return {
        binding.owner_id
        for group in record.product_groups
        for item in group.items
        for binding in item.wmd_references
        if binding.reference_type == reference_type
    }


def test_active_wdv_switch_reconciles_wbv_reference_immediately(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    first = _record("first")
    second = _record("second")
    repo.upsert_record(first)
    repo.upsert_record(second)
    workspace = WdvWorkspaceService(repo, tmp_path / "wdv_workspace.json")
    service = ManagedWellInventoryService(repository=repo, workspace_service=workspace)

    service.set_active_wdv_well(first.managed_well_uid)
    assert _owners(repo.get_record(first.managed_well_id), WmdReferenceType.WBV) == {"wbv-session:default"}
    assert _owners(repo.get_record(second.managed_well_id), WmdReferenceType.WBV) == set()

    service.set_active_wdv_well(second.managed_well_uid)
    assert _owners(repo.get_record(first.managed_well_id), WmdReferenceType.WBV) == set()
    assert _owners(repo.get_record(second.managed_well_id), WmdReferenceType.WBV) == {"wbv-session:default"}


def test_saved_workspace_reconcile_moves_uuidv7_owned_references(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    first = _record("first")
    second = _record("second")
    repo.upsert_record(first)
    repo.upsert_record(second)
    service = ManagedWellInventoryService(repository=repo)
    workspace_uid = new_uuid7_str()

    service.reconcile_saved_workspace_references(
        workspace_uid,
        {first.managed_well_uid: [first.product_groups[0].items[0].managed_product_uid]},
    )
    assert _owners(repo.get_record(first.managed_well_id), WmdReferenceType.SAVED_WORKSPACE) == {workspace_uid}
    assert _item_owners(repo.get_record(first.managed_well_id), WmdReferenceType.SAVED_WORKSPACE) == {workspace_uid}

    service.reconcile_saved_workspace_references(
        workspace_uid,
        {second.managed_well_uid: [second.product_groups[0].items[0].managed_product_uid]},
    )
    assert _owners(repo.get_record(first.managed_well_id), WmdReferenceType.SAVED_WORKSPACE) == set()
    assert _item_owners(repo.get_record(first.managed_well_id), WmdReferenceType.SAVED_WORKSPACE) == set()
    assert _owners(repo.get_record(second.managed_well_id), WmdReferenceType.SAVED_WORKSPACE) == {workspace_uid}


def test_saved_workspace_release_removes_all_owned_bindings(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    record = _record("one")
    repo.upsert_record(record)
    service = ManagedWellInventoryService(repository=repo)
    workspace_uid = new_uuid7_str()

    service.reconcile_saved_workspace_references(workspace_uid, {record.managed_well_id: None})
    service.release_saved_workspace_references(workspace_uid)

    saved = repo.get_record(record.managed_well_id)
    assert _owners(saved, WmdReferenceType.SAVED_WORKSPACE) == set()
    assert _item_owners(saved, WmdReferenceType.SAVED_WORKSPACE) == set()


def test_saved_workspace_resume_rejects_cleared_payload_without_stale_binding(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    record = _record("blocked", loaded=False).model_copy(
        update={
            "wmd_working_state": WmdWorkingState.CLEARED,
            "wmd_retention_state": WmdRetentionState.CLEARED,
        }
    )
    repo.upsert_record(record)
    service = ManagedWellInventoryService(repository=repo)
    workspace_uid = new_uuid7_str()

    with pytest.raises(ValueError, match="downstream payload unavailable"):
        service.reconcile_saved_workspace_references(
            workspace_uid, {record.managed_well_uid: None}
        )

    saved = repo.get_record(record.managed_well_id)
    assert _owners(saved, WmdReferenceType.SAVED_WORKSPACE) == set()
    assert _item_owners(saved, WmdReferenceType.SAVED_WORKSPACE) == set()
