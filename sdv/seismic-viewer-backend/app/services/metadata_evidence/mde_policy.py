"""
MDE-1: Field policy definitions for the Metadata / Evidence contract.

Each field entry specifies:
  field_required_for_loading:   bool  — row cannot load without this field approved
  field_required_for_registration: bool — row cannot register without this field
  auto_accept_sources:          list  — evidence source types that may auto-accept when
                                        submitted value is absent
  candidate_sources_allowed:    list  — evidence source types considered valid candidates
  conflict_requires_review:     bool  — a match conflict requires user review
  missing_classification:       str   — "missing_required" or "missing_recommended"
  bulk_action_eligible:         bool  — field may be resolved via bulk action

Design rules:
  - Safe technical fields (sample_interval_ms, samples_per_trace, format codes) may be
    auto-accepted when the candidate comes from a high-authority source (segy_binary_header).
  - Identity/business fields (survey_name, line_name, volume_name, record_type,
    processing_stage, operator, area_or_block) are never auto-accepted.
  - CRS/datum: missing creates a review exception; not auto-accepted from weak evidence.

No SBLT imports. No SSI imports. No MSI imports. No file I/O.
"""

from __future__ import annotations

from .mde_models import (
    EVIDENCE_SOURCE_AI_SUGGESTION,
    EVIDENCE_SOURCE_FILENAME,
    EVIDENCE_SOURCE_FOLDER_PATH,
    EVIDENCE_SOURCE_LOADSHEET,
    EVIDENCE_SOURCE_MANUAL,
    EVIDENCE_SOURCE_SEGY_BINARY_HEADER,
    EVIDENCE_SOURCE_SEGY_TEXTUAL_HEADER,
    EVIDENCE_SOURCE_SOURCE_INTAKE,
    EVIDENCE_SOURCE_SUPPORTING_DOCUMENT,
    REVIEW_MISSING_RECOMMENDED,
    REVIEW_MISSING_REQUIRED,
)

# ---------------------------------------------------------------------------
# Source sets
# ---------------------------------------------------------------------------

_ALL_CANDIDATE_SOURCES: list[str] = [
    EVIDENCE_SOURCE_SEGY_BINARY_HEADER,
    EVIDENCE_SOURCE_SEGY_TEXTUAL_HEADER,
    EVIDENCE_SOURCE_FILENAME,
    EVIDENCE_SOURCE_FOLDER_PATH,
    EVIDENCE_SOURCE_LOADSHEET,
    EVIDENCE_SOURCE_MANUAL,
    EVIDENCE_SOURCE_AI_SUGGESTION,
    EVIDENCE_SOURCE_SUPPORTING_DOCUMENT,
    EVIDENCE_SOURCE_SOURCE_INTAKE,
]

# Safe technical auto-accept: SEG-Y binary header is the primary high-authority source
_TECHNICAL_AUTO_ACCEPT_SOURCES: list[str] = [EVIDENCE_SOURCE_SEGY_BINARY_HEADER]

# Identity/business fields: no auto-accept from any source
_NO_AUTO_ACCEPT: list[str] = []

# ---------------------------------------------------------------------------
# Field policy registry
# ---------------------------------------------------------------------------

