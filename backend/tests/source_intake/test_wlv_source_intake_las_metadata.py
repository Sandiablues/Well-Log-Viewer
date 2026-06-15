from pathlib import Path

from app.source_intake.models import SourceIntakeParseStatus, SourceRepositoryCreateRequest
from app.source_intake.service import WlvSourceIntakeService


VALID_LAS = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. Forge 21-31 : Well name
UWI. 1234567890 : Unique well identifier
COMP. Ormat Nevada, Inc. : Company
FLD. Carson Field : Field
BLOCK. Carson Block : Block
CTRY. USA : Country
RUN. ONE : Run number
DATE. 2026-06-10 : Run date
SRVC. Test Logging Co : Service company
~Curve
DEPT.FT : Depth
GR.GAPI : Gamma Ray
RHOB.G/C3 : Standard Resolution Formation Density
~ASCII
100.0 50.0 2.30
101.0 51.0 2.35
102.0 52.0 2.40
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_source_intake_extracts_three_level_las_metadata(tmp_path: Path) -> None:
    root = tmp_path / "Forge_21_31"
    _write(root / "FORGE_21_31.las", VALID_LAS)

    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    result = service.scan_repository(repository.repository_id)

    candidate = result.candidates[0]
    assert candidate.file_name == "FORGE_21_31.las"
    assert candidate.parser_status == SourceIntakeParseStatus.PARSED
    assert candidate.parsed_metadata is not None
    assert candidate.review_required is False

    parsed = candidate.parsed_metadata
    assert parsed.well_header.well_name == "Forge 21-31"
    assert parsed.well_header.uwi == "1234567890"
    assert parsed.well_header.operator == "Ormat Nevada, Inc."
    assert parsed.well_header.field == "Carson Field"
    assert parsed.well_header.block == "Carson Block"
    assert parsed.well_header.country == "USA"
    assert parsed.well_header.depth_unit == "ft"

    assert parsed.log_header is not None
    assert parsed.log_header.file_name == "FORGE_21_31.las"
    assert parsed.log_header.run_date == "2026-06-10"
    assert parsed.log_header.run_number == "ONE"
    assert parsed.log_header.service_company == "Test Logging Co"
    assert parsed.log_header.start_depth == 100.0
    assert parsed.log_header.stop_depth == 102.0
    assert parsed.log_header.step == 1.0
    assert parsed.log_header.null_value == -999.25
    assert parsed.log_header.curve_count == 2

    curve_headers = {curve.mnemonic: curve for curve in parsed.curve_headers}
    assert sorted(curve_headers) == ["GR", "RHOB"]
    assert curve_headers["GR"].description == "Gamma Ray"
    assert curve_headers["GR"].unit == "GAPI"
    assert curve_headers["RHOB"].description == "Standard Resolution Formation Density"
    assert curve_headers["RHOB"].unit == "G/C3"


def test_source_intake_marks_invalid_las_as_parse_failed(tmp_path: Path) -> None:
    root = tmp_path / "bad_las"
    _write(root / "bad.las", "~Version\nVERS. 2.0\n")

    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root)))
    result = service.scan_repository(repository.repository_id)

    candidate = result.candidates[0]
    assert candidate.parser_status == SourceIntakeParseStatus.PARSE_FAILED
    assert candidate.parsed_metadata is None
    assert candidate.parse_error
    assert candidate.review_required is True
