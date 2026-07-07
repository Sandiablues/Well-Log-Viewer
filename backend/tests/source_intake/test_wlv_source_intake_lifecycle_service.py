import pytest
from app.source_intake.lifecycle_service import SourceIntakeLifecycleService
from app.source_intake.models import SourceFileCandidate, SourceIntakeCandidateRole, SourceIntakeFileType, SourceIntakeReferenceType, SourceIntakeRetentionState, SourceIntakeWorkingDataState

def make_candidate() -> SourceFileCandidate:
    return SourceFileCandidate(source_file_id="candidate-1", occurrence_id="occurrence-1", repository_id="repo-1", scan_id="scan-1", file_name="sample.las", original_path="/external/sample.las", relative_path="sample.las", file_extension=".las", detected_file_type=SourceIntakeFileType.LAS, candidate_role=SourceIntakeCandidateRole.WELL_LOG_CANDIDATE, size_bytes=10, modified_at="2026-07-06T00:00:00Z", checksum="abc")

def test_lifecycle_service_acquires_and_releases_reference() -> None:
    service = SourceIntakeLifecycleService(); item = make_candidate()
    service.acquire_reference(item, SourceIntakeReferenceType.WDV, "well-1", "loaded")
    assert item.reference_counts["wdv"] == 1
    assert item.retention_state == SourceIntakeRetentionState.ACTIVE
    assert service.release_reference(item, SourceIntakeReferenceType.WDV, "well-1") is True

def test_lifecycle_service_projects_inventory_state() -> None:
    class State:
        def __init__(self, value: str): self.value = value
    class Ref: source_id = "candidate-1"
    class Record:
        managed_well_id = "managed-well-1"; well_name = "Well 1"; source_references = [Ref()]; product_groups = []; wmdp_state = State("staged_in_wmdp"); wdv_state = State("loaded_to_wdv")
    service = SourceIntakeLifecycleService(); item = make_candidate()
    assert service.synchronize_inventory_record([item], Record()) == 1
    assert item.managed_well_id == "managed-well-1"
    assert item.working_data_state == SourceIntakeWorkingDataState.LOADED_IN_WMD
    assert item.reference_counts["wmd"] == 1
    assert item.reference_counts["wdv"] == 1

def test_lifecycle_service_rejects_blank_reference_owner() -> None:
    with pytest.raises(ValueError, match="owner_id"):
        SourceIntakeLifecycleService().acquire_reference(make_candidate(), SourceIntakeReferenceType.EXPORT, "")
