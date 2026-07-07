from pathlib import Path

from app.source_intake.las_asset_store import LasAssetStore
from app.source_intake.models import (
    SourceIntakeReferenceType,
    SourceIntakeRetentionState,
)
from app.source_intake.service import WlvSourceIntakeService

LAS = b"""~Version Information
VERS. 2.0
~Well Information
WELL. CLEANUP
~Curve Information
DEPT.M
GR.API
~ASCII
1000 50
"""


def _request(root: Path):
    return type(
        "R",
        (),
        {"root_path": str(root), "name": "External", "include_subfolders": False},
    )()


def test_reference_summary_enables_cleanup_only_at_zero_references(tmp_path: Path) -> None:
    external = tmp_path / "external"
    external.mkdir()
    (external / "well.las").write_bytes(LAS)
    service = WlvSourceIntakeService(storage_path=tmp_path / "state" / "source_intake.json")
    repo = service.create_repository(_request(external))
    result = service.scan_repository(repo.repository_id)
    candidate = result.candidates[0]
    assert candidate.active_reference_count == 1
    assert candidate.cleanup_eligible is False
    service.lifecycle_service.prepare_for_wsi_close(candidate)
    assert candidate.active_reference_count == 0
    assert candidate.cleanup_eligible is True
    assert candidate.retention_state == SourceIntakeRetentionState.ELIGIBLE_FOR_CLEANUP


def test_external_remove_clears_derived_cache_but_never_source(tmp_path: Path, monkeypatch) -> None:
    external = tmp_path / "external"
    external.mkdir()
    source = external / "well.las"
    source.write_bytes(LAS)
    cache_root = tmp_path / "las_assets"
    monkeypatch.setattr(LasAssetStore, "__init__", lambda self, storage_root=None, parser=None: setattr(self, "storage_root", cache_root))
    service = WlvSourceIntakeService(storage_path=tmp_path / "state" / "source_intake.json")
    repo = service.create_repository(_request(external))
    result = service.scan_repository(repo.repository_id)
    candidate = result.candidates[0]
    fingerprint = candidate.content_fingerprint or candidate.checksum
    cache_dir = cache_root / fingerprint[:2] / fingerprint
    cache_dir.mkdir(parents=True)
    (cache_dir / "samples.json.gz").write_bytes(b"derived")
    removed = service.remove_repository(repo.repository_id)
    assert removed.derived_cache_entries_cleared == 1
    assert removed.cleanup_deferred_count == 0
    assert not cache_dir.exists()
    assert source.read_bytes() == LAS


def test_temporary_upload_removed_only_when_no_downstream_reference(tmp_path: Path, monkeypatch) -> None:
    cache_root = tmp_path / "las_assets"
    monkeypatch.setattr(LasAssetStore, "__init__", lambda self, storage_root=None, parser=None: setattr(self, "storage_root", cache_root))
    service = WlvSourceIntakeService(storage_path=tmp_path / "state" / "source_intake.json")
    result = service.ingest_uploaded_files([("upload.las", LAS)])
    batch_root = Path(result.repository.root_path)
    candidate = result.candidates[0]
    service.acquire_candidate_reference(
        candidate.source_file_id,
        SourceIntakeReferenceType.EXPORT,
        "export-1",
    )
    removed = service.remove_repository(result.repository.repository_id)
    assert removed.cleanup_deferred_count == 1
    assert removed.temporary_materialization_cleared is False
    assert batch_root.exists()


def test_temporary_upload_is_cleared_when_wsi_is_final_reference(tmp_path: Path, monkeypatch) -> None:
    cache_root = tmp_path / "las_assets"
    monkeypatch.setattr(LasAssetStore, "__init__", lambda self, storage_root=None, parser=None: setattr(self, "storage_root", cache_root))
    service = WlvSourceIntakeService(storage_path=tmp_path / "state" / "source_intake.json")
    result = service.ingest_uploaded_files([("upload.las", LAS)])
    batch_root = Path(result.repository.root_path)
    removed = service.remove_repository(result.repository.repository_id)
    assert removed.cleanup_deferred_count == 0
    assert removed.temporary_materialization_cleared is True
    assert not batch_root.exists()
