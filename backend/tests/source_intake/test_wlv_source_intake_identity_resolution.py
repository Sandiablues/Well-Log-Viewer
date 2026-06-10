from pathlib import Path

from backend.app.source_intake.models import SourceRepositoryCreateRequest
from backend.app.source_intake.service import WlvSourceIntakeService


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
~ASCII
100.0 50.0
101.0 51.0
102.0 52.0
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


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _scan_single(root: Path, las_text: str, relative_path: str = "FORGE_21_31.las"):
    _write(root / relative_path, las_text)
    service = WlvSourceIntakeService(storage_path=root.parent / "source_intake.json")
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    result = service.scan_repository(repository.repository_id)
    return service, result.candidates[0]


def test_source_intake_resolves_las_identity_with_evidence(tmp_path: Path) -> None:
    _service, candidate = _scan_single(tmp_path / "Forge_21_31", LAS_WITH_UWI)

    assert candidate.resolved_metadata is not None
    resolved = candidate.resolved_metadata
    assert resolved.review_required is False
    assert resolved.well_name.value == "Forge 21-31"
    assert resolved.well_name.confidence == "high"
    assert resolved.well_name.source == "LAS ~Well WELL field"
    assert resolved.well_name.evidence[0].source_path == "FORGE_21_31.las"

    assert resolved.uwi.value == "1234567890"
    assert resolved.uwi.confidence == "high"
    assert resolved.operator.value == "Ormat Nevada, Inc."
    assert resolved.field.value == "Carson Field"
    assert resolved.block.value == "Carson Block"
    assert resolved.evidence_count >= 5
    assert candidate.review_required is False


def test_source_intake_missing_uwi_is_review_required_evidence(tmp_path: Path) -> None:
    _service, candidate = _scan_single(tmp_path / "Forge_21_31", LAS_WITHOUT_UWI)

    assert candidate.resolved_metadata is not None
    resolved = candidate.resolved_metadata
    assert resolved.uwi.value is None
    assert resolved.uwi.confidence == "missing"
    assert resolved.uwi.review_required is True
    assert resolved.review_required is True
    assert candidate.review_required is True
    assert "Missing UWI/API in LAS well header; review required." in resolved.warnings
    assert "Missing UWI/API in LAS well header; review required." in candidate.warnings


def test_source_intake_path_identity_conflict_is_flagged_without_overwriting_las_header(tmp_path: Path) -> None:
    _service, candidate = _scan_single(tmp_path / "Repository", LAS_WITH_UWI, "Wrong_Well/FORGE_21_31.las")

    assert candidate.resolved_metadata is not None
    resolved = candidate.resolved_metadata
    assert resolved.well_name.value == "Forge 21-31"
    assert resolved.well_name.review_required is True
    assert resolved.review_required is True
    assert candidate.review_required is True
    assert any("Path-derived well hint conflicts" in warning for warning in resolved.warnings)
    assert any(evidence.source == "relative path parent folder hint" for evidence in resolved.well_name.evidence)


def test_source_intake_resolved_metadata_survives_persistence_reload(tmp_path: Path) -> None:
    root = tmp_path / "Forge_21_31"
    storage = tmp_path / "source_intake.json"
    _write(root / "FORGE_21_31.las", LAS_WITHOUT_UWI)

    service = WlvSourceIntakeService(storage_path=storage)
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    service.scan_repository(repository.repository_id)

    reloaded = WlvSourceIntakeService(storage_path=storage)
    workbench = reloaded.get_workbench()
    candidate = workbench.candidates[0]

    assert candidate.resolved_metadata is not None
    assert candidate.resolved_metadata.well_name.value == "Forge 21-31"
    assert candidate.resolved_metadata.uwi.value is None
    assert candidate.resolved_metadata.uwi.review_required is True
    assert candidate.review_required is True
