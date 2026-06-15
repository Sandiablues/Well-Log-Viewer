from pathlib import Path

from app.source_intake.models import (
    SourceIntakeQaqcStatus,
    SourceRepositoryCreateRequest,
)
from app.source_intake.service import WlvSourceIntakeService


LAS_WITH_UWI = """~Version
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
~Curve
DEPT.FT : Depth
GR.GAPI : Gamma Ray
RHOB.G/C3 : Standard Resolution Formation Density
~ASCII
100.0 50.0 2.30
101.0 51.0 2.35
102.0 52.0 2.40
"""

LAS_WITHOUT_UWI = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. Forge 21-31 : Well name
COMP. Ormat Nevada, Inc. : Company
FLD. Carson Field : Field
BLOCK. Carson Block : Block
~Curve
DEPT.FT : Depth
GR.GAPI : Gamma Ray
~ASCII
100.0 50.0
101.0 51.0
102.0 52.0
"""

INVALID_LAS = """~Version
VERS. 2.0
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _scan_single(root: Path, las_text: str):
    _write(root / "FORGE_21_31.las", las_text)
    service = WlvSourceIntakeService(storage_path=root.parent / "source_intake.json")
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    result = service.scan_repository(repository.repository_id)
    return service, result.candidates[0]


def test_source_intake_qaqc_passes_complete_las_candidate(tmp_path: Path) -> None:
    _service, candidate = _scan_single(tmp_path / "Forge_21_31", LAS_WITH_UWI)

    assert candidate.qaqc_status.status == SourceIntakeQaqcStatus.PASS
    assert candidate.qaqc_status.failure_count == 0
    assert candidate.qaqc_status.review_required is False
    assert candidate.qaqc_status.check_count >= 10
    assert candidate.review_required is False


def test_source_intake_qaqc_marks_missing_uwi_review_required(tmp_path: Path) -> None:
    _service, candidate = _scan_single(tmp_path / "Forge_21_31", LAS_WITHOUT_UWI)

    assert candidate.qaqc_status.status == SourceIntakeQaqcStatus.REVIEW_REQUIRED
    assert candidate.qaqc_status.failure_count == 0
    assert candidate.qaqc_status.review_required is True
    assert candidate.review_required is True
    assert any("Missing UWI/API" in message for message in candidate.qaqc_status.messages)


def test_source_intake_qaqc_fails_invalid_las_parse(tmp_path: Path) -> None:
    _service, candidate = _scan_single(tmp_path / "bad_las", INVALID_LAS)

    assert candidate.qaqc_status.status == SourceIntakeQaqcStatus.FAIL
    assert candidate.qaqc_status.failure_count >= 1
    assert candidate.qaqc_status.review_required is True
    assert candidate.review_required is True
    assert any("LAS metadata parse failed" in message for message in candidate.qaqc_status.messages)


def test_source_intake_qaqc_survives_persistence_reload(tmp_path: Path) -> None:
    root = tmp_path / "Forge_21_31"
    storage = tmp_path / "source_intake.json"
    _write(root / "FORGE_21_31.las", LAS_WITHOUT_UWI)

    service = WlvSourceIntakeService(storage_path=storage)
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    service.scan_repository(repository.repository_id)

    reloaded = WlvSourceIntakeService(storage_path=storage)
    candidate = reloaded.get_workbench().candidates[0]

    assert candidate.qaqc_status.status == SourceIntakeQaqcStatus.REVIEW_REQUIRED
    assert candidate.qaqc_status.review_required is True
    assert candidate.review_required is True
