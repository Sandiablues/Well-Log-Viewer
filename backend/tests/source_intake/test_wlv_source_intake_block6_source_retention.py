from pathlib import Path
import pytest

from app.source_intake.lifecycle_service import SourceIntakeLifecycleService
from app.source_intake.models import SourceMaterialization
from app.source_intake.service import WlvSourceIntakeService

LAS = b"""~Version Information\nVERS. 2.0\n~Well Information\nWELL. QUICK\n~Curve Information\nDEPT.M\nGR.API\n~ASCII\n1000 50\n"""


def test_external_repository_remains_external_and_untouched(tmp_path: Path) -> None:
    external = tmp_path / "external"
    external.mkdir()
    source = external / "well.las"
    source.write_bytes(LAS)
    service = WlvSourceIntakeService(storage_path=tmp_path / "state" / "source_intake.json")
    repo = service.create_repository(type("R", (), {"root_path": str(external), "name": "External", "include_subfolders": False})())
    result = service.scan_repository(repo.repository_id)
    assert result.repository.materialization == SourceMaterialization.EXTERNAL_REFERENCE
    assert result.repository.wlv_owned_temporary_storage is False
    assert result.candidates[0].source_reference.materialization == SourceMaterialization.EXTERNAL_REFERENCE
    service.remove_repository(repo.repository_id)
    assert source.read_bytes() == LAS


def test_browser_upload_is_isolated_temporary_materialization(tmp_path: Path) -> None:
    service = WlvSourceIntakeService(storage_path=tmp_path / "state" / "source_intake.json")
    first = service.ingest_uploaded_files([("first.las", LAS)])
    second = service.ingest_uploaded_files([("second.las", LAS.replace(b"QUICK", b"QUICK2"))])
    assert first.file_count == 1
    assert second.file_count == 1
    assert first.repository.root_path != second.repository.root_path
    assert second.repository.materialization == SourceMaterialization.TEMPORARY_UPLOAD
    assert second.repository.wlv_owned_temporary_storage is True
    assert second.repository.include_subfolders is True
    assert [c.file_name for c in second.candidates] == ["second.las"]
    assert second.candidates[0].source_reference.materialization == SourceMaterialization.TEMPORARY_UPLOAD


def test_cleanup_guard_rejects_external_path_and_allows_temp_child(tmp_path: Path) -> None:
    lifecycle = SourceIntakeLifecycleService()
    temporary_root = tmp_path / "temporary_uploads"
    batch = temporary_root / "batch"
    batch.mkdir(parents=True)
    (batch / "x.las").write_bytes(LAS)
    external = tmp_path / "external.las"
    external.write_bytes(LAS)
    with pytest.raises(ValueError):
        lifecycle.clear_temporary_materialization(external, temporary_root)
    assert external.exists()
    assert lifecycle.clear_temporary_materialization(batch, temporary_root) is True
    assert not batch.exists()
    assert external.exists()
