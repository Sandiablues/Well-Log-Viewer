from app.source_intake.models import (
    WLV_SOURCE_INTAKE_WORKFLOW_STEPS,
    SourceFileCandidate,
    SourceIntakeFileType,
    SourceIntakeCandidateRole,
    SourceIntakeResolutionState,
    SourceIntakeReadinessState,
)
from app.source_intake.readiness import (
    evaluate_registration_readiness,
    evaluate_wmd_availability_readiness,
)
from app.source_intake.resolution_service import (
    SourceIntakeResolutionService,
    is_ingestible,
    is_wmd_eligible,
)


def _candidate() -> SourceFileCandidate:
    return SourceFileCandidate(
        source_file_id="candidate-1",
        repository_id="repo-1",
        scan_id="scan-1",
        file_name="well.las",
        relative_path="well.las",
        original_path="/external/well.las",
        detected_file_type=SourceIntakeFileType.LAS,
        file_extension=".las",
        candidate_role=SourceIntakeCandidateRole.WELL_LOG_CANDIDATE,
        size_bytes=1,
        modified_at="now",
        checksum="abc",
        resolution_state=SourceIntakeResolutionState.RESOLVED,
    )


def test_workflow_exposes_transient_wmd_semantics():
    joined = " | ".join(WLV_SOURCE_INTAKE_WORKFLOW_STEPS)
    assert "Make Available in WMD" in joined
    assert "Register to MSI" not in joined
    assert "Stage in WMDP" not in joined


def test_canonical_wmd_eligibility_preserves_legacy_alias():
    candidate = _candidate()
    assert is_wmd_eligible(candidate) is True
    assert is_ingestible(candidate) is True


def test_mark_available_to_wmd_preserves_serialized_compatibility_state():
    candidate = _candidate()
    candidate.readiness_state = SourceIntakeReadinessState.READY
    SourceIntakeResolutionService().mark_available_to_wmd(candidate)
    assert candidate.resolution_state == SourceIntakeResolutionState.REGISTERED


def test_legacy_readiness_entrypoint_delegates_to_canonical_function():
    legacy = evaluate_registration_readiness(_candidate())
    canonical = evaluate_wmd_availability_readiness(_candidate())
    assert legacy.readiness_state == canonical.readiness_state
    assert legacy.readiness_issues == canonical.readiness_issues
    assert legacy.available_human_actions == canonical.available_human_actions
