from app.source_intake.models import (
    ExternalSourceReference,
    SourceFileCandidate,
    SourceIntakeCandidateRole,
    SourceIntakeCurrentDecision,
    SourceIntakeFileType,
    SourceIntakeHumanDecision,
    SourceIntakeQaqcResult,
    SourceIntakeSavedWorkspaceSaveRequest,
    SourceIntakeSnapshot,
)
from app.source_intake.service import WlvSourceIntakeService


def _candidate(candidate_id: str = "candidate-1") -> SourceFileCandidate:
    return SourceFileCandidate(
        source_file_id=candidate_id,
        occurrence_id=f"occurrence-{candidate_id}",
        repository_id="repo-1",
        scan_id="scan-1",
        file_name="well.las",
        original_path="/external/well.las",
        relative_path="well.las",
        file_extension=".las",
        detected_file_type=SourceIntakeFileType.LAS,
        candidate_role=SourceIntakeCandidateRole.WELL_LOG_CANDIDATE,
        size_bytes=10,
        modified_at="2026-01-01T00:00:00Z",
        checksum="a" * 64,
        content_fingerprint="a" * 64,
        source_reference=ExternalSourceReference(
            source_uri="/external/well.las",
            display_name="well.las",
            source_format="LAS",
            fingerprint="a" * 64,
        ),
        current_decision=SourceIntakeCurrentDecision(
            decision=SourceIntakeHumanDecision.CORRECT,
            actor="tester",
            corrected_values={"well_name": "Corrected Well"},
        ),
        qaqc_status=SourceIntakeQaqcResult(),
    )


def test_saved_workspace_persists_references_decisions_and_viewer_state_only(tmp_path):
    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    candidate = _candidate()
    service._save_snapshot(SourceIntakeSnapshot(candidates=[candidate]))

    record = service.save_workspace(
        SourceIntakeSavedWorkspaceSaveRequest(
            name="Project A",
            candidate_ids=[candidate.source_file_id],
            viewer_state={"wdv_session_uid": "wdv-session-1", "depth_unit": "m"},
        )
    )

    assert record.retain_parsed_samples is False
    assert record.viewer_state["wdv_session_uid"] == "wdv-session-1"
    assert record.sources[0].source_reference.source_uri == "/external/well.las"
    assert record.sources[0].metadata_overlay == {"well_name": "Corrected Well"}
    assert not hasattr(record.sources[0], "parsed_metadata")

    snapshot = service._load_snapshot()
    assert snapshot.candidates[0].reference_counts["saved_workspace"] == 1
    assert len(snapshot.saved_workspaces) == 1


def test_deleting_saved_workspace_releases_source_reference(tmp_path):
    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    candidate = _candidate()
    service._save_snapshot(SourceIntakeSnapshot(candidates=[candidate]))
    saved = service.save_workspace(
        SourceIntakeSavedWorkspaceSaveRequest(
            name="Project A",
            candidate_ids=[candidate.source_file_id],
        )
    )

    response = service.delete_saved_workspace(saved.workspace_uid)
    assert response.released_source_count == 1
    snapshot = service._load_snapshot()
    assert snapshot.saved_workspaces == []
    assert snapshot.candidates[0].reference_counts["saved_workspace"] == 0


def test_updating_saved_workspace_releases_removed_candidates(tmp_path):
    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    first = _candidate("candidate-1")
    second = _candidate("candidate-2")
    service._save_snapshot(SourceIntakeSnapshot(candidates=[first, second]))
    saved = service.save_workspace(
        SourceIntakeSavedWorkspaceSaveRequest(
            name="Project A",
            candidate_ids=[first.source_file_id, second.source_file_id],
        )
    )

    service.save_workspace(
        SourceIntakeSavedWorkspaceSaveRequest(
            workspace_uid=saved.workspace_uid,
            name="Project A revised",
            candidate_ids=[second.source_file_id],
        )
    )
    snapshot = service._load_snapshot()
    by_id = {item.source_file_id: item for item in snapshot.candidates}
    assert by_id[first.source_file_id].reference_counts["saved_workspace"] == 0
    assert by_id[second.source_file_id].reference_counts["saved_workspace"] == 1
