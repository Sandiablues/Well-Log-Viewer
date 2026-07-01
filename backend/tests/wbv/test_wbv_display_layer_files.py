from pathlib import Path

from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedWmdpState,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.wbv.service import WbvService


def _record(managed_well_id: str, product_id: str, *, layer_type: str, staged: bool = True) -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id=managed_well_id,
        well_id=managed_well_id.replace("managed-well:", ""),
        well_name=managed_well_id,
        product_groups=[
            ManagedProductGroup(
                group_key="display_layers",
                group_label="Display layers",
                items=[
                    ManagedProductGroupItem(
                        product_id=product_id,
                        display_name=f"{product_id} display",
                        curve_name=product_id,
                        curve_type="display_layer",
                        display_layer_type=layer_type,
                        depth_reference="MD",
                        depth_units="ft",
                        depth_start=100.0,
                        depth_end=2000.0,
                        wmdp_state=(
                            ManagedWmdpState.STAGED_IN_WMDP
                            if staged
                            else ManagedWmdpState.REGISTERED
                        ),
                    )
                ],
            )
        ],
    )


def test_display_layer_files_are_grouped_for_selected_well(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    repository.upsert_record(_record("managed-well:a", "tops-a", layer_type="formation_tops"))
    repository.upsert_record(_record("managed-well:b", "tops-b", layer_type="formation_tops"))

    contract = WbvService(repository=repository).get_display_layer_files("managed-well:a")

    assert contract.managed_well_id == "managed-well:a"
    assert [item.product_id for item in contract.layers["formation_tops"]] == ["tops-a"]
    item = contract.layers["formation_tops"][0]
    assert item.display_name == "tops-a display"
    assert item.depth_reference == "MD"
    assert item.depth_units == "ft"
    assert item.depth_start == 100.0
    assert item.depth_end == 2000.0


def test_display_layer_files_exclude_unstaged_or_incomplete_products(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    record = _record("managed-well:a", "tops-a", layer_type="formation_tops", staged=False)
    repository.upsert_record(record)

    contract = WbvService(repository=repository).get_display_layer_files("managed-well:a")

    assert contract.layers["formation_tops"] == []
    assert set(contract.layers) == {
        "formation_tops",
        "lithology_intervals",
        "casing_hole_sections",
        "completions",
        "curve_overlays",
        "borehole_imagery",
    }
