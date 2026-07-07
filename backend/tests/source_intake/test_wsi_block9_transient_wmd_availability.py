from pathlib import Path

from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.source_intake.models import (
    SourceIntakeBulkResolutionRequest, SourceIntakeRegisterRequest,
    SourceIntakeResolutionAction, SourceIntakeResolutionDecision,
    SourceIntakeWmdAvailabilityStatus, SourceIntakeWorkingDataState,
    SourceRepositoryCreateRequest,
)
from app.source_intake.service import WlvSourceIntakeService

LAS = """~Version
VERS. 2.0
~Well
STRT.FT 100
STOP.FT 101
STEP.FT 1
NULL. -999.25
WELL. TEST-1
~Curve
DEPT.FT
GR.GAPI
~ASCII
100 50
101 51
"""

def test_registration_compatibility_projects_transient_wmd_availability(tmp_path: Path):
    root = tmp_path / "source"; root.mkdir(); (root / "test.las").write_text(LAS)
    source = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    inventory = ManagedWellInventoryService(repository=ManagedWellInventoryRepository(tmp_path / "managed.json"))
    repo = source.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    candidate = source.scan_repository(repo.repository_id).candidates[0]
    source.resolve_candidates(SourceIntakeBulkResolutionRequest(decisions=[SourceIntakeResolutionDecision(
        occurrence_id=candidate.occurrence_id, action=SourceIntakeResolutionAction.WARNING_ACCEPTED,
        actor="test", reason="Reviewed", accepted_warning_codes=["missing_uwi"]
    )]))
    response = source.register_candidates(SourceIntakeRegisterRequest(candidate_ids=[candidate.source_file_id]), inventory_service=inventory)
    updated = next(row for row in response.workbench.candidates if row.source_file_id == candidate.source_file_id)
    assert updated.wmd_availability_status == SourceIntakeWmdAvailabilityStatus.LOADED
    assert updated.working_data_state == SourceIntakeWorkingDataState.LOADED_IN_WMD
    assert updated.is_available_to_wmd
    assert updated.registration_status == "registered"  # compatibility alias only

def test_legacy_registered_record_maps_to_transient_availability():
    from app.source_intake.models import SourceFileCandidate, SourceIntakeCandidateRole, SourceIntakeFileType
    row = SourceFileCandidate(
        source_file_id="x", occurrence_id="x", repository_id="r", scan_id="s", file_name="x.las",
        original_path="/external/x.las", relative_path="x.las", file_extension=".las",
        detected_file_type=SourceIntakeFileType.LAS, candidate_role=SourceIntakeCandidateRole.WELL_LOG_CANDIDATE,
        size_bytes=1, modified_at="now", checksum="abc", registration_status="registered"
    )
    assert row.wmd_availability_status == SourceIntakeWmdAvailabilityStatus.AVAILABLE
    assert row.is_available_to_wmd
