from pathlib import Path

from app.source_intake.models import (
    ExternalSourceReference, SourceFileCandidate, SourceIntakeCandidateRole,
    SourceIntakeCurrentDecision, SourceIntakeFileType, SourceIntakeHumanDecision,
    SourceIntakeParseStatus, SourceIntakeParsedMetadata, SourceIntakeQaqcCheck,
    SourceIntakeQaqcResult, SourceIntakeQaqcSeverity, SourceIntakeQaqcStatus,
    SourceIntakeFindingClass, SourceIntakeWellHeader, SourceIntakeLogHeader,
    SourceIntakeResolvedMetadata, SourceIntakeResolvedField, SourceIntakeSnapshot,
)
from app.source_intake.service import WlvSourceIntakeService


def _candidate() -> SourceFileCandidate:
    return SourceFileCandidate(
        source_file_id="candidate-1", occurrence_id="occurrence-1", repository_id="repo-1", scan_id="scan-1",
        file_name="well.las", original_path="/external/well.las", relative_path="well.las", file_extension=".las",
        detected_file_type=SourceIntakeFileType.LAS, candidate_role=SourceIntakeCandidateRole.WELL_LOG_CANDIDATE,
        size_bytes=10, modified_at="2026-01-01T00:00:00Z", checksum="a" * 64, content_fingerprint="a" * 64,
        parser_status=SourceIntakeParseStatus.PARSED_WITH_WARNINGS,
        source_reference=ExternalSourceReference(source_uri="/external/well.las", display_name="well.las", source_format="LAS"),
        parsed_metadata=SourceIntakeParsedMetadata(
            parser_id="test_parser", source_format="LAS",
            well_header=SourceIntakeWellHeader(well_name="RAW", operator="Raw Operator"),
            log_header=SourceIntakeLogHeader(file_name="well.las", file_type=SourceIntakeFileType.LAS),
        ),
        resolved_metadata=SourceIntakeResolvedMetadata(
            well_name=SourceIntakeResolvedField(field_name="well_name", value="CORRECTED", source="manual_resolution"),
            uwi=SourceIntakeResolvedField(field_name="uwi"), operator=SourceIntakeResolvedField(field_name="operator", value="Raw Operator", source="header"),
            field=SourceIntakeResolvedField(field_name="field"), block=SourceIntakeResolvedField(field_name="block"),
        ),
        current_decision=SourceIntakeCurrentDecision(
            decision=SourceIntakeHumanDecision.CORRECT, actor="tester", reason="Header correction", corrected_values={"well_name": "CORRECTED"},
            accepted_finding_codes=["metadata_warning"],
        ),
        qaqc_status=SourceIntakeQaqcResult(
            status=SourceIntakeQaqcStatus.WARNING, severity=SourceIntakeQaqcSeverity.MEDIUM, check_count=2, warning_count=2,
            checks=[
                SourceIntakeQaqcCheck(check_id="metadata_warning", status=SourceIntakeQaqcStatus.WARNING, severity=SourceIntakeQaqcSeverity.MEDIUM, finding_class=SourceIntakeFindingClass.REVIEW_CONTROLLED, message="Metadata warning"),
                SourceIntakeQaqcCheck(check_id="other_warning", status=SourceIntakeQaqcStatus.WARNING, severity=SourceIntakeQaqcSeverity.LOW, finding_class=SourceIntakeFindingClass.NON_BLOCKING_WARNING, message="Other warning"),
            ],
        ),
    )


def test_export_overlay_package_contains_original_effective_overlay_and_qaqc(tmp_path: Path):
    service = WlvSourceIntakeService(storage_path=tmp_path / "snapshot.json")
    candidate = _candidate()
    service._save_snapshot(SourceIntakeSnapshot(candidates=[candidate]))
    package = service.export_overlay_package([candidate.source_file_id])
    assert package.source_files_modified is False
    assert package.candidate_count == 1
    item = package.candidates[0]
    assert item.original_metadata["well_name"] == "RAW"
    assert item.effective_metadata["well_name"] == "CORRECTED"
    assert item.metadata_overlay == {"well_name": "CORRECTED"}
    assert item.resolved_finding_codes == ["metadata_warning"]
    assert item.unresolved_finding_codes == ["other_warning"]


def test_export_reference_is_released_after_package_generation(tmp_path: Path):
    service = WlvSourceIntakeService(storage_path=tmp_path / "snapshot.json")
    candidate = _candidate()
    service._save_snapshot(SourceIntakeSnapshot(candidates=[candidate]))
    service.export_overlay_package([candidate.source_file_id])
    snapshot = service._load_snapshot()
    assert snapshot.candidates[0].reference_counts.get("export", 0) == 0
