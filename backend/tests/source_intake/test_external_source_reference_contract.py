from __future__ import annotations

import hashlib
from pathlib import Path

from app.source_intake.dlis_asset_store import DlisAssetStore
from app.source_intake.las_asset_store import LasAssetStore
from app.source_intake.models import (
    SourceAccessMode,
    SourceFileCandidate,
    SourceIntakeCandidateRole,
    SourceIntakeFileType,
    SourceOwnership,
)


def _las_bytes() -> bytes:
    return b"""~Version Information
VERS. 2.0
WRAP. NO
~Well Information
STRT.FT 1000
STOP.FT 1001
STEP.FT 1
NULL. -999.25
WELL. TEST
~Curve Information
DEPT.FT : DEPTH
GR.API : GAMMA RAY
~ASCII
1000 50
1001 51
"""


def test_candidate_builds_external_read_only_source_reference() -> None:
    candidate = SourceFileCandidate(
        source_file_id="source:test",
        repository_id="repo:test",
        scan_id="scan:test",
        file_name="test.las",
        original_path="/external/test.las",
        relative_path="test.las",
        file_extension=".las",
        detected_file_type=SourceIntakeFileType.LAS,
        candidate_role=SourceIntakeCandidateRole.WELL_LOG_CANDIDATE,
        size_bytes=10,
        modified_at="2026-07-06T00:00:00+00:00",
        checksum="abc",
    )
    assert candidate.source_reference is not None
    assert candidate.source_reference.source_uri == "/external/test.las"
    assert candidate.source_reference.ownership == SourceOwnership.EXTERNAL
    assert candidate.source_reference.access_mode == SourceAccessMode.READ_ONLY


def test_las_store_does_not_copy_authoritative_source(tmp_path: Path) -> None:
    source = tmp_path / "external" / "test.las"
    source.parent.mkdir()
    payload = _las_bytes()
    source.write_bytes(payload)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    cache_root = tmp_path / "cache"

    stored = LasAssetStore(storage_root=cache_root).preserve_path(
        source, source_id="source:test"
    )

    assert stored.original_uri == str(source.resolve())
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert not list(cache_root.rglob("original.las"))
    assert Path(stored.manifest_uri).is_file()
    assert Path(stored.samples_uri).is_file()


def test_dlis_store_returns_external_reference_without_copy(tmp_path: Path) -> None:
    source = tmp_path / "external" / "test.dlis"
    source.parent.mkdir()
    payload = b"test-dlis-payload"
    source.write_bytes(payload)
    cache_root = tmp_path / "cache"

    stored = DlisAssetStore(storage_root=cache_root).preserve_path(
        source, source_id="source:test"
    )

    assert stored.original_uri == str(source.resolve())
    assert stored.source_fingerprint == hashlib.sha256(payload).hexdigest()
    assert stored.created is False
    assert not cache_root.exists()
    assert source.read_bytes() == payload
