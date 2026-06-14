"""Response models for backend-owned WDV template contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


CONTRACT_VERSION = "wdv_backend_template_service_v1"


class WdvKnowledgePolicy(BaseModel):
    approved_only: bool = True
    candidate_records_used: bool = False
    deprecated_records_used: bool = False
    frontend_inference_allowed: bool = False
    runtime_record_types: list[str] = Field(default_factory=list)


class WdvTrackObjectTypeResponse(BaseModel):
    object_type: str
    default_renderer: str | None = None
    compatible_data_types: list[str] = Field(default_factory=list)
    preview_supported: bool = False
    auto_build_supported: bool = False
    requires_capability: str | None = None
    fallback_behavior: str | None = None
    review_required: bool = False
    notes: str | None = None


class WdvScaleDefaultResponse(BaseModel):
    curve_family: str
    unit_family: str | None = None
    scale_type: str | None = None
    scale_min: float | int | None = None
    scale_max: float | int | None = None
    display_direction: str | None = None
    override_allowed: bool = True
    scale_confidence: str | None = None
    review_required: bool = False
    notes: str | None = None


class WdvCurveFamilyRequirementResponse(BaseModel):
    curve_family: str
    curve_role: str | None = None
    requirement_level: str
    preferred_mnemonics: list[str] = Field(default_factory=list)
    max_auto_plotted_count: int | None = None
    selection_priority: int | None = None
    selection_policy: str | None = None
    requires_unit_family: str | None = None
    requires_depth_role: str | None = None


class WdvPreviewTemplateTrackResponse(BaseModel):
    track_id: str
    track_key: str
    track_number: int
    track_name: str
    track_role: str | None = None
    renderer_type: str
    scale_behavior: str | None = None
    display_notes: str | None = None
    required_renderer_capability: str | None = None
    supports_overlay: bool = False
    is_optional_track: bool = False
    curve_families: list[str] = Field(default_factory=list)
    requirements: list[WdvCurveFamilyRequirementResponse] = Field(default_factory=list)


class WdvTemplateSelectionRuleResponse(BaseModel):
    rule_id: str
    workflow_context: str | None = None
    required_families: list[str] = Field(default_factory=list)
    preferred_families: list[str] = Field(default_factory=list)
    optional_families: list[str] = Field(default_factory=list)
    renderer_requirements: list[str] = Field(default_factory=list)
    ranking_weight: float | int | None = None
    minimum_coverage_threshold: float | int | None = None
    degraded_mode_allowed: bool = False
    missing_required_behavior: str | None = None
    selection_notes: str | None = None


class WdvPreviewTemplateSummaryResponse(BaseModel):
    template_key: str
    template_label: str
    workflow_context: str | None = None
    primary_usage: str | None = None
    core_display_content: str | None = None
    required_curve_families: list[str] = Field(default_factory=list)
    preferred_curve_families: list[str] = Field(default_factory=list)
    optional_curve_families: list[str] = Field(default_factory=list)
    requires_renderer_capabilities: list[str] = Field(default_factory=list)
    track_count: int = 0
    preview_eligible: bool = False
    auto_build_eligible: bool = False
    production_eligible: bool = False
    runtime_eligible: bool = False
    status: str
    rule_status: str | None = None
    source_pages: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class WdvPreviewTemplateDetailResponse(WdvPreviewTemplateSummaryResponse):
    tracks: list[WdvPreviewTemplateTrackResponse] = Field(default_factory=list)
    selection_rule: WdvTemplateSelectionRuleResponse | None = None
    scale_defaults: list[WdvScaleDefaultResponse] = Field(default_factory=list)
    track_object_types: list[WdvTrackObjectTypeResponse] = Field(default_factory=list)


class WdvTemplateListResponse(BaseModel):
    service: str = "wdv_backend_template_service"
    contract_version: str = CONTRACT_VERSION
    template_count: int
    templates: list[WdvPreviewTemplateSummaryResponse]
    knowledge_policy: WdvKnowledgePolicy


class WdvTemplateDetailEnvelope(BaseModel):
    service: str = "wdv_backend_template_service"
    contract_version: str = CONTRACT_VERSION
    template: WdvPreviewTemplateDetailResponse
    knowledge_policy: WdvKnowledgePolicy


class WdvTemplateReferenceSummaryResponse(BaseModel):
    service: str = "wdv_backend_template_service"
    contract_version: str = CONTRACT_VERSION
    record_type_counts: dict[str, int]
    reference_sources: list[dict[str, Any]]
    knowledge_policy: WdvKnowledgePolicy


class WdvLoadedCurveRecommendationInput(BaseModel):
    product_id: str | None = None
    curve_id: str | None = None
    display_curve_id: str | None = None
    canonical_curve_id: str | None = None
    original_mnemonic: str | None = None
    mnemonic: str | None = None
    normalized_name: str | None = None
    display_name: str | None = None
    curve_family: str | None = None
    track_family: str | None = None
    unit: str | None = None
    is_renderable: bool | None = True
    support_status: str | None = None
    source_id: str | None = None


class WdvTemplateRecommendationRequest(BaseModel):
    loaded_curve_items: list[WdvLoadedCurveRecommendationInput] = Field(default_factory=list)
    workflow_context: str | None = None
    selected_product_ids: list[str] = Field(default_factory=list)
    include_ineligible: bool = True


class WdvRecommendedCurveResponse(BaseModel):
    product_id: str
    curve_id: str
    mnemonic: str
    display_name: str
    unit: str | None = None
    curve_family: str | None = None
    raw_curve_family: str | None = None
    canonical_curve_id: str | None = None
    depth_role: str | None = None
    selection_reason: str


class WdvTemplateRequirementCoverageResponse(BaseModel):
    available_families: list[str] = Field(default_factory=list)
    missing_families: list[str] = Field(default_factory=list)
    coverage_ratio: float = 0.0


class WdvTemplateRecommendationTrackResponse(BaseModel):
    track_id: str
    track_key: str
    track_number: int
    track_name: str
    track_role: str | None = None
    renderer_type: str
    required_renderer_capability: str | None = None
    selected_curves: list[WdvRecommendedCurveResponse] = Field(default_factory=list)
    alternate_curves: list[WdvRecommendedCurveResponse] = Field(default_factory=list)
    missing_curve_families: list[str] = Field(default_factory=list)
    scale_defaults: list[dict[str, Any]] = Field(default_factory=list)


class WdvTemplateRecommendationItemResponse(BaseModel):
    template_key: str
    template_label: str
    workflow_context: str | None = None
    template_priority: int | None = None
    is_eligible: bool
    rank: int
    score: float
    required_coverage: WdvTemplateRequirementCoverageResponse
    preferred_coverage: WdvTemplateRequirementCoverageResponse
    optional_coverage: WdvTemplateRequirementCoverageResponse
    missing_required_families: list[str] = Field(default_factory=list)
    missing_preferred_families: list[str] = Field(default_factory=list)
    selected_curve_count: int = 0
    alternate_curve_count: int = 0
    excluded_curve_count: int = 0
    selected_curves: list[WdvRecommendedCurveResponse] = Field(default_factory=list)
    alternate_curves: list[WdvRecommendedCurveResponse] = Field(default_factory=list)
    excluded_curves: list[WdvRecommendedCurveResponse] = Field(default_factory=list)
    tracks: list[WdvTemplateRecommendationTrackResponse] = Field(default_factory=list)
    renderer_requirements: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


class WdvTemplateRecommendationEnvelope(BaseModel):
    service: str = "wdv_template_recommendation_service"
    contract_version: str
    source: str
    available_curve_count: int
    classified_curve_count: int
    unresolved_curve_count: int
    unresolved_curves: list[WdvRecommendedCurveResponse] = Field(default_factory=list)
    recommendation_count: int
    recommendations: list[WdvTemplateRecommendationItemResponse] = Field(default_factory=list)
    knowledge_policy: dict[str, Any]


class WdvTemplateApplicationPlanRequest(BaseModel):
    """Request a backend-owned, non-mutating template application plan."""

    template_key: str
    loaded_curve_items: list[WdvLoadedCurveRecommendationInput] = Field(default_factory=list)
    workflow_context: str | None = None
    selected_product_ids: list[str] = Field(default_factory=list)
    include_ineligible_recommendations: bool = True


class WdvTemplateApplicationTrackPlanResponse(BaseModel):
    track_id: str
    track_key: str
    track_number: int
    track_name: str
    track_role: str | None = None
    renderer_type: str
    required_renderer_capability: str | None = None
    selected_curves: list[WdvRecommendedCurveResponse] = Field(default_factory=list)
    alternate_curves: list[WdvRecommendedCurveResponse] = Field(default_factory=list)
    missing_curve_families: list[str] = Field(default_factory=list)
    scale_defaults: list[dict[str, Any]] = Field(default_factory=list)
    planned_action: str = "stage_track_for_user_review"


class WdvTemplateApplicationPlanResponse(BaseModel):
    application_plan_id: str
    plan_status: str
    template_key: str
    template_label: str
    workflow_context: str | None = None
    source_recommendation_rank: int
    source_recommendation_score: float
    apply_eligible: bool
    apply_mode: str = "review_required_non_mutating_plan"
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    selected_curve_count: int = 0
    alternate_curve_count: int = 0
    excluded_curve_count: int = 0
    selected_curves: list[WdvRecommendedCurveResponse] = Field(default_factory=list)
    alternate_curves: list[WdvRecommendedCurveResponse] = Field(default_factory=list)
    excluded_curves: list[WdvRecommendedCurveResponse] = Field(default_factory=list)
    tracks: list[WdvTemplateApplicationTrackPlanResponse] = Field(default_factory=list)
    renderer_requirements: list[str] = Field(default_factory=list)
    missing_required_families: list[str] = Field(default_factory=list)
    missing_preferred_families: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


class WdvTemplateApplicationPlanEnvelope(BaseModel):
    service: str = "wdv_template_application_plan_service"
    contract_version: str = "wdv_template_application_plan_v1"
    mutation_performed: bool = False
    plan: WdvTemplateApplicationPlanResponse
    knowledge_policy: dict[str, Any]
