"""Backend-owned Curve Fill v2 domain contracts.

These contracts are intentionally independent of the frontend.  The backend
owns rule meaning, compatibility, transform inputs, dependency identity and
resolved geometry.  Frontend consumers may only render the returned polygons.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class RuleType(str, Enum):
    CONDITIONAL = "conditional"
    CROSSOVER = "crossover"
    BETWEEN_CURVES = "between_curves"
    TO_BOUNDARY = "to_boundary"
    VALUE_BAND = "value_band"
    CURVE_TO_VALUE = "curve_to_value"
    THRESHOLD = "threshold"
    CURVE_ENVELOPE = "curve_envelope"
    SEPARATION = "separation"


class Comparison(str, Enum):
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"


class ScaleType(str, Enum):
    LINEAR = "linear"
    LOGARITHMIC = "logarithmic"


class ScaleDirection(str, Enum):
    NORMAL = "normal"
    REVERSED = "reversed"


class Boundary(str, Enum):
    LEFT = "left"
    RIGHT = "right"


class SeparationMode(str, Enum):
    ABSOLUTE = "absolute"
    A_RIGHT_OF_B = "a_right_of_b"
    A_LEFT_OF_B = "a_left_of_b"


class DepthExtent(str, Enum):
    ENTIRE_TRACK = "entire_track"
    SPECIFIED_INTERVAL = "specified_interval"


class CurveSeries(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    managed_well_uid: str = Field(min_length=1)
    managed_curve_uid: str = Field(min_length=1)
    sample_revision: str = Field(min_length=1)
    depth_unit: str = Field(min_length=1)
    value_unit: str | None = None
    samples: tuple[tuple[FiniteFloat, FiniteFloat], ...]

    @model_validator(mode="after")
    def validate_samples(self) -> "CurveSeries":
        if len(self.samples) < 2:
            raise ValueError("curve series requires at least two samples")
        previous = None
        for depth, _ in self.samples:
            if previous is not None and depth <= previous:
                raise ValueError("curve samples must be strictly depth ascending")
            previous = depth
        return self


class CurveTransform(BaseModel):
    """Complete backend-owned WDV value-to-pixel transform contract."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    assignment_uid: str = Field(min_length=1)
    managed_curve_uid: str = Field(min_length=1)
    transform_revision: str = Field(min_length=1)
    track_width_px: int = Field(ge=40)
    horizontal_padding_px: FiniteFloat = Field(default=10.0, ge=0)
    scale_min: FiniteFloat
    scale_max: FiniteFloat
    scale_type: ScaleType = ScaleType.LINEAR
    scale_direction: ScaleDirection = ScaleDirection.NORMAL
    position_anchor: Literal["left", "center", "right"] = "center"
    horizontal_offset_pct: FiniteFloat = Field(default=0.0, ge=-100, le=100)
    clip_to_track: bool = True

    @model_validator(mode="after")
    def validate_transform(self) -> "CurveTransform":
        if self.scale_min == self.scale_max:
            raise ValueError("scale limits must differ")
        if self.scale_type == ScaleType.LOGARITHMIC and (
            self.scale_min <= 0 or self.scale_max <= 0
        ):
            raise ValueError("logarithmic scales require positive limits")
        if self.track_width_px <= 2 * self.horizontal_padding_px:
            raise ValueError("track width must exceed twice the horizontal padding")
        return self


class FillAppearance(str, Enum):
    SOLID = "solid"
    PATTERN = "pattern"
    RASTER = "raster"


class FillStyle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    appearance: FillAppearance = FillAppearance.SOLID
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    opacity: FiniteFloat = Field(ge=0, le=1)
    pattern_uid: str | None = None
    pattern_scale: FiniteFloat = Field(default=1.0, ge=0.25, le=8.0)
    raster_asset_uid: str | None = None

    @model_validator(mode="after")
    def validate_appearance(self) -> "FillStyle":
        if self.appearance == FillAppearance.SOLID:
            if self.pattern_uid is not None or self.raster_asset_uid is not None:
                raise ValueError("solid fill cannot carry pattern or raster identity")
        elif self.appearance == FillAppearance.PATTERN:
            if not self.pattern_uid or self.raster_asset_uid is not None:
                raise ValueError("pattern fill requires pattern_uid only")
        else:
            if not self.raster_asset_uid or self.pattern_uid is not None:
                raise ValueError("raster fill requires raster_asset_uid only")
        return self




class ResolvedRasterPaint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    raster_asset_uid: str
    image_url: str
    top_depth: FiniteFloat
    base_depth: FiniteFloat
    depth_unit: str
    horizontal_fit: str = "cover"


