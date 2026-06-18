from __future__ import annotations

from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService


def _record(*, legacy_curve_uid: str | None = None) -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id="managed-well:uid9b",
        well_id="well-uid9b",
        well_name="UID-9B Well",
        product_groups=[
            ManagedProductGroup(
                group_key="curve_data",
                group_label="Curve Data",
                items=[
                    ManagedProductGroupItem(
                        product_id="curve:uid9b:gr",
                        curve_uid=legacy_curve_uid,
                        display_name="GR",
                        curve_name="GR",
                        curve_type="Gamma Ray",
                        observed_mnemonic="GR",
                        normalized_mnemonic="GR",
                    )
                ],
            )
        ],
    )


def _item(record: ManagedWellRecord) -> ManagedProductGroupItem:
    return record.product_groups[0].items[0]


def test_new_curve_gets_uuid7_without_new_sha1_legacy_identity(tmp_path) -> None:
    service = ManagedWellInventoryService(
        repository=ManagedWellInventoryRepository(
            storage_path=tmp_path / "managed_wells.json"
        )
    )

    _, saved = service.upsert_managed_record(_record())
    item = _item(saved)

    assert item.managed_curve_uid is not None
    assert item.curve_uid is None
    assert not any(
        alias.value.startswith("wlv_curve:")
        for alias in item.legacy_ids
    )

    contract = service._wdv_curve_contract_from_product_item(saved, item)
    assert contract["managed_curve_uid"] == str(item.managed_curve_uid)
    assert contract["curve_uid"] == str(item.managed_curve_uid)


def test_existing_sha1_curve_uid_is_preserved_only_as_legacy_alias(tmp_path) -> None:
    service = ManagedWellInventoryService(
        repository=ManagedWellInventoryRepository(
            storage_path=tmp_path / "managed_wells.json"
        )
    )

    _, saved = service.upsert_managed_record(
        _record(legacy_curve_uid="wlv_curve:existinglegacy")
    )
    item = _item(saved)

    assert item.managed_curve_uid is not None
    assert item.curve_uid == "wlv_curve:existinglegacy"
    assert (
        "wlv_curve_sha1_v1",
        "wlv_curve:existinglegacy",
    ) in {
        (alias.scheme, alias.value)
        for alias in item.legacy_ids
    }

    _, repeated = service.upsert_managed_record(_record())
    repeated_item = _item(repeated)

    assert repeated_item.managed_curve_uid == item.managed_curve_uid
    assert repeated_item.curve_uid is None
    assert (
        "wlv_curve_sha1_v1",
        "wlv_curve:existinglegacy",
    ) in {
        (alias.scheme, alias.value)
        for alias in repeated_item.legacy_ids
    }


def test_service_source_contains_no_sha1_curve_uid_generator() -> None:
    assert not hasattr(
        ManagedWellInventoryService,
        "_curve_uid_for_registered_curve",
    )
    assert not hasattr(
        ManagedWellInventoryService,
        "_curve_uid_from_product_item",
    )
