from pathlib import Path

from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.source_intake.models import (
    SourceIntakeBulkResolutionRequest,
    SourceIntakeRegisterRequest,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionDecision,
    SourceIntakeResolutionState,
    SourceRepositoryCreateRequest,
)
from app.source_intake.service import WlvSourceIntakeService
from app.wbv.service import WbvService


GEOMETRY_CSV = """MD,INC,AZI,TVD,X,Y
0,0,0,0,0,0
100,2,90,99.9,3,0
200,4,90,199.4,10,0
"""

BAD_GEOMETRY_CSV = """A,B,C
1,2,3
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _services(tmp_path: Path):
    source = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    inventory = ManagedWellInventoryService(repository=repository)
    return source, inventory, repository




def _resolve_geometry(source: WlvSourceIntakeService, candidate) -> None:
    source.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=candidate.occurrence_id,
                    action=SourceIntakeResolutionAction.WARNING_ACCEPTED,
                    actor="test",
                    reason="Geometry mapping and QAQC warnings reviewed.",
                    accepted_warning_codes=["geometry_review"],
                )
            ]
        )
    )

    # WLV-WSI-GEOMETRY-EXPLICIT-WELL-RESOLUTION-REGRESSION-ALIGNMENT:
    # Filename/path text is no longer authoritative well identity. Legacy
    # geometry registration tests explicitly model the required human correction.
    refreshed = next(
        item
        for item in source.get_workbench().candidates
        if item.source_file_id == candidate.source_file_id
    )
    if (
        refreshed.resolved_metadata is None
        or not refreshed.resolved_metadata.well_name.value
    ):
        source.resolve_candidates(
            SourceIntakeBulkResolutionRequest(
                decisions=[
                    SourceIntakeResolutionDecision(
                        occurrence_id=refreshed.occurrence_id,
                        action=SourceIntakeResolutionAction.MANUAL_CORRECTION,
                        actor="test",
                        reason="Explicitly confirm geometry destination well.",
                        resolved_values={"well_name": "Forge 21-31"},
                    )
                ]
            )
        )


def _scan_geometry(tmp_path: Path, file_name: str, text: str):
    root = tmp_path / "source"
    _write(root / file_name, text)
    source, inventory, repository = _services(tmp_path)
    source_repository = source.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    result = source.scan_repository(source_repository.repository_id)
    return source, inventory, repository, result.candidates[0]


def test_parsed_wellbore_geometry_candidate_registers_as_managed_trajectory(tmp_path: Path) -> None:
    source, inventory, repository, candidate = _scan_geometry(
        tmp_path,
        "FORGE_21_31_Final_Deviation_Survey.csv",
        GEOMETRY_CSV,
    )

    _resolve_geometry(source, candidate)

    response = source.register_candidates(
        SourceIntakeRegisterRequest(
            candidate_ids=[candidate.source_file_id],
            approval={"approved_by": "test", "approval_note": "geometry registration approval"},
        ),
        inventory_service=inventory,
    )

    assert response.registered_count == 1
    assert response.skipped_count == 0
    result = response.results[0]
    assert result.status == "registered"
    assert result.registered_curve_count == 0
    assert result.registered_trajectory_count == 1
    assert result.managed_well_id is not None

    record = inventory.get_well(result.managed_well_id)
    trajectories = record.metadata["wbv_trajectory_records"]
    assert len(trajectories) == 1
    trajectory = trajectories[0]
    assert trajectory["source_file_id"] == candidate.source_file_id
    assert trajectory["status"] == "approved"
    assert trajectory["wbv_eligible"] is True
    assert trajectory["is_active"] is False
    assert trajectory["station_count"] == 3
    assert trajectory["md_min"] == 0.0
    assert trajectory["md_max"] == 200.0
    assert "active_trajectory_id" not in record.metadata
    assert record.metadata["wellbore_geometry_status"] == "registered_trajectory_available"

    wbv = WbvService(repository=repository).list_trajectories(result.managed_well_id)
    assert len(wbv.trajectories) == 1
    assert wbv.trajectories[0].source_file_id == candidate.source_file_id
    assert wbv.trajectories[0].trajectory_package["source_intake_candidate_id"] == candidate.source_file_id


def test_geometry_registration_preserves_existing_las_inventory_record(tmp_path: Path) -> None:
    las = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. Forge 21-31 : Well name
UWI. 1234567890 : Unique well identifier
COMP. Ormat Nevada, Inc. : Company
FLD. Carson Field : Field
BLOCK. Carson Block : Block
~Curve
DEPT.FT : Depth
GR.GAPI : Gamma Ray
~ASCII
100.0 50.0
101.0 51.0
102.0 52.0
"""
    root = tmp_path / "source"
    _write(root / "FORGE_21_31.las", las)
    _write(root / "FORGE_21_31_Final_Deviation_Survey.csv", GEOMETRY_CSV)

    source, inventory, repository = _services(tmp_path)
    source_repository = source.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    scan = source.scan_repository(source_repository.repository_id)
    las_candidate = next(candidate for candidate in scan.candidates if candidate.file_name.endswith(".las"))
    geom_candidate = next(candidate for candidate in scan.candidates if candidate.candidate_role == "wellbore_geometry_candidate")

    las_response = source.register_candidates(SourceIntakeRegisterRequest(candidate_ids=[las_candidate.source_file_id]), inventory_service=inventory)
    assert las_response.registered_count == 1
    assert las_response.results[0].status == "registered"
    assert las_response.results[0].managed_well_id is not None

    _resolve_geometry(source, geom_candidate)
    geometry_response = source.register_candidates(SourceIntakeRegisterRequest(candidate_ids=[geom_candidate.source_file_id]), inventory_service=inventory)
    assert geometry_response.registered_count == 1
    assert geometry_response.results[0].status == "registered"
    assert geometry_response.results[0].managed_well_id is not None

    assert las_response.results[0].managed_well_id == geometry_response.results[0].managed_well_id
    record = inventory.get_well(las_response.results[0].managed_well_id)
    curve_items = [
        item
        for group in record.product_groups
        if group.group_key != "wellbore_geometry"
        for item in group.items
    ]
    geometry_group = next(
        group for group in record.product_groups
        if group.group_key == "wellbore_geometry"
    )
    assert len(curve_items) == 1
    assert len(geometry_group.items) == 1
    assert len(record.metadata["wbv_trajectory_records"]) == 1
    assert any(ref.source_id == geom_candidate.source_file_id for ref in record.source_references)


