import gzip
import json

from app.inventory.curve_sample_service import CurveSampleService
from app.inventory.models import ManagedProductGroup, ManagedProductGroupItem, ManagedWellRecord
from app.inventory.repository import ManagedWellInventoryRepository


def test_curve_samples_prefer_managed_las_sample_store(tmp_path):
    sample_store = tmp_path / "samples.json.gz"
    payload = {
        "storage_contract": "wlv_las_samples_v1",
        "asset_id": "las-asset:test",
        "source_fingerprint": "abc",
        "depth_mnemonic": "DEPT",
        "depth_unit": "ft",
        "depth_values": [1000.0, 1000.5, 1001.0],
        "curves": [
            {
                "curve_index": 0,
                "mnemonic": "GR",
                "unit": "API",
                "description": "Gamma ray",
                "sample_count": 3,
                "values": [50.0, None, 60.0],
            }
        ],
    }
    with gzip.open(sample_store, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)

    repo = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    item = ManagedProductGroupItem(
        product_id="gr-product",
        display_name="GR",
        curve_name="GR",
        curve_type="Gamma Ray",
        curve_unit="API",
        source_kind="las",
        source_id="source-1",
        provenance={"las_samples_uri": str(sample_store), "source_curve_index": 0},
    )
    repo.upsert_record(ManagedWellRecord(
        managed_well_id="managed-well:test",
        well_id="test",
        well_name="Test",
        product_groups=[ManagedProductGroup(group_key="open_hole_logs", group_label="Open Hole", items=[item])],
    ))

    result = CurveSampleService(repo).get_curve_samples("managed-well:test", "gr-product")
    assert result["sample_source"] == "managed_las_sample_store"
    assert result["source_path"] == str(sample_store.resolve())
    assert result["sample_count"] == 2
    assert result["samples"] == [[1000.0, 50.0], [1001.0, 60.0]]
