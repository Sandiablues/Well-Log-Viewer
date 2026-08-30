"""Revision-guarded canonical Curve Fill commands."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.curve_fill_v2.models import (
    Boundary,
    Comparison,
    DepthExtent,
    FillStyle,
    RuleType,
    SeparationMode,
)
from app.identity.wdv_contract_v2 import CanonicalUuid7, FiniteNumber


class RevisionGuardedCurveFillCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected_revision: int = Field(ge=0)
    command_id: CanonicalUuid7 | None = None


class CreateCurveFillRuleCommand(RevisionGuardedCurveFillCommand):
    track_uid: CanonicalUuid7
    curve_a_assignment_uid: CanonicalUuid7
    curve_b_assignment_uid: CanonicalUuid7 | None = None
    curve_operand_assignment_uids: tuple[CanonicalUuid7, ...] = ()
    rule_type: RuleType
    comparison: Comparison | None = None
    boundary: Boundary | None = None
    reference_value: FiniteNumber | None = None
    band_min_value: FiniteNumber | None = None
    band_max_value: FiniteNumber | None = None
    minimum_separation_px: FiniteNumber = Field(default=0.0, ge=0)
    separation_mode: SeparationMode = SeparationMode.ABSOLUTE
    overlay_policy_uid: str | None = None
    overlay_policy_revision: str | None = None
    enabled: bool = True
    deadband: FiniteNumber = Field(default=0.0, ge=0)
    minimum_interval: FiniteNumber = Field(default=0.0, ge=0)
    depth_extent: DepthExtent = DepthExtent.ENTIRE_TRACK
    interval_from_md: FiniteNumber | None = None
    interval_to_md: FiniteNumber | None = None
    style: FillStyle
    target_order: int | None = Field(default=None, ge=0)


class UpdateCurveFillRuleCommand(RevisionGuardedCurveFillCommand):
    rule_uid: CanonicalUuid7
    enabled: bool | None = None
    comparison: Comparison | None = None
    boundary: Boundary | None = None
    reference_value: FiniteNumber | None = None
    band_min_value: FiniteNumber | None = None
    band_max_value: FiniteNumber | None = None
    minimum_separation_px: FiniteNumber | None = Field(default=None, ge=0)
    separation_mode: SeparationMode | None = None
    deadband: FiniteNumber | None = Field(default=None, ge=0)
    minimum_interval: FiniteNumber | None = Field(default=None, ge=0)
    depth_extent: DepthExtent | None = None
    interval_from_md: FiniteNumber | None = None
    interval_to_md: FiniteNumber | None = None
    clear_interval: bool | None = None
    style: FillStyle | None = None

    @model_validator(mode="after")
    def require_patch(self) -> "UpdateCurveFillRuleCommand":
        if all(
            value is None
            for value in (
                self.enabled,
                self.comparison,
                self.boundary,
                self.reference_value,
                self.band_min_value,
                self.band_max_value,
                self.minimum_separation_px,
                self.separation_mode,
                self.deadband,
                self.minimum_interval,
                self.depth_extent,
                self.interval_from_md,
                self.interval_to_md,
                self.clear_interval,
                self.style,
            )
        ):
            raise ValueError("UpdateCurveFillRuleCommand requires at least one field")
        return self


class RemoveCurveFillRuleCommand(RevisionGuardedCurveFillCommand):
    rule_uid: CanonicalUuid7


class ReorderCurveFillRulesCommand(RevisionGuardedCurveFillCommand):
    track_uid: CanonicalUuid7
    rule_uids: tuple[CanonicalUuid7, ...]

    @model_validator(mode="after")
    def unique_rules(self) -> "ReorderCurveFillRulesCommand":
        if len(self.rule_uids) != len(set(self.rule_uids)):
            raise ValueError("rule_uids must be unique")
        return self