def test_parse_failed_geometry_candidate_is_blocked_from_registration(tmp_path: Path) -> None:
    source, inventory, _repository, candidate = _scan_geometry(
        tmp_path,
        "FORGE_21_31_Final_Deviation_Survey.csv",
        BAD_GEOMETRY_CSV,
    )

    response = source.register_candidates(
        SourceIntakeRegisterRequest(candidate_ids=[candidate.source_file_id]),
        inventory_service=inventory,
    )

    assert response.registered_count == 0
    assert response.skipped_count == 1
    assert response.results[0].status == "blocked"
    assert "parser_status" in response.results[0].reason
    assert inventory.list_wells() == []


def test_geometry_registration_reparses_and_registers_all_61_stations(tmp_path: Path) -> None:
    rows = ["MD,INC,AZI,TVD,Northing,Easting,X_OFFSET,Y_OFFSET"]
    rows.extend(
        f"{index * 100},{min(index, 30)},{(index * 5) % 360},{index * 90},{5000 + index},{6000 + index},{index * 10},{index * 20}"
        for index in range(61)
    )
    source, inventory, repository, candidate = _scan_geometry(
        tmp_path,
        "FORGE_21_31_deviation_survey_2000ft_offset_bottom30_log.csv",
        "\n".join(rows) + "\n",
    )
    assert candidate.geometry_preview.station_count == 61
    assert candidate.geometry_preview.preview_station_count == 25
    _resolve_geometry(source, candidate)

    response = source.register_candidates(
        SourceIntakeRegisterRequest(
            candidate_ids=[candidate.source_file_id],
            approval={"approved_by": "test", "approval_note": "full geometry registration"},
        ),
        inventory_service=inventory,
    )

    assert response.registered_count == 1
    saved_candidate = source.get_workbench().candidates[0]
    assert saved_candidate.resolution_state == SourceIntakeResolutionState.REGISTERED
    record = inventory.get_well(response.results[0].managed_well_id)
    trajectory = record.metadata["wbv_trajectory_records"][0]
    package = trajectory["trajectory_package"]
    assert trajectory["station_count"] == 61
    assert trajectory["geometry_class"] == "registered_deviation_survey_full"
    assert package["method"] == "source_intake_full_registration"
    assert package["source_station_count"] == 61
    assert package["preview_station_count"] == 25
    assert len(package["stations"]) == 61
    assert len(package["render_points"]) == 61
    assert package["column_mapping"]["inclination"] == "INC"
    assert package["column_mapping"]["northing"] == "Northing"
    assert package["column_mapping"]["easting"] == "Easting"
    assert package["column_mapping"]["x_offset"] == "X_OFFSET"
    assert package["column_mapping"]["y_offset"] == "Y_OFFSET"
    assert trajectory["is_active"] is False
    assert "active_trajectory_id" not in record.metadata
