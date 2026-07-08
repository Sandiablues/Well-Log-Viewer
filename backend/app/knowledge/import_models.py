"""KR-3 import payload schema models.

Pydantic models defining the structured JSON import contract for the
Knowledge Repository Definition Import and Staging layer.

These models are the external import schema.  They are intentionally
separate from:
  - managed_models.py  (internal domain records)
  - models.py          (KR-1 response models)

Consumers: import_validation_service, import_staging_service,
           api_managed_knowledge (POST /import/preview and /import/stage).

All sections except ``source`` are optional.  Missing sections are treated
as empty lists and do not cause validation errors.  Only the ``source``
block is required for every import payload.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Source / provenance block
# ---------------------------------------------------------------------------


class ImportSource(BaseModel):
    """Provenance / source descriptor for an import payload.

    Required in every import payload.  Becomes a single EvidenceRecord
    that all staged candidate records reference via evidence_refs.
    """

    source_type: str = Field(
        ...,
        description="Type of import source (e.g. 'manual_import', 'vendor_spec', 'observed_las')",
    )
    source_label: str = Field(
        ...,
        description="Human-readable label for this import batch",
    )
    source_reference: Optional[str] = Field(
        None,
        description="Stable reference identifier for the source (e.g. a document key or URL)",
    )
    source_file: Optional[str] = Field(
        None,
        description="Source filename if applicable",
    )
    notes: Optional[str] = Field(
        None,
        description="Optional free-text import notes",
    )


# ---------------------------------------------------------------------------
# Curve definition entry
# ---------------------------------------------------------------------------



class ImportCurveDefinition(BaseModel):
    """Single curve definition entry in an import payload."""

    canonical_curve_id: Optional[str] = Field(
        default=None,
        description="Unique canonical identifier for this curve type.",
    )
    display_name: Optional[str] = Field(
        default=None,
        description="Human-readable display name.",
    )
    family: Optional[str] = Field(
        default=None,
        description="Curve family key.",
    )
    product_group: Optional[str] = Field(
        default=None,
        description="Product group key.",
    )
    product_subgroup: Optional[str] = Field(
        default=None,
        description="Product subgroup key within the product group.",
    )
    default_unit: Optional[str] = Field(
        default=None,
        description="Default measurement unit.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional human-readable description.",
    )
    standard_mnemonics: list[str] = Field(
        default_factory=list,
        description="Accepted exact/source mnemonics that map to this canonical curve.",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Secondary/vendor/legacy mnemonic aliases that map to this canonical curve.",
    )


class ImportDisplayRule(BaseModel):
    """Single display rule entry in an import payload."""

    canonical_curve_id: Optional[str] = Field(
        default=None,
        description="Canonical curve ID this display rule applies to.",
    )
    preferred_track_family: Optional[str] = Field(
        default=None,
        description="Preferred viewer track family for this curve.",
    )
    scale_type: Optional[str] = Field(
        default=None,
        description="Scale type: linear or log.",
    )
    display_min: float = Field(
        0.0,
        description="Minimum display scale value.",
    )
    display_max: float = Field(
        150.0,
        description="Maximum display scale value.",
    )
    default_unit: Optional[str] = Field(
        default=None,
        description="Default unit for display scale.",
    )
    reverse_scale: bool = Field(
        False,
        description="Whether the scale reads right-to-left.",
    )
    overlay_group: Optional[str] = Field(
        default=None,
        description="Overlay group hint for co-rendering.",
    )


class ImportClassificationRule(BaseModel):
    """Single classification rule entry in an import payload."""

    rule_key: Optional[str] = Field(
        default=None,
        description="Unique rule identifier key.",
    )
    match_type: Optional[str] = Field(
        default=None,
        description="Match strategy.",
    )
    match_value: Optional[str] = Field(
        default=None,
        description="Value to match against.",
    )
    product_group: Optional[str] = Field(
        default=None,
        description="Product group to assign when this rule matches.",
    )
    product_subgroup: Optional[str] = Field(
        default=None,
        description="Product subgroup to assign when this rule matches.",
    )
    curve_family: Optional[str] = Field(
        default=None,
        description="Curve family to assign when this rule matches.",
    )
    confidence: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="Rule confidence from 0.0 to 1.0.",
    )
    context_requirements: list[str] = Field(
        default_factory=list,
        description="Context tags required for this rule.",
    )


class ImportTemplateRule(BaseModel):
    """Single template rule entry in an import payload."""

    template_key: Optional[str] = Field(
        default=None,
        description="Unique template key.",
    )
    template_label: Optional[str] = Field(
        default=None,
        description="Human-readable template label.",
    )
    track_order: list[str] = Field(
        default_factory=list,
        description="Ordered list of track family keys.",
    )
    required_curve_families: list[str] = Field(
        default_factory=list,
        description="Required curve families.",
    )
    preferred_curve_families: list[str] = Field(
        default_factory=list,
        description="Preferred curve families.",
    )
    fallback_curve_families: list[str] = Field(
        default_factory=list,
        description="Fallback curve families.",
    )
    overlay_rules: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Track overlay construction rules.",
    )
    missing_curve_behavior: str = Field(
        "skip",
        description="Behavior when a required curve family is absent.",
    )



class ImportPayload(BaseModel):
    """Top-level KR-3 structured import payload.

    The ``source`` block is required.  All other sections are optional;
    missing sections are treated as empty lists and do not trigger errors.

    Example minimal payload::

        {
          "source": {
            "source_type": "manual_import",
            "source_label": "Extension Set 001"
          },
          "curve_definitions": [...]
        }
    """

    source: ImportSource
    curve_definitions: list[ImportCurveDefinition] = Field(
        default_factory=list,
        description="Curve definitions to import as candidate records",
    )
    display_rules: list[ImportDisplayRule] = Field(
        default_factory=list,
        description="Display rules to import as candidate records",
    )
    classification_rules: list[ImportClassificationRule] = Field(
        default_factory=list,
        description="Classification rules to import as candidate records",
    )
    template_rules: list[ImportTemplateRule] = Field(
        default_factory=list,
        description="Template rules to import as candidate records (empty by convention in KR-3)",
    )
