from pathlib import Path

from app.source_intake.models import (
    SourceIntakeBulkResolutionRequest,
    SourceIntakeFindingDisposition,
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
GR. : Gamma Ray
~ASCII
100.0 50.0
101.0 51.0
102.0 52.0
"""


def _scan(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "candidate.las").write_text(LAS)
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


def test_manual_correction_recomputes_identity_and_archives_prior_qaqc(tmp_path: Path) -> None:
    service, candidate = _scan(tmp_path)
    assert any(
        check.check_id == "identity.uwi.missing"
        for check in candidate.qaqc_status.checks
    )

    _resolve(
        service,
        SourceIntakeResolutionDecision(
            occurrence_id=candidate.occurrence_id,
            action=SourceIntakeResolutionAction.MANUAL_CORRECTION,
            actor="reviewer",
            reason="Corrected UWI.",
            resolved_values={"uwi": "2700190539"},
        ),
    )

    updated = service.get_workbench().candidates[0]
    assert updated.qaqc_history
    assert any(
        check.check_id == "identity.uwi.missing"
        for check in updated.qaqc_history[-1].result.checks
    )
    assert any(
        check.check_id == "identity.uwi.present"
        for check in updated.qaqc_status.checks
    )


def test_warning_acceptance_deactivates_only_the_target_finding(tmp_path: Path) -> None:
    service, candidate = _scan(tmp_path)
    before_review_count = candidate.qaqc_status.review_controlled_count

    _resolve(
        service,
        SourceIntakeResolutionDecision(
            occurrence_id=candidate.occurrence_id,
            action=SourceIntakeResolutionAction.WARNING_ACCEPTED,
            actor="reviewer",
            reason="Missing UWI reviewed and accepted.",
            accepted_warning_codes=["missing_uwi"],
        ),
    )

    updated = service.get_workbench().candidates[0]
    check = next(
        item
        for item in updated.qaqc_status.checks
        if item.check_id == "identity.uwi.missing"
    )
    assert check.disposition == SourceIntakeFindingDisposition.ACCEPTED
    assert check.disposition_event_id == updated.resolution_history[-1].event_id
    assert check.review_required is False
    assert updated.qaqc_status.review_controlled_count == before_review_count - 1
    assert updated.qaqc_status.review_controlled_count > 0
    assert updated.qaqc_history[-1].result.review_controlled_count == before_review_count


def test_promote_with_exception_accepts_review_findings_without_erasing_them(tmp_path: Path) -> None:
    service, candidate = _scan(tmp_path)

    _resolve(
        service,
        SourceIntakeResolutionDecision(
            occurrence_id=candidate.occurrence_id,
            action=SourceIntakeResolutionAction.PROMOTE_WITH_EXCEPTION,
            actor="reviewer",
            reason="Package evidence reviewed.",
            accepted_warning_codes=["missing_uwi"],
        ),
    )

    updated = service.get_workbench().candidates[0]
    accepted = [
        check
        for check in updated.qaqc_status.checks
        if check.disposition == SourceIntakeFindingDisposition.ACCEPTED
    ]
    assert accepted
    assert all(check.finding_class.value != "hard_failure" for check in accepted)
    assert updated.qaqc_history


def test_qaqc_history_survives_persistence_reload(tmp_path: Path) -> None:
    service, candidate = _scan(tmp_path)

    _resolve(
        service,
        SourceIntakeResolutionDecision(
            occurrence_id=candidate.occurrence_id,
            action=SourceIntakeResolutionAction.WARNING_ACCEPTED,
            actor="reviewer",
            reason="Accepted.",
            accepted_warning_codes=["missing_uwi"],
        ),
    )

    reloaded = WlvSourceIntakeService(storage_path=tmp_path / "source.json")
    updated = reloaded.get_workbench().candidates[0]
    assert len(updated.qaqc_history) == 1
    assert updated.qaqc_history[0].trigger_event_id == updated.resolution_history[-1].event_id