class ResolvedFillPaint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    appearance: FillAppearance
    pattern_uid: str | None = None
    pattern_scale: FiniteFloat = 1.0
    raster: ResolvedRasterPaint | None = None

class CurveFillRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rule_uid: str = Field(min_length=1)
    managed_well_uid: str = Field(min_length=1)
    track_uid: str = Field(min_length=1)
    order: int = Field(ge=0)
    enabled: bool = True
    rule_type: RuleType
    curve_a_uid: str = Field(min_length=1)
    curve_b_uid: str | None = None
    curve_operand_uids: tuple[str, ...] = ()
    comparison: Comparison | None = None
    boundary: Boundary | None = None
    reference_value: FiniteFloat | None = None
    band_min_value: FiniteFloat | None = None
    band_max_value: FiniteFloat | None = None
    minimum_separation_px: FiniteFloat = Field(default=0.0, ge=0)
    separation_mode: SeparationMode = SeparationMode.ABSOLUTE
    overlay_policy_uid: str | None = None
    overlay_policy_revision: str | None = None
    deadband: FiniteFloat = Field(default=0.0, ge=0)
    minimum_interval: FiniteFloat = Field(default=0.0, ge=0)
    depth_extent: DepthExtent = DepthExtent.ENTIRE_TRACK
    interval_from_md: FiniteFloat | None = None
    interval_to_md: FiniteFloat | None = None
    style: FillStyle

    @model_validator(mode="after")
    def validate_rule(self) -> "CurveFillRule":
        pair_types = {RuleType.CONDITIONAL, RuleType.CROSSOVER, RuleType.BETWEEN_CURVES, RuleType.SEPARATION}
        scalar_types = {RuleType.CURVE_TO_VALUE, RuleType.THRESHOLD}
        if self.rule_type == RuleType.CONDITIONAL:
            if not self.curve_b_uid or self.comparison is None:
                raise ValueError("conditional rule requires curve_b_uid and comparison")
        elif self.rule_type == RuleType.CROSSOVER:
            if not self.curve_b_uid:
                raise ValueError("crossover rule requires curve_b_uid")
            if not self.overlay_policy_uid or not self.overlay_policy_revision:
                raise ValueError("crossover rule requires versioned overlay policy")
        elif self.rule_type == RuleType.BETWEEN_CURVES:
            if not self.curve_b_uid:
                raise ValueError("between-curves rule requires curve_b_uid")
        elif self.rule_type == RuleType.TO_BOUNDARY:
            if self.boundary is None:
                raise ValueError("boundary rule requires boundary")
        elif self.rule_type == RuleType.VALUE_BAND:
            if self.band_min_value is None or self.band_max_value is None:
                raise ValueError("value-band rule requires minimum and maximum values")
            if self.band_min_value >= self.band_max_value:
                raise ValueError("value-band minimum must be less than maximum")
        elif self.rule_type == RuleType.CURVE_TO_VALUE:
            if self.reference_value is None:
                raise ValueError("curve-to-value rule requires reference_value")
        elif self.rule_type == RuleType.THRESHOLD:
            if self.reference_value is None or self.comparison is None:
                raise ValueError("threshold rule requires reference_value and comparison")
        elif self.rule_type == RuleType.CURVE_ENVELOPE:
            if len(self.curve_operand_uids) < 2:
                raise ValueError("curve-envelope rule requires at least two curve operands")
            if len(set(self.curve_operand_uids)) != len(self.curve_operand_uids):
                raise ValueError("curve-envelope operands must be unique")
        elif self.rule_type == RuleType.SEPARATION:
            if not self.curve_b_uid:
                raise ValueError("separation rule requires curve_b_uid")

        if self.rule_type != RuleType.CROSSOVER and (self.overlay_policy_uid is not None or self.overlay_policy_revision is not None):
            raise ValueError("only crossover rules may carry overlay policy")
        if self.rule_type not in {RuleType.CONDITIONAL, RuleType.THRESHOLD} and self.comparison is not None:
            raise ValueError("comparison is not valid for this rule type")
        if self.rule_type not in {RuleType.TO_BOUNDARY, RuleType.THRESHOLD} and self.boundary is not None:
            raise ValueError("boundary is only valid for curve-to-boundary and threshold rules")
        if self.rule_type not in pair_types and self.curve_b_uid is not None:
            raise ValueError("Curve B is not valid for this rule type")
        if self.rule_type != RuleType.CURVE_ENVELOPE and self.curve_operand_uids:
            raise ValueError("curve operands are only valid for curve-envelope rules")
        if self.rule_type not in scalar_types and self.reference_value is not None:
            raise ValueError("reference_value is not valid for this rule type")
        if self.rule_type != RuleType.VALUE_BAND and (self.band_min_value is not None or self.band_max_value is not None):
            raise ValueError("band values are only valid for value-band rules")
        if self.rule_type != RuleType.SEPARATION and self.minimum_separation_px != 0:
            raise ValueError("minimum_separation_px is only valid for separation rules")

        if self.depth_extent == DepthExtent.ENTIRE_TRACK:
            if self.interval_from_md is not None or self.interval_to_md is not None:
                raise ValueError("entire-track fill cannot carry interval depths")
        else:
            if self.interval_from_md is None or self.interval_to_md is None:
                raise ValueError("specified interval requires From MD and To MD")
            if self.interval_from_md >= self.interval_to_md:
                raise ValueError("From MD must be less than To MD")
        return self