FIELD_POLICIES: dict[str, dict] = {

    # ------------------------------------------------------------------
    # Identity / business fields — no auto-accept
    # ------------------------------------------------------------------

    "survey_name": {
        "field_required_for_loading": True,
        "field_required_for_registration": True,
        "auto_accept_sources": _NO_AUTO_ACCEPT,
        "candidate_sources_allowed": _ALL_CANDIDATE_SOURCES,
        "conflict_requires_review": True,
        "missing_classification": REVIEW_MISSING_REQUIRED,
        "bulk_action_eligible": False,
    },
    "line_name": {
        # Required for 2D datasets; recommended otherwise (record_type determines need)
        "field_required_for_loading": True,
        "field_required_for_registration": True,
        "auto_accept_sources": _NO_AUTO_ACCEPT,
        "candidate_sources_allowed": _ALL_CANDIDATE_SOURCES,
        "conflict_requires_review": True,
        "missing_classification": REVIEW_MISSING_RECOMMENDED,
        "bulk_action_eligible": False,
    },
    "volume_name": {
        # Required for 3D datasets; recommended otherwise
        "field_required_for_loading": True,
        "field_required_for_registration": True,
        "auto_accept_sources": _NO_AUTO_ACCEPT,
        "candidate_sources_allowed": _ALL_CANDIDATE_SOURCES,
        "conflict_requires_review": True,
        "missing_classification": REVIEW_MISSING_RECOMMENDED,
        "bulk_action_eligible": False,
    },
    "record_type": {
        "field_required_for_loading": True,
        "field_required_for_registration": True,
        "auto_accept_sources": _NO_AUTO_ACCEPT,
        "candidate_sources_allowed": _ALL_CANDIDATE_SOURCES,
        "conflict_requires_review": True,
        "missing_classification": REVIEW_MISSING_REQUIRED,
        "bulk_action_eligible": False,
    },
    "processing_stage": {
        "field_required_for_loading": False,
        "field_required_for_registration": False,
        "auto_accept_sources": _NO_AUTO_ACCEPT,
        "candidate_sources_allowed": _ALL_CANDIDATE_SOURCES,
        "conflict_requires_review": True,
        "missing_classification": REVIEW_MISSING_RECOMMENDED,
        "bulk_action_eligible": False,
    },
    "operator": {
        "field_required_for_loading": False,
        "field_required_for_registration": False,
        "auto_accept_sources": _NO_AUTO_ACCEPT,
        "candidate_sources_allowed": _ALL_CANDIDATE_SOURCES,
        "conflict_requires_review": False,
        "missing_classification": REVIEW_MISSING_RECOMMENDED,
        "bulk_action_eligible": False,
    },
    "area_or_block": {
        "field_required_for_loading": False,
        "field_required_for_registration": False,
        "auto_accept_sources": _NO_AUTO_ACCEPT,
        "candidate_sources_allowed": _ALL_CANDIDATE_SOURCES,
        "conflict_requires_review": False,
        "missing_classification": REVIEW_MISSING_RECOMMENDED,
        "bulk_action_eligible": False,
    },

    # ------------------------------------------------------------------
    # Safe technical fields — auto-accept from SEG-Y binary header
    # ------------------------------------------------------------------

    "sample_interval_ms": {
        "field_required_for_loading": False,
        "field_required_for_registration": True,
        "auto_accept_sources": _TECHNICAL_AUTO_ACCEPT_SOURCES,
        "candidate_sources_allowed": _ALL_CANDIDATE_SOURCES,
        "conflict_requires_review": True,
        "missing_classification": REVIEW_MISSING_RECOMMENDED,
        "bulk_action_eligible": True,
    },
    "samples_per_trace": {
        "field_required_for_loading": False,
        "field_required_for_registration": True,
        "auto_accept_sources": _TECHNICAL_AUTO_ACCEPT_SOURCES,
        "candidate_sources_allowed": _ALL_CANDIDATE_SOURCES,
        "conflict_requires_review": True,
        "missing_classification": REVIEW_MISSING_RECOMMENDED,
        "bulk_action_eligible": True,
    },
    "data_sample_format_code": {
        "field_required_for_loading": False,
        "field_required_for_registration": True,
        "auto_accept_sources": _TECHNICAL_AUTO_ACCEPT_SOURCES,
        "candidate_sources_allowed": _ALL_CANDIDATE_SOURCES,
        "conflict_requires_review": True,
        "missing_classification": REVIEW_MISSING_RECOMMENDED,
        "bulk_action_eligible": True,
    },
    "data_sample_format_name": {
        "field_required_for_loading": False,
        "field_required_for_registration": False,
        "auto_accept_sources": _TECHNICAL_AUTO_ACCEPT_SOURCES,
        "candidate_sources_allowed": _ALL_CANDIDATE_SOURCES,
        "conflict_requires_review": False,
        "missing_classification": REVIEW_MISSING_RECOMMENDED,
        "bulk_action_eligible": True,
    },

    # ------------------------------------------------------------------
    # CRS / datum — missing creates review exception; no weak-evidence auto-accept
    # ------------------------------------------------------------------

    "crs": {
        "field_required_for_loading": False,
        "field_required_for_registration": True,
        "auto_accept_sources": _NO_AUTO_ACCEPT,
        "candidate_sources_allowed": _ALL_CANDIDATE_SOURCES,
        "conflict_requires_review": True,
        "missing_classification": REVIEW_MISSING_REQUIRED,
        "bulk_action_eligible": False,
    },
    "datum": {
        "field_required_for_loading": False,
        "field_required_for_registration": False,
        "auto_accept_sources": _NO_AUTO_ACCEPT,
        "candidate_sources_allowed": _ALL_CANDIDATE_SOURCES,
        "conflict_requires_review": True,
        "missing_classification": REVIEW_MISSING_RECOMMENDED,
        "bulk_action_eligible": False,
    },
}

# ---------------------------------------------------------------------------
# Conservative default for unknown / unregistered fields
# ---------------------------------------------------------------------------

_DEFAULT_POLICY: dict = {
    "field_required_for_loading": False,
    "field_required_for_registration": False,
    "auto_accept_sources": _NO_AUTO_ACCEPT,
    "candidate_sources_allowed": _ALL_CANDIDATE_SOURCES,
    "conflict_requires_review": True,
    "missing_classification": REVIEW_MISSING_RECOMMENDED,
    "bulk_action_eligible": False,
}


def get_field_policy(field: str) -> dict:
    """
    Return policy for a known field, or a conservative default for unknown fields.

    Never raises — always returns a dict with all required policy keys.
    """
    return FIELD_POLICIES.get(field, _DEFAULT_POLICY)


def is_field_known(field: str) -> bool:
    """Return True if the field has an explicit policy entry."""
    return field in FIELD_POLICIES
