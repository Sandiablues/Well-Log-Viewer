from __future__ import annotations
import json
from pathlib import Path
import pytest
from app.inventory.models import ManagedInventorySnapshot, ManagedProductGroup, ManagedProductGroupItem, ManagedSourceKind, ManagedSourceReference, ManagedWellRecord
from app.inventory.mwd_transient_flush import MwdTransientFlushRequest, MwdTransientFlushService
from app.inventory.repository import ManagedInventoryStoreError, ManagedWellInventoryRepository
from app.source_intake.models import SourceIntakeSnapshot

WELL_UID = "019f5203-7a11-7e01-8a01-000000000001"
SOURCE_UID = "019f5203-7a11-7e01-8a01-000000000002"
PRODUCT_UID = "019f5203-7a11-7e01-8a01-000000000003"
CURVE_UID = "019f5203-7a11-7e01-8a01-000000000004"

def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

def _service(tmp_path: Path):
    inventory_path = tmp_path / "managed_wells.json"
    source_path = tmp_path / "source_intake.json"
    workspace_path = tmp_path / "wdv_workspace.json"
    canonical_path = tmp_path / "canonical_sessions_v2_1.json"
    record = ManagedWellRecord(
        managed_well_id="managed:F-21-31", managed_well_uid=WELL_UID, well_id="F-21-31", well_name="F 21-31",
        source_references=[ManagedSourceReference(source_id="occ:test", managed_source_uid=SOURCE_UID, source_kind=ManagedSourceKind.LAS, display_name="F-21-31.las", checksum="same-content")],
        product_groups=[ManagedProductGroup(group_key="open_hole", group_label="Open hole", items=[ManagedProductGroupItem(product_id="curve:GR", managed_product_uid=PRODUCT_UID, managed_curve_uid=CURVE_UID, managed_source_uid=SOURCE_UID, display_name="GR", curve_name="GR", curve_type="gamma_ray", source_intake_candidate_id="occ:test")])],
    )
    _write_json(inventory_path, ManagedInventorySnapshot(records=[record]).model_dump(mode="json"))
    _write_json(source_path, SourceIntakeSnapshot().model_dump(mode="json"))
    _write_json(workspace_path, {"schema_version":"wlv_wdv_workspace_v2","workspace_id":"default","revision":4,"common_depth_unit":"m","active_managed_well_id":record.managed_well_id,"active_managed_well_uid":WELL_UID,"loaded_managed_well_ids":[record.managed_well_id],"loaded_managed_well_uids":[WELL_UID]})
    _write_json(canonical_path, {"schema_version":"wdv_canonical_sessions_v2_1","sessions":{WELL_UID:{"owned":"target"},"unrelated":{"owned":"other"}},"command_receipts":{WELL_UID:{"owned":"target"},"unrelated":{"owned":"other"}}})
    service = MwdTransientFlushService(repository=ManagedWellInventoryRepository(storage_path=inventory_path), source_intake_path=source_path, workspace_path=workspace_path, canonical_session_path=canonical_path)
    return service, {"inventory":inventory_path,"source":source_path,"workspace":workspace_path,"canonical":canonical_path}

def _request(*, dry_run=False):
    return MwdTransientFlushRequest(confirm="FLUSH_MWD_TRANSIENT_DATA", actor="regression-test", reason="Verify global transient MWD flush contract", dry_run=dry_run)

def test_dry_run_reports_removal_without_writing(tmp_path: Path) -> None:
    service, paths = _service(tmp_path)
    before = {name:path.read_bytes() for name,path in paths.items()}
    response = service.flush(request=_request(dry_run=True))
    assert response.dry_run is True
    assert response.removed_managed_well_count == 1
    assert response.removed_product_count == 1
    assert response.removed_source_reference_count == 1
    assert response.removed_workspace_loaded_count == 1
    assert response.removed_canonical_session_count == 1
    assert response.removed_command_receipt_group_count == 1
    assert {name:path.read_bytes() for name,path in paths.items()} == before

def test_flush_empties_inventory_and_workspace_and_preserves_unrelated_canonical_state(tmp_path: Path) -> None:
    service, paths = _service(tmp_path)
    response = service.flush(request=_request())
    assert response.ok is True
    assert json.loads(paths["inventory"].read_text())["records"] == []
    workspace = json.loads(paths["workspace"].read_text())
    assert workspace["loaded_managed_well_ids"] == []
    assert workspace["loaded_managed_well_uids"] == []
    assert workspace["active_managed_well_id"] is None
    assert workspace["active_managed_well_uid"] is None
    assert workspace["common_depth_unit"] == "m"
    canonical = json.loads(paths["canonical"].read_text())
    assert WELL_UID not in canonical["sessions"]
    assert WELL_UID not in canonical["command_receipts"]
    assert canonical["sessions"]["unrelated"] == {"owned":"other"}
    assert canonical["command_receipts"]["unrelated"] == {"owned":"other"}

def test_failed_post_write_validation_restores_every_store_byte_for_byte(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, paths = _service(tmp_path)
    before = {name:path.read_bytes() for name,path in paths.items()}
    monkeypatch.setattr(service, "_post_write_validate", lambda **_: (_ for _ in ()).throw(ValueError("forced post-write regression")))
    with pytest.raises(ManagedInventoryStoreError, match="all touched stores were restored"):
        service.flush(request=_request())
    assert {name:path.read_bytes() for name,path in paths.items()} == before
