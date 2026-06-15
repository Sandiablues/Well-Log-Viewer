from pathlib import Path

from app.source_intake.models import SourceRepositoryCreateRequest
from app.source_intake.service import WlvSourceIntakeService


def _write(path: Path, text: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_clear_workbench_candidate_rows_removes_only_selected_register_rows(tmp_path: Path) -> None:
    # WLV-WSI-CLEAR-CANDIDATE-ROWS-1
    root = tmp_path / "well_folder"
    keep_file = root / "keep.las"
    remove_file = root / "remove.pdf"
    _write(keep_file, "~Version\n")
    _write(remove_file, "%PDF")

    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root)))
    service.scan_repository(repository.repository_id)

    before = service.get_workbench()
    remove_candidate = next(candidate for candidate in before.candidates if candidate.file_name == "remove.pdf")

    response = service.clear_workbench_selection(candidate_ids=[remove_candidate.source_file_id])
    after = response.workbench

    assert response.action == "clear_candidate_register_rows"
    assert response.records_deleted == 1
    assert response.destructive is False
    assert [candidate.file_name for candidate in after.candidates] == ["keep.las"]
    assert keep_file.exists()
    assert remove_file.exists()
    assert after.summary.file_count == 1
    assert after.repositories[0].file_count == 1

    reloaded = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    persisted = reloaded.get_workbench()
    assert [candidate.file_name for candidate in persisted.candidates] == ["keep.las"]
