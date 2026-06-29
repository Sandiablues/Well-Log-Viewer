from pathlib import Path

import pytest

from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService


def _record(managed_well_id: str, product_id: str) -> ManagedWellRecord:
    well_uid = {
        "managed-well:a": "019f1000-0000-7000-8000-000000000001",
        "managed-well:b": "019f1000-0000-7000-8000-000000000002",
    }[managed_well_id]
    return ManagedWellRecord(
        managed_well_id=managed_well_id,
        managed_well_uid=well_uid,
        well_id=managed_well_id.replace("managed-well:", ""),
        well_name=managed_well_id,
        source_references=[
            ManagedSourceReference(
                source_id=f"source:{managed_well_id}",
                source_kind=ManagedSourceKind.LAS,
                display_name=f"{managed_well_id}.las",
            )
        ],
        product_groups=[
            ManagedProductGroup(
                group_key="open_hole_logs",
                group_label="Open hole logs",
                items=[
                    ManagedProductGroupItem(
                        product_id=product_id,
                        display_name=product_id,
                        curve_name=product_id,
                        curve_type="Gamma Ray",
                        curve_description="Gamma Ray",
                        curve_unit="API",
                        product_category="open_hole_logs",
                        curve_family="Gamma Ray",
                        review_required=False,
                        source_kind=ManagedSourceKind.LAS.value,
                    )
                ],
            )
        ],
    )


def test_workspace_tracks_multiple_loaded_wells_and_active_selection(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    repository.upsert_record(_record("managed-well:a", "curve:a:gr"))
    repository.upsert_record(_record("managed-well:b", "curve:b:gr"))

    service.load_managed_well_to_wdv("managed-well:a")
    service.load_managed_well_to_wdv("managed-well:b")

    workspace = service.get_wdv_workspace()
    assert workspace.contract_version == "wdv_workspace_v2"
    assert workspace.active_managed_well_id == "managed-well:b"
    assert [item.managed_well_id for item in workspace.loaded_wells] == [
        "managed-well:a",
        "managed-well:b",
    ]

    switched = service.set_active_wdv_well("managed-well:a")
    assert switched.active_managed_well_id == "managed-well:a"

    service.unload_managed_well_from_wdv("managed-well:a")
    reconciled = service.get_wdv_workspace()
    assert reconciled.active_managed_well_id == "managed-well:b"
    assert [item.managed_well_id for item in reconciled.loaded_wells] == ["managed-well:b"]


def test_workspace_rejects_non_loaded_active_well(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    repository.upsert_record(_record("managed-well:a", "curve:a:gr"))

    with pytest.raises(ValueError, match="must already be loaded"):
        service.set_active_wdv_well("managed-well:a")
