"""KR-DATA-MODEL-1 — AliasEnrichmentRecord.

Backend-owned governed record type that attaches technical-subtype metadata
to an existing alias/canonical mapping without replacing the display canonical
curve.

Design principle
----------------
One alias may map to:
  - a display_canonical_curve_id  (broad display identity, unchanged by KR-6/7/8)
  - a technical_curve_id          (precise technical subtype, enrichment metadata only)

The enrichment does NOT replace the existing alias record and does NOT change
how KR-6 resolves the alias for display.  It adds a parallel technical identity
queryable as metadata after approval.

Example::

    AliasEnrichmentRecord(
        record_id="enrich_ILD_deep_induction_resistivity",
        alias="ILD",
        normalized_alias="ILD",
        display_canonical_curve_id="deep_resistivity",
        technical_curve_id="deep_induction_resistivity",
        technical_display_name="Deep Induction Resistivity",
        parent_canonical_curve_id="deep_resistivity",
        measurement_family="induction",
        measurement_depth="deep",
        tool_family="induction_resistivity",
    )

Governance
----------
AliasEnrichmentRecord is a governed record (status ∈ GovernanceStatus).
It participates in the standard candidate → approved / rejected lifecycle.

Candidate enrichments are NOT production-eligible and do NOT affect KR-6/7/8.
Approved enrichments are production-eligible as metadata only; they still do
NOT remap the display canonical curve.

Storage
-------
Serialized/deserialized through managed_storage.py alongside other governed
records.  record_type = "alias_enrichment" is the dispatch key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .governance import GovernanceStatus

KR_DATA_MODEL_1_VERSION = "kr-data-model-1"


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class AliasEnrichmentRecord:
    """Governed record attaching a technical subtype identity to an alias.

    Required fields
    ---------------
    record_id               : unique record identifier
    alias                   : original mnemonic string
    normalized_alias        : upper-case normalised mnemonic
    display_canonical_curve_id : broad display canonical (e.g. 'deep_resistivity')
    technical_curve_id      : precise technical subtype (e.g. 'deep_induction_resistivity')
    technical_display_name  : human-readable name for technical subtype
    parent_canonical_curve_id : broad parent canonical (same as display_canonical_curve_id
                                in most cases; explicit field for clarity)

    Optional enrichment metadata
    ----------------------------
    technical_family        : curve family for the technical subtype
    measurement_family      : measurement physics (e.g. 'induction', 'laterolog')
    measurement_depth       : investigation depth label ('deep', 'medium', 'shallow')
    tool_family             : tool type (e.g. 'induction_resistivity', 'laterolog_resistivity')
    vendor_context          : optional vendor / tool-brand context
    selection_priority      : integer priority hint for subtype selection (lower = higher priority)

    Provenance
    ----------
    source_label            : human-readable import source label
    source_reference        : stable source reference (document key, etc.)
    evidence_refs           : list of evidence_id strings
    confidence              : float 0.0–1.0
    review_notes            : free-text notes from curator / reviewer

    Governance
    ----------
    status, created_at, updated_at, approved_by, approved_at,
    change_reason, governance_history — standard governed-record fields.
    """

    # --- Core identity (required) ---
    record_id: str
    alias: str
    normalized_alias: str
    display_canonical_curve_id: str
    technical_curve_id: str
    technical_display_name: str
    parent_canonical_curve_id: str

    # --- Record type (fixed) ---
    record_type: str = "alias_enrichment"

    # --- Governance ---
    status: GovernanceStatus = GovernanceStatus.CANDIDATE

    # --- Optional enrichment metadata ---
    technical_family: Optional[str] = None
    measurement_family: Optional[str] = None
    measurement_depth: Optional[str] = None
    tool_family: Optional[str] = None
    vendor_context: Optional[str] = None
    selection_priority: Optional[int] = None

    # --- Provenance ---
    source_label: Optional[str] = None
    source_reference: Optional[str] = None
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float = 1.0
    review_notes: Optional[str] = None

    # --- Standard governance fields ---
    created_at: Optional[datetime] = field(default_factory=_utcnow)
    updated_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    change_reason: Optional[str] = None
    governance_history: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.normalized_alias:
            self.normalized_alias = self.alias.strip().upper()