class FillVertex(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    depth: FiniteFloat
    x_a_px: FiniteFloat
    x_b_px: FiniteFloat


class FillPolygon(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    polygon_uid: str = Field(min_length=1)
    top_depth: FiniteFloat
    base_depth: FiniteFloat
    vertices: tuple[FillVertex, ...]


class CurveFillGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: Literal["wdv_curve_fill_geometry_v2"] = "wdv_curve_fill_geometry_v2"
    rule_uid: str
    order: int = Field(ge=0)
    dependency_key: str
    geometry_revision: str
    managed_well_uid: str
    track_uid: str
    depth_unit: str
    style: FillStyle
    paint: ResolvedFillPaint
    polygons: tuple[FillPolygon, ...]
    warnings: tuple[str, ...] = ()


class CurveFillRuleState(str, Enum):
    STORED = "stored"
    PENDING_GEOMETRY = "pending_geometry"
    RESOLVED = "resolved"
    DISABLED = "disabled"
    INVALID = "invalid"


class CanonicalCurveFillRule(BaseModel):
    """Durable backend-owned fill-rule state embedded in the WDV session.

    Assignment UIDs are authoritative. Managed curve identities are resolved
    from those assignments when geometry is requested; they are not duplicated
    as competing persistent truth.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_uid: str = Field(min_length=1)
    managed_well_uid: str = Field(min_length=1)
    track_uid: str = Field(min_length=1)
    curve_a_assignment_uid: str = Field(min_length=1)
    curve_b_assignment_uid: str | None = None
    curve_operand_assignment_uids: tuple[str, ...] = ()
    order: int = Field(ge=0)
    enabled: bool = True
    rule_type: RuleType
    comparison: Comparison | None = None
    boundary: Boundary | None = None
    reference_value: FiniteFloat | None = None
    band_min_value: FiniteFloat | None = None
    band_max_value: FiniteFloat | None = None
    minimum_separation_px: FiniteFloat = Field(default=0.0, ge=0)
    separation_mode: SeparationMode = SeparationMode.ABSOLUTE
    overlay_policy_uid: str | None = None
    overlay_policy_revision: str | None = None
    deadband: FiniteFloat = Field(default=0.0, ge=0)
    minimum_interval: FiniteFloat = Field(default=0.0, ge=0)
    depth_extent: DepthExtent = DepthExtent.ENTIRE_TRACK
    interval_from_md: FiniteFloat | None = None
    interval_to_md: FiniteFloat | None = None
    style: FillStyle
    state: CurveFillRuleState = CurveFillRuleState.STORED
    state_reason: str | None = None
    geometry_revision: str | None = None

    @model_validator(mode="after")
    def validate_canonical_rule(self) -> "CanonicalCurveFillRule":
        pair_types = {RuleType.CONDITIONAL, RuleType.CROSSOVER, RuleType.BETWEEN_CURVES, RuleType.SEPARATION}
        scalar_types = {RuleType.CURVE_TO_VALUE, RuleType.THRESHOLD}
        if self.rule_type == RuleType.CONDITIONAL:
            if not self.curve_b_assignment_uid or self.comparison is None:
                raise ValueError("conditional rule requires curve_b_assignment_uid and comparison")
        elif self.rule_type == RuleType.CROSSOVER:
            if not self.curve_b_assignment_uid:
                raise ValueError("crossover rule requires curve_b_assignment_uid")
            if not self.overlay_policy_uid or not self.overlay_policy_revision:
                raise ValueError("crossover rule requires versioned overlay policy")
        elif self.rule_type == RuleType.BETWEEN_CURVES:
            if not self.curve_b_assignment_uid:
                raise ValueError("between-curves rule requires curve_b_assignment_uid")
        elif self.rule_type == RuleType.TO_BOUNDARY:
            if self.boundary is None:
                raise ValueError("boundary rule requires boundary")
        elif self.rule_type == RuleType.VALUE_BAND:
            if self.band_min_value is None or self.band_max_value is None:
                raise ValueError("value-band rule requires minimum and maximum values")
            if self.band_min_value >= self.band_max_value:
                raise ValueError("value-band minimum must be less than maximum")
        elif self.rule_type == RuleType.CURVE_TO_VALUE:
            if self.reference_value is None:
                raise ValueError("curve-to-value rule requires reference_value")
        elif self.rule_type == RuleType.THRESHOLD:
            if self.reference_value is None or self.comparison is None:
                raise ValueError("threshold rule requires reference_value and comparison")
        elif self.rule_type == RuleType.CURVE_ENVELOPE:
            if len(self.curve_operand_assignment_uids) < 2:
                raise ValueError("curve-envelope rule requires at least two curve operands")
            if len(set(self.curve_operand_assignment_uids)) != len(self.curve_operand_assignment_uids):
                raise ValueError("curve-envelope operands must be unique")
        elif self.rule_type == RuleType.SEPARATION:
            if not self.curve_b_assignment_uid:
                raise ValueError("separation rule requires curve_b_assignment_uid")

        if self.rule_type != RuleType.CROSSOVER and (self.overlay_policy_uid is not None or self.overlay_policy_revision is not None):
            raise ValueError("only crossover rules may carry overlay policy")
        if self.rule_type not in {RuleType.CONDITIONAL, RuleType.THRESHOLD} and self.comparison is not None:
            raise ValueError("comparison is not valid for this rule type")
        if self.rule_type not in {RuleType.TO_BOUNDARY, RuleType.THRESHOLD} and self.boundary is not None:
            raise ValueError("boundary is only valid for curve-to-boundary and threshold rules")
        if self.rule_type not in pair_types and self.curve_b_assignment_uid is not None:
            raise ValueError("Curve B is not valid for this rule type")
        if self.rule_type != RuleType.CURVE_ENVELOPE and self.curve_operand_assignment_uids:
            raise ValueError("curve operands are only valid for curve-envelope rules")
        if self.rule_type not in scalar_types and self.reference_value is not None:
            raise ValueError("reference_value is not valid for this rule type")
        if self.rule_type != RuleType.VALUE_BAND and (self.band_min_value is not None or self.band_max_value is not None):
            raise ValueError("band values are only valid for value-band rules")
        if self.rule_type != RuleType.SEPARATION and self.minimum_separation_px != 0:
            raise ValueError("minimum_separation_px is only valid for separation rules")
        if self.curve_b_assignment_uid == self.curve_a_assignment_uid:
            raise ValueError("Curve A and Curve B assignments must differ")
        if self.rule_type == RuleType.CURVE_ENVELOPE and self.curve_a_assignment_uid not in self.curve_operand_assignment_uids:
            raise ValueError("curve-envelope operands must include Curve A")

        if self.enabled and self.state == CurveFillRuleState.DISABLED:
            raise ValueError("enabled rules cannot have disabled state")
        if not self.enabled and self.state != CurveFillRuleState.DISABLED:
            raise ValueError("disabled rules must have disabled state")
        if self.state == CurveFillRuleState.RESOLVED and not self.geometry_revision:
            raise ValueError("resolved rules require geometry_revision")
        if self.state != CurveFillRuleState.RESOLVED and self.geometry_revision is not None:
            raise ValueError("only resolved rules may carry geometry_revision")
        if self.state in {CurveFillRuleState.DISABLED, CurveFillRuleState.INVALID} and not self.state_reason:
            raise ValueError("disabled or invalid rules require state_reason")
        if self.state in {CurveFillRuleState.STORED, CurveFillRuleState.PENDING_GEOMETRY, CurveFillRuleState.RESOLVED} and self.state_reason is not None:
            raise ValueError("normal rule states cannot carry state_reason")
        if self.depth_extent == DepthExtent.ENTIRE_TRACK:
            if self.interval_from_md is not None or self.interval_to_md is not None:
                raise ValueError("entire-track fill cannot carry interval depths")
        else:
            if self.interval_from_md is None or self.interval_to_md is None:
                raise ValueError("specified interval requires From MD and To MD")
            if self.interval_from_md >= self.interval_to_md:
                raise ValueError("From MD must be less than To MD")
        return self

