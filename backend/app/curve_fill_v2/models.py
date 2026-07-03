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
    comparison: Comparison | None = None
    boundary: Boundary | None = None
    overlay_policy_uid: str | None = None
    overlay_policy_revision: str | None = None
    deadband: FiniteFloat = Field(default=0.0, ge=0)
    minimum_interval: FiniteFloat = Field(default=0.0, ge=0)
    style: FillStyle

    @model_validator(mode="after")
    def validate_rule(self) -> "CurveFillRule":
        if self.rule_type == RuleType.CONDITIONAL:
            if not self.curve_b_uid or self.comparison is None:
                raise ValueError("conditional rule requires curve_b_uid and comparison")
            if self.boundary is not None or self.overlay_policy_uid is not None:
                raise ValueError("conditional rule cannot carry boundary or overlay policy")
        elif self.rule_type == RuleType.CROSSOVER:
            if not self.curve_b_uid:
                raise ValueError("crossover rule requires curve_b_uid")
            if not self.overlay_policy_uid or not self.overlay_policy_revision:
                raise ValueError("crossover rule requires versioned overlay policy")
            if self.comparison is not None or self.boundary is not None:
                raise ValueError("crossover polarity is policy-owned")
        elif self.rule_type == RuleType.BETWEEN_CURVES:
            if not self.curve_b_uid:
                raise ValueError("between-curves rule requires curve_b_uid")
            if self.comparison is not None or self.boundary is not None or self.overlay_policy_uid is not None:
                raise ValueError("between-curves rule cannot carry comparison, boundary, or overlay policy")
        else:
            if self.boundary is None:
                raise ValueError("boundary rule requires boundary")
            if self.curve_b_uid is not None or self.comparison is not None:
                raise ValueError("boundary rule cannot carry curve B or comparison")
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
    order: int = Field(ge=0)
    enabled: bool = True
    rule_type: RuleType
    comparison: Comparison | None = None
    boundary: Boundary | None = None
    overlay_policy_uid: str | None = None
    overlay_policy_revision: str | None = None
    deadband: FiniteFloat = Field(default=0.0, ge=0)
    minimum_interval: FiniteFloat = Field(default=0.0, ge=0)
    style: FillStyle
    state: CurveFillRuleState = CurveFillRuleState.STORED
    state_reason: str | None = None
    geometry_revision: str | None = None

    @model_validator(mode="after")
    def validate_canonical_rule(self) -> "CanonicalCurveFillRule":
        if self.rule_type == RuleType.CONDITIONAL:
            if not self.curve_b_assignment_uid or self.comparison is None:
                raise ValueError(
                    "conditional rule requires curve_b_assignment_uid and comparison"
                )
            if self.boundary is not None or self.overlay_policy_uid is not None:
                raise ValueError(
                    "conditional rule cannot carry boundary or overlay policy"
                )
        elif self.rule_type == RuleType.CROSSOVER:
            if not self.curve_b_assignment_uid:
                raise ValueError("crossover rule requires curve_b_assignment_uid")
            if not self.overlay_policy_uid or not self.overlay_policy_revision:
                raise ValueError("crossover rule requires versioned overlay policy")
            if self.comparison is not None or self.boundary is not None:
                raise ValueError("crossover polarity is policy-owned")
        elif self.rule_type == RuleType.BETWEEN_CURVES:
            if not self.curve_b_assignment_uid:
                raise ValueError("between-curves rule requires curve_b_assignment_uid")
            if self.comparison is not None or self.boundary is not None or self.overlay_policy_uid is not None:
                raise ValueError("between-curves rule cannot carry comparison, boundary, or overlay policy")
        else:
            if self.boundary is None:
                raise ValueError("boundary rule requires boundary")
            if self.curve_b_assignment_uid is not None or self.comparison is not None:
                raise ValueError(
                    "boundary rule cannot carry Curve B or comparison"
                )

        if self.curve_b_assignment_uid == self.curve_a_assignment_uid:
            raise ValueError("Curve A and Curve B assignments must differ")
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
        return self
