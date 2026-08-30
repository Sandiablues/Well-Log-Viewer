from pathlib import Path
from app.source_intake.lis_parser import inspect_lis

def test_real_lti_fixture_is_parsed():
    fixture = Path(__file__).parent / "fixtures" / "L898CMP.LTI"
    result = inspect_lis(fixture)
    assert result.source_format == "LIS"
    assert result.logical_file_count >= 1
    assert result.log_set_count >= 1
    assert len(result.channel_inventory) >= 1
    assert len(result.scalar_channels) >= 1
    assert all("|" in item.source_curve_name for item in result.scalar_channels)
