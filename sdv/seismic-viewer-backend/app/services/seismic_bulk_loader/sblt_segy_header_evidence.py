"""
SBLT-5: SEG-Y header evidence → MDE candidate observation builder.

Translates the output of sblt_segy_header_reader.read_segy_fixed_headers()
into a list of candidate observation dicts suitable for
build_metadata_evidence_bundle() from the shared MDE package.

Rules:
  - Binary header fields → high-confidence technical candidates.
  - Textual header: if submitted field value is present, search for it → MATCH
    evidence observation; if absent, pattern-search → candidate observation.
  - No file I/O.
  - No direct MDE builder imports — uses MDE constants only.

No SBLT session imports.  No MSI imports.  No frontend.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.metadata_evidence.mde_models import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    EVIDENCE_SOURCE_SEGY_BINARY_HEADER,
    EVIDENCE_SOURCE_SEGY_TEXTUAL_HEADER,
)

# ---------------------------------------------------------------------------
# Data sample format and measurement system maps
# ---------------------------------------------------------------------------

_DATA_SAMPLE_FORMAT_MAP: dict[int, str] = {
    1: "IBM float",
    2: "32-bit integer",
    3: "16-bit integer",
    5: "IEEE float",
    8: "8-bit integer",
}

_MEASUREMENT_SYSTEM_MAP: dict[int, str] = {
    1: "meters",
    2: "feet",
}

# ---------------------------------------------------------------------------
# Textual header search patterns
#
# Each entry: (field_name, [regex_pattern, ...])
# Patterns are applied to individual lines (case-insensitive).
# Group 1, if present, is used as the candidate value; otherwise match[0].
# ---------------------------------------------------------------------------

_TEXTUAL_SEARCH_PATTERNS: list[tuple[str, list[str]]] = [
    # survey_name — handles: SURVEY:  SURVEY NAME:  SURVEY_NAME:  PROJECT:  etc.
    # [\s_]* between word parts so both "SURVEY NAME:" and "SURVEY_NAME:" match.
    # Longer alternatives (SURVEY[\s_]*NAME) are tried before the bare SURVEY
    # fallback so the richer match wins.
    ("survey_name", [
        r"(?:SURVEY[\s_]*NAME|PROJECT[\s_]*NAME|SURVEY|PROJECT)\s*[:\-=]\s*([A-Za-z0-9_\-\./ ]{2,40})",
    ]),
    # line_name — handles: LINE:  LINE NAME:  LINE_NAME:  LINENAME:  LINE NO.:
    ("line_name", [
        r"(?:LINE[\s_]*NAME|LINENAME|LINE[\s_]*NO\.?|LINE)\s*[:\-=]\s*([A-Za-z0-9_\-\./ ]{1,40})",
        r"\bLINE\s+([A-Za-z0-9_\-\.]{1,30})\b",
    ]),
    # volume_name — handles: VOLUME:  VOLUME NAME:  VOLUME_NAME:  CUBE:  DATASET:
    ("volume_name", [
        r"(?:VOLUME[\s_]*NAME|CUBE|DATASET|VOLUME)\s*[:\-=]\s*([A-Za-z0-9_\-\./ ]{2,40})",
    ]),
    # processing_stage — handles: PROCESSING STAGE:  PROCESSING_STAGE:  PROC STAGE:  DATA TYPE:
    # Also recognises common bare keywords (STACK, PSTM, …) without a colon.
    ("processing_stage", [
        r"(?:PROCESSING[\s_]*STAGE|PROC[\s_]*STAGE|DATA[\s_]*TYPE)\s*[:\-=]\s*([A-Za-z0-9_\-\. ]{2,30})",
        (
            r"\b(PRE\s*STACK|POSTSTACK|POST\s*STACK|PRESTACK|MIGRATION|STACK|"
            r"RAW\s+GATHERS|PSTM|PSDM|KIRCHHOFF|COMMON\s+OFFSET|"
            r"NEAR\s+OFFSET|FAR\s+OFFSET)\b"
        ),
    ]),
]

# Module-level compiled pattern cache
_COMPILED_PATTERNS: dict[str, list[re.Pattern]] = {}


def _get_compiled(field: str, raw_patterns: list[str]) -> list[re.Pattern]:
    if field not in _COMPILED_PATTERNS:
        _COMPILED_PATTERNS[field] = [
            re.compile(p, re.IGNORECASE) for p in raw_patterns
        ]
    return _COMPILED_PATTERNS[field]


# ---------------------------------------------------------------------------
# Textual header helpers
# ---------------------------------------------------------------------------

def _search_textual_candidate(
    lines: list[str],
    field: str,
    patterns: list[str],
) -> tuple[str | None, int | None, str | None]:
    """
    Pattern-search textual lines for a candidate value for field.

    Returns (candidate_value, 1-indexed line_number, matched_line) or (None, None, None).
    """
    compiled = _get_compiled(field, patterns)
    for pattern in compiled:
        for i, line in enumerate(lines, start=1):
            m = pattern.search(line)
            if m:
                val = (m.group(1).strip() if m.lastindex else m.group(0).strip())
                if val:
                    return val, i, line[:80]
    return None, None, None


def _search_textual_value(
    lines: list[str],
    value: str,
) -> tuple[bool, int | None, str | None]:
    """
    Search for a specific (submitted) value in the textual header.

    Returns (found, 1-indexed line_number, matched_line).
    """
    if not value or not lines:
        return False, None, None
    norm = value.strip().upper()
    for i, line in enumerate(lines, start=1):
        if norm in line.upper():
            return True, i, line[:80]
    return False, None, None


# ---------------------------------------------------------------------------
# Binary header → candidate observations
# ---------------------------------------------------------------------------

def _binary_observations(binary_fields: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert parsed binary header fields into MDE candidate observations."""
    obs: list[dict[str, Any]] = []

    # sample_interval_ms  (from sample_interval_us / 1000.0)
    si_us = binary_fields.get("sample_interval_us")
    if si_us is not None and isinstance(si_us, int) and si_us > 0:
        si_ms = round(si_us / 1000.0, 6)
        obs.append({
            "field": "sample_interval_ms",
            "observed_value": si_ms,
            "source_type": EVIDENCE_SOURCE_SEGY_BINARY_HEADER,
            "source_label": "SEG-Y binary header: sample_interval_us",
            "confidence": CONFIDENCE_HIGH,
            "evidence_detail": {
                "header_field": "sample_interval_us",
                "byte_range": "3217-3218",
                "raw_text": str(si_us),
                "line_number": None,
                "document_id": None,
            },
        })

    # samples_per_trace
    spt = binary_fields.get("samples_per_trace")
    if spt is not None and isinstance(spt, int) and spt > 0:
        obs.append({
            "field": "samples_per_trace",
            "observed_value": spt,
            "source_type": EVIDENCE_SOURCE_SEGY_BINARY_HEADER,
            "source_label": "SEG-Y binary header: samples_per_trace",
            "confidence": CONFIDENCE_HIGH,
            "evidence_detail": {
                "header_field": "samples_per_trace",
                "byte_range": "3221-3222",
                "raw_text": str(spt),
                "line_number": None,
                "document_id": None,
            },
        })

    # data_sample_format_code
    dsfc = binary_fields.get("data_sample_format_code")
    if dsfc is not None and isinstance(dsfc, int) and dsfc > 0:
        obs.append({
            "field": "data_sample_format_code",
            "observed_value": dsfc,
            "source_type": EVIDENCE_SOURCE_SEGY_BINARY_HEADER,
            "source_label": "SEG-Y binary header: data_sample_format_code",
            "confidence": CONFIDENCE_HIGH,
            "evidence_detail": {
                "header_field": "data_sample_format_code",
                "byte_range": "3225-3226",
                "raw_text": str(dsfc),
                "line_number": None,
                "document_id": None,
            },
        })

        # data_sample_format_name — derived from code
        fmt_name = _DATA_SAMPLE_FORMAT_MAP.get(dsfc)
        if fmt_name:
            obs.append({
                "field": "data_sample_format_name",
                "observed_value": fmt_name,
                "source_type": EVIDENCE_SOURCE_SEGY_BINARY_HEADER,
                "source_label": "SEG-Y binary header: data_sample_format_code (mapped)",
                "confidence": CONFIDENCE_HIGH,
                "evidence_detail": {
                    "header_field": "data_sample_format_code",
                    "byte_range": "3225-3226",
                    "raw_text": str(dsfc),
                    "line_number": None,
                    "document_id": None,
                },
            })

    # measurement_system
    ms = binary_fields.get("measurement_system")
    if ms is not None and ms in _MEASUREMENT_SYSTEM_MAP:
        obs.append({
            "field": "measurement_system",
            "observed_value": _MEASUREMENT_SYSTEM_MAP[ms],
            "source_type": EVIDENCE_SOURCE_SEGY_BINARY_HEADER,
            "source_label": "SEG-Y binary header: measurement_system",
            "confidence": CONFIDENCE_HIGH,
            "evidence_detail": {
                "header_field": "measurement_system",
                "byte_range": "3255-3256",
                "raw_text": str(ms),
                "line_number": None,
                "document_id": None,
            },
        })

    return obs


