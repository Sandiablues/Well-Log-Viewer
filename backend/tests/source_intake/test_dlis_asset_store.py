from pathlib import Path
import os, pytest
from app.source_intake.dlis_asset_store import DlisAssetStore

def test_dlis_asset_store_preserves_bytes(tmp_path: Path):
    raw=os.environ.get("WLV_TEST_DLIS_PATH")
    if not raw or not Path(raw).is_file(): pytest.skip("WLV_TEST_DLIS_PATH unavailable")
    source=Path(raw); stored=DlisAssetStore(tmp_path).preserve_path(source, source_id="test")
    assert Path(stored.original_uri) == source.resolve()
    assert source.read_bytes() == Path(raw).read_bytes()
    assert not tmp_path.exists()
    assert stored.asset_id.startswith("dlis-asset:sha256:")
