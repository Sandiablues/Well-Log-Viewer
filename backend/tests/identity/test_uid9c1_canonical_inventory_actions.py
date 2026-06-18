from __future__ import annotations

from pathlib import Path

from app.identity import LegacyIdentityAlias
from app.inventory.models import (
    LoadManagedWellToWdvRequest,
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedWellRecord,
    RemoveManagedDataFromMdpRequest,
    UnloadManagedWellFromWdvRequest,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService


WELL_UID = "01976c6d-4aa7-7e43-b118-d7d30e773e71"
PRODUCT_UID = "01976c6d-4aa7-7e43-b118-d7d30e773e72"
CURVE_UID = "01976c6d-4aa7-7e43-b118-d7d30e773e73"


def _service(tmp_path: Path) -> ManagedWellInventoryService:
    repository = ManagedWellInventoryRepository(
        storage_path=tmp_path / "managed_wells.json"
    )
    service = ManagedWellInventoryService(repository=repository)
    record = ManagedWellRecord(
        managed_well_id="legacy-well",
        well_id="legacy-well-id",
        managed_well_uid=WELL_UID,
        well_name="Canonical Well",
        legacy_ids=[
            LegacyIdentityAlias(
                scheme="managed_well_id",
                value="old-well-alias",
            )
        ],
        product_groups=[
            ManagedProductGroup(
                group_key="curves",
                group_label="Curves",
                items=[
                    ManagedProductGroupItem(
                        product_id="legacy-product",
                        managed_product_uid=PRODUCT_UID,
                        managed_curve_uid=CURVE_UID,
                        display_name="GR",
                        curve_name="GR",
                        curve_type="Gamma Ray",
                        legacy_ids=[
                            LegacyIdentityAlias(
                                scheme="product_id",
                                value="old-product-alias",
                            )
                        ],
                    )
                ],
            )
        ],
    )
    service.upsert_managed_record(record)
    return service


def test_request_models_prefer_canonical_references() -> None:
    load = LoadManagedWellToWdvRequest(
        managed_well_uid=WELL_UID,
        managed_well_id="legacy-well",
        managed_product_uids=[PRODUCT_UID],
        product_ids=["legacy-product"],
    )
    assert load.well_reference == WELL_UID
    assert load.product_references == [PRODUCT_UID, "legacy-product"]

    unload = UnloadManagedWellFromWdvRequest(
        managed_well_uid=WELL_UID,
        managed_product_uids=[PRODUCT_UID],
    )
    assert unload.well_reference == WELL_UID
    assert unload.product_references == [PRODUCT_UID]

    remove = RemoveManagedDataFromMdpRequest(
        managed_well_uids=[WELL_UID],
        managed_product_uids=[PRODUCT_UID],
    )
    assert remove.well_references == [WELL_UID]
    assert remove.product_references == [PRODUCT_UID]


def test_load_and_unload_resolve_canonical_uuid7_references(tmp_path: Path) -> None:
    service = _service(tmp_path)

    loaded = service.load_managed_well_to_wdv(
        WELL_UID,
        [PRODUCT_UID],
    )
    assert loaded.result.managed_well_id == "legacy-well"
    assert loaded.result.loaded_product_ids == ["legacy-product"]

    unloaded = service.unload_managed_well_from_wdv(
        WELL_UID,
        [CURVE_UID],
    )
    assert unloaded.result.unloaded_product_ids == ["legacy-product"]


def test_legacy_aliases_remain_accepted_at_boundary(tmp_path: Path) -> None:
    service = _service(tmp_path)

    loaded = service.load_managed_well_to_wdv(
        "old-well-alias",
        ["old-product-alias"],
    )
    assert loaded.result.loaded_product_ids == ["legacy-product"]


def test_remove_from_mdp_resolves_canonical_references(tmp_path: Path) -> None:
    service = _service(tmp_path)

    response = service.remove_managed_data_from_mdp(
        managed_well_ids=[WELL_UID],
        product_ids=[PRODUCT_UID],
    )
    assert response.result.removed_managed_well_ids == ["legacy-well"]
    assert response.result.removed_product_ids == ["legacy-product"]
