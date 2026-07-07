from pathlib import Path

from app.source_intake.dlis_parser import (
    DlisChannelInventoryItem,
    DlisInspection,
    DlisScalarChannel,
)
from app.source_intake.las_asset_store import LasAssetStore
from app.source_intake.models import SourceIntakeFileType
from app.source_intake.service import WlvSourceIntakeService

LAS = b"""~Version Information
VERS. 2.0
~Well Information
WELL. REBUILD
~Curve Information
DEPT.M
GR.API
~ASCII
1000 50
1001 51
"""


def _request(root: Path):
    return type("R", (), {"root_path": str(root), "name": "External", "include_subfolders": False})()


def _fake_dlis_inspection() -> DlisInspection:
    scalar = DlisScalarChannel(
        logical_file_id="LF1", frame_id="F1", mnemonic="GR",
        description="Gamma ray", unit="API", dimensions=(1,),
        index_channel="DEPTH", sample_count=2, top_depth=1000.0,
        base_depth=1001.0, depth_unit="m", raw_depth_unit="m",
        depth_scale_factor=1.0, raw_top_depth=1000.0, raw_base_depth=1001.0,
    )
    inventory = DlisChannelInventoryItem(
        logical_file_id="LF1", frame_id="F1", mnemonic="GR",
        description="Gamma ray", unit="API", dimensions=(1,),
        index_channel="DEPTH", sample_count=2, role="curve", supported=True,
        raw_depth_unit="m", depth_scale_factor=1.0, normalized_depth_unit="m",
    )
    return DlisInspection(
        parser_id="test_dlis", source_format="DLIS", well_name="F5",
        uwi=None, operator=None, field=None, service_company=None,
        logical_file_count=1, frame_count=1, scalar_channels=(scalar,),
        channel_inventory=(inventory,), non_scalar_channel_count=0, warnings=(),
    )


def test_las_cleanup_and_rebuild_restores_same_working_inventory(tmp_path: Path, monkeypatch) -> None:
    external = tmp_path / "external"
    external.mkdir()
    source = external / "well.las"
    source.write_bytes(LAS)
    cache_root = tmp_path / "las_assets"
    monkeypatch.setattr(LasAssetStore, "__init__", lambda self, storage_root=None, parser=None: setattr(self, "storage_root", cache_root))
    service = WlvSourceIntakeService(storage_path=tmp_path / "state" / "source_intake.json")
    repo = service.create_repository(_request(external))
    first = service.scan_repository(repo.repository_id).candidates[0]
    signature = (first.detected_file_type, first.parsed_metadata.log_header.curve_count, first.parsed_metadata.log_header.start_depth, first.parsed_metadata.log_header.stop_depth)
    fingerprint = first.content_fingerprint or first.checksum
    cache_dir = cache_root / fingerprint[:2] / fingerprint
    cache_dir.mkdir(parents=True)
    (cache_dir / "samples.json.gz").write_bytes(b"derived")
    rebuilt = service.rebuild_candidate_from_external_source(first.source_file_id)
    assert (rebuilt.detected_file_type, rebuilt.parsed_metadata.log_header.curve_count, rebuilt.parsed_metadata.log_header.start_depth, rebuilt.parsed_metadata.log_header.stop_depth) == signature
    assert source.read_bytes() == LAS


def test_changed_las_fingerprint_invalidates_prior_occurrence(tmp_path: Path) -> None:
    external = tmp_path / "external"
    external.mkdir()
    source = external / "well.las"
    source.write_bytes(LAS)
    service = WlvSourceIntakeService(storage_path=tmp_path / "state" / "source_intake.json")
    repo = service.create_repository(_request(external))
    first = service.scan_repository(repo.repository_id).candidates[0]
    source.write_bytes(LAS.replace(b"1001 51", b"1001 61"))
    rebuilt = service.rebuild_candidate_from_external_source(first.source_file_id)
    assert rebuilt.source_file_id != first.source_file_id
    assert rebuilt.current_decision is None
    assert rebuilt.active_reference_count == 1


def test_dlis_rebuild_reparses_external_source_without_persistent_store(tmp_path: Path, monkeypatch) -> None:
    external = tmp_path / "external"
    external.mkdir()
    source = external / "F5.dlis"
    payload = b"synthetic-dlis-container"
    source.write_bytes(payload)
    calls = {"count": 0}
    def fake_inspect(path):
        calls["count"] += 1
        assert Path(path).read_bytes() == payload
        return _fake_dlis_inspection()
    monkeypatch.setattr("app.source_intake.service.inspect_dlis", fake_inspect)
    service = WlvSourceIntakeService(storage_path=tmp_path / "state" / "source_intake.json")
    repo = service.create_repository(_request(external))
    first = service.scan_repository(repo.repository_id).candidates[0]
    rebuilt = service.rebuild_candidate_from_external_source(first.source_file_id)
    assert calls["count"] == 2
    assert rebuilt.detected_file_type == SourceIntakeFileType.DLIS
    assert rebuilt.parsed_metadata.log_header.curve_count == 1
    assert rebuilt.parsed_metadata.log_header.depth_unit == "m"
    assert source.read_bytes() == payload


def test_dlis_cleanup_is_explicit_noop_for_nonexistent_persistent_cache(tmp_path: Path, monkeypatch) -> None:
    external = tmp_path / "external"
    external.mkdir()
    source = external / "F5.dlis"
    payload = b"synthetic-dlis-container"
    source.write_bytes(payload)
    monkeypatch.setattr("app.source_intake.service.inspect_dlis", lambda path: _fake_dlis_inspection())
    service = WlvSourceIntakeService(storage_path=tmp_path / "state" / "source_intake.json")
    repo = service.create_repository(_request(external))
    candidate = service.scan_repository(repo.repository_id).candidates[0]
    service.lifecycle_service.prepare_for_wsi_close(candidate)
    assert service.lifecycle_service.clear_candidate_derived_data(candidate, las_storage_root=tmp_path / "las_assets") is False
    assert source.read_bytes() == payload
