
from pathlib import Path
import hashlib

import pytest

from app.identity import new_uuid7_str
from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
    ManagedWmdpState,
    WmdReferenceType,
    WmdRetentionState,
    WmdWorkingState,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService


LAS_TEXT = """~Version
VERS. 2.0
~Well
STRT.FT 1000
STOP.FT 1002
STEP.FT 1
NULL. -999.25
~Curve
DEPT.FT : Depth
GR.API : Gamma Ray
~Ascii
1000 50
1001 60
1002 70
"""


def _record(source_path: Path, fingerprint: str) -> ManagedWellRecord:
    product_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    return ManagedWellRecord(
        managed_well_id="managed-well:test",
        managed_well_uid=new_uuid7_str(),
        well_id="test",
        well_name="Test",
        wmdp_available=False,
        wmdp_state=ManagedWmdpState.REMOVED_FROM_WMDP,
        source_references=[
            ManagedSourceReference(
                source_id="source:test",
                source_kind=ManagedSourceKind.LAS,
                display_name="test.las",
                original_path=str(source_path),
                checksum=fingerprint,
                metadata={"metadata_overlay": {"well_name": "Corrected"}},
            )
        ],
        metadata={
            "metadata_overlay": {"field": "Corrected field"},
            "qaqc_decision": {"decision": "accepted"},
        },
        product_groups=[
            ManagedProductGroup(
                group_key="openhole",
                group_label="Openhole",
                items=[
                    ManagedProductGroupItem(
                        product_id="curve:test:gr",
                        managed_product_uid=product_uid,
                        managed_curve_uid=curve_uid,
                        curve_uid=curve_uid,
                        display_name="GR",
                        curve_name="GR",
                        curve_type="Gamma Ray",
                        curve_unit="API",
                        source_kind="las",
                        source_id="source:test",
                        wmdp_state=ManagedWmdpState.REMOVED_FROM_WMDP,
                        provenance={
                            "original_path": str(source_path),
                            "source_fingerprint": fingerprint,
                            "source_curve_index": 1,
                            "metadata_overlay": {"curve_name": "Gamma Ray"},
                        },
                    )
                ],
            )
        ],
    )


def _cleared_service(tmp_path: Path):
    source = tmp_path / "external.las"
    source.write_text(LAS_TEXT, encoding="utf-8")
    fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repo)
    original = _record(source, fingerprint)
    repo.upsert_record(original)
    cleaned = service.execute_wmd_cleanup("managed-well:test").record
    return service, source, original, cleaned


def test_rebuild_restores_transient_availability_and_preserves_identity(tmp_path: Path):
    service, source, original, cleaned = _cleared_service(tmp_path)
    original_bytes = source.read_bytes()
    before_item = original.product_groups[0].items[0]

    response = service.rebuild_wmd_payload("managed-well:test")
    rebuilt = response.record
    item = rebuilt.product_groups[0].items[0]

    assert response.result.rebuilt_product_ids == ["curve:test:gr"]
    assert response.result.identities_preserved is True
    assert response.result.external_sources_touched is False
    assert source.read_bytes() == original_bytes
    assert rebuilt.wmdp_available is True
    assert rebuilt.wmdp_state == ManagedWmdpState.STAGED_IN_WMDP
    assert rebuilt.wmd_working_state == WmdWorkingState.AVAILABLE
    assert rebuilt.wmd_retention_state == WmdRetentionState.ACTIVE
    assert item.wmd_retention_state == WmdRetentionState.ACTIVE
    assert item.managed_product_uid == before_item.managed_product_uid
    assert item.managed_curve_uid == before_item.managed_curve_uid
    assert item.curve_uid == before_item.curve_uid
    assert rebuilt.metadata["metadata_overlay"] == cleaned.metadata["metadata_overlay"]
    assert rebuilt.metadata["qaqc_decision"] == cleaned.metadata["qaqc_decision"]
    assert rebuilt.source_references == cleaned.source_references
    assert any(ref.reference_type == WmdReferenceType.WMD for ref in rebuilt.wmd_references)


def test_rebuilt_payload_can_load_to_wdv_with_same_identities(tmp_path: Path):
    service, _source, original, _cleaned = _cleared_service(tmp_path)
    service.rebuild_wmd_payload("managed-well:test")
    loaded = service.load_managed_well_to_wdv("managed-well:test")
    item = loaded.record.product_groups[0].items[0]
    original_item = original.product_groups[0].items[0]

    assert loaded.result.loaded_product_ids == ["curve:test:gr"]
    assert item.managed_product_uid == original_item.managed_product_uid
    assert item.managed_curve_uid == original_item.managed_curve_uid
    contract = service.get_viewer_package_contract("managed-well:test")
    loaded_contract_item = contract["loaded_curve_items"][0]
    assert loaded_contract_item["managed_product_uid"] == str(original_item.managed_product_uid)
    assert loaded_contract_item["managed_curve_uid"] == str(original_item.managed_curve_uid)


def test_rebuild_rejects_changed_authoritative_source(tmp_path: Path):
    service, source, _original, _cleaned = _cleared_service(tmp_path)
    source.write_text(LAS_TEXT + "\n# changed", encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint changed"):
        service.rebuild_wmd_payload("managed-well:test")


def test_rebuild_rejects_active_or_uncleared_payload(tmp_path: Path):
    source = tmp_path / "external.las"
    source.write_text(LAS_TEXT, encoding="utf-8")
    fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
    record = _record(source, fingerprint)
    record.wmdp_available = True
    record.wmdp_state = ManagedWmdpState.STAGED_IN_WMDP
    record.product_groups[0].items[0].wmdp_state = ManagedWmdpState.STAGED_IN_WMDP
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repo)
    repo.upsert_record(record)

    with pytest.raises(ValueError, match="not cleared"):
        service.rebuild_wmd_payload("managed-well:test")
