"""Evidence-backed metadata resolution for WLV Source Intake.

Canonical values are resolved only from explicit parser-native source metadata
or explicit human corrections applied elsewhere in the intake workflow.
Missing values remain missing. No path, filename, geographic, or external
knowledge inference is permitted.
"""

from __future__ import annotations

from typing import Optional

from .identity_gate import clean_identity_value
from .canonical_metadata import canonical_value
from .models import (
    SourceFileCandidate,
    SourceIntakeCanonicalMetadataField,
    SourceIntakeEvidenceRecord,
    SourceIntakeResolvedField,
    SourceIntakeResolvedMetadata,
)

_REQUIRED_REVIEW_FIELDS = {"well_name", "uwi"}
_CANONICAL_FIELDS = (
    "well_name",
    "wellbore_name",
    "uwi",
    "operator",
    "field",
    "block",
    "country",
    "latitude",
    "longitude",
    "producer",
    "product",
    "version",
    "creation_date",
    "run_date",
)


def resolve_candidate_metadata(
    candidate: SourceFileCandidate,
) -> Optional[SourceIntakeResolvedMetadata]:
    parsed = candidate.parsed_metadata
    if parsed is None:
        return None

    fields = {
        field_name: _resolved_field(
            field_name,
            parsed.canonical_metadata.fields.get(field_name)
            if parsed.canonical_metadata is not None
            else None,
            candidate,
        )
        for field_name in _CANONICAL_FIELDS
    }

    # Compatibility for pre-v2 parsed records: use only explicit parsed header
    # values. This is not inference.
    compatibility = {
        "well_name": parsed.well_header.well_name,
        "uwi": parsed.well_header.uwi,
        "operator": parsed.well_header.operator,
        "field": parsed.well_header.field,
        "block": parsed.well_header.block,
        "country": parsed.well_header.country,
        "producer": parsed.log_header.service_company if parsed.log_header else None,
        "run_date": parsed.log_header.run_date if parsed.log_header else None,
    }
    for field_name, value in compatibility.items():
        if fields[field_name].value is None and value is not None:
            fields[field_name] = _explicit_compatibility_field(
                field_name,
                value,
                parsed.parser_id,
                parsed.source_format,
                candidate,
            )

    warnings = [
        warning
        for field in fields.values()
        for warning in field.warnings
    ]
    evidence_count = sum(len(field.evidence) for field in fields.values())

    return SourceIntakeResolvedMetadata(
        well_name=fields["well_name"],
        wellbore_name=fields["wellbore_name"],
        uwi=fields["uwi"],
        operator=fields["operator"],
        field=fields["field"],
        block=fields["block"],
        country=fields["country"],
        latitude=fields["latitude"],
        longitude=fields["longitude"],
        producer=fields["producer"],
        product=fields["product"],
        version=fields["version"],
        creation_date=fields["creation_date"],
        run_date=fields["run_date"],
        review_required=any(field.review_required for field in fields.values()),
        warning_count=len(warnings),
        warnings=warnings,
        evidence_count=evidence_count,
    )


def _resolved_field(
    field_name: str,
    field: SourceIntakeCanonicalMetadataField | None,
    candidate: SourceFileCandidate,
) -> SourceIntakeResolvedField:
    if field is not None and clean_identity_value(field.value):
        value = clean_identity_value(field.value)
        source = f"{field.source_format} {field.source_section} {field.original_field}"
        return SourceIntakeResolvedField(
            field_name=field_name,
            value=value,
            source=source,
            confidence="high",
            review_required=field.review_required,
            evidence=[
                SourceIntakeEvidenceRecord(
                    field_name=field_name,
                    value=value,
                    source=source,
                    source_path=candidate.relative_path,
                    confidence="high",
                    message=(
                        f"Explicit source field {field.original_field!r}; "
                        f"normalization={field.normalization_rule or 'none'}."
                    ),
                )
            ],
        )

    review_required = field_name in _REQUIRED_REVIEW_FIELDS
    warnings: list[str] = []
    if review_required:
        warnings.append(
            f"Missing {field_name} in authoritative source metadata; review required."
        )

    return SourceIntakeResolvedField(
        field_name=field_name,
        value=None,
        source="missing",
        confidence="missing",
        review_required=review_required,
        evidence=[
            SourceIntakeEvidenceRecord(
                field_name=field_name,
                value=None,
                source="missing",
                source_path=candidate.relative_path,
                confidence="missing",
                message=(
                    f"No explicit {field_name} value was supplied by the source."
                ),
            )
        ],
        warnings=warnings,
    )


def _explicit_compatibility_field(
    field_name: str,
    value: str,
    parser_id: str,
    source_format: str,
    candidate: SourceFileCandidate,
) -> SourceIntakeResolvedField:
    clean_value = clean_identity_value(value)
    if clean_value is None:
        return _resolved_field(field_name, None, candidate)
    source = f"{source_format} parsed header compatibility field"
    return SourceIntakeResolvedField(
        field_name=field_name,
        value=clean_value,
        source=source,
        confidence="high",
        review_required=False,
        evidence=[
            SourceIntakeEvidenceRecord(
                field_name=field_name,
                value=clean_value,
                source=source,
                source_path=candidate.relative_path,
                confidence="high",
                message=f"Explicit value emitted by parser {parser_id}.",
            )
        ],
    )
