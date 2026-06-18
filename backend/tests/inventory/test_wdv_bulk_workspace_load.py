from pathlib import Path

import pytest

from app.inventory.models import (
    BulkLoadWdvWellSelection,
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWdvState,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService


def _record(well_id: str, products: list[str]) -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id=well_id,
        well_id=well_id,
        well_name=well_id,
        source_references=[
            ManagedSourceReference(
                source_id=f"source:{well_id}",
                source_kind=ManagedSourceKind.LAS,
                display_name=f"{well_id}.las",
            )
        ],
        product_groups=[
            ManagedProductGroup(
                group_key="logs",
                group_label="Logs",
                items=[
                    ManagedProductGroupItem(
                        product_id=product_id,
                        display_name=product_id,
                        curve_name=product_id,
                        curve_type="Gamma Ray",
                        curve_unit="API",
                        product_category="logs",
                        curve_family="Gamma Ray",
                        source_kind=ManagedSourceKind.LAS.value,
                    )
                    for product_id in products
                ],
            )
        ],
    )


def test_bulk_load_writes_all_wells_once_and_preserves_active_well(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    for name in ["a", "b", "c", "d", "e"]:
        repository.upsert_record(_record(f"managed-well:{name}", [f"{name}:gr", f"{name}:dt"]))

    service.load_managed_well_to_wdv("managed-well:c")
    result = service.bulk_load_wdv_workspace([
        BulkLoadWdvWellSelection(managed_well_id=f"managed-well:{name}")
        for name in ["a", "b", "c", "d", "e"]
    ])

    assert result.requested_count == 5
    assert result.loaded_count == 4
    assert result.already_loaded_count == 1
    assert result.failed_count == 0
    assert result.workspace.active_managed_well_id == "managed-well:c"
    assert {item.managed_well_id for item in result.workspace.loaded_wells} == {
        "managed-well:a", "managed-well:b", "managed-well:c", "managed-well:d", "managed-well:e"
    }
    assert all(record.wdv_state == ManagedWdvState.LOADED_TO_WDV for record in repository.list_records())


def test_bulk_load_validates_all_references_before_write(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    repository.upsert_record(_record("managed-well:a", ["a:gr"]))

    with pytest.raises(KeyError):
        service.bulk_load_wdv_workspace([
            BulkLoadWdvWellSelection(managed_well_id="managed-well:a"),
            BulkLoadWdvWellSelection(managed_well_id="managed-well:missing"),
        ])

    retained = repository.get_record("managed-well:a")
    assert retained.wdv_state == ManagedWdvState.NOT_LOADED


def test_bulk_load_rejects_duplicate_well_selections(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    repository.upsert_record(_record("managed-well:a", ["a:gr"]))

    with pytest.raises(ValueError, match="Duplicate managed well selection"):
        service.bulk_load_wdv_workspace([
            BulkLoadWdvWellSelection(managed_well_id="managed-well:a"),
            BulkLoadWdvWellSelection(managed_well_id="managed-well:a"),
        ])


def test_bulk_unload_is_atomic_and_replaces_active_well(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    for name in ["a", "b", "c"]:
        repository.upsert_record(_record(f"managed-well:{name}", [f"{name}:gr", f"{name}:dt"]))

    service.bulk_load_wdv_workspace([
        BulkLoadWdvWellSelection(managed_well_id=f"managed-well:{name}")
        for name in ["a", "b", "c"]
    ])
    service.set_active_wdv_well("managed-well:b")

    result = service.bulk_unload_wdv_workspace([
        BulkLoadWdvWellSelection(managed_well_id="managed-well:a"),
        BulkLoadWdvWellSelection(managed_well_id="managed-well:b"),
    ])

    assert result.requested_count == 2
    assert result.unloaded_count == 2
    assert result.already_unloaded_count == 0
    assert [item.managed_well_id for item in result.workspace.loaded_wells] == ["managed-well:c"]
    assert result.workspace.active_managed_well_id == "managed-well:c"
    assert repository.get_record("managed-well:a").wdv_state == ManagedWdvState.NOT_LOADED
    assert repository.get_record("managed-well:b").wdv_state == ManagedWdvState.NOT_LOADED
    assert repository.get_record("managed-well:c").wdv_state == ManagedWdvState.LOADED_TO_WDV


def test_bulk_unload_validates_every_reference_before_write(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    repository.upsert_record(_record("managed-well:a", ["a:gr"]))
    service.load_managed_well_to_wdv("managed-well:a")

    with pytest.raises(KeyError):
        service.bulk_unload_wdv_workspace([
            BulkLoadWdvWellSelection(managed_well_id="managed-well:a"),
            BulkLoadWdvWellSelection(managed_well_id="managed-well:missing"),
        ])

    assert repository.get_record("managed-well:a").wdv_state == ManagedWdvState.LOADED_TO_WDV


def test_workspace_materializes_authoritative_package_before_counting(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    repository.upsert_record(_record("managed-well:a", ["a:gr", "a:dt", "a:sp", "a:resd"]))
    service.load_managed_well_to_wdv("managed-well:a")

    record = repository.get_record("managed-well:a")
    session = dict(record.metadata["wdv_load_session_contract"])
    session["contract_version"] = "legacy-stale-contract"
    session["curves"] = session["curves"][:2]
    session["viewer_curve_count"] = 2
    session["displayable_curve_count"] = 2
    record.metadata["wdv_load_session_contract"] = session
    repository.upsert_record(record)

    # Workspace is intentionally read first. It must repair/persist the package
    # before calculating aggregate counts.
    workspace = service.get_wdv_workspace()
    package = service.get_viewer_package_contract("managed-well:a")
    summary = workspace.loaded_wells[0]

    assert len(package["curves"]) == 4
    assert package["loaded_product_count"] == 4
    assert package["viewer_curve_count"] == 4
    assert package["displayable_curve_count"] == 4
    assert summary.loaded_product_count == package["loaded_product_count"]
    assert summary.viewer_curve_count == package["viewer_curve_count"]
    assert summary.displayable_curve_count == package["displayable_curve_count"]
    assert summary.loaded_curve_count == package["displayable_curve_count"]

    listed = service.list_wells()[0]
    assert listed.loaded_product_count == package["loaded_product_count"]
    assert listed.viewer_curve_count == package["viewer_curve_count"]
    assert listed.displayable_curve_count == package["displayable_curve_count"]
