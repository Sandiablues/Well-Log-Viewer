"""Managed KR domain record models for KR-2 through KR-DATA-MODEL-1.

These dataclasses are backend-internal domain objects representing governed
records in the Knowledge Repository.  They are separate from the KR-1 Pydantic
response models in models.py, which remain the stable external API contract.

Record type hierarchy
---------------------
CurveDefinitionRecord    ��� canonical curve knowledge
AliasRecord              – mnemonic/alias mapping (context-aware)
DisplayRuleRecord        – curve rendering display rules
ClassificationRuleRecord – deterministic classification hints
TemplateRuleRecord       – future template construction knowledge (empty in KR-2)
AliasEnrichmentRecord    – technical-subtype enrichment for existing alias mappings
                           (KR-DATA-MODEL-1; see alias_enrichment_models.py)
EvidenceRecord           – provenance / source record (no lifecycle status)

All governed records (all types except EvidenceRecord) carry a GovernanceStatus
field.  EvidenceRecord is provenance-only and has no governance lifecycle.

KR-DATA-MODEL-1 note
--------------------
AliasEnrichmentRecord allows curated catalogue entries to attach a specific
technical-subtype identity to an existing broad alias/canonical mapping without
replacing the display canonical curve and without triggering alias conflicts in
the KR-3 import validator.  The record type "alias_enrichment" is registered in
GOVERNED_RECORD_TYPES and ALL_RECORD_TYPES below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .governance import GovernanceStatus

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KR2_VERSION = "kr-2"
KR3_VERSION = "kr-3"
KR4_VERSION = "kr-4"
KR5_VERSION = "kr-5"
KR_DATA_MODEL_1_VERSION = "kr-data-model-1"

GOVERNED_RECORD_TYPES: frozenset[str] = frozenset(
    {
        "curve_definition",
        "alias",
        "display_rule",
        "classification_rule",
        "template_rule",
        "alias_enrichment",  # KR-DATA-MODEL-1: technical-subtype enrichment records
    }
)

ALL_RECORD_TYPES: frozenset[str] = GOVERNED_RECORD_TYPES | frozenset({"evidence"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    """Return current UTC datetime (used as dataclass field default factory)."""
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# A. Curve Definition Record
# ---------------------------------------------------------------------------

@dataclass
class CurveDefinitionRecord:
    """Canonical curve knowledge record.

    Represents one well-log curve type with identity, classification, and
    governance metadata.  Multiple AliasRecords may link to the same
    canonical_curve_id.
    """

    record_id: str
    canonical_curve_id: str
    display_name: str
    family: str
    product_group: str

    record_type: str = "curve_definition"
    product_subgroup: Optional[str] = None
    default_unit: Optional[str] = None
    description: Optional[str] = None

    # Governance
    status: GovernanceStatus = GovernanceStatus.SEED
    version: int = 1
    source_type: str = "seed"
    source_reference: Optional[str] = None
    created_at: Optional[datetime] = field(default_factory=_utcnow)
    updated_at: Optional[datetime] = None
    created_by: str = "system"
    reviewed_by: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    deprecated_at: Optional[datetime] = None
    change_reason: Optional[str] = None
    evidence_refs: list[str] = field(default_factory=list)
    # KR-4: compact governance audit history.  Each entry records:
    # {action, actor, timestamp, previous_status, new_status, reason, notes}
    governance_history: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# B. Alias / Mnemonic Record
# ---------------------------------------------------------------------------

@dataclass
class AliasRecord:
    """Mnemonic alias record linking a mnemonic to a canonical curve.

    Aliases may be context-dependent.  A single mnemonic (e.g. "GR") may
    resolve to different canonical curves depending on borehole context
    (open-hole vs cased-hole).  context_hint captures this.
    """

    record_id: str
    alias: str
    canonical_curve_id: str

    record_type: str = "alias"
    normalized_alias: str = ""
    unit_hint: Optional[str] = None
    description_hint: Optional[str] = None
    vendor_hint: Optional[str] = None
    context_hint: Optional[str] = None
    confidence: float = 1.0

    # Governance
    status: GovernanceStatus = GovernanceStatus.SEED
    evidence_refs: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = field(default_factory=_utcnow)
    updated_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    approved_by: Optional[str] = None
    change_reason: Optional[str] = None
    governance_history: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.normalized_alias:
            self.normalized_alias = self.alias.strip().upper()


# ---------------------------------------------------------------------------
# C. Display Rule Record
# ---------------------------------------------------------------------------

@dataclass
class DisplayRuleRecord:
    """Curve display rendering rule.

    Captures default scale, track placement, and visual hints for a canonical
    curve.  Does not drive rendering directly in KR-2; feeds future template
    and viewer pipeline.
    """

    record_id: str
    canonical_curve_id: str
    preferred_track_family: str

    record_type: str = "display_rule"
    scale_type: str = "linear"
    display_min: float = 0.0
    display_max: float = 150.0
    default_unit: Optional[str] = None
    reverse_scale: bool = False
    overlay_group: Optional[str] = None
    line_style_hint: Optional[str] = None
    color_hint: Optional[str] = None

    # Governance
    status: GovernanceStatus = GovernanceStatus.SEED
    version: int = 1
    evidence_refs: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = field(default_factory=_utcnow)
    updated_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    change_reason: Optional[str] = None
    governance_history: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# D. Classification Rule Record
# ---------------------------------------------------------------------------

@dataclass
class ClassificationRuleRecord:
    """Deterministic classification hint rule.

    Encodes rules that map mnemonic/unit/context patterns to product groups,
    subgroups, and curve families.  The classifier layer will consume approved
    classification rules in a future KR block.
    """

    record_id: str
    rule_key: str
    match_type: str
    match_value: str
    product_group: str

    record_type: str = "classification_rule"
    product_subgroup: Optional[str] = None
    curve_family: Optional[str] = None
    confidence: float = 1.0
    context_requirements: list[str] = field(default_factory=list)

    # Governance
    status: GovernanceStatus = GovernanceStatus.SEED
    version: int = 1
    evidence_refs: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = field(default_factory=_utcnow)
    updated_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    change_reason: Optional[str] = None
    governance_history: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# E. Template Rule Record
# ---------------------------------------------------------------------------

@dataclass
class TemplateRuleRecord:
    """Viewer template construction rule.

    Captures the knowledge needed to build a standard viewer track template
    for a product type.  Template records exist structurally in KR-2 but the
    /api/wlv/knowledge/templates endpoint remains empty; template seeding is
    deferred to a later block.
    """

    record_id: str
    template_key: str
    template_label: str

    record_type: str = "template_rule"
    track_order: list[str] = field(default_factory=list)
    required_curve_families: list[str] = field(default_factory=list)
    preferred_curve_families: list[str] = field(default_factory=list)
    fallback_curve_families: list[str] = field(default_factory=list)
    overlay_rules: list[dict] = field(default_factory=list)  # type: ignore[type-arg]
    missing_curve_behavior: str = "skip"

    # Governance
    status: GovernanceStatus = GovernanceStatus.SEED
    version: int = 1
    evidence_refs: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = field(default_factory=_utcnow)
    updated_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    change_reason: Optional[str] = None
    governance_history: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# F. Evidence / Source Record
# ---------------------------------------------------------------------------

@dataclass
class EvidenceRecord:
    """Provenance / source record for knowledge items.

    Captures where a piece of knowledge came from: a document, publication,
    observed LAS file, or vendor spec.  Evidence records are not governed
    (no lifecycle status); they are immutable provenance anchors.

    Internet access is NOT required — source_url is optional and the system
    works fully standalone.
    """

    evidence_id: str
    source_type: str
    source_label: str

    record_type: str = "evidence"
    source_reference: Optional[str] = None
    source_file: Optional[str] = None
    source_url: Optional[str] = None
    extracted_text: Optional[str] = None
    observed_mnemonic: Optional[str] = None
    observed_unit: Optional[str] = None
    observed_description: Optional[str] = None
    confidence: float = 1.0
    created_at: Optional[datetime] = field(default_factory=_utcnow)
    notes: Optional[str] = None
