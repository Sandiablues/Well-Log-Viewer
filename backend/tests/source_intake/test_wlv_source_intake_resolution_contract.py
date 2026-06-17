from app.source_intake.models import (
    SourceFileCandidate,
    SourceIntakeBulkResolutionRequest,
    SourceIntakeCandidateRole,
    SourceIntakeFileType,
    SourceIntakeParseStatus,
    SourceIntakeQaqcResult,
    SourceIntakeQaqcStatus,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionDecision,
    SourceIntakeResolutionState,
)
from app.source_intake.resolution_service import (
    SourceIntakeResolutionError,
    SourceIntakeResolutionService,
    is_ingestible,
)


def candidate(path: str, checksum: str, *, review=False, failures=0):
    return SourceFileCandidate(
        source_file_id=f"legacy:{checksum}:{path}",
        repository_id="repo-1",
        scan_id="scan-1",
        file_name=path.rsplit("/", 1)[-1],
        original_path=f"/tmp/{path}",
        relative_path=path,
        file_extension="las",
        detected_file_type=SourceIntakeFileType.LAS,
        candidate_role=SourceIntakeCandidateRole.WELL_LOG_CANDIDATE,
        size_bytes=100,
        modified_at="2026-06-17T00:00:00+00:00",
        checksum=checksum,
        parser_status=SourceIntakeParseStatus.PARSED_WITH_WARNINGS if review else SourceIntakeParseStatus.PARSED,
        qaqc_status=SourceIntakeQaqcResult(
            status=SourceIntakeQaqcStatus.REVIEW_REQUIRED if review else SourceIntakeQaqcStatus.PASS,
            failure_count=failures,
            review_required=review,
        ),
        review_required=review,
    )


def test_occurrence_identity_separates_paths_but_duplicate_group_uses_content():
    service = SourceIntakeResolutionService()
    rows = service.initialize_candidates([
        candidate("a/file.las", "abc"),
        candidate("b/file.las", "abc"),
    ])
    assert rows[0].occurrence_id != rows[1].occurrence_id
    assert rows[0].duplicate_group_id == rows[1].duplicate_group_id
    states = {row.resolution_state for row in rows}
    assert states == {SourceIntakeResolutionState.AUTO_INGESTIBLE, SourceIntakeResolutionState.DUPLICATE}


def test_warning_candidate_can_be_reviewed_without_overriding_hard_failure():
    service = SourceIntakeResolutionService()
    row = service.initialize_candidates([candidate("warn.las", "warn", review=True)])[0]
    assert row.resolution_state == SourceIntakeResolutionState.UNRESOLVED
    response = service.apply_bulk([row], SourceIntakeBulkResolutionRequest(decisions=[
        SourceIntakeResolutionDecision(
            occurrence_id=row.occurrence_id,
            action=SourceIntakeResolutionAction.WARNING_ACCEPTED,
            actor="reviewer",
            reason="Missing optional unit accepted.",
            accepted_warning_codes=["missing_optional_unit"],
        )
    ]))
    assert response.resolved_count == 1
    assert row.resolution_state == SourceIntakeResolutionState.RESOLVED
    assert is_ingestible(row)
    assert row.resolution_history[-1].actor == "reviewer"


def test_exclusion_requires_reason_and_is_audited():
    service = SourceIntakeResolutionService()
    row = service.initialize_candidates([candidate("x.las", "x", review=True)])[0]
    try:
        service.apply_bulk([row], SourceIntakeBulkResolutionRequest(decisions=[
            SourceIntakeResolutionDecision(
                occurrence_id=row.occurrence_id,
                action=SourceIntakeResolutionAction.EXCLUDED,
            )
        ]))
    except SourceIntakeResolutionError:
        pass
    else:
        raise AssertionError("exclusion without reason should fail")


def test_accounting_states_are_explicit_for_all_occurrences():
    service = SourceIntakeResolutionService()
    rows = service.initialize_candidates([
        candidate("good.las", "g"),
        candidate("review.las", "r", review=True),
        candidate("bad.las", "b", review=True, failures=1),
        candidate("dup-a.las", "d"),
        candidate("dup-b.las", "d"),
    ])
    assert len(rows) == 5
    assert all(row.occurrence_id for row in rows)
    assert all(row.content_fingerprint for row in rows)
    assert {row.resolution_state for row in rows} == {
        SourceIntakeResolutionState.AUTO_INGESTIBLE,
        SourceIntakeResolutionState.UNRESOLVED,
        SourceIntakeResolutionState.HARD_FAILED,
        SourceIntakeResolutionState.DUPLICATE,
    }
