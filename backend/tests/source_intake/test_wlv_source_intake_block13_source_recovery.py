from pathlib import Path

from app.source_intake.models import SourceIntakeSourceAccessStatus
from app.source_intake.service import WlvSourceIntakeService

LAS = b"""~Version Information
VERS. 2.0
~Well Information
WELL. RECOVERY
~Curve Information
DEPT.M
GR.API
~ASCII
1000 50
1001 51
"""


def _request(root: Path):
    return type("R", (), {"root_path": str(root), "name": "External", "include_subfolders": False})()


def _setup(tmp_path: Path):
    external = tmp_path / "external"
    external.mkdir()
    source = external / "well.las"
    source.write_bytes(LAS)
    service = WlvSourceIntakeService(storage_path=tmp_path / "state" / "source_intake.json")
    repo = service.create_repository(_request(external))
    candidate = service.scan_repository(repo.repository_id).candidates[0]
    return service, source, candidate


def test_unchanged_external_source_is_available_and_not_rebuilt(tmp_path: Path):
    service, source, candidate = _setup(tmp_path)
    result = service.recover_candidate_source(candidate.source_file_id)
    assert result.status == SourceIntakeSourceAccessStatus.AVAILABLE
    assert result.rebuilt is False
    assert result.current_fingerprint == candidate.content_fingerprint
    assert source.read_bytes() == LAS


def test_missing_external_source_is_reported_without_deletion(tmp_path: Path):
    service, source, candidate = _setup(tmp_path)
    source.unlink()
    result = service.recover_candidate_source(candidate.source_file_id)
    assert result.status == SourceIntakeSourceAccessStatus.MISSING
    assert result.rebuilt is False
    snapshot = service._load_snapshot()
    stored = snapshot.candidates[0]
    assert stored.source_reference is not None
    assert stored.source_reference.accessible is False


def test_changed_external_source_reparses_and_invalidates_transient_decisions(tmp_path: Path):
    service, source, candidate = _setup(tmp_path)
    original_id = candidate.source_file_id
    source.write_bytes(LAS.replace(b"1001 51", b"1001 61"))
    result = service.recover_candidate_source(original_id)
    assert result.status == SourceIntakeSourceAccessStatus.CHANGED
    assert result.rebuilt is True
    assert result.cache_invalidated is True
    assert result.candidate is not None
    assert result.candidate.source_file_id == original_id
    assert result.candidate.current_decision is None
    assert result.candidate.source_reference is not None
    assert result.candidate.source_reference.fingerprint == result.current_fingerprint
    assert source.read_bytes().endswith(b"1001 61\n")
