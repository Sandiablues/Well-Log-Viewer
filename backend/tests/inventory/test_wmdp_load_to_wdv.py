from pathlib import Path

from backend.app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWdvState,
    ManagedWellRecord,
)
from backend.app.inventory.repository import ManagedWellInventoryRepository
from backend.app.inventory.service import ManagedWellInventoryService


def _record(managed_well_id: str, product_ids: list[str]) -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id=managed_well_id,
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
                    for product_id in product_ids
                ],
            ),
            ManagedProductGroup(
                group_key="supporting_documents",
                group_label="Supporting documents",
                items=[
                    ManagedProductGroupItem(
                        product_id=f"doc:{managed_well_id}",
                        display_name="Report.pdf",
                        curve_name="Report.pdf",
                        curve_type="PDF",
                        product_category="supporting_documents",
                        curve_family="Supporting Document",
                        source_kind=ManagedSourceKind.DOCUMENT.value,
                    )
                ],
            ),
        ],
    )


def test_load_to_wdv_marks_one_well_loaded_and_unloads_others(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    repository.upsert_record(_record("managed-well:a", ["curve:a:gr", "curve:a:rt"]))
    repository.upsert_record(_record("managed-well:b", ["curve:b:gr"]))

    first = service.load_managed_well_to_wdv("managed-well:a")
    assert first.record.wdv_state == ManagedWdvState.LOADED_TO_WDV
    assert set(first.result.loaded_product_ids) == {"curve:a:gr", "curve:a:rt"}
    assert "doc:managed-well:a" not in first.result.loaded_product_ids

    second = service.load_managed_well_to_wdv("managed-well:b", product_ids=["curve:b:gr"])
    assert second.record.wdv_state == ManagedWdvState.LOADED_TO_WDV
    assert second.result.loaded_product_ids == ["curve:b:gr"]
    assert "managed-well:a" in second.result.unloaded_managed_well_ids

    reloaded_a = repository.get_record("managed-well:a")
    reloaded_b = repository.get_record("managed-well:b")
    assert reloaded_a.wdv_state == ManagedWdvState.NOT_LOADED
    assert all(item.wdv_state == ManagedWdvState.NOT_LOADED for group in reloaded_a.product_groups for item in group.items)
    assert reloaded_b.wdv_state == ManagedWdvState.LOADED_TO_WDV


def test_unload_from_wdv_is_non_destructive_and_preserves_wmdp_state(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    repository.upsert_record(_record("managed-well:a", ["curve:a:gr", "curve:a:rt"]))

    loaded = service.load_managed_well_to_wdv("managed-well:a")
    assert loaded.record.wdv_state == ManagedWdvState.LOADED_TO_WDV

    partial = service.unload_managed_well_from_wdv("managed-well:a", product_ids=["curve:a:gr"])
    assert partial.record.wdv_state == ManagedWdvState.LOADED_TO_WDV
    assert partial.result.unloaded_product_ids == ["curve:a:gr"]
    assert partial.result.remaining_loaded_product_ids == ["curve:a:rt"]

    full = service.unload_managed_well_from_wdv("managed-well:a")
    assert full.record.wdv_state == ManagedWdvState.NOT_LOADED
    assert set(full.result.unloaded_product_ids) == {"curve:a:gr", "curve:a:rt"}
    assert full.result.remaining_loaded_product_ids == []
    assert full.record.wmdp_state.value in {"registered", "staged_in_wmdp"}
    assert all(
        item.wdv_state == ManagedWdvState.NOT_LOADED
        for group in full.record.product_groups
        for item in group.items
    )


def test_viewer_package_contract_filters_to_loaded_wmdp_curves(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    record = _record("managed-well:a", ["GR", "RT"])
    record.metadata["viewer_package_contract"] = {
        "viewer_package_version": "well_multitrack_v1",
        "dataset_id": "dataset:a",
        "representation_id": "representation:a",
        "well_id": "a",
        "wellbore_id": "a-main",
        "depth_unit": "ft",
        "depth_range": {"min": 100.0, "max": 200.0},
        "tracks": [
            {"track_id": "depth", "track_type": "depth", "title": "Depth", "curves": []},
            {
                "track_id": "track-main",
                "track_type": "curve",
                "title": "Main",
                "curves": [
                    {"curve_id": "GR", "mnemonic": "GR", "unit": "API", "samples_url": "/samples/gr", "scale": {"type": "linear", "min": 0, "max": 150}},
                    {"curve_id": "RT", "mnemonic": "RT", "unit": "OHMM", "samples_url": "/samples/rt", "scale": {"type": "log", "min": 0.2, "max": 2000}},
                ],
            },
        ],
    }
    repository.upsert_record(record)

    service.load_managed_well_to_wdv("managed-well:a", product_ids=["GR"])
    package = service.get_viewer_package_contract("managed-well:a")

    assert package["wmdp_loaded_curve_names"] == ["GR"]
    assert [track["track_id"] for track in package["tracks"]] == ["depth", "track-main"]
    loaded_curve = package["tracks"][1]["curves"][0]
    assert loaded_curve["original_mnemonic"] == "GR"
    assert loaded_curve["canonical_curve_id"] == "gamma_ray"
    assert loaded_curve["display_curve_id"] == "GR"
    assert loaded_curve["is_renderable"] is True
