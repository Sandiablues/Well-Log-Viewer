"""Canonical LAS import service tests."""

from pathlib import Path

import pytest

from app.wells.las_import_service import LasImportError, LasImportService
from app.wells.models import MsiSourceRef


LAS = b"""~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
WRAP. NO
~Well
STRT.FT 100.0 : Start
STOP.FT 102.0 : Stop
STEP.FT 1.0 : Step
NULL. -999.25 : Null
WELL. Forge 21-31 : Well name
UWI. 1234567890 : UWI
~Curve
DEPT.FT : Depth
GR.API : Gamma ray
GR.API : Duplicate source mnemonic
~ASCII
100 10 11
101 -999.25 12
102 13 14
"""


def test_import_from_bytes_preserves_source_order_duplicates_and_nulls():
    result = LasImportService().import_from_bytes(
        LAS, MsiSourceRef(source_id="src-001", filename="forge.las")
    )
    assert result.well.well_name == "Forge 21-31"
    assert result.well.well_id == "1234567890"
    assert result.depth_mnemonic == "DEPT"
    assert result.depth_unit == "ft"
    assert result.depth_values == [100.0, 101.0, 102.0]
    assert [curve.mnemonic for curve in result.curves] == ["GR", "GR"]
    assert [curve.curve_index for curve in result.curves] == [1, 2]
    assert result.curves[0].values == [10.0, None, 13.0]
    assert result.source_bytes == LAS
    assert result.curve_count == 2
    assert result.sample_count == 3
    assert result.well.dataset_ref.dataset_id.startswith("las-product:")


def test_import_from_path_reads_original_bytes(tmp_path: Path):
    path = tmp_path / "sample.las"
    path.write_bytes(LAS)
    result = LasImportService().import_from_path(
        str(path), MsiSourceRef(source_id="src-path")
    )
    assert result.well.source_ref.filename == "sample.las"
    assert result.source_bytes == LAS


def test_generic_well_identity_is_not_accepted_as_canonical():
    payload = LAS.replace(b"Forge 21-31", b"WELL       ").replace(b"1234567890", b"WELL ID   ")
    result = LasImportService().import_from_bytes(
        payload, MsiSourceRef(source_id="src-generic", filename="Forge_21_31.las")
    )
    assert result.well.well_name == "Forge_21_31"
    assert result.well.well_id.startswith("las-source-")
    assert len(result.warnings) == 2


def test_wrapped_las_is_reconstructed_by_curve_count():
    wrapped = LAS.replace(b"WRAP. NO", b"WRAP. YES").replace(
        b"100 10 11\n101 -999.25 12\n102 13 14",
        b"100 10\n11 101\n-999.25 12 102\n13 14",
    )
    result = LasImportService().import_from_bytes(
        wrapped, MsiSourceRef(source_id="src-wrap")
    )
    assert result.wrap is True
    assert result.depth_values == [100.0, 101.0, 102.0]
    assert result.curves[1].values == [11.0, 12.0, 14.0]


def test_exact_content_has_exact_fingerprint():
    service = LasImportService()
    first = service.import_from_bytes(LAS, MsiSourceRef(source_id="a"))
    second = service.import_from_bytes(LAS, MsiSourceRef(source_id="b"))
    changed = service.import_from_bytes(LAS + b"\n", MsiSourceRef(source_id="c"))
    assert first.source_fingerprint == second.source_fingerprint
    assert first.source_fingerprint != changed.source_fingerprint


@pytest.mark.parametrize("payload", [b"", b"not a las"])
def test_invalid_sources_raise_domain_error(payload: bytes):
    with pytest.raises(LasImportError):
        LasImportService().import_from_bytes(payload, MsiSourceRef(source_id="bad"))
