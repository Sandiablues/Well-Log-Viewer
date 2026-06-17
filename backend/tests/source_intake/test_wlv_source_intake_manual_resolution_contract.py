from pathlib import Path

import pytest

from app.source_intake.models import (
    SourceIntakeBulkResolutionRequest,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionDecision,
    SourceRepositoryCreateRequest,
)
from app.source_intake.service import SourceIntakeError, WlvSourceIntakeService


LAS_WITH_REVIEW = """~Version
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


def _scan(tmp_path: Path, text: str = LAS_WITH_REVIEW):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "candidate.las").write_text(text)
    service = WlvSourceIntakeService(storage_path=tmp_path / "source.json")
    repository = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True)
    )
    candidate = service.scan_repository(repository.repository_id).candidates[0]
    return service, candidate


def _resolve(service, decision):
    return service.resolve_candidates(
        SourceIntakeBulkResolutionRequest(decisions=[decision])
    )


def test_established_warning_code_vocabulary_remains_accepted(tmp_path: Path) -> None:
    service, candidate = _scan(tmp_path)

    response = _resolve(
        service,
        SourceIntakeResolutionDecision(
            occurrence_id=candidate.occurrence_id,
            action=SourceIntakeResolutionAction.WARNING_ACCEPTED,
            actor="reviewer",
            reason="Missing UWI reviewed and accepted.",
            accepted_warning_codes=["missing_uwi"],
        ),
    )

    assert response.resolved_count == 1
    updated = service.get_workbench().candidates[0]
    assert updated.resolution_history[-1].accepted_warning_codes == ["missing_uwi"]


def test_manual_correction_requires_values_and_is_audited(tmp_path: Path) -> None:
    service, candidate = _scan(tmp_path)

    with pytest.raises(SourceIntakeError, match="requires at least one resolved value"):
        _resolve(
            service,
            SourceIntakeResolutionDecision(
                occurrence_id=candidate.occurrence_id,
                action=SourceIntakeResolutionAction.MANUAL_CORRECTION,
                actor="reviewer",
            ),
        )

    _resolve(
        service,
        SourceIntakeResolutionDecision(
            occurrence_id=candidate.occurrence_id,
            action=SourceIntakeResolutionAction.MANUAL_CORRECTION,
            actor="reviewer",
            reason="Corrected canonical UWI.",
            resolved_values={"uwi": "2700190539"},
        ),
    )

    updated = service.get_workbench().candidates[0]
    assert updated.resolved_metadata.uwi.value == "2700190539"
    assert updated.resolution_history[-1].action == SourceIntakeResolutionAction.MANUAL_CORRECTION


def test_confirm_suggestion_is_explicit_and_audited(tmp_path: Path) -> None:
    service, candidate = _scan(tmp_path)

    _resolve(
        service,
        SourceIntakeResolutionDecision(
            occurrence_id=candidate.occurrence_id,
            action=SourceIntakeResolutionAction.CONFIRM_SUGGESTION,
            actor="reviewer",
            reason="Confirmed detected well identity.",
        ),
    )

    updated = service.get_workbench().candidates[0]
    assert updated.resolution_history[-1].action == SourceIntakeResolutionAction.CONFIRM_SUGGESTION
    assert updated.resolved_metadata.well_name.source == "confirmed_suggestion"
    assert updated.resolved_metadata.well_name.confidence == "reviewed"


def test_promote_with_exception_requires_reason_and_code(tmp_path: Path) -> None:
    service, candidate = _scan(tmp_path)

    with pytest.raises(SourceIntakeError, match="requires a reason"):
        _resolve(
            service,
            SourceIntakeResolutionDecision(
                occurrence_id=candidate.occurrence_id,
                action=SourceIntakeResolutionAction.PROMOTE_WITH_EXCEPTION,
                actor="reviewer",
                accepted_warning_codes=["missing_uwi"],
            ),
        )

    with pytest.raises(SourceIntakeError, match="requires at least one accepted finding code"):
        _resolve(
            service,
            SourceIntakeResolutionDecision(
                occurrence_id=candidate.occurrence_id,
                action=SourceIntakeResolutionAction.PROMOTE_WITH_EXCEPTION,
                actor="reviewer",
                reason="Reviewed against package evidence.",
            ),
        )

    _resolve(
        service,
        SourceIntakeResolutionDecision(
            occurrence_id=candidate.occurrence_id,
            action=SourceIntakeResolutionAction.PROMOTE_WITH_EXCEPTION,
            actor="reviewer",
            reason="Reviewed against package evidence.",
            accepted_warning_codes=["missing_uwi"],
        ),
    )

    updated = service.get_workbench().candidates[0]
    event = updated.resolution_history[-1]
    assert event.action == SourceIntakeResolutionAction.PROMOTE_WITH_EXCEPTION
    assert event.reason == "Reviewed against package evidence."
    assert event.accepted_warning_codes == ["missing_uwi"]


def test_hard_failure_cannot_be_promoted(tmp_path: Path) -> None:
    service, candidate = _scan(tmp_path, INVALID_LAS)

    with pytest.raises(SourceIntakeError, match="Hard failures"):
        _resolve(
            service,
            SourceIntakeResolutionDecision(
                occurrence_id=candidate.occurrence_id,
                action=SourceIntakeResolutionAction.PROMOTE_WITH_EXCEPTION,
                actor="reviewer",
                reason="Attempted exception.",
                accepted_warning_codes=["parser_failure"],
            ),
        )


def test_backend_advertises_explicit_resolution_actions(tmp_path: Path) -> None:
    service, _ = _scan(tmp_path)
    candidate = service.get_workbench().candidates[0]

    assert "confirm_suggestion" in candidate.available_resolution_actions
    assert "manual_correction" in candidate.available_resolution_actions
    assert "accept_warnings" in candidate.available_resolution_actions
    assert "promote_with_exception" in candidate.available_resolution_actions
    assert "exclude_candidate" in candidate.available_resolution_actions
