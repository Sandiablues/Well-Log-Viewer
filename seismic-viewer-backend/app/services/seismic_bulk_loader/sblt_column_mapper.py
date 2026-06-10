"""
SBLT-2: Backend-owned column alias mapper for prepared seismic loadsheets.

Ownership: backend SBLT service.

Responsibilities:
- Normalise source column names (case-insensitive, whitespace/underscore/hyphen-
  tolerant) and map them to canonical SBLT field names.
- Normalise raw record_type cell values to canonical type strings.
- Detect duplicate canonical mappings (two source columns that map to the same
  canonical field) and record QAQC evidence rather than silently discarding.
- Preserve original source_values — never mutate them.

SBLT-2 scope:
- Column alias mapping only.
- No file/path existence validation.
- No SEG-Y header inspection.
- No MSI interaction.
- No duplicate seismic record detection.
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Canonical field definitions
# ---------------------------------------------------------------------------

# All canonical fields produced by SBLT-2 column mapping.
ALL_CANONICAL_FIELDS: list[str] = [
    "survey_name",
    "line_name",
    "volume_name",
    "record_type",
    "segy_path",
    "processing_stage",
    "crs",
    "datum",
    "sample_interval_ms",
    "operator",
    "area_or_block",
    "supporting_document_paths",
]

# Fields that must be present for a row to be potentially valid.
REQUIRED_FIELDS: list[str] = [
    "survey_name",
    "record_type",
    "segy_path",
]

# Fields whose absence produces info-level QAQC flags but does not block.
RECOMMENDED_FIELDS: list[str] = [
    "processing_stage",
    "crs",
    "datum",
    "sample_interval_ms",
    "operator",
    "area_or_block",
    "supporting_document_paths",
]

# Conditional: when record_type is the key, the value field is also required.
CONDITIONAL_FIELDS: dict[str, str] = {
    "2d_line": "line_name",
    "3d_volume": "volume_name",
}


# ---------------------------------------------------------------------------
# Alias map (pre-normalised aliases stored as normalised strings)
# ---------------------------------------------------------------------------
#
# Normalisation: lowercase, collapse whitespace/underscore/hyphen to single space,
# strip. Slashes are preserved (so "2d/3d" stays "2d/3d").
#
# Source column names are normalised the same way at match time.

_CANONICAL_ALIASES: dict[str, list[str]] = {
    "survey_name": [
        "survey",
        "survey name",
        "project",
        "project name",
    ],
    "line_name": [
        "line",
        "line name",
        "seismic line",
        "2d line",
    ],
    "volume_name": [
        "volume",
        "volume name",
        "cube",
        "cube name",
        "dataset",
        "dataset name",
    ],
    "record_type": [
        "type",
        "data type",
        "dataset type",
        "seismic type",
        "2d/3d",
        "dimension",
    ],
    "segy_path": [
        # Hyphens normalised to spaces: "seg-y file" → "seg y file"
        "seg y file",
        "segy file",
        "seg y path",
        "segy path",
        "source file",
        "file path",
        "path",
    ],
    "processing_stage": [
        "processing stage",
        "processing",
        "product",
        "process",
        "processing product",
    ],
    "crs": [
        "crs",
        "coordinate reference system",
        "projection",
        "projected crs",
    ],
    "datum": [
        "datum",
        "geodetic datum",
    ],
    "sample_interval_ms": [
        "sample interval",
        "sample interval ms",
        "sample rate",
        "sample rate ms",
        "dt",
        "dt ms",
    ],
    "operator": [
        "operator",
        "client",
        "company",
    ],
    "area_or_block": [
        "area",
        "block",
        "field",
        "concession",
    ],
    "supporting_document_paths": [
        "documents",
        "supporting documents",
        "support documents",
        "document paths",
        "report paths",
    ],
}

# Build reverse map: normalised alias → canonical field name.
_REVERSE_MAP: dict[str, str] = {}
for _canonical, _aliases in _CANONICAL_ALIASES.items():
    for _alias in _aliases:
        _REVERSE_MAP[_alias] = _canonical


# ---------------------------------------------------------------------------
# Record-type value normalization
# ---------------------------------------------------------------------------
#
# Maps normalised raw cell values to canonical record type strings.
# Hyphens in raw values are normalised to spaces before lookup.

_RECORD_TYPE_VALUES: dict[str, str] = {
    "2d": "2d_line",
    "2 d": "2d_line",          # "2-D" after normalisation
    "line": "2d_line",
    "2d line": "2d_line",
    "seismic line": "2d_line",
    "3d": "3d_volume",
    "3 d": "3d_volume",        # "3-D" after normalisation
    "volume": "3d_volume",
    "cube": "3d_volume",
    "3d volume": "3d_volume",
    "seismic volume": "3d_volume",
}


def normalize_record_type(raw_value: str | None) -> str:
    """
    Normalise a raw record_type cell value to a canonical type string.

    Returns one of: "2d_line", "3d_volume", "unknown".
    An empty or None value returns "unknown".
    """
    if not raw_value or not str(raw_value).strip():
        return "unknown"
    normed = _normalize(raw_value)
    return _RECORD_TYPE_VALUES.get(normed, "unknown")


# ---------------------------------------------------------------------------
# Normalisation helper
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    """
    Produce a canonical string for alias matching.

    Rules:
    - Lowercase.
    - Collapse runs of whitespace, underscores, and hyphens to a single space.
    - Strip leading/trailing whitespace.
    - Slashes are preserved (e.g. "2d/3d" stays "2d/3d").
    """
    s = str(name).lower()
    s = re.sub(r"[\s_\-]+", " ", s)
    return s.strip()


# ---------------------------------------------------------------------------
# Mapping result
# ---------------------------------------------------------------------------

class ColumnMappingResult:
    """
    Result of mapping source column names to canonical SBLT fields.

    Attributes:
        canonical_values    — dict of all canonical field names → raw source
                              value (str) or None if no source column mapped to it.
        mapped_columns      — dict of canonical field name → original source
                              column name (the winning column for duplicates).
        unmapped_columns    — list of original source column names that did not
                              match any canonical alias.
        duplicate_mappings  — list of dicts describing columns that both mapped
                              to the same canonical field; first value wins.
    """

    __slots__ = (
        "canonical_values",
        "mapped_columns",
        "unmapped_columns",
        "duplicate_mappings",
    )

    def __init__(
        self,
        canonical_values: dict[str, str | None],
        mapped_columns: dict[str, str],
        unmapped_columns: list[str],
        duplicate_mappings: list[dict[str, Any]],
    ) -> None:
        self.canonical_values = canonical_values
        self.mapped_columns = mapped_columns
        self.unmapped_columns = unmapped_columns
        self.duplicate_mappings = duplicate_mappings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def map_columns(source_values: dict[str, str]) -> ColumnMappingResult:
    """
    Map source loadsheet column names to canonical SBLT field names.

    Matching is case-insensitive and whitespace/underscore/hyphen-tolerant.
    Original source_values are never modified.

    Duplicate handling: if two source columns both normalise to aliases for
    the same canonical field, the first one encountered wins and evidence is
    recorded in duplicate_mappings.

    Returns a ColumnMappingResult.
    """
    # canonical_field → (original_source_col, raw_value) — first match wins
    canonical_map: dict[str, tuple[str, str]] = {}
    duplicate_mappings: list[dict[str, Any]] = []
    unmapped: list[str] = []

    for src_col, src_val in source_values.items():
        normed = _normalize(src_col)
        canonical = _REVERSE_MAP.get(normed)

        if canonical is None:
            unmapped.append(src_col)
            continue

        if canonical in canonical_map:
            existing_col = canonical_map[canonical][0]
            duplicate_mappings.append({
                "canonical_field": canonical,
                "columns": [existing_col, src_col],
            })
        else:
            canonical_map[canonical] = (src_col, str(src_val) if src_val is not None else "")

    # All canonical fields in order; None for fields with no source match.
    canonical_values: dict[str, str | None] = {
        f: (canonical_map[f][1] if f in canonical_map else None)
        for f in ALL_CANONICAL_FIELDS
    }

    # mapped_columns: canonical field → original source column name (first winner).
    mapped_columns: dict[str, str] = {
        canonical: src_col
        for canonical, (src_col, _) in canonical_map.items()
    }

    return ColumnMappingResult(
        canonical_values=canonical_values,
        mapped_columns=mapped_columns,
        unmapped_columns=unmapped,
        duplicate_mappings=duplicate_mappings,
    )
