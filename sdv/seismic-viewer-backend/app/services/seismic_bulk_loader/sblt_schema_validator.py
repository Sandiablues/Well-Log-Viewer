"""
SBLT-2: Schema validator for mapped SBLT loadsheet rows.

Ownership: backend SBLT service.

Responsibilities:
- Validate canonical fields produced by sblt_column_mapper.
- Generate structured, machine-readable QAQC flags.
- Assign a deterministic row status based on schema validation only.

SBLT-2 scope:
- Schema / column presence validation only.
- No file or SEG-Y path existence validation.
- No SEG-Y header inspection.
- No metadata normalisation beyond record_type canonicalisation.
- No MSI interaction.
- No duplicate seismic record detection.

Status assignment rules:
    ready           — all required fields present, record_type is 2d_line or
                      3d_volume, conditional field (line_name / volume_name)
                      is also present. Missing recommended fields produce
                      info-level QAQC flags but do NOT change this status.
    review_required — required and conditional fields present, but record_type
                      value is unrecognised (normalises to "unknown").
    blocked         — one or more required fields missing, OR conditional field
                      is missing for a known record_type.
"""

from __future__ import annotations

from typing import Any

from .sblt_column_mapper import (
    REQUIRED_FIELDS,
    RECOMMENDED_FIELDS,
    CONDITIONAL_FIELDS,
    ALL_CANONICAL_FIELDS,
    ColumnMappingResult,
    normalize_record_type,
)


# ---------------------------------------------------------------------------
# QAQC flag builder
# ---------------------------------------------------------------------------

def _flag(
    severity: str,
    code: str,
    message: str,
    field: str | None = None,
    source: str = "loadsheet",
) -> dict[str, Any]:
    """
    Build a structured QAQC flag.

    Severity values: info | warning | error | blocker
    """
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "field": field,
        "source": source,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_row_schema(
    mapping: ColumnMappingResult,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str]:
    """
    Validate a single row's canonical fields against the SBLT-2 schema.

    Args:
        mapping — ColumnMappingResult from sblt_column_mapper.map_columns()

    Returns:
        A 4-tuple of:
            canonical_fields  — dict of all canonical field names with values;
                                record_type is the normalised canonical string.
            validation        — structured validation block for the row.
            qaqc_flags        — list of structured QAQC flag dicts.
            status            — row status string: "ready" | "review_required" | "blocked"
    """
    canonical: dict[str, str | None] = dict(mapping.canonical_values)
    flags: list[dict[str, Any]] = []
    required_missing: list[str] = []
    recommended_missing: list[str] = []

    # --- Required field checks (before record_type normalisation) ---
    # survey_name and segy_path are simple presence checks.
    for field in ("survey_name", "segy_path"):
        val = canonical.get(field)
        if not val or not str(val).strip():
            required_missing.append(field)
            flags.append(_flag(
                severity="blocker",
                code="MISSING_REQUIRED_FIELD",
                message=f"Required field '{field}' is missing.",
                field=field,
            ))

    # --- record_type: presence check then value normalisation ---
    raw_record_type = canonical.get("record_type") or ""
    raw_stripped = str(raw_record_type).strip()

    if not raw_stripped:
        # record_type column absent or blank
        required_missing.append("record_type")
        flags.append(_flag(
            severity="blocker",
            code="MISSING_REQUIRED_FIELD",
            message="Required field 'record_type' is missing.",
            field="record_type",
        ))
        normalised_record_type = "unknown"
    else:
        normalised_record_type = normalize_record_type(raw_stripped)
        if normalised_record_type == "unknown":
            flags.append(_flag(
                severity="warning",
                code="UNKNOWN_RECORD_TYPE",
                message=(
                    f"record_type value '{raw_stripped}' was not recognised. "
                    "Expected: 2D, 3D, Line, Volume, or equivalent. "
                    "Row set to review_required unless other issues are blocking."
                ),
                field="record_type",
            ))

    # Write the normalised canonical value back into the dict.
    canonical["record_type"] = normalised_record_type if raw_stripped else None

    # --- Conditional field checks ---
    conditional_field = CONDITIONAL_FIELDS.get(normalised_record_type)
    if conditional_field is not None:
        val = canonical.get(conditional_field)
        if not val or not str(val).strip():
            required_missing.append(conditional_field)
            flags.append(_flag(
                severity="blocker",
                code="MISSING_CONDITIONAL_FIELD",
                message=(
                    f"Field '{conditional_field}' is required when "
                    f"record_type is '{normalised_record_type}'."
                ),
                field=conditional_field,
            ))

    # --- Recommended field checks ---
    for field in RECOMMENDED_FIELDS:
        val = canonical.get(field)
        if not val or not str(val).strip():
            recommended_missing.append(field)
            flags.append(_flag(
                severity="info",
                code="MISSING_RECOMMENDED_FIELD",
                message=f"Recommended field '{field}' is missing.",
                field=field,
            ))

    # --- Duplicate canonical column QAQC warnings ---
    for dup in mapping.duplicate_mappings:
        flags.append(_flag(
            severity="warning",
            code="DUPLICATE_CANONICAL_COLUMN",
            message=(
                f"Multiple source columns map to canonical field "
                f"'{dup['canonical_field']}': {dup['columns']}. "
                "First value used; remaining values discarded."
            ),
            field=dup["canonical_field"],
        ))

    # --- Status determination ---
    # Recommended fields missing produces QAQC info flags only — they do NOT
    # change row status. The ground-truth test cases (work order §Required Tests)
    # show that a row with all required + conditional fields and no recommended
    # fields should be "ready", not "review_required".
    #
    # Status rules:
    #   blocked         — any required or conditional field missing
    #   review_required — required + conditional fields present, but
    #                     record_type is unknown (unrecognised value)
    #   ready           — required + conditional fields present, record_type
    #                     is 2d_line or 3d_volume
    if required_missing:
        status = "blocked"
    elif normalised_record_type == "unknown":
        # record_type column was present but unrecognised; non-blocking.
        status = "review_required"
    else:
        status = "ready"

    # --- Build output dicts ---
    validation: dict[str, Any] = {
        "schema_validated": True,
        "required_missing": required_missing,
        "recommended_missing": recommended_missing,
        "mapped_columns": mapping.mapped_columns,
        "unmapped_columns": mapping.unmapped_columns,
        "duplicate_mappings": mapping.duplicate_mappings,
    }

    return canonical, validation, flags, status
