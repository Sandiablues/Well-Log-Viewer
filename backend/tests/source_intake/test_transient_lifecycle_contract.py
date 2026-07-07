from pathlib import Path

from app.source_intake.models import (
    SourceFileCandidate,
    SourceIntakeCandidateRole,
    SourceIntakeFileType,
    SourceIntakeRetentionState,
    SourceIntakeWorkingDataState,
    SourceIntakeSnapshot,
)
from app.source_intake.service import WlvSourceIntakeService


def _candidate(*, registration_status="not_registered", wmdp_state=None):
    return SourceFileCandidate(
        source_file_id="source-1",
        repository_id="repo-1",
        scan_id="scan-1",
        file_name="example.las",
        original_path="/external/example.las",
        relative_path="example.las",
        file_extension=".las",
        detected_file_type=SourceIntakeFileType.LAS,
        candidate_role=SourceIntakeCandidateRole.WELL_LOG_CANDIDATE,
        size_bytes=123,
        modified_at="2026-07-06T00:00:00+00:00",
        checksum="abc123",
        registration_status=registration_status,
        wmdp_state=wmdp_state,
    )


def test_new_candidate_is_active_wsi_only_and_not_cleanup_eligible():
    candidate = _candidate()

    assert candidate.working_data_state == SourceIntakeWorkingDataState.WSI_ONLY
    assert candidate.retention_state == SourceIntakeRetentionState.ACTIVE
    assert candidate.cleanup_eligible is False


def test_registered_candidate_is_available_to_wmd():
    candidate = _candidate(registration_status="registered")
    assert candidate.working_data_state == SourceIntakeWorkingDataState.AVAILABLE_TO_WMD


def test_staged_candidate_is_loaded_in_wmd():
    candidate = _candidate(registration_status="registered", wmdp_state="staged_in_wmdp")
    assert candidate.working_data_state == SourceIntakeWorkingDataState.LOADED_IN_WMD


def test_removed_candidate_is_recorded_without_enabling_cleanup():
    candidate = _candidate(registration_status="registered", wmdp_state="removed_from_wmdp")
    assert candidate.working_data_state == SourceIntakeWorkingDataState.REMOVED_FROM_WMD
    assert candidate.retention_state == SourceIntakeRetentionState.ACTIVE
    assert candidate.cleanup_eligible is False


def test_snapshot_persistence_synchronizes_lifecycle(tmp_path: Path):
    storage = tmp_path / "source_intake.json"
    service = WlvSourceIntakeService(storage_path=storage)
    candidate = _candidate()
    candidate.registration_status = "registered"
    candidate.wmdp_state = "staged_in_wmdp"
    snapshot = SourceIntakeSnapshot(candidates=[candidate])

    service._save_snapshot(snapshot)
    reloaded = service._load_snapshot()

    assert reloaded.candidates[0].working_data_state == SourceIntakeWorkingDataState.LOADED_IN_WMD
    assert reloaded.candidates[0].retention_state == SourceIntakeRetentionState.ACTIVE
    assert reloaded.candidates[0].cleanup_eligible is False
