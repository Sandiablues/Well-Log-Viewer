from pathlib import Path

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


def _record(source_path: Path) -> ManagedWellRecord:
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
                checksum="a" * 64,
                metadata={"metadata_overlay": {"well_name": "Corrected"}},
            )
        ],
        metadata={
            "viewer_package_contract": {"curves": ["GR"]},
            "wdv_load_session_contract": {"source_product_ids": ["curve:test:gr"]},
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
                        display_name="GR",
                        curve_name="GR",
                        curve_type="Gamma Ray",
                        source_id="source:test",
                        wmdp_state=ManagedWmdpState.REMOVED_FROM_WMDP,
                        provenance={
                            "original_path": str(source_path),
                            "source_fingerprint": "a" * 64,
                            "las_samples_uri": "/tmp/wlv-owned-derived/samples.json.gz",
                            "metadata_overlay": {"curve_name": "Gamma Ray"},
                        },
                    )
                ],
            )
        ],
    )


def test_cleanup_execution_is_guarded_by_eligibility(tmp_path: Path):
    source = tmp_path / "external.las"
    source.write_text("external authoritative bytes", encoding="utf-8")
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repo)
    record = _record(source)
    service.wmd_lifecycle_service.acquire_reference(
        record, WmdReferenceType.SAVED_WORKSPACE, "workspace:test"
    )
    repo.upsert_record(record)

    with pytest.raises(ValueError, match="not eligible"):
        service.execute_wmd_cleanup("managed-well:test")

    assert source.read_text(encoding="utf-8") == "external authoritative bytes"


def test_cleanup_clears_only_transient_viewer_payload_and_preserves_rebuild_contract(tmp_path: Path):
    source = tmp_path / "external.las"
    original = b"external authoritative bytes"
    source.write_bytes(original)
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repo)
    repo.upsert_record(_record(source))

    response = service.execute_wmd_cleanup("managed-well:test")
    record = response.record
    item = record.product_groups[0].items[0]

    assert response.result.external_sources_touched is False
    assert response.result.cleared_product_ids == ["curve:test:gr"]
    assert source.read_bytes() == original
    assert record.source_references[0].original_path == str(source)
    assert record.source_references[0].checksum == "a" * 64
    assert record.source_references[0].metadata["metadata_overlay"]["well_name"] == "Corrected"
    assert record.metadata["metadata_overlay"]["field"] == "Corrected field"
    assert record.metadata["qaqc_decision"]["decision"] == "accepted"
    assert "viewer_package_contract" not in record.metadata
    assert "wdv_load_session_contract" not in record.metadata
    assert record.viewer_packages == []
    assert record.wmd_working_state == WmdWorkingState.CLEARED
    assert record.wmd_retention_state == WmdRetentionState.CLEARED
    assert record.wmd_cleanup_eligible is False
    assert item.wmd_working_state == WmdWorkingState.CLEARED
    assert item.provenance["original_path"] == str(source)
    assert item.provenance["source_fingerprint"] == "a" * 64
    assert item.provenance["metadata_overlay"]["curve_name"] == "Gamma Ray"


def test_partial_cleanup_does_not_clear_record_payload(tmp_path: Path):
    source = tmp_path / "external.las"
    source.write_text("external", encoding="utf-8")
    record = _record(source)
    second = ManagedProductGroupItem(
        product_id="curve:test:rhob",
        display_name="RHOB",
        curve_name="RHOB",
        curve_type="Bulk Density",
        wmdp_state=ManagedWmdpState.STAGED_IN_WMDP,
    )
    record.product_groups[0].items.append(second)
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repo)
    repo.upsert_record(record)

    response = service.execute_wmd_cleanup(
        "managed-well:test", product_ids=["curve:test:gr"]
    )
    items = {item.product_id: item for item in response.record.product_groups[0].items}
    assert response.result.cleared_record_payload is False
    assert response.record.metadata["viewer_package_contract"] == {"curves": ["GR"]}
    assert items["curve:test:gr"].wmd_retention_state == WmdRetentionState.CLEARED
    assert items["curve:test:rhob"].wmd_retention_state == WmdRetentionState.ACTIVE
