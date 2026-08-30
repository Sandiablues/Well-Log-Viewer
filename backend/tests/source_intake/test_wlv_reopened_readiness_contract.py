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
VERS. 2.0
WRAP. NO
~Well
WELL. Reopen Test
STRT.FT 0
STOP.FT 100
STEP.FT 50
NULL. -999.25
~Curve
DEPT.FT : Depth
GR.API : Gamma Ray
~ASCII
0 10
50 20
100 30
"""


def test_reopened_candidate_stays_review_required(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / "reopen-test.las").write_text(LAS)

    source = WlvSourceIntakeService(
        storage_path=tmp_path / "source_intake.json"
    )
    repository = source.create_repository(
        SourceRepositoryCreateRequest(
            root_path=str(root),
            include_subfolders=True,
        )
    )
    candidate = source.scan_repository(repository.repository_id).candidates[0]

    source.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=candidate.occurrence_id,
                    action=SourceIntakeResolutionAction.REOPENED,
                    actor="test",
                    reason="Return to unresolved review.",
                )
            ]
        )
    )

    updated = source.get_workbench().candidates[0]
    assert updated.current_decision is not None
    assert updated.current_decision.decision.value == "clear_decision"
    assert updated.readiness_state == SourceIntakeReadinessState.REVIEW_REQUIRED
    assert any(
        "reopened" in issue.lower()
        for issue in updated.readiness_issues
    )
