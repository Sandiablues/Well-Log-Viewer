from pathlib import Path

import pytest

from app.source_intake.models import (
    SourceIntakeBulkResolutionRequest,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionDecision,
    SourceRepositoryCreateRequest,
)
from app.source_intake.qaqc import run_source_intake_qaqc
from app.source_intake.service import SourceIntakeError, WlvSourceIntakeService


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
        SourceRepositoryCreateRequest(
            root_path=str(root),
            include_subfolders=True,
        )
    )
    candidate = service.scan_repository(repository.repository_id).candidates[0]
    return service, candidate


def _resolve(service, decision):
    return service.resolve_candidates(
        SourceIntakeBulkResolutionRequest(decisions=[decision])
    )


def test_manual_correction_replaces_current_qaqc_state(tmp_path: Path) -> None:
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

    assert any(
        check.check_id == "identity.uwi.present"
        for check in updated.qaqc_status.checks
    )
    assert not any(
        check.check_id == "identity.uwi.missing"
        for check in updated.qaqc_status.checks
    )
    assert not hasattr(updated, "qaqc_history")


def test_warning_acceptance_removes_only_current_target_finding(
    tmp_path: Path,
) -> None:
    service, candidate = _scan(tmp_path)
    before_ids = {check.check_id for check in candidate.qaqc_status.checks}

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
    after_ids = {check.check_id for check in updated.qaqc_status.checks}

    assert "identity.uwi.missing" not in after_ids
    assert after_ids == before_ids - {"identity.uwi.missing"}
    assert updated.resolution_history[-1].actor == "reviewer"


def test_hard_failure_override_is_rejected(tmp_path: Path) -> None:
    service, candidate = _scan(tmp_path)
    candidate.parse_error = "Unreadable source."
    candidate.qaqc_status = run_source_intake_qaqc(candidate)

    snapshot = service._load_snapshot()
    service._save_snapshot(
        snapshot.model_copy(update={"candidates": [candidate]})
    )

    with pytest.raises(
        SourceIntakeError,
        match="Hard failures cannot be overridden",
    ):
        _resolve(
            service,
            SourceIntakeResolutionDecision(
                occurrence_id=candidate.occurrence_id,
                action=SourceIntakeResolutionAction.PROMOTE_WITH_EXCEPTION,
                actor="reviewer",
                reason="Attempted exception.",
                accepted_warning_codes=["review_required"],
            ),
        )


def test_current_state_survives_persistence_without_qaqc_history(
    tmp_path: Path,
) -> None:
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

    reloaded = WlvSourceIntakeService(
        storage_path=tmp_path / "source.json"
    )
    updated = reloaded.get_workbench().candidates[0]

    assert not hasattr(updated, "qaqc_history")
    assert not any(
        check.check_id == "identity.uwi.missing"
        for check in updated.qaqc_status.checks
    )
    assert updated.resolution_history[-1].actor == "reviewer"
