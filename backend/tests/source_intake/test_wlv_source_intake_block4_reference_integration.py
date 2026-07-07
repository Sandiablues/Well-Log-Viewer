from pathlib import Path
from types import SimpleNamespace

from app.source_intake.models import (
    SourceFileCandidate,
    SourceIntakeCandidateRole,
    SourceIntakeFileType,
    SourceIntakeReferenceType,
    SourceIntakeWorkingDataState,
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
        registration_status="registered",
        managed_well_id="managed-well:f5",
        managed_well_name="F5",
        wmdp_state="staged_in_wmdp",
        wdv_state="not_loaded",
    )


def _record(*, wmdp_state: str, wdv_state: str):
    return SimpleNamespace(
        managed_well_id="managed-well:f5",
        well_name="F5",
        wmdp_state=SimpleNamespace(value=wmdp_state),
        wdv_state=SimpleNamespace(value=wdv_state),
        source_references=[SimpleNamespace(source_id="source-file-1")],
        product_groups=[],
    )


def test_inventory_state_sync_acquires_and_releases_wdv_reference(tmp_path: Path) -> None:
    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    snapshot = service._load_snapshot()
    snapshot.candidates = [_candidate(tmp_path)]
    service._save_snapshot(snapshot)

    matched = service.synchronize_managed_well_reference_state(
        _record(wmdp_state="staged_in_wmdp", wdv_state="loaded_to_wdv")
    )
    assert matched == 1
    loaded = service._load_snapshot().candidates[0]
    assert loaded.reference_counts[SourceIntakeReferenceType.WMD.value] == 1
    assert loaded.reference_counts[SourceIntakeReferenceType.WDV.value] == 1
    assert loaded.working_data_state == SourceIntakeWorkingDataState.LOADED_IN_WMD

    service.synchronize_managed_well_reference_state(
        _record(wmdp_state="staged_in_wmdp", wdv_state="not_loaded")
    )
    unloaded = service._load_snapshot().candidates[0]
    assert unloaded.reference_counts[SourceIntakeReferenceType.WMD.value] == 1
    assert unloaded.reference_counts[SourceIntakeReferenceType.WDV.value] == 0


def test_inventory_state_sync_releases_wmd_and_wdv_after_wmd_removal(tmp_path: Path) -> None:
    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    snapshot = service._load_snapshot()
    snapshot.candidates = [_candidate(tmp_path)]
    service._save_snapshot(snapshot)

    service.synchronize_managed_well_reference_state(
        _record(wmdp_state="removed_from_wmdp", wdv_state="not_loaded")
    )
    removed = service._load_snapshot().candidates[0]
    assert removed.reference_counts[SourceIntakeReferenceType.WSI.value] == 1
    assert removed.reference_counts[SourceIntakeReferenceType.WMD.value] == 0
    assert removed.reference_counts[SourceIntakeReferenceType.WDV.value] == 0
    assert removed.working_data_state == SourceIntakeWorkingDataState.REMOVED_FROM_WMD
    assert removed.cleanup_eligible is False
