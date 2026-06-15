from pathlib import Path

import pytest

from app.source_intake.models import SourceRepositoryCreateRequest
from app.source_intake.service import SourceIntakeError, WlvSourceIntakeService


def _write(path: Path, text: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_remove_source_repository_removes_repository_and_candidate_rows_only(tmp_path: Path) -> None:
    # WLV-WSI-REMOVE-SOURCE-1
    root_a = tmp_path / "well_folder_a"
    root_b = tmp_path / "well_folder_b"
    file_a = root_a / "remove_me.las"
    file_b = root_b / "keep_me.las"
    _write(file_a, "~Version\n")
    _write(file_b, "~Version\n")

    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repo_a = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root_a), name="RemoveMe"))
    repo_b = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root_b), name="KeepMe"))
    service.scan_repository(repo_a.repository_id)
    service.scan_repository(repo_b.repository_id)

    before = service.get_workbench()
    assert before.summary.repository_count == 2
    assert before.summary.file_count == 2

    response = service.remove_repository(repo_a.repository_id)
    after = response.workbench

    assert response.action == "remove_source_repository"
    assert response.destructive is False
    assert response.repository_removed is True
    assert response.candidate_rows_removed == 1
    assert [repo.repository_id for repo in after.repositories] == [repo_b.repository_id]
    assert [candidate.file_name for candidate in after.candidates] == ["keep_me.las"]
    assert after.summary.repository_count == 1
    assert after.summary.file_count == 1
    assert file_a.exists()
    assert file_b.exists()

    reloaded = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    persisted = reloaded.get_workbench()
    assert [repo.repository_id for repo in persisted.repositories] == [repo_b.repository_id]


def test_remove_source_repository_rejects_unknown_repository(tmp_path: Path) -> None:
    # WLV-WSI-REMOVE-SOURCE-1
    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")

    with pytest.raises(SourceIntakeError):
        service.remove_repository("missing-repository")
