from pathlib import Path

from app.source_intake.models import (
    SourceIntakeBulkResolutionRequest,
    SourceIntakeReadinessState,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionDecision,
    SourceRepositoryCreateRequest,
)
from app.source_intake.service import WlvSourceIntakeService


LAS = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. Forge 21-31 : Well name
~Curve
DEPT.FT : Depth
GR.GAPI : Gamma Ray
~ASCII
100.0 50.0
101.0 51.0
102.0 52.0
"""


def _scan(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.las").write_text(LAS)

    service = WlvSourceIntakeService(
        storage_path=tmp_path / "source.json"
    )
    repository = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root))
    )
    candidate = service.scan_repository(
        repository.repository_id
    ).candidates[0]

    return service, repository, candidate


def _accept_missing_uwi(service, candidate) -> None:
    service.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=candidate.occurrence_id,
                    action=SourceIntakeResolutionAction.WARNING_ACCEPTED,
                    actor="reviewer",
                    reason="Missing UWI reviewed and accepted.",
                    accepted_warning_codes=["missing_uwi"],
                )
            ]
        )
    )


def test_unresolved_candidate_requires_human_decision(
    tmp_path: Path,
) -> None:
    service, _, candidate = _scan(tmp_path)

    assert (
        candidate.readiness_state
        == SourceIntakeReadinessState.REVIEW_REQUIRED
    )
    assert candidate.readiness_issues
    assert set(candidate.available_human_actions) == {
        "accept",
        "correct",
        "assign",
        "exclude",
    }


def test_explicit_human_decision_makes_candidate_ready(
    tmp_path: Path,
) -> None:
    service, _, candidate = _scan(tmp_path)

    _accept_missing_uwi(service, candidate)

    accepted = service.get_workbench().candidates[0]

    assert accepted.readiness_state == SourceIntakeReadinessState.READY
    assert accepted.readiness_issues == []
    assert accepted.available_human_actions == []


def test_human_decision_survives_rescan(
    tmp_path: Path,
) -> None:
    service, repository, candidate = _scan(tmp_path)

    _accept_missing_uwi(service, candidate)

    rescanned = service.scan_repository(
        repository.repository_id
    ).candidates[0]

    assert rescanned.readiness_state == SourceIntakeReadinessState.READY
    assert rescanned.readiness_issues == []
