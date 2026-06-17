from pathlib import Path

from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.source_intake.models import (
    SourceIntakeBulkResolutionRequest,
    SourceIntakeRegisterRequest,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionDecision,
    SourceIntakeWellAssignmentMode,
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
WELL. Forge 21-31
~Curve
DEPT.FT : Depth
GR.GAPI : Gamma Ray
~ASCII
0 1
1 2
2 3
"""
GEOMETRY = """MD,INC,AZI,TVD,X_OFFSET,Y_OFFSET
0,0,0,0,0,0
100,2,90,99.9,3,0
200,4,90,199.4,10,0
"""


def test_geometry_assignment_persists_backend_owned_mdp_group(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / "FORGE_21_31.las").write_text(LAS)
    (root / "unrelated_name_deviation_survey.csv").write_text(GEOMETRY)

    source = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    inventory = ManagedWellInventoryService(
        repository=ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    )
    repository = source.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True)
    )
    scan = source.scan_repository(repository.repository_id)
    las = next(item for item in scan.candidates if item.file_name.endswith(".las"))
    geometry = next(item for item in scan.candidates if item.file_name.endswith(".csv"))

    source.resolve_candidates(SourceIntakeBulkResolutionRequest(decisions=[
        SourceIntakeResolutionDecision(
            occurrence_id=las.occurrence_id,
            action=SourceIntakeResolutionAction.WELL_ASSIGNED,
            actor="test",
            reason="Create the managed well used by the geometry assignment test.",
            assignment_mode=SourceIntakeWellAssignmentMode.NEW_WELL,
            new_well_values={"well_name": "Forge 21-31"},
        )
    ]))

    las_response = source.register_candidates(
        SourceIntakeRegisterRequest(candidate_ids=[las.source_file_id]),
        inventory_service=inventory,
    )
    managed_well_id = las_response.results[0].managed_well_id
    assert managed_well_id

    source.resolve_candidates(SourceIntakeBulkResolutionRequest(decisions=[
        SourceIntakeResolutionDecision(
            occurrence_id=geometry.occurrence_id,
            action=SourceIntakeResolutionAction.WELL_ASSIGNED,
            actor="test",
            reason="Assign geometry to existing managed well.",
            assignment_mode=SourceIntakeWellAssignmentMode.EXISTING_WELL,
            target_managed_well_id=managed_well_id,
        )
    ]))

    response = source.register_candidates(
        SourceIntakeRegisterRequest(candidate_ids=[geometry.source_file_id]),
        inventory_service=inventory,
    )
    assert response.registered_count == 1
    assert response.results[0].managed_well_id == managed_well_id
    assert response.results[0].registered_trajectory_count == 1

    record = inventory.get_well(managed_well_id)
    geometry_group = next(
        group for group in record.product_groups
        if group.group_key == "wellbore_geometry"
    )
    assert geometry_group.group_label == "Wellbore Geometry"
    assert len(geometry_group.items) == 1
    assert geometry_group.items[0].source_id == geometry.source_file_id
    assert any(ref.source_id == geometry.source_file_id for ref in record.source_references)
    assert len(record.metadata["wbv_trajectory_records"]) == 1
