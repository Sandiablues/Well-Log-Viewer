from pathlib import Path

from app.identity.uuid7 import new_uuid7_str
from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedWdvState,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.wdv_workspace import WdvWorkspaceService


def test_workspace_returns_and_persists_active_identity_pair(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    uid = new_uuid7_str()
    record = ManagedWellRecord(
        managed_well_id="managed-well:test",
        managed_well_uid=uid,
        well_id="test",
        well_name="Test",
        product_groups=[
            ManagedProductGroup(
                group_key="logs",
                group_label="Logs",
                items=[
                    ManagedProductGroupItem(
                        product_id="curve:test",
                        product_type="curve",
                        display_name="GR",
                        curve_name="GR",
                        curve_type="Gamma Ray",
                        wdv_state=ManagedWdvState.LOADED_TO_WDV,
                    )
                ],
            )
        ],
    )
    snapshot = repository.snapshot()
    repository.write_snapshot(snapshot.model_copy(update={"records": [record]}))
    service = WdvWorkspaceService(repository, tmp_path / "wdv_workspace.json")

    workspace = service.get_workspace()

    assert workspace.contract_version == "wdv_workspace_v2"
    assert workspace.active_managed_well_id == record.managed_well_id
    assert workspace.active_managed_well_uid == uid
    assert workspace.loaded_wells[0].managed_well_id == record.managed_well_id
    assert workspace.loaded_wells[0].managed_well_uid == uid

    restored = service.get_workspace()

    assert restored.contract_version == "wdv_workspace_v2"
    assert restored.active_managed_well_id == record.managed_well_id
    assert restored.active_managed_well_uid == uid
    assert restored.loaded_wells[0].managed_well_uid == uid
