from pathlib import Path

from app.source_intake.canonical_metadata import (
    canonical_metadata_from_dlis_values,
    canonical_metadata_from_las_header,
)
from app.source_intake.metadata_resolver import resolve_candidate_metadata
from app.source_intake.models import (
    SourceFileCandidate,
    SourceIntakeCandidateRole,
    SourceIntakeFileType,
    SourceIntakeParsedMetadata,
    SourceIntakeWellHeader,
)


def _candidate(parsed: SourceIntakeParsedMetadata) -> SourceFileCandidate:
    return SourceFileCandidate(
        source_file_id="source-1",
        repository_id="repo-1",
        scan_id="scan-1",
        file_name="example.las",
        original_path="/tmp/example.las",
        relative_path="field/country/example.las",
        file_extension=".las",
        detected_file_type=SourceIntakeFileType.LAS,
        candidate_role=SourceIntakeCandidateRole.WELL_LOG_CANDIDATE,
        size_bytes=1,
        modified_at="2026-07-06T00:00:00+00:00",
        checksum="abc",
        parsed_metadata=parsed,
    )


def test_las_header_extracts_only_explicit_values() -> None:
    metadata = canonical_metadata_from_las_header(
        {
            "WELL": {"value": "Well A"},
            "CTRY": {"value": "Norway"},
            "COMP": {"value": "Operator A"},
            "UNRECOGNIZED": {"value": "keep me"},
        },
        parser_id="las-test",
    )

    assert metadata.fields["well_name"].value == "Well A"
    assert metadata.fields["country"].value == "Norway"
    assert metadata.fields["operator"].value == "Operator A"
    assert "field" not in metadata.fields
    assert "UNRECOGNIZED" in metadata.unmapped_header_values


def test_missing_country_is_not_inferred_from_path_or_context() -> None:
    metadata = canonical_metadata_from_las_header(
        {"WELL": {"value": "Well A"}},
        parser_id="las-test",
    )
    parsed = SourceIntakeParsedMetadata(
        parser_id="las-test",
        source_format="LAS",
        well_header=SourceIntakeWellHeader(well_name="Well A"),
        canonical_metadata=metadata,
    )

    resolved = resolve_candidate_metadata(_candidate(parsed))

    assert resolved is not None
    assert resolved.well_name.value == "Well A"
    assert resolved.country is not None
    assert resolved.country.value is None
    assert resolved.country.source == "missing"


def test_dlis_values_preserve_explicit_source_only() -> None:
    metadata = canonical_metadata_from_dlis_values(
        {
            "well_name": "15/9-F-5",
            "operator": "StatoilHydro ASA",
            "field": "Volve",
            "producer": "CROCKER DATA PROCESSING",
            "unknown_origin_attribute": "preserve",
        },
        parser_id="dlis-test",
    )

    assert metadata.fields["well_name"].value == "15/9-F-5"
    assert metadata.fields["producer"].value == "CROCKER DATA PROCESSING"
    assert "country" not in metadata.fields
    assert metadata.unmapped_header_values["unknown_origin_attribute"] == "preserve"


def test_resolver_evidence_retains_original_field_and_parser() -> None:
    metadata = canonical_metadata_from_las_header(
        {"COUNTRY": {"value": "Portugal"}},
        parser_id="las-test",
    )
    parsed = SourceIntakeParsedMetadata(
        parser_id="las-test",
        source_format="LAS",
        canonical_metadata=metadata,
    )

    resolved = resolve_candidate_metadata(_candidate(parsed))

    assert resolved is not None
    assert resolved.country is not None
    assert resolved.country.value == "Portugal"
    assert resolved.country.evidence[0].source == "LAS LAS ~Well COUNTRY"
    assert "parser" not in resolved.country.value.lower()
