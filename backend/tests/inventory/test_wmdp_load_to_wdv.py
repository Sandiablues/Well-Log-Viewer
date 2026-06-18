from pathlib import Path

from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWdvState,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService


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


def test_load_to_wdv_is_additive_and_preserves_other_loaded_wells(tmp_path: Path) -> None:
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
    assert second.result.unloaded_managed_well_ids == []

    reloaded_a = repository.get_record("managed-well:a")
    reloaded_b = repository.get_record("managed-well:b")
    assert reloaded_a.wdv_state == ManagedWdvState.LOADED_TO_WDV
    assert {
        item.product_id
        for group in reloaded_a.product_groups
        for item in group.items
        if item.wdv_state == ManagedWdvState.LOADED_TO_WDV
    } == {"curve:a:gr", "curve:a:rt"}
    assert reloaded_b.wdv_state == ManagedWdvState.LOADED_TO_WDV

    workspace = service.get_wdv_workspace()
    assert workspace.active_managed_well_id == "managed-well:b"
    assert {item.managed_well_id for item in workspace.loaded_wells} == {
        "managed-well:a",
        "managed-well:b",
    }


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

    assert package["contract_kind"] == "wdv_load_session"
    assert package["source_product_ids"] == ["GR"]
    assert package["loaded_product_count"] == 1
    assert package["loaded_curve_names"] == ["GR"]
    assert package["mdp_loaded_curve_names"] == ["GR"]
    assert package["wmdp_loaded_curve_names"] == ["GR"]
    assert [item["product_id"] for item in package["loaded_curve_items"]] == ["GR"]
    assert [track["track_id"] for track in package["tracks"]] == ["depth"]
    assert package["tracks"][0]["curves"] == []
    assert package["visible_tracks"] == []
    assert package["display_tracks"] == []
    assert package["track_layout_state"] == "manual_empty"
    loaded_curve = package["loaded_curve_items"][0]
    assert loaded_curve["original_mnemonic"] == "GR"
    assert loaded_curve["canonical_curve_id"] == "gamma_ray"
    assert loaded_curve["display_curve_id"] == "GR"
    assert loaded_curve["is_renderable"] is False
    assert loaded_curve["support_status"] == "samples_unavailable"
    assert loaded_curve["sample_access"]["status"] == "unavailable"
    assert loaded_curve["sample_access"]["sample_count"] == 0


def test_wdv_load_session_depth_domain_uses_loaded_curve_interval_union(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    record = _record("managed-well:a", ["SHALLOW", "DEEP"])
    record.top_depth = 300.0
    record.base_depth = 6075.5
    for group in record.product_groups:
        for item in group.items:
            if item.product_id == "SHALLOW":
                item.run_interval = "300–6075.5 ft"
            if item.product_id == "DEEP":
                item.run_interval = "5970.5–8150 ft"
    repository.upsert_record(record)

    service.load_managed_well_to_wdv("managed-well:a", product_ids=["SHALLOW", "DEEP"])
    package = service.get_viewer_package_contract("managed-well:a")

    assert package["depth_range"] == {"min": 300.0, "max": 8150.0}
    assert package["depth_domain"]["min"] == 300.0
    assert package["depth_domain"]["max"] == 8150.0
    assert package["depth_domain"]["source"] == "union_loaded_curve_intervals"
    assert package["depth_domain"]["contributing_product_ids"] == ["SHALLOW", "DEEP"]



def test_remove_from_mdp_hides_well_and_unloads_wdv_but_retains_record(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    repository.upsert_record(_record("managed-well:a", ["curve:a:gr", "curve:a:rt"]))

    service.load_managed_well_to_wdv("managed-well:a")
    removed = service.remove_managed_data_from_mdp(managed_well_ids=["managed-well:a"])

    assert removed.result.removed_managed_well_ids == ["managed-well:a"]
    assert removed.result.retained_msi_records is True
    assert "managed-well:a" in removed.result.unloaded_managed_well_ids

    retained = repository.get_record("managed-well:a")
    assert retained.wmdp_available is False
    assert retained.wmdp_state.value == "removed_from_wmdp"
    assert retained.wdv_state == ManagedWdvState.NOT_LOADED
    assert all(
        item.wdv_state == ManagedWdvState.NOT_LOADED
        for group in retained.product_groups
        for item in group.items
    )
    assert service.list_wells() == []


def test_load_to_wdv_creates_backend_owned_load_session_package(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    repository.upsert_record(_record("managed-well:a", ["GR", "RT", "NPHI"]))

    loaded = service.load_managed_well_to_wdv("managed-well:a", product_ids=["GR", "RT"])

    assert loaded.result.active_viewer_package_id is not None
    assert loaded.result.active_viewer_package_id.startswith("wdv-load-session:")
    saved = repository.get_record("managed-well:a")
    assert saved.metadata["wdv_load_session"]["loaded_product_count"] == 2
    assert saved.metadata["wdv_load_session_contract"]["contract_kind"] == "wdv_load_session"
    assert len(saved.viewer_packages) == 1
    assert saved.viewer_packages[0].viewer_package_id == loaded.result.active_viewer_package_id

    package = service.get_viewer_package_contract("managed-well:a")
    loaded_curves = package["loaded_curve_items"]
    visible_curves = [curve for track in package["tracks"] for curve in track.get("curves", [])]
    assert package["loaded_product_count"] == 2
    assert package["source_product_ids"] == ["GR", "RT"]
    assert package["loaded_curve_names"] == ["GR", "RT"]
    assert package["mdp_loaded_curve_names"] == ["GR", "RT"]
    assert package["wmdp_loaded_curve_names"] == ["GR", "RT"]
    assert [item["product_id"] for item in loaded_curves] == ["GR", "RT"]
    assert visible_curves == []
    assert package["visible_tracks"] == []
    assert package["display_tracks"] == []
    assert all(curve["is_renderable"] is False for curve in loaded_curves)
    assert all(curve["support_status"] == "samples_unavailable" for curve in loaded_curves)
    assert all(curve["sample_access"]["status"] == "unavailable" for curve in loaded_curves)
    assert all(curve["sample_access"]["sample_count"] == 0 for curve in loaded_curves)


def test_viewer_package_endpoint_repairs_legacy_loaded_state_without_session(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    record = _record("managed-well:a", ["GR", "RT"])
    for group in record.product_groups:
        for item in group.items:
            if item.product_id == "GR":
                item.wdv_state = ManagedWdvState.LOADED_TO_WDV
    record.wdv_state = ManagedWdvState.LOADED_TO_WDV
    repository.upsert_record(record)

    package = service.get_viewer_package_contract("managed-well:a")

    assert package["contract_kind"] == "wdv_load_session"
    assert package["loaded_product_count"] == 1
    repaired = repository.get_record("managed-well:a")
    assert isinstance(repaired.metadata.get("wdv_load_session_contract"), dict)
    assert repaired.viewer_packages[0].viewer_package_id.startswith("wdv-load-session:")


def test_unload_from_wdv_clears_backend_owned_load_session_package(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    repository.upsert_record(_record("managed-well:a", ["GR", "RT"]))

    service.load_managed_well_to_wdv("managed-well:a")
    assert repository.get_record("managed-well:a").metadata.get("wdv_load_session_contract")

    unloaded = service.unload_managed_well_from_wdv("managed-well:a")

    assert unloaded.record.wdv_state == ManagedWdvState.NOT_LOADED
    assert unloaded.record.metadata.get("wdv_load_session_contract") is None
    assert unloaded.record.viewer_packages == []

