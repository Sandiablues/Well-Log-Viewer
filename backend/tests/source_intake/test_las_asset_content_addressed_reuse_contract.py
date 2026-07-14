from pathlib import Path

from app.source_intake.las_asset_store import LasAssetStore
from app.wells.las_import_service import LasImportService


LAS = b"""~Version Information
VERS. 2.0 : LAS VERSION
WRAP. NO : ONE LINE PER DEPTH STEP
~Well Information
STRT.FT 1000
STOP.FT 1001
STEP.FT 1
NULL. -999.25
WELL. Test Well : Well name
UWI. 1234567890 : UWI
~Curve Information
DEPT.FT : DEPTH
GR.API : GAMMA RAY
~ASCII
1000 50
1001 51
"""


class CountingParser(LasImportService):
    def __init__(self):
        super().__init__()
        self.import_from_bytes_calls = 0

    def import_from_bytes(self, *args, **kwargs):
        self.import_from_bytes_calls += 1
        return super().import_from_bytes(*args, **kwargs)


def test_existing_valid_content_addressed_asset_skips_reparse_and_rewrite(tmp_path: Path):
    source = tmp_path / "source.las"
    source.write_bytes(LAS)
    parser = CountingParser()
    store = LasAssetStore(storage_root=tmp_path / "assets", parser=parser)

    first = store.preserve_path(source, source_id="source:first")
    manifest_mtime = Path(first.manifest_uri).stat().st_mtime_ns
    samples_mtime = Path(first.samples_uri).stat().st_mtime_ns

    second = store.preserve_path(source, source_id="source:second")

    assert parser.import_from_bytes_calls == 1
    assert first.asset_id == second.asset_id
    assert first.source_fingerprint == second.source_fingerprint
    assert first.created is True
    assert second.created is False
    assert Path(second.original_uri) == source.resolve()
    assert Path(first.manifest_uri).stat().st_mtime_ns == manifest_mtime
    assert Path(first.samples_uri).stat().st_mtime_ns == samples_mtime


def test_missing_cache_member_forces_safe_rebuild(tmp_path: Path):
    source = tmp_path / "source.las"
    source.write_bytes(LAS)
    parser = CountingParser()
    store = LasAssetStore(storage_root=tmp_path / "assets", parser=parser)

    first = store.preserve_path(source, source_id="source:first")
    Path(first.samples_uri).unlink()

    rebuilt = store.preserve_path(source, source_id="source:second")

    assert parser.import_from_bytes_calls == 2
    assert rebuilt.asset_id == first.asset_id
    assert Path(rebuilt.samples_uri).is_file()
