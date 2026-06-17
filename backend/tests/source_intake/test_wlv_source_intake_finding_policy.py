from pathlib import Path

from app.source_intake.models import (
    SourceIntakeFindingClass,
    SourceRepositoryCreateRequest,
)
from app.source_intake.service import WlvSourceIntakeService


LAS_COMPLETE = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. Forge 21-31 : Well name
UWI. 1234567890 : Unique well identifier
~Curve
DEPT.FT : Depth
GR.GAPI : Gamma Ray
~ASCII
100.0 50.0
101.0 51.0
102.0 52.0
"""

LAS_MISSING_UWI_AND_CURVE_UNIT = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. Forge 21-31 : Well name
~Curve
DEPT.FT : Depth
GR. : Gamma Ray
~ASCII
100.0 50.0
101.0 51.0
102.0 52.0
"""

INVALID_LAS = """~Version
VERS. 2.0
"""


def _scan(tmp_path: Path, text: str):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "candidate.las").write_text(text)
    service = WlvSourceIntakeService(storage_path=tmp_path / "source.json")
    repository = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True)
    )
    return service.scan_repository(repository.repository_id).candidates[0]


def test_complete_candidate_findings_are_informational(tmp_path: Path) -> None:
    candidate = _scan(tmp_path, LAS_COMPLETE)

    assert candidate.qaqc_status.hard_failure_count == 0
    assert candidate.qaqc_status.review_controlled_count == 0
    assert candidate.qaqc_status.non_blocking_warning_count == 0
    assert all(
        check.finding_class == SourceIntakeFindingClass.INFORMATIONAL
        for check in candidate.qaqc_status.checks
    )


def test_review_and_warning_findings_are_separated(tmp_path: Path) -> None:
    candidate = _scan(tmp_path, LAS_MISSING_UWI_AND_CURVE_UNIT)

    by_id = {check.check_id: check for check in candidate.qaqc_status.checks}
    assert by_id["identity.uwi.missing"].finding_class == SourceIntakeFindingClass.REVIEW_CONTROLLED
    assert by_id["curve.unit.missing"].finding_class == SourceIntakeFindingClass.NON_BLOCKING_WARNING

    assert candidate.qaqc_status.review_controlled_count >= 1
    assert candidate.qaqc_status.non_blocking_warning_count >= 1
    assert candidate.readiness_state.value == "review_required"
    assert candidate.readiness_issues


def test_hard_failures_are_non_overridable_policy_findings(tmp_path: Path) -> None:
    candidate = _scan(tmp_path, INVALID_LAS)

    hard = [
        check for check in candidate.qaqc_status.checks
        if check.finding_class == SourceIntakeFindingClass.HARD_FAILURE
    ]
    assert hard
    assert candidate.qaqc_status.hard_failure_count == len(hard)
    assert candidate.readiness_state.value == "blocked"
    assert candidate.readiness_issues


def test_finding_policy_survives_persistence_reload(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "candidate.las").write_text(LAS_MISSING_UWI_AND_CURVE_UNIT)
    storage = tmp_path / "source.json"

    service = WlvSourceIntakeService(storage_path=storage)
    repository = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True)
    )
    service.scan_repository(repository.repository_id)

    reloaded = WlvSourceIntakeService(storage_path=storage)
    candidate = reloaded.get_workbench().candidates[0]
    by_id = {check.check_id: check for check in candidate.qaqc_status.checks}

    assert by_id["identity.uwi.missing"].finding_class == SourceIntakeFindingClass.REVIEW_CONTROLLED
    assert by_id["curve.unit.missing"].finding_class == SourceIntakeFindingClass.NON_BLOCKING_WARNING
