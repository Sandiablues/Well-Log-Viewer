"""Pydantic contracts for KR-backed WDV layout presets.

The WDV frontend renders these contracts. It must not classify curves, choose
layout curves, infer display scale truth, or mutate WDV session state from this
recommendation endpoint.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

CONTRACT_VERSION = "wdv_layout_presets_v1r"


class WdvLayoutPresetTrackDefinition(BaseModel):
    """One logical track defined from an approved KR template_rule record."""

    track_id: str
    label: str
    purpose: str
    required_families: list[str] = Field(default_factory=list)
    optional_families: list[str] = Field(default_factory=list)
    overlay_rules: list[dict[str, Any]] = Field(default_factory=list)
    max_curves: Optional[int] = None


class WdvLayoutPresetDefinition(BaseModel):
    """Backend-owned preset definition returned by the list endpoint.

    Preset identity comes from the approved KR template_rule.template_key.
    """

    preset_id: str
    name: str
    description: str
    category: str = "kr_template"
    kr_record_id: str
    kr_record_status: str
    production_eligible: bool
    source: str = "managed_kr_template_rule"
    is_placeholder: bool = False
    tracks: list[WdvLayoutPresetTrackDefinition] = Field(default_factory=list)
    required_families: list[str] = Field(default_factory=list)
    optional_families: list[str] = Field(default_factory=list)
    fallback_families: list[str] = Field(default_factory=list)
    missing_curve_behavior: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


class WdvLayoutPresetListResponse(BaseModel):
    """Response for GET /api/wlv/wdv/layout-presets."""

    contract_version: str = CONTRACT_VERSION
    preset_count: int
    presets: list[WdvLayoutPresetDefinition]
    warnings: list[str] = Field(default_factory=list)
    knowledge_policy: dict[str, Any] = Field(default_factory=dict)


class WdvDisplayScaleRecommendation(BaseModel):
    """Display-rule fields resolved by backend KR display recommendation."""

    scale_type: Optional[str] = None
    display_min: Optional[float] = None
    display_max: Optional[float] = None
    default_unit: Optional[str] = None
    reverse_scale: Optional[bool] = None
    overlay_group: Optional[str] = None
    preferred_track_family: Optional[str] = None
    source: str = "unresolved"


class WdvPresetCurveCandidate(BaseModel):
    """One managed inventory curve selected for a KR-backed preset track."""

    product_id: str
    curve_name: str
    mnemonic: str
    display_name: Optional[str] = None
    canonical_curve_id: Optional[str] = None
    curve_family: Optional[str] = None
    product_category: Optional[str] = None
    product_subgroup_key: Optional[str] = None
    product_subgroup_label: Optional[str] = None
    classification_source: Optional[str] = None
    classification_confidence: Optional[str] = None
    unit: Optional[str] = None
    display_scale: WdvDisplayScaleRecommendation = Field(
        default_factory=WdvDisplayScaleRecommendation
    )
    reason: str
    evidence: list[str] = Field(default_factory=list)


class WdvPresetTrackRecommendation(BaseModel):
    """Recommended curve assignment for one logical KR template track."""

    track_id: str
    label: str
    status: str
    required_families: list[str] = Field(default_factory=list)
    optional_families: list[str] = Field(default_factory=list)
    overlay_rules: list[dict[str, Any]] = Field(default_factory=list)
    curves: list[WdvPresetCurveCandidate] = Field(default_factory=list)
    missing_required_families: list[str] = Field(default_factory=list)
    missing_optional_families: list[str] = Field(default_factory=list)
    reason: str


class WdvLayoutPresetRecommendationResponse(BaseModel):
    """Response for GET /api/wlv/wdv/layout-presets/recommend."""

    contract_version: str = CONTRACT_VERSION
    managed_well_id: str
    well_name: Optional[str] = None
    preset_id: str
    preset_name: str
    kr_template_record_id: str
    kr_template_status: str
    recommendation_status: str
    completeness_score: float
    available_curve_count: int
    selected_curve_count: int
    excluded_other_review_count: int
    missing_required_families: list[str] = Field(default_factory=list)
    tracks: list[WdvPresetTrackRecommendation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    knowledge_policy: dict[str, Any] = Field(default_factory=dict)
    apply_ready: bool = False
