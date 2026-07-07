"""Format-neutral source metadata extraction for WLV Source Intake.

Only explicit values present in parser-native source headers are mapped into
canonical metadata. Missing values remain unset. No filename, path, geographic,
field, or external-knowledge inference is permitted.
"""

from __future__ import annotations

from typing import Any, Iterable

from .models import (
    SourceIntakeCanonicalMetadata,
    SourceIntakeCanonicalMetadataField,
)


_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "well_name": ("WELL", "WELL_NAME", "WELLNAME"),
    "wellbore_name": ("WELLBORE", "WELLBORE_NAME", "BOREHOLE"),
    "uwi": ("UWI", "API", "WELLID", "WELL_ID"),
    "operator": ("COMP", "COMPANY", "OPERATOR", "OPER"),
    "field": ("FLD", "FIELD"),
    "block": ("BLOCK", "BLK", "LICENSE", "LICENCE"),
    "country": ("CTRY", "COUNTRY"),
    "latitude": ("LATI", "LAT", "LATITUDE"),
    "longitude": ("LONG", "LON", "LONGITUDE"),
    "producer": ("SRVC", "SERVICE", "SERVICE_COMPANY", "PRODUCER"),
    "product": ("PRODUCT", "PROD"),
    "version": ("VERSION", "VERS"),
    "creation_date": ("CREATION_DATE", "CREATED_AT", "DATE"),
    "run_date": ("RUN_DATE", "LOG_DATE", "DATE"),
}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("value", "data", "text"):
            if key in value:
                return _text(value[key])
        return None
    rendered = str(value).strip()
    return rendered or None


def _normalized_header(header: dict[str, Any]) -> dict[str, tuple[str, Any]]:
    result: dict[str, tuple[str, Any]] = {}
    for original_field, value in header.items():
        key = str(original_field).strip().upper()
        if not key:
            continue
        result[key] = (str(original_field), value)
    return result


def canonical_metadata_from_las_header(
    header: dict[str, Any],
    *,
    parser_id: str,
) -> SourceIntakeCanonicalMetadata:
    normalized = _normalized_header(header)
    fields: dict[str, SourceIntakeCanonicalMetadataField] = {}
    consumed: set[str] = set()

    for canonical_field, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            match = normalized.get(alias)
            if match is None:
                continue
            original_field, raw_value = match
            value = _text(raw_value)
            consumed.add(alias)
            if value is None:
                break
            fields[canonical_field] = SourceIntakeCanonicalMetadataField(
                canonical_field=canonical_field,
                value=value,
                original_field=original_field,
                original_value=value,
                source_section="LAS ~Well",
                parser_id=parser_id,
                source_format="LAS",
                normalization_rule="trim_whitespace",
            )
            break

    unmapped = {
        original_field: raw_value
        for key, (original_field, raw_value) in normalized.items()
        if key not in consumed
    }

    return SourceIntakeCanonicalMetadata(
        schema_version="source_metadata_v1",
        source_format="LAS",
        parser_id=parser_id,
        fields=fields,
        unmapped_header_values=unmapped,
    )


def canonical_metadata_from_dlis_values(
    values: dict[str, Any],
    *,
    parser_id: str,
    source_section: str = "DLIS ORIGIN",
) -> SourceIntakeCanonicalMetadata:
    fields: dict[str, SourceIntakeCanonicalMetadataField] = {}
    unmapped: dict[str, Any] = {}

    for canonical_field, raw in values.items():
        value = _text(raw)
        if canonical_field not in _FIELD_ALIASES:
            unmapped[canonical_field] = raw
            continue
        if value is None:
            continue
        fields[canonical_field] = SourceIntakeCanonicalMetadataField(
            canonical_field=canonical_field,
            value=value,
            original_field=canonical_field,
            original_value=value,
            source_section=source_section,
            parser_id=parser_id,
            source_format="DLIS",
            normalization_rule="trim_whitespace",
        )

    return SourceIntakeCanonicalMetadata(
        schema_version="source_metadata_v1",
        source_format="DLIS",
        parser_id=parser_id,
        fields=fields,
        unmapped_header_values=unmapped,
    )


def canonical_value(
    metadata: SourceIntakeCanonicalMetadata | None,
    field_name: str,
) -> str | None:
    if metadata is None:
        return None
    field = metadata.fields.get(field_name)
    return field.value if field is not None else None
