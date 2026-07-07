"""Backend-owned 3D Wellbore Viewer contract models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.inventory.models import CanonicalUuid7


class WbvViewerState(str, Enum):
    NOT_LOADED = "not_loaded"
    MISSING_SURVEY = "missing_survey"
    INVALID_SURVEY = "invalid_survey"
    RELATIVE_ONLY = "relative_only"
    AVAILABLE = "available"
    AVAILABLE_VERTICAL = "available_vertical"
    NEEDS_REVIEW = "needs_review"
    UNAVAILABLE = "unavailable"


class WbvCoordinateMode(str, Enum):
    UNAVAILABLE = "unavailable"
    RELATIVE = "relative"
    PROJECTED = "projected"
    GEOGRAPHIC_NORMALIZED = "geographic_normalized"


class WbvWarning(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"] = "warning"
    message: str
    target: str | None = None


class WbvAvailableLayers(BaseModel):
    trajectory: bool = False
    survey_stations: bool = False
    depth_labels: bool = False
    formation_tops: bool = False
    lithology: bool = False
    casing: bool = False
    completions: bool = False
    loaded_curves: bool = False
    curve_attributes: bool = False


class WbvSourceSession(BaseModel):
    contract_kind: str = "wdv_load_session"
    active_viewer_package_id: str | None = None
    loaded_product_count: int = 0
    source_product_ids: list[str] = Field(default_factory=list)
    depth_domain: dict[str, Any] | None = None


class WbvTrajectoryPackage(BaseModel):
    method: str | None = None
    source: str | None = None
    trajectory_class: str | None = None
    viewer_state: str | None = None
    station_count: int | None = None
    source_station_count: int | None = None
    fixture_sampling: dict[str, Any] = Field(default_factory=dict)
    stations: list[dict[str, Any]] = Field(default_factory=list)
    render_points: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    directional_values_status: str = "not_available"
    point_value_sources: dict[str, str] = Field(default_factory=dict)


class WbvSetActiveWellRequest(BaseModel):
    managed_well_id: str = Field(min_length=1)


class WbvSessionContract(BaseModel):
    contract_kind: str = "wbv_session"
    contract_version: str = "wbv_session_v1"
    viewer: Literal["WBV"] = "WBV"
    active_managed_well_id: str | None = None
    active_managed_well_uid: CanonicalUuid7 | None = None
    well_id: str | None = None
    well_name: str | None = None
    viewer_state: WbvViewerState = WbvViewerState.NOT_LOADED
    coordinate_mode: WbvCoordinateMode = WbvCoordinateMode.UNAVAILABLE
    source_session: WbvSourceSession | None = None
    available_layers: WbvAvailableLayers = Field(default_factory=WbvAvailableLayers)
    warnings: list[WbvWarning] = Field(default_factory=list)




class WbvSurveyQaqcFinding(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"] = "warning"
    message: str
    station_index: int | None = None
    md_start: float | None = None
    md_end: float | None = None
    target: str | None = None


class WbvSurveyQaqcSummary(BaseModel):
    contract_kind: str = "wbv_survey_qaqc"
    contract_version: str = "wbv_survey_qaqc_v1"
    station_count: int = 0
    source_station_count: int | None = None
    valid_point_count: int = 0
    md_monotonic: bool = True
    tvd_monotonic: bool = True
    duplicate_md_count: int = 0
    reversed_md_count: int = 0
    zero_length_interval_count: int = 0
    invalid_inclination_count: int = 0
    invalid_azimuth_count: int = 0
    missing_inclination_count: int = 0
    missing_azimuth_count: int = 0
    derived_inclination_count: int = 0
    derived_azimuth_count: int = 0
    overall_state: Literal["pass", "warning", "error"] = "pass"
    max_station_gap: float | None = None
    max_dogleg_severity: float | None = None
    finding_count: int = 0
    findings: list[WbvSurveyQaqcFinding] = Field(default_factory=list)


class WbvSurveyQaqcContract(BaseModel):
    contract_kind: str = "wbv_survey_qaqc_response"
    contract_version: str = "wbv_survey_qaqc_response_v1"
    viewer: Literal["WBV"] = "WBV"
    managed_well_id: str
    well_id: str
    well_name: str
    trajectory_id: str | None = None
    trajectory_uid: CanonicalUuid7 | None = None
    depth_unit: str = "ft"
    angle_unit: str = "deg"
    summary: WbvSurveyQaqcSummary = Field(default_factory=WbvSurveyQaqcSummary)




class WbvDisplayLayerFile(BaseModel):
    product_id: str
    display_name: str
    display_layer_type: str
    depth_reference: str
    depth_units: str
    depth_start: float | None = None
    depth_end: float | None = None


class WbvDisplayLayerFilesContract(BaseModel):
    contract_kind: str = "wbv_display_layer_files"
    contract_version: str = "wbv_display_layer_files_v1"
    viewer: Literal["WBV"] = "WBV"
    managed_well_id: str
    layers: dict[str, list[WbvDisplayLayerFile]] = Field(default_factory=dict)


class WbvCurveOverlayCurve(BaseModel):
    curve_product_id: str
    managed_curve_uid: CanonicalUuid7 | None = None
    display_name: str
    mnemonic: str
    description: str | None = None
    unit: str | None = None
    curve_family: str | None = None
    depth_start: float | None = None
    depth_end: float | None = None
    depth_units: str | None = None
    run_interval: str | None = None
    run_number: str | None = None
    run_date: str | None = None
    curve_type: str | None = None
    classification_source: str | None = None
    classification_confidence: str | None = None
    review_required: bool = False
    source_display_name: str | None = None


class WbvCurveOverlayProduct(BaseModel):
    curve_product_id: str
    display_name: str
    curve_count: int = 0
    curves: list[WbvCurveOverlayCurve] = Field(default_factory=list)


class WbvCurveOverlayProductsContract(BaseModel):
    contract_kind: str = "wbv_curve_overlay_products"
    contract_version: str = "wbv_curve_overlay_products_v1"
    viewer: Literal["WBV"] = "WBV"
    managed_well_id: str
    products: list[WbvCurveOverlayProduct] = Field(default_factory=list)


class WbvCurveOverlayNormalizationRequest(BaseModel):
    curve_product_ids: list[str] = Field(default_factory=list, min_length=1)


class WbvCurveOverlayNormalizationItem(BaseModel):
    curve_product_id: str
    managed_curve_uid: CanonicalUuid7 | None = None
    display_name: str
    mnemonic: str
    unit: str | None = None
    display_min: float
    display_max: float
    scale_type: Literal["linear", "logarithmic"] = "linear"
    display_direction: Literal["normal", "reversed"] = "normal"
    range_source: str
    policy_revision: str | None = None
    provenance: dict[str, object] = Field(default_factory=dict)
    clamp: bool = True
    requires_review: bool = False
    sample_count: int = 0
    below_range_count: int = 0
    above_range_count: int = 0
    clipped_fraction: float = 0.0


class WbvCurveOverlayRenderSample(BaseModel):
    md: float
    value: float
    normalized: float = Field(ge=0.0, le=1.0)


class WbvTrackConfiguration(BaseModel):
    track_id: str
    display_name: str
    track_type: Literal["curve", "reference", "image", "interval"] = "curve"
    display_order: int = Field(default=0, ge=0)
    side: Literal["left", "right", "center"] = "right"
    geometry_type: Literal["legacy_planar", "camera_ribbon", "radial_panel"] = "legacy_planar"
    radial_lane: int = Field(default=0, ge=0)
    angular_position_deg: float = Field(default=0.0, ge=-360.0, le=360.0)
    orientation_mode: Literal["follow_trajectory", "camera_facing"] = "camera_facing"
    thickness: float = Field(default=0.05, gt=0.0, le=20.0)
    width: float = Field(default=1.0, ge=0.1, le=20.0)
    background_mode: Literal["transparent", "black", "white", "custom"] = "transparent"
    background_color: str = "#000000"
    background_opacity: float = Field(default=0.0, ge=0.0, le=1.0)
    border_visible: bool = False
    border_color: str = "#5f6d73"
    grid_mode: Literal["off", "linear", "logarithmic"] = "off"
    grid_color: str = "#44545d"
    wellbore_offset: float = Field(default=0.15, ge=0.0, le=20.0)
    previous_track_gap: float = Field(default=0.05, ge=0.0, le=20.0)


class WbvCurveOverlayRenderCurve(BaseModel):
    curve_product_id: str
    display_name: str
    mnemonic: str
    unit: str | None = None
    display_order: int = 0
    radial_lane: int = 0
    track_id: str | None = None
    radial_width: float = 1.0
    color: str = "#58d39b"
    line_width: float = 1.5
    opacity: float = 1.0
    fill_mode: Literal["none", "to_baseline", "between_curves", "crossover"] = "none"
    fill_target_curve_product_id: str | None = None
    fill_side: Literal["positive", "negative"] = "positive"
    fill_color: str = "#58d39b"
    fill_opacity: float = 0.35
    fill_outline: bool = True
    baseline_normalized: float = Field(default=0.0, ge=0.0, le=1.0)
    display_min: float | None = None
    display_max: float | None = None
    scale_type: Literal["linear", "logarithmic"] | None = None
    display_direction: Literal["normal", "reversed"] | None = None
    range_source: str | None = None
    policy_revision: str | None = None
    provenance: dict[str, object] = Field(default_factory=dict)
    samples: list[WbvCurveOverlayRenderSample] = Field(default_factory=list)


class WbvCurveOverlayRenderContract(BaseModel):
    contract_kind: str = "wbv_curve_overlay_render"
    contract_version: str = "wbv_curve_overlay_render_v1"
    viewer: Literal["WBV"] = "WBV"
    managed_well_id: str
    track_spacing: float = 0.05
    tracks: list[WbvTrackConfiguration] = Field(default_factory=list)
    curves: list[WbvCurveOverlayRenderCurve] = Field(default_factory=list)


class WbvCurveOverlayNormalizationContract(BaseModel):
    contract_kind: str = "wbv_curve_overlay_normalization"
    contract_version: str = "wbv_curve_overlay_normalization_v1"
    viewer: Literal["WBV"] = "WBV"
    managed_well_id: str
    curves: list[WbvCurveOverlayNormalizationItem] = Field(default_factory=list)


class WbvLayerScaleSettings(BaseModel):
    mode: Literal["backend_default", "manual"] = "backend_default"
    minimum: float | None = None
    maximum: float | None = None
    scale_type: Literal["linear", "logarithmic"] = "linear"
    direction: Literal["normal", "reversed"] = "normal"


class WbvLayerAppearanceSettings(BaseModel):
    color: str | None = None
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    line_width: float = Field(default=1.0, ge=0.1, le=20.0)
    display_mode: str | None = None
    show_labels: bool = True


class WbvCurveScaleSettings(BaseModel):
    source: Literal[
        "backend_default",
        "kr_curve",
        "kr_family",
        "robust_p5_p95",
        "manual",
    ] = "backend_default"
    minimum: float | None = None
    maximum: float | None = None
    scale_type: Literal["linear", "logarithmic"] = "linear"
    direction: Literal["normal", "reversed"] = "normal"
    direction_source: Literal["governed", "manual"] = "governed"
    clamp_outliers: bool = True
    show_clipping: bool = True

    @model_validator(mode="after")
    def validate_manual_range(self) -> "WbvCurveScaleSettings":
        if self.source == "manual":
            if self.minimum is None or self.maximum is None:
                raise ValueError("Manual curve scale requires minimum and maximum.")
            if self.maximum <= self.minimum:
                raise ValueError("Curve scale maximum must be greater than minimum.")
        if self.scale_type == "logarithmic" and self.minimum is not None and self.minimum <= 0:
            raise ValueError("Logarithmic curve scale requires a positive minimum.")
        return self


class WbvCurveAppearanceSettings(BaseModel):
    color: str = "#58d39b"
    line_width: float = Field(default=1.5, ge=0.1, le=20.0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    display_mode: Literal["line", "ribbon"] = "line"
    radial_lane: int = Field(default=0, ge=0, le=31)
    track_id: str | None = None
    radial_width: float = Field(default=1.0, ge=0.1, le=10.0)
    show_label: bool = True
    label_position: Literal["top", "base", "both", "none"] = "top"
    show_clipped_markers: bool = True
    fill_mode: Literal["none", "to_baseline", "between_curves"] = "none"
    fill_target_curve_product_id: str | None = None
    fill_side: Literal["positive", "negative"] = "positive"
    fill_color: str = "#58d39b"
    fill_opacity: float = Field(default=0.35, ge=0.0, le=1.0)
    fill_baseline_source: Literal["governed", "manual"] = "governed"
    fill_baseline_value: float | None = None
    fill_outline: bool = True

    @model_validator(mode="after")
    def validate_fill_baseline(self) -> "WbvCurveAppearanceSettings":
        if self.fill_mode == "to_baseline" and self.fill_baseline_source == "manual":
            if self.fill_baseline_value is None:
                raise ValueError("Manual curve fill baseline requires a value.")
        return self


class WbvCurveOverlayItemConfiguration(BaseModel):
    curve_product_id: str
    display_order: int = Field(default=0, ge=0)
    scale: WbvCurveScaleSettings = Field(default_factory=WbvCurveScaleSettings)
    appearance: WbvCurveAppearanceSettings = Field(default_factory=WbvCurveAppearanceSettings)


class WbvDisplayLayerConfiguration(BaseModel):
    layer_type: str
    visible: bool = False
    selected_item_ids: list[str] = Field(default_factory=list)
    source_type: Literal["wmd", "wdv_template"] = "wmd"
    source_product_id: str | None = None
    scale: WbvLayerScaleSettings = Field(default_factory=WbvLayerScaleSettings)
    appearance: WbvLayerAppearanceSettings = Field(default_factory=WbvLayerAppearanceSettings)
    curve_settings: list[WbvCurveOverlayItemConfiguration] = Field(default_factory=list)


class WbvDisplayLayerConfigurationRequest(BaseModel):
    track_spacing: float = Field(default=0.05, ge=0.0, le=20.0)
    tracks: list[WbvTrackConfiguration] = Field(default_factory=list)
    layers: list[WbvDisplayLayerConfiguration] = Field(default_factory=list)


class WbvDisplayLayerConfigurationContract(BaseModel):
    contract_kind: str = "wbv_display_layer_configuration"
    contract_version: str = "wbv_display_layer_configuration_v1"
    viewer: Literal["WBV"] = "WBV"
    managed_well_id: str
    track_spacing: float = 0.05
    tracks: list[WbvTrackConfiguration] = Field(default_factory=list)
    layers: list[WbvDisplayLayerConfiguration] = Field(default_factory=list)


class WbvDisplaySettingsRequest(BaseModel):
    depth_unit: Literal["ft", "m"]


class WbvDisplaySettingsContract(BaseModel):
    contract_kind: str = "wbv_display_settings"
    contract_version: str = "wbv_display_settings_v1"
    viewer: Literal["WBV"] = "WBV"
    managed_well_id: str
    depth_unit: Literal["ft", "m"] = "ft"


class WbvViewerPackageContract(BaseModel):
    contract_kind: str = "wbv_viewer_package"
    contract_version: str = "wbv_viewer_package_v1"
    viewer: Literal["WBV"] = "WBV"
    managed_well_id: str
    well_id: str
    well_name: str
    viewer_state: WbvViewerState
    coordinate_mode: WbvCoordinateMode = WbvCoordinateMode.UNAVAILABLE
    depth_unit: str = "ft"
    angle_unit: str = "deg"
    datum: dict[str, Any] = Field(default_factory=dict)
    crs: dict[str, Any] = Field(default_factory=lambda: {"epsg": None, "status": "not_available"})
    trajectory: WbvTrajectoryPackage = Field(default_factory=WbvTrajectoryPackage)
    survey_qaqc: WbvSurveyQaqcSummary = Field(default_factory=WbvSurveyQaqcSummary)
    bounding_box: dict[str, Any] = Field(default_factory=dict)
    axes: dict[str, Any] = Field(default_factory=dict)
    available_layers: WbvAvailableLayers = Field(default_factory=WbvAvailableLayers)
    markers: list[dict[str, Any]] = Field(default_factory=list)
    intervals: list[dict[str, Any]] = Field(default_factory=list)
    available_attribute_tracks: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[WbvWarning] = Field(default_factory=list)

class WbvManagedTrajectoryStatus(str, Enum):
    CANDIDATE = "candidate"
    PARSED = "parsed"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    SYNTHETIC_DEMO = "synthetic_demo"


class WbvManagedTrajectoryRecord(BaseModel):
    """Backend-owned managed wellbore geometry record surfaced to MDP/WBV.

    A well may have many records, but only one approved/eligible trajectory is
    active at a time for WBV rendering and WDV correlation.
    """

    trajectory_id: str
    managed_trajectory_uid: CanonicalUuid7 | None = None
    trajectory_revision_uid: CanonicalUuid7 | None = None
    representation_uid: CanonicalUuid7 | None = None
    source_occurrence_uid: CanonicalUuid7 | None = None
    revision_number: int = 1
    revision_fingerprint: str | None = None
    supersedes_trajectory_revision_uid: CanonicalUuid7 | None = None
    trajectory_name: str
    trajectory_type: str = "deviation_survey"
    status: WbvManagedTrajectoryStatus = WbvManagedTrajectoryStatus.CANDIDATE
    wbv_eligible: bool = False
    is_active: bool = False
    is_canonical: bool = False
    is_synthetic: bool = False
    source_file_id: str | None = None
    source_label: str | None = None
    station_count: int | None = None
    md_min: float | None = None
    md_max: float | None = None
    tvd_min: float | None = None
    tvd_max: float | None = None
    geometry_class: str | None = None
    coordinate_mode: WbvCoordinateMode = WbvCoordinateMode.UNAVAILABLE
    trajectory_package: dict[str, Any] = Field(default_factory=dict)
    qa_flags: list[str] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    supersedes_trajectory_id: str | None = None
    created_at: str | None = None
    approved_at: str | None = None


class WbvTrajectoryListContract(BaseModel):
    contract_kind: str = "wbv_trajectory_list"
    contract_version: str = "wbv_trajectory_list_v1"
    viewer: Literal["WBV"] = "WBV"
    managed_well_id: str
    well_id: str
    well_name: str
    active_trajectory_id: str | None = None
    active_trajectory_uid: CanonicalUuid7 | None = None
    geometry_status: str = "missing"
    wbv_ready: bool = False
    trajectories: list[WbvManagedTrajectoryRecord] = Field(default_factory=list)
    warnings: list[WbvWarning] = Field(default_factory=list)


class WbvSetActiveTrajectoryRequest(BaseModel):
    managed_trajectory_uid: CanonicalUuid7 | None = None
    trajectory_uid: CanonicalUuid7 | None = None
    trajectory_id: str | None = None
    requested_by: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def require_trajectory_reference(self) -> "WbvSetActiveTrajectoryRequest":
        if (
            not self.managed_trajectory_uid
            and not self.trajectory_uid
            and not str(self.trajectory_id or "").strip()
        ):
            raise ValueError(
                "managed_trajectory_uid, trajectory_uid, or trajectory_id is required"
            )
        return self

    @property
    def canonical_or_legacy_reference(self) -> str:
        return str(
            self.managed_trajectory_uid
            or self.trajectory_uid
            or self.trajectory_id
        )


class WbvSetActiveTrajectoryResponse(BaseModel):
    contract_kind: str = "wbv_set_active_trajectory"
    contract_version: str = "wbv_set_active_trajectory_v1"
    viewer: Literal["WBV"] = "WBV"
    managed_well_id: str
    active_trajectory_id: str
    active_trajectory_uid: CanonicalUuid7 | None = None
    active_trajectory_name: str
    geometry_status: str
    wbv_ready: bool
    trajectories: list[WbvManagedTrajectoryRecord] = Field(default_factory=list)

