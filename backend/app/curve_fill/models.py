"""Canonical backend contracts for conditional and crossover curve fill."""

from __future__ import annotations

from enum import Enum
from math import isfinite
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class FillMode(str, Enum):
    CONDITIONAL = "conditional"
    CROSSOVER = "crossover"


class ComparisonCondition(str, Enum):
    A_GREATER_THAN_B = "a_greater_than_b"
    A_LESS_THAN_B = "a_less_than_b"


class ComparisonBasis(str, Enum):
    ENGINEERING_VALUE = "engineering_value"
    NORMALIZED_TRACK_POSITION = "normalized_track_position"


class CurveOperand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["curve"] = "curve"
    managed_well_uid: str = Field(min_length=1)
    curve_uid: str = Field(min_length=1)
    depth_domain_uid: str = Field(min_length=1)
    unit: str | None = None


class ConstantReferenceOperand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["constant_reference"] = "constant_reference"
    managed_well_uid: str = Field(min_length=1)
    reference_uid: str = Field(min_length=1)
    depth_domain_uid: str = Field(min_length=1)
    unit: str | None = None
    value: FiniteFloat


class SteppedReferencePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    top_depth: FiniteFloat
    base_depth: FiniteFloat
    value: FiniteFloat

    @model_validator(mode="after")
    def validate_interval(self) -> "SteppedReferencePoint":
        if self.base_depth <= self.top_depth:
            raise ValueError("stepped-reference base_depth must exceed top_depth")
        return self


class SteppedReferenceOperand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["stepped_reference"] = "stepped_reference"
    managed_well_uid: str = Field(min_length=1)
    reference_uid: str = Field(min_length=1)
    depth_domain_uid: str = Field(min_length=1)
    unit: str | None = None
    intervals: tuple[SteppedReferencePoint, ...]


class DerivedReferenceOperand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["derived_reference"] = "derived_reference"
    managed_well_uid: str = Field(min_length=1)
    reference_uid: str = Field(min_length=1)
    depth_domain_uid: str = Field(min_length=1)
    unit: str | None = None
    policy_id: str = Field(min_length=1)
    policy_revision: str = Field(min_length=1)


FillOperand = CurveOperand | ConstantReferenceOperand | SteppedReferenceOperand | DerivedReferenceOperand


class FillStyle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fill: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    opacity: FiniteFloat = Field(ge=0.0, le=1.0)


class FillSample(BaseModel):
    """One backend-aligned sample. Values may be null, which terminates geometry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    depth: FiniteFloat
    a_value: FiniteFloat | None
    b_value: FiniteFloat | None
    a_track_position: FiniteFloat | None = Field(default=None, ge=0.0, le=1.0)
    b_track_position: FiniteFloat | None = Field(default=None, ge=0.0, le=1.0)


class CurveFillResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["wdv_curve_fill_v1"] = "wdv_curve_fill_v1"
    fill_mode: FillMode
    operand_a: FillOperand
    operand_b: FillOperand
    condition: ComparisonCondition | None = None
    comparison_basis: ComparisonBasis
    overlay_policy_id: str | None = None
    overlay_policy_revision: str | None = None
    style: FillStyle
    deadband: FiniteFloat | None = Field(default=None, ge=0.0)
    minimum_interval: FiniteFloat | None = Field(default=None, ge=0.0)
    depth_unit: str = Field(min_length=1)
    samples: tuple[FillSample, ...]

    @model_validator(mode="after")
    def validate_contract(self) -> "CurveFillResolveRequest":
        if self.operand_a.managed_well_uid != self.operand_b.managed_well_uid:
            raise ValueError("fill operands must belong to the same managed well")
        if self.operand_a.depth_domain_uid != self.operand_b.depth_domain_uid:
            raise ValueError("fill operands must share one depth domain")
        if self.fill_mode == FillMode.CONDITIONAL:
            if self.condition is None:
                raise ValueError("conditional fill requires a comparison condition")
            if self.comparison_basis != ComparisonBasis.ENGINEERING_VALUE:
                raise ValueError("conditional fill requires engineering-value comparison")
            if self.overlay_policy_id is not None or self.overlay_policy_revision is not None:
                raise ValueError("conditional fill cannot carry an overlay policy")
            unit_a = self.operand_a.unit
            unit_b = self.operand_b.unit
            if unit_a and unit_b and unit_a.strip().lower() != unit_b.strip().lower():
                raise ValueError("engineering-value comparison requires compatible units")
        else:
            if self.condition is not None:
                raise ValueError("crossover direction is owned by the overlay policy")
            if self.comparison_basis != ComparisonBasis.NORMALIZED_TRACK_POSITION:
                raise ValueError("crossover fill requires normalized track positions")
            if not self.overlay_policy_id or not self.overlay_policy_revision:
                raise ValueError("crossover fill requires a versioned approved overlay policy")
        last_depth: float | None = None
        for sample in self.samples:
            if last_depth is not None and sample.depth <= last_depth:
                raise ValueError("fill samples must be strictly depth-ascending")
            last_depth = sample.depth
            for value in (sample.a_value, sample.b_value, sample.a_track_position, sample.b_track_position):
                if value is not None and not isfinite(value):
                    raise ValueError("fill sample values must be finite or null")
        return self


class FillVertex(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    depth: FiniteFloat
    a_track_position: FiniteFloat = Field(ge=0.0, le=1.0)
    b_track_position: FiniteFloat = Field(ge=0.0, le=1.0)


class ResolvedFillSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    top_depth: FiniteFloat
    base_depth: FiniteFloat
    vertices: tuple[FillVertex, ...]


class CurveFillResolveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["wdv_curve_fill_render_v1"] = "wdv_curve_fill_render_v1"
    managed_well_uid: str
    depth_domain_uid: str
    fill_mode: FillMode
    comparison_basis: ComparisonBasis
    style: FillStyle
    depth_unit: str
    segments: tuple[ResolvedFillSegment, ...]
    warnings: tuple[str, ...] = ()
