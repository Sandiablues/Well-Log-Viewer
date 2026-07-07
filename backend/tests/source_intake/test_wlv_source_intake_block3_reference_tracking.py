from pathlib import Path

from app.source_intake.models import (
    SourceFileCandidate,
    SourceIntakeCandidateRole,
    SourceIntakeFileType,
    SourceIntakeReferenceType,
    SourceIntakeRetentionState,
)
from app.source_intake.service import WlvSourceIntakeService


def _candidate(tmp_path: Path) -> SourceFileCandidate:
    source = tmp_path / "F5.dlis"
    source.write_bytes(b"dlis-test")
    return SourceFileCandidate(
        source_file_id="source-file-1",
        occurrence_id="occurrence-1",
        repository_id="repository-1",
        scan_id="scan-1",
        file_name=source.name,
        original_path=str(source),
        relative_path=source.name,
        file_extension=".dlis",
        detected_file_type=SourceIntakeFileType.DLIS,
        candidate_role=SourceIntakeCandidateRole.WELL_LOG_CANDIDATE,
        size_bytes=source.stat().st_size,
        modified_at="2026-07-06T00:00:00+00:00",
        checksum="abc",
    )


def test_candidate_has_explicit_wsi_reference_by_default(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    assert candidate.reference_counts["wsi"] == 1
    assert candidate.active_reference_count == 1
    assert candidate.retention_state == SourceIntakeRetentionState.ACTIVE
    assert candidate.cleanup_eligible is False


def test_reference_types_are_idempotent_and_releaseable(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    first = candidate.acquire_reference(SourceIntakeReferenceType.WDV, "canvas-1")
    second = candidate.acquire_reference(SourceIntakeReferenceType.WDV, "canvas-1")
    assert first.reference_uid == second.reference_uid
    assert candidate.reference_counts["wdv"] == 1
    assert candidate.release_reference(SourceIntakeReferenceType.WDV, "canvas-1") is True
    assert candidate.reference_counts["wdv"] == 0


def test_all_reference_classes_are_supported(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    for reference_type in (
        SourceIntakeReferenceType.WMD,
        SourceIntakeReferenceType.WDV,
        SourceIntakeReferenceType.WBV,
        SourceIntakeReferenceType.EXPORT,
        SourceIntakeReferenceType.SAVED_WORKSPACE,
    ):
        candidate.acquire_reference(reference_type, f"owner-{reference_type.value}")
    assert candidate.active_reference_count == 6
    assert all(candidate.reference_counts[item.value] == 1 for item in SourceIntakeReferenceType)


def test_service_persists_acquire_and_release(tmp_path: Path) -> None:
    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    candidate = _candidate(tmp_path)
    snapshot = service._load_snapshot()
    snapshot.candidates = [candidate]
    service._save_snapshot(snapshot)

    binding = service.acquire_candidate_reference(
        candidate.source_file_id,
        SourceIntakeReferenceType.EXPORT,
        "export-job-1",
        "Metadata overlay export is active.",
    )
    assert binding.reference_type == SourceIntakeReferenceType.EXPORT

    reloaded = service._load_snapshot().candidates[0]
    assert reloaded.reference_counts["export"] == 1

    released = service.release_candidate_reference(
        candidate.source_file_id,
        SourceIntakeReferenceType.EXPORT,
        "export-job-1",
    )
    assert released.reference_counts["export"] == 0
    assert released.cleanup_eligible is False
