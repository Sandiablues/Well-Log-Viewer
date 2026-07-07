from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from app.source_intake.las_asset_store import LasAssetStore


def _las_bytes() -> bytes:
    return b"""~Version Information
VERS. 2.0 : LAS VERSION
WRAP. NO : ONE LINE PER DEPTH STEP
~Well Information
STRT.FT 1000
STOP.FT 1001
STEP.FT 1
NULL. -999.25
WELL. WELL : generic placeholder
UWI. WELL ID : generic placeholder
~Curve Information
DEPT.FT : DEPTH
GR.API : GAMMA RAY
GR.API : SECOND GAMMA RAY
~ASCII
1000 50 -999.25
1001 51 61
"""


def test_asset_store_preserves_original_and_source_ordered_samples(tmp_path: Path) -> None:
    source = tmp_path / "field.las"
    payload = _las_bytes()
    source.write_bytes(payload)
    store = LasAssetStore(storage_root=tmp_path / "assets")

    stored = store.preserve_path(source, source_id="source:test", filename=source.name)

    assert stored.source_fingerprint == hashlib.sha256(payload).hexdigest()
    assert Path(stored.original_uri) == source.resolve()
    assert source.read_bytes() == payload
    assert not list((tmp_path / "assets").rglob("original.las"))
    manifest = json.loads(Path(stored.manifest_uri).read_text())
    assert manifest["curve_count"] == 2
    assert manifest["sample_count"] == 2
    assert manifest["well"]["well_name"] == "field"
    with gzip.open(stored.samples_uri, "rt", encoding="utf-8") as handle:
        samples = json.load(handle)
    assert [curve["mnemonic"] for curve in samples["curves"]] == ["GR", "GR"]
    assert samples["curves"][0]["values"] == [50.0, 51.0]
    assert samples["curves"][1]["values"] == [None, 61.0]


def test_asset_store_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "field.las"
    source.write_bytes(_las_bytes())
    store = LasAssetStore(storage_root=tmp_path / "assets")
    first = store.preserve_path(source, source_id="source:first")
    second = store.preserve_path(source, source_id="source:second")
    assert first.asset_id == second.asset_id
    assert first.created is True
    assert second.created is False
    assert first.original_uri == second.original_uri