# ---------------------------------------------------------------------------
# Textual header → candidate / evidence observations
# ---------------------------------------------------------------------------

def _textual_observations(
    textual_lines: list[str],
    normalized_metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Produce textual-header observations for identity / business fields.

    For each tracked field:
      • If the submitted value is present in normalized_metadata: search the
        textual header for it.  If found, create a MATCH evidence observation.
        If not found, skip (no blocker).
      • If the submitted value is absent: pattern-search for a candidate.
        If found, create a candidate observation (confidence: medium).
        Identity fields will be classified as suggested_review by MDE policy.
    """
    obs: list[dict[str, Any]] = []

    if not textual_lines:
        return obs

    for field, patterns in _TEXTUAL_SEARCH_PATTERNS:
        # Submitted value is the display-cleaned string from normalized_metadata.
        # normalized_metadata keys use plain field names (survey_name, etc.).
        submitted_raw = normalized_metadata.get(field)
        submitted_val = str(submitted_raw).strip() if submitted_raw is not None else ""
        has_submitted = bool(submitted_val)

        if has_submitted:
            found, line_no, matched_line = _search_textual_value(
                textual_lines, submitted_val
            )
            if found:
                obs.append({
                    "field": field,
                    "observed_value": submitted_val,
                    "source_type": EVIDENCE_SOURCE_SEGY_TEXTUAL_HEADER,
                    "source_label": f"SEG-Y textual header: submitted {field!r} found",
                    "confidence": CONFIDENCE_HIGH,
                    "evidence_detail": {
                        "header_field": field,
                        "byte_range": None,
                        "raw_text": matched_line,
                        "line_number": line_no,
                        "document_id": None,
                    },
                })
            # Not found → no observation, no blocker
        else:
            candidate_val, line_no, matched_line = _search_textual_candidate(
                textual_lines, field, patterns
            )
            if candidate_val:
                obs.append({
                    "field": field,
                    "observed_value": candidate_val,
                    "source_type": EVIDENCE_SOURCE_SEGY_TEXTUAL_HEADER,
                    "source_label": f"SEG-Y textual header: candidate {field!r}",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_detail": {
                        "header_field": field,
                        "byte_range": None,
                        "raw_text": matched_line,
                        "line_number": line_no,
                        "document_id": None,
                    },
                })

    return obs


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_segy_candidate_observations(
    header_result: dict[str, Any],
    normalized_metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Convert a SEG-Y header read result into MDE candidate observations.

    Args:
        header_result:      Output of sblt_segy_header_reader.read_segy_fixed_headers().
        normalized_metadata: The row's normalized_metadata dict from SBLT-3.

    Returns:
        List of observation dicts for build_metadata_evidence_bundle(
            candidate_observations=...).
    """
    observations: list[dict[str, Any]] = []

    binary_fields = header_result.get("binary_fields")
    if binary_fields:
        observations.extend(_binary_observations(binary_fields))

    textual_lines: list[str] = header_result.get("textual_lines") or []
    observations.extend(_textual_observations(textual_lines, normalized_metadata or {}))

    return observations
