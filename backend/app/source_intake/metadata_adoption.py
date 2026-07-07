"""Read-only adoption planning for legacy managed source metadata.

This module computes what `source_metadata_v1` would contain from metadata
already persisted by the parser. It never mutates managed records and never
infers values from paths, filenames, geography, or external knowledge.
"""

from __future__ import annotations

from typing import Any

from .canonical_metadata import (
    canonical_metadata_from_dlis_values,
    canonical_metadata_from_las_header,
)
from .models import SourceIntakeCanonicalMetadata


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _header_value(header: dict[str, Any], key: str) -> Any:
    value = header.get(key)
    if isinstance(value, dict):
        return value.get("value")
    return value


def build_canonical_metadata_from_persisted_source(
    source_metadata: dict[str, Any],
) -> SourceIntakeCanonicalMetadata | None:
    """Return a read-only canonical metadata proposal for one managed source.

    Existing canonical metadata is returned unchanged. Legacy records are
    converted only from explicit parser-emitted header values.
    """

    existing = source_metadata.get("canonical_source_metadata")
    if isinstance(existing, dict):
        return SourceIntakeCanonicalMetadata.model_validate(existing)

    parsed = _dict(source_metadata.get("parsed_metadata"))
    if not parsed:
        return None

    source_format = (_text(parsed.get("source_format")) or "").upper()
    parser_id = _text(parsed.get("parser_id")) or "unknown-parser"
    well_header = _dict(parsed.get("well_header"))
    log_header = _dict(parsed.get("log_header"))

    if source_format == "LAS":
        explicit_header: dict[str, Any] = {}
        mapping = {
            "WELL": well_header.get("well_name"),
            "UWI": well_header.get("uwi"),
            "COMP": well_header.get("operator"),
            "FLD": well_header.get("field"),
            "BLOCK": well_header.get("block"),
            "CTRY": well_header.get("country"),
            "SRVC": log_header.get("service_company"),
            "RUN_DATE": log_header.get("run_date"),
        }
        for key, value in mapping.items():
            if _text(value) is not None:
                explicit_header[key] = {"value": value}

        return canonical_metadata_from_las_header(
            explicit_header,
            parser_id=parser_id,
        )

    if source_format == "DLIS":
        explicit_values = {
            "well_name": well_header.get("well_name"),
            "uwi": well_header.get("uwi"),
            "operator": well_header.get("operator"),
            "field": well_header.get("field"),
            "block": well_header.get("block"),
            "country": well_header.get("country"),
            "producer": log_header.get("service_company"),
            "run_date": log_header.get("run_date"),
        }
        return canonical_metadata_from_dlis_values(
            explicit_values,
            parser_id=parser_id,
            source_section="Persisted parser metadata",
        )

    return None


def adoption_summary(
    source_metadata: dict[str, Any],
) -> dict[str, Any]:
    proposed = build_canonical_metadata_from_persisted_source(source_metadata)
    return {
        "already_canonical": isinstance(
            source_metadata.get("canonical_source_metadata"),
            dict,
        ),
        "proposal_available": proposed is not None,
        "source_format": proposed.source_format if proposed is not None else None,
        "parser_id": proposed.parser_id if proposed is not None else None,
        "fields": (
            {
                key: {
                    "value": field.value,
                    "original_field": field.original_field,
                    "source_section": field.source_section,
                    "normalization_rule": field.normalization_rule,
                }
                for key, field in proposed.fields.items()
            }
            if proposed is not None
            else {}
        ),
        "unmapped_header_values": (
            proposed.unmapped_header_values if proposed is not None else {}
        ),
    }
