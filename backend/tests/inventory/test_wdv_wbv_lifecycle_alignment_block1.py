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


def _types(record: ManagedWellRecord) -> set[WmdReferenceType]:
    return {binding.reference_type for binding in record.wmd_references}


def test_reconcile_wbv_reference_moves_with_active_wdv_well(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    first = _record("first")
    second = _record("second")
    repo.upsert_record(first)
    repo.upsert_record(second)
    service = ManagedWellInventoryService(repository=repo)

    service.reconcile_wbv_session_reference(first.managed_well_id)
    assert WmdReferenceType.WBV in _types(repo.get_record(first.managed_well_id))
    assert WmdReferenceType.WBV not in _types(repo.get_record(second.managed_well_id))

    service.reconcile_wbv_session_reference(second.managed_well_id)
    assert WmdReferenceType.WBV not in _types(repo.get_record(first.managed_well_id))
    assert WmdReferenceType.WBV in _types(repo.get_record(second.managed_well_id))


def test_reconcile_wbv_reference_releases_when_workspace_has_no_active_well(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    record = _record("one")
    repo.upsert_record(record)
    service = ManagedWellInventoryService(repository=repo)

    service.reconcile_wbv_session_reference(record.managed_well_id)
    service.reconcile_wbv_session_reference(None)

    saved = repo.get_record(record.managed_well_id)
    assert WmdReferenceType.WBV not in _types(saved)
    assert all(
        binding.reference_type != WmdReferenceType.WBV
        for group in saved.product_groups
        for item in group.items
        for binding in item.wmd_references
    )


def test_reconcile_wbv_reference_rejects_cleared_or_unavailable_payload(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    record = _record("blocked", loaded=False)
    record = record.model_copy(update={
        "wmd_working_state": WmdWorkingState.CLEARED,
        "wmd_retention_state": WmdRetentionState.CLEARED,
    })
    repo.upsert_record(record)
    service = ManagedWellInventoryService(repository=repo)

    with pytest.raises(ValueError, match="downstream payload unavailable"):
        service.reconcile_wbv_session_reference(record.managed_well_id)
