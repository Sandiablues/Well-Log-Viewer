from pathlib import Path

from backend.app.source_intake.models import SourceRepositoryCreateRequest
from backend.app.source_intake.service import WlvSourceIntakeService


def _write(path: Path, text: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_source_intake_scans_repository_and_classifies_candidates(tmp_path: Path) -> None:
    root = tmp_path / "Forge_21_31"
    _write(root / "FORGE_21_31.las", "~Version\n")
    _write(root / "report.pdf", "%PDF")
    _write(root / "raster.cgm", "CGM")
    _write(root / "notes.bin", "unknown")

    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    result = service.scan_repository(repository.repository_id)

    assert result.ok is True
    assert result.scan_scope == "root_plus_subfolders"
    assert result.file_count == 4
    roles = {candidate.file_name: candidate.candidate_role for candidate in result.candidates}
    assert roles["FORGE_21_31.las"] == "well_log_candidate"
    assert roles["report.pdf"] == "supporting_document_candidate"
    assert roles["raster.cgm"] == "raster_image_candidate"
    assert roles["notes.bin"] == "other_review_required"

    unknown = next(candidate for candidate in result.candidates if candidate.file_name == "notes.bin")
    assert unknown.review_required is True
    assert unknown.checksum
    assert unknown.parser_status == "not_parsed"


def test_source_intake_include_subfolders_toggle(tmp_path: Path) -> None:
    root = tmp_path / "well_folder"
    _write(root / "root.las")
    _write(root / "child" / "child.las")

    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=False))
    result = service.scan_repository(repository.repository_id)

    assert result.scan_scope == "root_only"
    assert [candidate.relative_path for candidate in result.candidates] == ["root.las"]

    result = service.scan_repository(repository.repository_id, include_subfolders=True)
    assert result.scan_scope == "root_plus_subfolders"
    assert sorted(candidate.relative_path for candidate in result.candidates) == ["child/child.las", "root.las"]


def test_source_intake_workbench_and_clear_are_non_destructive(tmp_path: Path) -> None:
    root = tmp_path / "well_folder"
    _write(root / "root.las")

    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root)))
    service.scan_repository(repository.repository_id)

    before = service.get_workbench()
    response = service.clear_workbench_selection()
    after = service.get_workbench()

    assert response.destructive is False
    assert response.records_deleted == 0
    assert before.summary.file_count == 1
    assert after.summary.file_count == 1
    assert after.candidates[0].file_name == "root.las"


def test_source_intake_persists_repository_and_candidates(tmp_path: Path) -> None:
    root = tmp_path / "well_folder"
    _write(root / "root.las")
    storage = tmp_path / "source_intake.json"

    service = WlvSourceIntakeService(storage_path=storage)
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root)))
    service.scan_repository(repository.repository_id)

    reloaded = WlvSourceIntakeService(storage_path=storage)
    workbench = reloaded.get_workbench()

    assert workbench.summary.repository_count == 1
    assert workbench.summary.file_count == 1
    assert workbench.repositories[0].repository_id == repository.repository_id
    assert workbench.candidates[0].relative_path == "root.las"


def test_source_intake_health_reserves_future_representation_step(tmp_path: Path) -> None:
    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    health = service.health()

    assert health["service"] == "wlv-source-intake"
    assert health["conversion_step_enabled"] is False
    assert health["reserved_future_representation_step"] is True
