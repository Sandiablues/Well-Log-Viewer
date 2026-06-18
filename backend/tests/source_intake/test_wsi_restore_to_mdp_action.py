from pathlib import Path

from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.source_intake.models import (
    SourceIntakeBulkResolutionRequest,
    SourceIntakeRegisterRequest,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionDecision,
    SourceIntakeRestoreToMdpRequest,
    SourceRepositoryCreateRequest,
)
from app.source_intake.service import WlvSourceIntakeService


LAS = """~Version
VERS. 2.0
~Well
STRT.FT 0
STOP.FT 2
STEP.FT 1
NULL. -999.25
WELL. Restore Test
~Curve
DEPT.FT : Depth
GR.GAPI : Gamma Ray
~ASCII
0 1
1 2
2 3
"""


def test_wsi_restore_to_mdp_uses_retained_msi_registration(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "restore_test.las").write_text(LAS)

    source = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    inventory = ManagedWellInventoryService(
        repository=ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    )

    repository = source.create_repository(
        SourceRepositoryCreateRequest(root_path=str(source_root), include_subfolders=True)
    )
    scan = source.scan_repository(repository.repository_id)
    candidate = next(item for item in scan.candidates if item.file_name.endswith(".las"))

    source.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=candidate.occurrence_id,
                    action=SourceIntakeResolutionAction.CONFIRM_SUGGESTION,
                    actor="restore-test",
                    reason="Confirm detected well identity before registration.",
                )
            ]
        )
    )

    registered = source.register_candidates(
        SourceIntakeRegisterRequest(candidate_ids=[candidate.source_file_id]),
        inventory_service=inventory,
    )
    assert registered.registered_count == 1
    managed_well_id = registered.results[0].managed_well_id
    assert managed_well_id

    inventory.remove_managed_data_from_mdp(managed_well_ids=[managed_well_id])
    response = source.restore_candidates_to_mdp(
        SourceIntakeRestoreToMdpRequest(candidate_ids=[candidate.source_file_id]),
        inventory_service=inventory,
    )

    assert response.restored_count == 1
    assert response.blocked_count == 0
    assert response.results[0].status == "restored"
    restored = inventory.get_well(managed_well_id)
    assert restored.wmdp_available is True
    assert restored.wmdp_state.value == "staged_in_wmdp"
    candidate_after = next(
        item for item in source.get_workbench().candidates
        if item.source_file_id == candidate.source_file_id
    )
    assert candidate_after.wmdp_state == "staged_in_wmdp"
