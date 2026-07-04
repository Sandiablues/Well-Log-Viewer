from pathlib import Path
import os, pytest
from app.source_intake.dlis_parser import inspect_dlis
from app.inventory.dlis_sample_reader import read_dlis_curve_samples

def fixture():
    value=os.environ.get("WLV_TEST_DLIS_PATH")
    if not value or not Path(value).is_file(): pytest.skip("WLV_TEST_DLIS_PATH unavailable")
    return Path(value)

def test_dlis_inspection_inventory_and_normalized_depth():
    result=inspect_dlis(fixture())
    assert result.well_name == "15/9-F-1 A"
    assert result.field == "VOLVE"
    assert result.logical_file_count == 1 and result.frame_count == 1
    assert [x.mnemonic for x in result.scalar_channels] == ["GR","CALI","RDEP","RMED","DEN","DENC","PEF","NEU","AC","ACS","ROP","BS"]
    assert result.scalar_channels[0].sample_count == 34871
    assert result.scalar_channels[0].depth_unit == "m"
    assert result.scalar_channels[0].top_depth == pytest.approx(197.0)
    assert result.scalar_channels[0].base_depth == pytest.approx(3684.0)

def test_dlis_scalar_samples_are_wdv_ready():
    data=read_dlis_curve_samples(source_path=fixture(), curve_mnemonic="GR", max_samples=2000,
        logical_file_id="Composite.logdata", frame_id="0", channel_mnemonic="GR")
    assert data["depth_unit"] == "m"
    assert data["value_unit"] == "gAPI"
    assert data["depth_min"] >= 197.0 and data["depth_max"] <= 3684.0
    assert data["sample_count"] > 10000
    assert len(data["samples"]) <= 2001
    assert data["raw_numeric_sample_count"] == (
        data["sample_count"]
        + data["rejected_null_count"]
        + data["rejected_sentinel_count"]
    )
    assert data["rejected_sample_count"] == (
        data["rejected_null_count"]
        + data["rejected_sentinel_count"]
        + data["rejected_nonfinite_count"]
        + data["rejected_row_count"]
    )
