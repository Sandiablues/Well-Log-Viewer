
from __future__ import annotations

from pathlib import Path

from app.identity import is_uuid7, new_uuid7_str
from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedWellRecord,
    ManagedWdvState,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.wdv_session.models import WdvSessionLayoutPutRequest
from app.wdv_session.service import WdvSessionLayoutStateService


def _record() -> ManagedWellRecord:
    well_uid = new_uuid7_str()
    wellbore_uid = new_uuid7_str()
    product_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    source_uid = new_uuid7_str()
    item = ManagedProductGroupItem(
        product_id="legacy-product-1",
        managed_product_uid=product_uid,
        managed_curve_uid=curve_uid,
        managed_wellbore_uid=wellbore_uid,
        managed_source_uid=source_uid,
        curve_uid="legacy-curve-1",
        well_uid="legacy-well-1",
        source_uid="legacy-source-1",
        display_name="Gamma Ray",
        curve_name="GR",
        curve_type="Gamma Ray",
        product_category="openhole_logs",
        review_required=False,
        selectable=True,
        wdv_state=ManagedWdvState.LOADED_TO_WDV,
    )
    return ManagedWellRecord(
        managed_well_id="managed-well:legacy-1",
        managed_well_uid=well_uid,
        managed_wellbore_uid=wellbore_uid,
        well_id="legacy-well-1",
        well_name="Test Well",
        product_groups=[ManagedProductGroup(group_key="openhole", group_label="Openhole", items=[item])],
    )


def test_wdv_load_contract_propagates_canonical_uuid7_fields(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "managed.json")
    service = ManagedWellInventoryService(repository=repo)
    record = _record()
    service._sync_wdv_load_session_for_record(record)

    contract = record.metadata["wdv_load_session_contract"]
    curve = contract["loaded_curve_items"][0]

    assert contract["managed_well_uid"] == record.managed_well_uid
    assert contract["managed_wellbore_uid"] == record.managed_wellbore_uid
    assert is_uuid7(contract["viewer_package_uid"])
    assert is_uuid7(contract["representation_uid"])
    assert curve["managed_product_uid"] == record.product_groups[0].items[0].managed_product_uid
    assert curve["managed_curve_uid"] == record.product_groups[0].items[0].managed_curve_uid
    assert curve["managed_source_uid"] == record.product_groups[0].items[0].managed_source_uid
    assert curve["managed_wellbore_uid"] == record.managed_wellbore_uid
    assert curve["product_id"] == "legacy-product-1"
    assert curve["curve_uid"] == "legacy-curve-1"


def test_rebuilding_same_wdv_package_reuses_package_and_representation_uids(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "managed.json")
    service = ManagedWellInventoryService(repository=repo)
    record = _record()

    service._sync_wdv_load_session_for_record(record)
    first = record.metadata["wdv_load_session_contract"].copy()
    service._sync_wdv_load_session_for_record(record)
    second = record.metadata["wdv_load_session_contract"].copy()

    assert second["viewer_package_uid"] == first["viewer_package_uid"]
    assert second["representation_uid"] == first["representation_uid"]


def test_saved_layout_preserves_canonical_curve_relationships(tmp_path: Path) -> None:
    store = tmp_path / "layouts.json"
    service = WdvSessionLayoutStateService(storage_path=store)
    managed_well_uid = new_uuid7_str()
    managed_curve_uid = new_uuid7_str()
    managed_product_uid = new_uuid7_str()
    managed_wellbore_uid = new_uuid7_str()
    managed_source_uid = new_uuid7_str()

    request = WdvSessionLayoutPutRequest.model_validate({
        "managed_well_uid": managed_well_uid,
        "tracks": [{
            "track_id": "track-1",
            "track_name": "Gamma",
            "track_type": "curve",
            "curves": [{
                "assignment_id": "assignment-1",
                "curve_id": "GR",
                "managed_curve_uid": managed_curve_uid,
                "managed_product_uid": managed_product_uid,
                "managed_well_uid": managed_well_uid,
                "managed_wellbore_uid": managed_wellbore_uid,
                "managed_source_uid": managed_source_uid,
                "product_id": "legacy-product-1",
                "curve_uid": "legacy-curve-1",
            }],
        }],
    })

    saved = service.put_layout("managed-well:legacy-1", request)
    loaded = service.get_layout("managed-well:legacy-1")
    curve = loaded.tracks[0].curves[0]

    assert saved.managed_well_uid == managed_well_uid
    assert curve.managed_curve_uid == managed_curve_uid
    assert curve.managed_product_uid == managed_product_uid
    assert curve.managed_well_uid == managed_well_uid
    assert curve.managed_wellbore_uid == managed_wellbore_uid
    assert curve.managed_source_uid == managed_source_uid
    assert curve.product_id == "legacy-product-1"
    assert curve.curve_uid == "legacy-curve-1"


def test_uuid4_is_rejected_in_layout_canonical_fields() -> None:
    import uuid
    try:
        WdvSessionLayoutPutRequest.model_validate({
            "managed_well_uid": str(uuid.uuid4()),
            "tracks": [],
        })
    except Exception:
        return
    raise AssertionError("UUIDv4 must be rejected for canonical UUIDv7 fields")
