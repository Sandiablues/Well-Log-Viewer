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
    WmdRetentionState,
    WmdSourceRecoveryState,
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


def _record(path: Path, fingerprint: str) -> ManagedWellRecord:
    curve_uid = new_uuid7_str()
    return ManagedWellRecord(
        managed_well_id="managed-well:test",
        managed_well_uid=new_uuid7_str(),
        well_id="test",
        well_name="Test",
        wmdp_available=False,
        wmdp_state=ManagedWmdpState.REMOVED_FROM_WMDP,
        source_references=[ManagedSourceReference(
            source_id="source:test", source_kind=ManagedSourceKind.LAS,
            display_name="external.las", original_path=str(path), checksum=fingerprint,
            metadata={"metadata_overlay": {"well_name": "Corrected"}},
        )],
        metadata={"metadata_overlay": {"field": "Corrected"}, "qaqc_decision": {"decision": "accepted"}},
        product_groups=[ManagedProductGroup(group_key="openhole", group_label="Openhole", items=[
            ManagedProductGroupItem(
                product_id="curve:test:gr", managed_product_uid=new_uuid7_str(),
                managed_curve_uid=curve_uid, curve_uid=curve_uid,
                display_name="GR", curve_name="GR", curve_type="Gamma Ray", curve_unit="API",
                source_kind="las", source_id="source:test", wmdp_state=ManagedWmdpState.REMOVED_FROM_WMDP,
                provenance={"original_path": str(path), "source_fingerprint": fingerprint, "source_curve_index": 1,
                            "metadata_overlay": {"curve_name": "Gamma Ray"}},
            )
        ])],
    )


def _cleared(tmp_path: Path):
    source = tmp_path / "external.las"
    source.write_text(LAS_TEXT, encoding="utf-8")
    fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repo)
    repo.upsert_record(_record(source, fingerprint))
    service.execute_wmd_cleanup("managed-well:test")
    return service, source, fingerprint


def _persisted(service: ManagedWellInventoryService):
    return service.repository.get_record("managed-well:test")


def test_missing_source_is_persisted_and_payload_stays_cleared(tmp_path: Path):
    service, source, _ = _cleared(tmp_path)
    source.unlink()
    with pytest.raises(ValueError, match="source is missing"):
        service.rebuild_wmd_payload("managed-well:test")
    record = _persisted(service)
    item = record.product_groups[0].items[0]
    assert record.wmd_source_recovery_state == WmdSourceRecoveryState.MISSING
    assert item.wmd_source_recovery_state == WmdSourceRecoveryState.MISSING
    assert item.wmd_working_state == WmdWorkingState.CLEARED
    assert item.wmd_retention_state == WmdRetentionState.CLEARED
    assert record.metadata["metadata_overlay"] == {"field": "Corrected"}
    assert record.metadata["qaqc_decision"] == {"decision": "accepted"}


def test_changed_source_is_persisted_without_accepting_new_fingerprint(tmp_path: Path):
    service, source, expected = _cleared(tmp_path)
    source.write_text(LAS_TEXT + "\n# changed", encoding="utf-8")
    changed = hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="fingerprint changed"):
        service.rebuild_wmd_payload("managed-well:test")
    record = _persisted(service)
    item = record.product_groups[0].items[0]
    assert record.wmd_source_recovery_state == WmdSourceRecoveryState.CHANGED
    assert item.wmd_source_recovery_state == WmdSourceRecoveryState.CHANGED
    assert item.wmd_observed_source_fingerprint == changed
    assert item.provenance["source_fingerprint"] == expected
    assert record.source_references[0].checksum == expected
    assert item.wmd_retention_state == WmdRetentionState.CLEARED


def test_inaccessible_source_state_does_not_restore_payload(tmp_path: Path):
    service, source, _ = _cleared(tmp_path)
    source.unlink()
    source.mkdir()
    with pytest.raises(ValueError, match="source is inaccessible"):
        service.rebuild_wmd_payload("managed-well:test")
    item = _persisted(service).product_groups[0].items[0]
    assert item.wmd_source_recovery_state == WmdSourceRecoveryState.INACCESSIBLE
    assert item.wmd_retention_state == WmdRetentionState.CLEARED


def test_rebuild_after_source_restored_returns_available_state(tmp_path: Path):
    service, source, _ = _cleared(tmp_path)
    original_bytes = source.read_bytes()
    source.unlink()
    with pytest.raises(ValueError, match="source is missing"):
        service.rebuild_wmd_payload("managed-well:test")
    source.write_bytes(original_bytes)
    response = service.rebuild_wmd_payload("managed-well:test")
    item = response.record.product_groups[0].items[0]
    assert response.record.wmd_source_recovery_state == WmdSourceRecoveryState.AVAILABLE
    assert item.wmd_source_recovery_state == WmdSourceRecoveryState.AVAILABLE
    assert item.wmd_retention_state == WmdRetentionState.ACTIVE
    assert source.read_bytes() == original_bytes
