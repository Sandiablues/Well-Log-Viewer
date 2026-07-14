from pathlib import Path

from app.identity import new_uuid7_str
from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService


def _density_item(
    *,
    product_id: str,
    mnemonic: str,
    detailed_family: str,
    detailed_key: str,
) -> ManagedProductGroupItem:
    return ManagedProductGroupItem(
        product_id=product_id,
        display_name=mnemonic,
        curve_name=mnemonic,
        curve_type=detailed_family,
        curve_description=detailed_family,
        curve_unit="G/C3",
        product_category="open_hole_logs",
        product_subgroup_key="density",
        product_subgroup_label="Density",
        curve_family=detailed_family,
        curve_family_key=detailed_key,
        general_curve_family="Density",
        general_curve_family_key="density",
        general_curve_family_projection_version="general-curve-family-projection-v1",
        source_kind=ManagedSourceKind.LAS.value,
        source_id="source:density-family",
    )


def test_mwd_and_generated_wdv_use_identical_persisted_general_family_categories(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    inventory = ManagedWellInventoryService(repository=repository)

    record = ManagedWellRecord(
        managed_well_id="managed-well:density-family",
        managed_well_uid=new_uuid7_str(),
        managed_wellbore_uid=new_uuid7_str(),
        well_id="density-family",
        well_name="Density Family",
        source_references=[
            ManagedSourceReference(
                source_id="source:density-family",
                source_kind=ManagedSourceKind.LAS,
                display_name="density-family.las",
            )
        ],
        product_groups=[
            ManagedProductGroup(
                group_key="open_hole_logs",
                group_label="Open hole logs",
                items=[
                    _density_item(
                        product_id="p:rhoz",
                        mnemonic="RHOZ",
                        detailed_family="Density",
                        detailed_key="density",
                    ),
                    _density_item(
                        product_id="p:hdra",
                        mnemonic="HDRA",
                        detailed_family="Density Correction",
                        detailed_key="density_correction",
                    ),
                ],
            )
        ],
    )
    repository.upsert_record(record)

    mwd = repository.get_record(record.managed_well_id)
    density_items = [item for group in mwd.product_groups for item in group.items]

    # Detailed classification remains distinct.
    assert {item.curve_family_key for item in density_items} == {
        "density",
        "density_correction",
    }

    # MWD category authority is the persisted general family.
    assert {
        (item.product_subgroup_key, item.product_subgroup_label)
        for item in density_items
    } == {("density", "Density")}
    assert {
        (item.general_curve_family_key, item.general_curve_family)
        for item in density_items
    } == {("density", "Density")}

    inventory.load_managed_well_to_wdv(record.managed_well_id)
    loaded = repository.get_record(record.managed_well_id)
    session = loaded.metadata["wdv_load_session_contract"]
    wdv_items = [
        item
        for item in session["loaded_curve_items"]
        if item["mnemonic"] in {"RHOZ", "HDRA"}
    ]
    assert len(wdv_items) == 2

    # WDV uses exactly the same persisted general family category.
    assert {
        (item["curve_family_key"], item["curve_family"])
        for item in wdv_items
    } == {("density", "Density")}
    assert {
        (item["general_curve_family_key"], item["general_curve_family"])
        for item in wdv_items
    } == {("density", "Density")}

    # Detailed family metadata remains available in WDV.
    assert {item["classification_curve_family_key"] for item in wdv_items} == {
        "density",
        "density_correction",
    }
