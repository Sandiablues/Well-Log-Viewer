"""Evidence-backed metadata resolution for WLV Source Intake.

This module resolves parsed source metadata into backend-owned metadata fields
with evidence, confidence, and review flags. It does not promote records into
MSI/WMDP and does not create viewer representations.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .identity_gate import clean_identity_value
from .models import (
    SourceFileCandidate,
    SourceIntakeEvidenceRecord,
    SourceIntakeResolvedField,
    SourceIntakeResolvedMetadata,
)

_REQUIRED_REVIEW_FIELDS = {"well_name", "uwi"}
_FIELD_SOURCE_LABELS = {
    "well_name": "LAS ~Well WELL field",
    "uwi": "LAS ~Well UWI/API field",
    "operator": "LAS ~Well COMP/OPERATOR field",
    "field": "LAS ~Well FLD/FIELD field",
    "block": "LAS ~Well BLOCK/LICENSE field",
}


def resolve_candidate_metadata(candidate: SourceFileCandidate) -> Optional[SourceIntakeResolvedMetadata]:
    """Resolve parsed LAS metadata into evidence-backed source-intake metadata.

    The LAS header remains authoritative for extracted well identity values.
    Folder/path hints are treated only as low-confidence conflict evidence; they
    must not replace LAS header values.
    """
    parsed = candidate.parsed_metadata
    if parsed is None:
        return None

    well_header = parsed.well_header
    fields = {
        "well_name": _resolved_field("well_name", well_header.well_name, candidate),
        "uwi": _resolved_field("uwi", well_header.uwi, candidate),
        "operator": _resolved_field("operator", well_header.operator, candidate),
        "field": _resolved_field("field", well_header.field, candidate),
        "block": _resolved_field("block", well_header.block, candidate),
    }

    warnings: list[str] = []
    for field in fields.values():
        warnings.extend(field.warnings)

    _apply_path_identity_conflict(candidate, fields["well_name"], warnings)

    evidence_count = sum(len(field.evidence) for field in fields.values())
    review_required = any(field.review_required for field in fields.values()) or bool(warnings)

    return SourceIntakeResolvedMetadata(
        well_name=fields["well_name"],
        uwi=fields["uwi"],
        operator=fields["operator"],
        field=fields["field"],
        block=fields["block"],
        review_required=review_required,
        warning_count=len(warnings),
        warnings=warnings,
        evidence_count=evidence_count,
    )


def _resolved_field(field_name: str, value: Optional[str], candidate: SourceFileCandidate) -> SourceIntakeResolvedField:
    clean_value = _clean(value)
    source_label = _FIELD_SOURCE_LABELS[field_name]

    if clean_value:
        evidence = SourceIntakeEvidenceRecord(
            field_name=field_name,
            value=clean_value,
            source=source_label,
            source_path=candidate.relative_path,
            confidence="high",
        )
        return SourceIntakeResolvedField(
            field_name=field_name,
            value=clean_value,
            source=source_label,
            confidence="high",
            review_required=False,
            evidence=[evidence],
        )

    review_required = field_name in _REQUIRED_REVIEW_FIELDS
    warnings = []
    if review_required:
        label = "UWI/API" if field_name == "uwi" else "well name"
        warnings.append(f"Missing {label} in LAS well header; review required.")

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
                message=warnings[0] if warnings else f"No {field_name} evidence found in parsed LAS metadata.",
            )
        ],
        warnings=warnings,
    )


def _apply_path_identity_conflict(
    candidate: SourceFileCandidate,
    well_name_field: SourceIntakeResolvedField,
    warnings: list[str],
) -> None:
    if not well_name_field.value:
        return

    path_hint = _parent_folder_hint(candidate.relative_path)
    if not path_hint:
        return

    if _normalize_identity(path_hint) == _normalize_identity(well_name_field.value):
        return

    message = (
        "Path-derived well hint conflicts with LAS well header; "
        "LAS header value was retained and review is required."
    )
    warning = f"{message} path_hint={path_hint!r}; las_well={well_name_field.value!r}"
    warnings.append(warning)
    well_name_field.review_required = True
    well_name_field.warnings.append(warning)
    well_name_field.evidence.append(
        SourceIntakeEvidenceRecord(
            field_name="well_name",
            value=path_hint,
            source="relative path parent folder hint",
            source_path=candidate.relative_path,
            confidence="low_conflict",
            message=message,
        )
    )


def _parent_folder_hint(relative_path: str) -> Optional[str]:
    parent = Path(relative_path).parent
    if str(parent) in {"", "."}:
        return None
    parts = [part for part in parent.parts if part not in {"", "."}]
    if not parts:
        return None
    hint = parts[-1].replace("_", " ").replace("-", " ").strip()
    if not hint or _normalize_identity(hint) in {"logs", "las", "data", "welllogs", "welllogdata"}:
        return None
    return hint


def _normalize_identity(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _clean(value: Optional[str]) -> Optional[str]:
    return clean_identity_value(value)
