"""
SBLT-3: Row normalizer for SBLT-2 schema-validated sessions.

Ownership: backend SBLT service.

Responsibilities:
- Normalize display values from canonical_fields (trim, collapse whitespace).
- Build normalized key forms for identity purposes.
- Build dataset_label (human-readable) and dataset_key (deterministic internal hint).
- Parse numeric sample_interval_ms from free-text strings.
- Split supporting_document_paths strings into lists.
- Populate normalized_metadata and identity_hints per row.
- Append normalization-stage QAQC flags (preserving all SBLT-2 flags).
- Apply status rules: blocked → blocked, review_required → review_required.
  A ready row becomes review_required only if a usable dataset_key cannot be built.

SBLT-3 scope (this file does not):
- Access the filesystem.
- Resolve symlinks or expand paths.
- Check whether SEG-Y files or document paths exist.
- Inspect SEG-Y headers.
- Detect duplicate records.
- Create MSI records.
- Touch Source Intake.
- Touch frontend.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any


# ---------------------------------------------------------------------------
# Schema versions
# ---------------------------------------------------------------------------

NORMALIZED_METADATA_VERSION = "sblt.normalized_metadata.v1"
IDENTITY_HINTS_VERSION = "sblt.identity_hints.v1"
NORMALIZER_VERSION = "sblt.row_normalizer.v1"


# ---------------------------------------------------------------------------
# Text normalization helpers
# ---------------------------------------------------------------------------

def clean_display_text(s: str | None) -> str:
    """
    Produce a clean display string.

    - Strip leading/trailing whitespace.
    - Collapse repeated internal whitespace to a single space.
    - Preserve original casing.
    """
    if not s:
        return ""
    s = str(s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def make_key_text(s: str | None) -> str:
    """
    Produce a deterministic key string from a display value.

    - Lowercase.
    - Replace runs of whitespace, slash, colon, hyphen, or underscore
      with a single underscore.
    - Strip leading/trailing underscores.
    - Do not remove meaningful alphanumeric characters.
    """
    if not s:
        return ""
    s = str(s).lower()
    s = re.sub(r"[\s/:\-_]+", "_", s)
    return s.strip("_")


def make_filename_key(s: str | None) -> str:
    """
    Produce a deterministic key string from a filename (including extension).

    Like make_key_text but also replaces dots, so that "Line001.sgy"
    becomes "line001_sgy".
    """
    if not s:
        return ""
    s = str(s).lower()
    s = re.sub(r"[\s/:\-_.]+", "_", s)
    return s.strip("_")


# ---------------------------------------------------------------------------
# Numeric parsing
# ---------------------------------------------------------------------------

def parse_sample_interval_ms(
    raw: str | None,
) -> tuple[float | None, dict[str, Any] | None]:
    """
    Parse a sample interval string to a float (milliseconds).

    Accepts: "4", "4.0", "4 ms", "4ms", "4.0 MS" (case-insensitive "ms" suffix).

    Returns:
        (float_value, None)  — on success
        (None, None)         — if raw is blank or absent (not an error)
        (None, qaqc_flag)    — if present but unparseable
    """
    if not raw or not str(raw).strip():
        return None, None

    s = str(raw).strip()
    # Remove trailing whitespace + "ms" suffix (case-insensitive).
    s_clean = re.sub(r"\s*ms$", "", s, flags=re.IGNORECASE).strip()

    try:
        return float(s_clean), None
    except ValueError:
        flag: dict[str, Any] = {
            "severity": "info",
            "code": "UNPARSEABLE_RECOMMENDED_FIELD",
            "message": (
                f"Cannot parse sample_interval_ms value '{raw}'. "
                "Expected a numeric value (e.g. '4', '4.0', '4 ms')."
            ),
            "field": "sample_interval_ms",
            "source": "normalization",
        }
        return None, flag


# ---------------------------------------------------------------------------
# Supporting document path splitting
# ---------------------------------------------------------------------------

def split_supporting_document_paths(raw: str | None) -> list[str]:
    """
    Split a raw supporting_document_paths string into a list.

    - Split on semicolon first; fall back to comma if no semicolon present.
    - Trim each entry.
    - Drop empty entries.
    - Do not validate path existence.
    - Do not classify or move documents.
    """
    if not raw or not str(raw).strip():
        return []
    s = str(raw)
    if ";" in s:
        parts = s.split(";")
    else:
        parts = s.split(",")
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Dataset label and key builders
# ---------------------------------------------------------------------------

def build_dataset_label(
    record_type: str,
    survey_name: str,
    line_name: str,
    volume_name: str,
    segy_filename: str,
) -> str:
    """
    Build a human-readable dataset label.

    2d_line   → "{survey_name} / {line_name}"
    3d_volume → "{survey_name} / {volume_name}"
    unknown   → "{survey_name} / {segy_filename}" or just survey_name
    """
    if record_type == "2d_line" and line_name:
        return f"{survey_name} / {line_name}"
    if record_type == "3d_volume" and volume_name:
        return f"{survey_name} / {volume_name}"
    if survey_name and segy_filename:
        return f"{survey_name} / {segy_filename}"
    return survey_name


def build_dataset_key(
    record_type: str,
    survey_key: str,
    line_or_volume_key: str,
    segy_filename_key: str,
) -> str:
    """
    Build a deterministic, internal-only dataset identity key.

    Format: {record_type}__{survey_key}__{line_or_volume_key}__{segy_filename_key}
    Missing components are omitted (no trailing double-underscores).

    IMPORTANT: This is a normalization-stage identity hint only.
    It is NOT an MSI ID. It is NOT a final registered dataset ID.
    Do not treat it as such in downstream code.

    Note: "unknown" record_type is excluded from the key — it carries no
    identifying information.  A key built from an unknown type and empty
    survey/line/segy fields would produce the string "unknown", which is
    not a useful identity hint and is treated the same as an empty key by
    the caller.  Using "unknown" as a key prefix is therefore suppressed so
    that callers can reliably test `not dataset_key` to detect unusable keys.
    """
    parts = [record_type] if (record_type and record_type != "unknown") else []
    if survey_key:
        parts.append(survey_key)
    if line_or_volume_key:
        parts.append(line_or_volume_key)
    if segy_filename_key:
        parts.append(segy_filename_key)
    return "__".join(parts)


# ---------------------------------------------------------------------------
# QAQC flag builder (normalization-stage)
# ---------------------------------------------------------------------------

def _norm_flag(
    severity: str,
    code: str,
    message: str,
    field: str | None = None,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "field": field,
        "source": "normalization",
    }


# ---------------------------------------------------------------------------
# Public: normalize_row
# ---------------------------------------------------------------------------

def normalize_row(
    row: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str]:
    """
    Normalize a single SBLT row from its canonical_fields.

    Expects the row to have been schema-validated (SBLT-2) so that
    canonical_fields is populated.

    Args:
        row — the current row dict (must have canonical_fields, status).

    Returns:
        A 4-tuple of:
            normalized_metadata  — populated normalized_metadata dict
            identity_hints       — identity hint dict for this row
            new_qaqc_flags       — normalization-stage QAQC flags to append
                                   (existing SBLT-2 flags are NOT repeated here;
                                   the caller merges them)
            new_status           — updated row status (blocked stays blocked;
                                   review_required stays review_required;
                                   ready may become review_required if
                                   dataset_key cannot be built)
    """
    canonical: dict[str, Any] = row.get("canonical_fields") or {}
    current_status: str = str(row.get("status") or "blocked")
    new_qaqc_flags: list[dict[str, Any]] = []
    normalization_warnings: list[str] = []

    # --- Extract raw values from canonical_fields ---
    record_type: str = str(canonical.get("record_type") or "unknown")
    survey_name_raw: str = str(canonical.get("survey_name") or "")
    line_name_raw: str = str(canonical.get("line_name") or "")
    volume_name_raw: str = str(canonical.get("volume_name") or "")
    segy_path_raw: str = str(canonical.get("segy_path") or "")
    processing_stage_raw: str = str(canonical.get("processing_stage") or "")
    crs_raw: str = str(canonical.get("crs") or "")
    datum_raw: str = str(canonical.get("datum") or "")
    sample_interval_raw: str = str(canonical.get("sample_interval_ms") or "")
    operator_raw: str = str(canonical.get("operator") or "")
    area_or_block_raw: str = str(canonical.get("area_or_block") or "")
    supporting_docs_raw: str = str(canonical.get("supporting_document_paths") or "")

    # --- Display text (clean whitespace, preserve casing) ---
    survey_name: str = clean_display_text(survey_name_raw)
    line_name: str = clean_display_text(line_name_raw)
    volume_name: str = clean_display_text(volume_name_raw)
    processing_stage: str = clean_display_text(processing_stage_raw)
    operator: str = clean_display_text(operator_raw)
    area_or_block: str = clean_display_text(area_or_block_raw)

    # --- Key forms ---
    survey_name_key: str = make_key_text(survey_name)
    line_name_key: str = make_key_text(line_name)
    volume_name_key: str = make_key_text(volume_name)
    processing_stage_key: str = make_key_text(processing_stage)
    operator_key: str = make_key_text(operator)
    area_or_block_key: str = make_key_text(area_or_block)

    # --- SEG-Y filename (string parsing only — no file access) ---
    segy_filename: str = ""
    if segy_path_raw:
        # PurePosixPath is a pure string parser; it never touches the filesystem.
        segy_filename = PurePosixPath(segy_path_raw).name
    segy_filename_key: str = make_filename_key(segy_filename)

    # --- Sample interval ---
    sample_interval_ms, si_flag = parse_sample_interval_ms(sample_interval_raw)
    if si_flag is not None:
        new_qaqc_flags.append(si_flag)
        normalization_warnings.append(
            f"UNPARSEABLE_RECOMMENDED_FIELD: sample_interval_ms='{sample_interval_raw}'"
        )

    # --- Supporting document paths ---
    supporting_docs: list[str] = split_supporting_document_paths(supporting_docs_raw)

    # --- Dataset label ---
    dataset_label: str = build_dataset_label(
        record_type=record_type,
        survey_name=survey_name,
        line_name=line_name,
        volume_name=volume_name,
        segy_filename=segy_filename,
    )

    # --- Dataset key ---
    if record_type == "2d_line":
        line_or_volume_key = line_name_key
    elif record_type == "3d_volume":
        line_or_volume_key = volume_name_key
    else:
        line_or_volume_key = ""

    dataset_key: str = build_dataset_key(
        record_type=record_type,
        survey_key=survey_name_key,
        line_or_volume_key=line_or_volume_key,
        segy_filename_key=segy_filename_key,
    )

    # --- Status update: only affects rows that are currently ready ---
    new_status: str = current_status
    if current_status == "ready" and not dataset_key:
        new_status = "review_required"
        new_qaqc_flags.append(_norm_flag(
            severity="warning",
            code="IDENTITY_HINT_INCOMPLETE",
            message=(
                "Cannot build a deterministic dataset_key for this row. "
                "Row moved to review_required."
            ),
            field="dataset_key",
        ))
        normalization_warnings.append("IDENTITY_HINT_INCOMPLETE: dataset_key is empty.")

    # --- NORMALIZATION_COMPLETED flag ---
    new_qaqc_flags.append(_norm_flag(
        severity="info",
        code="NORMALIZATION_COMPLETED",
        message="Row normalization completed.",
        field=None,
    ))

    # --- Build normalized_metadata ---
    normalized_metadata: dict[str, Any] = {
        "schema_version": NORMALIZED_METADATA_VERSION,
        "record_type": record_type,
        "survey_name": survey_name,
        "survey_name_normalized": survey_name_key,
        "line_name": line_name,
        "line_name_normalized": line_name_key,
        "volume_name": volume_name,
        "volume_name_normalized": volume_name_key,
        "dataset_label": dataset_label,
        "dataset_key": dataset_key,
        "segy_path_raw": segy_path_raw,
        "segy_filename": segy_filename,
        "processing_stage": processing_stage,
        "processing_stage_normalized": processing_stage_key,
        "crs_raw": crs_raw,
        "datum_raw": datum_raw,
        "sample_interval_ms": sample_interval_ms,
        "operator": operator,
        "operator_normalized": operator_key,
        "area_or_block": area_or_block,
        "area_or_block_normalized": area_or_block_key,
        "supporting_document_paths_raw": supporting_docs_raw,
        "supporting_document_paths": supporting_docs,
        "normalization": {
            "normalized": True,
            "normalization_version": NORMALIZER_VERSION,
            "warnings": normalization_warnings,
        },
    }

    # --- Build identity_hints ---
    identity_hints: dict[str, Any] = {
        "identity_version": IDENTITY_HINTS_VERSION,
        "record_type": record_type,
        "survey_name_normalized": survey_name_key,
        "line_or_volume_name_normalized": line_or_volume_key,
        "dataset_label": dataset_label,
        "dataset_key": dataset_key,
        # Raw path string only — never a file hash, never opened.
        "source_path_fingerprint_input": segy_path_raw,
        "registration_ready_hint": new_status == "ready",
    }

    return normalized_metadata, identity_hints, new_qaqc_flags, new_status
