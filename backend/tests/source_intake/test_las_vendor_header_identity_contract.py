from pathlib import Path

from app.source_intake.models import SourceRepositoryCreateRequest
from app.source_intake.service import WlvSourceIntakeService


VENDOR_STYLE_LAS = """~Version Information
VERS. 1.2 : LAS VERSION
WRAP. NO : ONE LINE PER DEPTH STEP
~Well Information
STRT .FT              START DEPTH:  1000.0
STOP .FT               STOP DEPTH:  1001.0
STEP .FT               STEP VALUE:  1.0
NULL .            NULL VALUE:  -999.25
WELL .                    WELL:  Forge 21-31
API  .              API NUMBER:  2700190539
DATE .                LOG DATE:  19-JUL-2007
~Curve Information
DEPT .FT : DEPTH
GR   .GAPI : GAMMA RAY
~ASCII
1000 50
1001 51
"""


def test_vendor_label_before_colon_uses_value_after_colon_as_authoritative_identity(tmp_path: Path):
    root = tmp_path / "source"
    root.mkdir()
    path = root / "source.las"
    path.write_text(VENDOR_STYLE_LAS, encoding="utf-8")

    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True)
    )
    candidate = service.scan_repository(repository.repository_id).candidates[0]

    assert candidate.parsed_metadata is not None
    assert candidate.parsed_metadata.well_header is not None
    assert candidate.parsed_metadata.well_header.well_name == "Forge 21-31"
    assert candidate.parsed_metadata.well_header.uwi == "2700190539"
    assert candidate.resolved_metadata is not None
    assert candidate.resolved_metadata.well_name.value == "Forge 21-31"
    assert candidate.resolved_metadata.well_name.confidence == "high"
    assert candidate.resolved_metadata.well_name.review_required is False
    assert candidate.resolved_metadata.uwi.value == "2700190539"
    assert candidate.resolved_metadata.uwi.review_required is False
    assert candidate.resolved_metadata.review_required is False
