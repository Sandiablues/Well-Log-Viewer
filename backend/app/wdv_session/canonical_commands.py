"""Canonical backend-owned WDV session mutation commands."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.identity.wdv_contract_v2 import CanonicalUuid7, FiniteNumber, NonBlankString


class RevisionGuardedCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected_revision: int = Field(ge=0)
    command_id: CanonicalUuid7 | None = None


class CreateTrackCommand(RevisionGuardedCommand):
    track_name: NonBlankString
    track_type: Literal["depth", "curve", "image", "annotation"] = "curve"
    track_key: str | None = None
    track_number: int | None = Field(default=None, ge=0)
    renderer_type: str | None = None
    track_role: str | None = None
    width_px: int | None = Field(default=None, ge=1)
    lattice: str | None = None
    lattice_source: str | None = None
    source_template_key: str | None = None
    source_application_plan_uid: CanonicalUuid7 | None = None
    select_created_track: bool = True


class TrackInsertPosition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["before_track", "after_track", "far_right"] = "far_right"
    reference_track_uid: CanonicalUuid7 | None = None

    @model_validator(mode="after")
    def validate_reference(self) -> "TrackInsertPosition":
        if self.mode == "far_right" and self.reference_track_uid is not None:
            raise ValueError(
                "reference_track_uid must be omitted when mode is far_right"
            )
        if self.mode in {"before_track", "after_track"}:
            if self.reference_track_uid is None:
                raise ValueError(
                    "reference_track_uid is required for relative insertion"
                )
        return self


class CreateConfiguredTrackCommand(RevisionGuardedCommand):
    track_name: NonBlankString
    track_type: Literal["depth", "curve", "image", "annotation"] = "curve"
    track_key: str | None = None
    renderer_type: str | None = None
    track_role: str | None = None
    width_px: int | None = Field(default=None, ge=1)
    lattice: Literal["linear", "logarithmic"] | None = None
    lattice_source: str | None = None
    lattice_override: bool = False
    scale_mode: Literal["shared", "per_curve", "dual", "normalized"] = "per_curve"
    depth_basis: Literal["MD", "TVD", "TVDSS"] | None = None
    source_template_key: str | None = None
    source_application_plan_uid: CanonicalUuid7 | None = None
    insert_position: TrackInsertPosition = Field(
        default_factory=TrackInsertPosition
    )
    initial_managed_curve_uids: tuple[CanonicalUuid7, ...] = ()
    select_created_track: bool = True

    @model_validator(mode="after")
    def validate_configured_track(self) -> "CreateConfiguredTrackCommand":
        if self.depth_basis is not None and self.track_type != "depth":
            raise ValueError("depth_basis may only be set on depth tracks")
        if self.initial_managed_curve_uids and self.track_type != "curve":
            raise ValueError(
                "initial_managed_curve_uids require a curve track"
            )
        if len(self.initial_managed_curve_uids) != len(
            set(self.initial_managed_curve_uids)
        ):
            raise ValueError("initial_managed_curve_uids must be unique")
        return self


class ResetCurveTrackWidthsCommand(RevisionGuardedCommand):
    width_px: int = Field(ge=1)
    visible_curve_tracks_only: bool = True


class RemoveTrackCommand(RevisionGuardedCommand):
    track_uid: CanonicalUuid7


class AddCurveAssignmentCommand(RevisionGuardedCommand):
    track_uid: CanonicalUuid7
    managed_curve_uid: CanonicalUuid7
    target_stack_index: int | None = Field(default=None, ge=0)
    scale_min: FiniteNumber | None = None
    scale_max: FiniteNumber | None = None
    scale_type: Literal["linear", "logarithmic"] | None = None
    scale_direction: Literal["normal", "reversed"] | None = None
    color: str | None = None
    line_style: str | None = None
    line_width: FiniteNumber | None = Field(default=None, gt=0)
    fill_mode: str | None = None
    visible: bool = True
    source: NonBlankString = "manual_backend_command"


class RemoveCurveAssignmentCommand(RevisionGuardedCommand):
    assignment_uid: CanonicalUuid7


class ReorderCurveAssignmentsCommand(RevisionGuardedCommand):
    track_uid: CanonicalUuid7
    assignment_uids: tuple[CanonicalUuid7, ...]


class SelectTrackCommand(RevisionGuardedCommand):
    track_uid: CanonicalUuid7 | None


class UpdateTrackCommand(RevisionGuardedCommand):
    track_uid: CanonicalUuid7
    track_name: NonBlankString | None = None
    width_px: int | None = Field(default=None, ge=1)
    visible: bool | None = None
    lattice: Literal["linear", "logarithmic"] | None = None
    lattice_source: str | None = None
    lattice_override: bool | None = None
    scale_mode: Literal["shared", "per_curve", "dual", "normalized"] | None = None
    depth_basis: Literal["MD", "TVD", "TVDSS"] | None = None

    @model_validator(mode="after")
    def require_patch(self) -> "UpdateTrackCommand":
        fields = (
            self.track_name,
            self.width_px,
            self.visible,
            self.lattice,
            self.lattice_source,
            self.lattice_override,
            self.scale_mode,
            self.depth_basis,
        )
        if all(value is None for value in fields):
            raise ValueError("UpdateTrackCommand requires at least one field")
        return self


class ReorderTracksCommand(RevisionGuardedCommand):
    track_uids: tuple[CanonicalUuid7, ...]


class UpdateCurveAssignmentCommand(RevisionGuardedCommand):
    assignment_uid: CanonicalUuid7
    visible: bool | None = None
    scale_min: FiniteNumber | None = None
    scale_max: FiniteNumber | None = None
    scale_type: Literal["linear", "logarithmic"] | None = None
    scale_direction: Literal["normal", "reversed"] | None = None
    range_mode: Literal["auto", "fixed"] | None = None
    color: str | None = None
    line_visible: bool | None = None
    line_style: Literal["solid", "dash", "dot"] | None = None
    line_width: FiniteNumber | None = Field(default=None, gt=0)
    line_opacity: int | None = Field(default=None, ge=0, le=100)
    position_anchor: Literal["left", "center", "right"] | None = None
    horizontal_offset_pct: FiniteNumber | None = Field(default=None, ge=-100, le=100)
    clip_to_track: bool | None = None
    fill_side: Literal["none", "left", "right", "between"] | None = None
    fill_color: str | None = None
    fill_opacity: int | None = Field(default=None, ge=0, le=100)
    infill_source: Literal["solid", "lithology", "curve_pair"] | None = None
    infill_pattern: str | None = None
    infill_interval_column: str | None = None
    paired_managed_curve_uid: CanonicalUuid7 | None = None
    clear_paired_managed_curve_uid: bool = False
    # When True, clears scale_min, scale_max, scale_type, and scale_direction
    # on the assignment, restoring the governed KR/fallback display policy.
    # Must not be combined with explicit scale_min/max/type/direction values.
    # The frontend must send only this flag — never recalculate and resend KR values.
    reset_scale_to_governed_default: bool = False
    display_priority: Literal["background", "normal", "foreground"] | None = None
    show_qaqc_warnings: bool | None = None
    show_null_gaps: bool | None = None
    show_out_of_range: bool | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> "UpdateCurveAssignmentCommand":
        if (self.scale_min is None) != (self.scale_max is None):
            raise ValueError("scale_min and scale_max must be supplied together")
        if self.reset_scale_to_governed_default and (
            self.scale_min is not None
            or self.scale_max is not None
            or self.scale_type is not None
            or self.scale_direction is not None
        ):
            raise ValueError(
                "reset_scale_to_governed_default may not be combined with "
                "explicit scale fields"
            )
        fields = (
            self.visible,
            self.scale_min,
            self.scale_type,
            self.scale_direction,
            self.range_mode,
            self.color,
            self.line_visible,
            self.line_style,
            self.line_width,
            self.line_opacity,
            self.position_anchor,
            self.horizontal_offset_pct,
            self.clip_to_track,
            self.fill_side,
            self.fill_color,
            self.fill_opacity,
            self.infill_source,
            self.infill_pattern,
            self.infill_interval_column,
            self.paired_managed_curve_uid,
            self.display_priority,
            self.show_qaqc_warnings,
            self.show_null_gaps,
            self.show_out_of_range,
        )
        if (
            all(value is None for value in fields)
            and not self.clear_paired_managed_curve_uid
            and not self.reset_scale_to_governed_default
        ):
            raise ValueError(
                "UpdateCurveAssignmentCommand requires at least one field"
            )
        return self


class MoveCurveAssignmentCommand(RevisionGuardedCommand):
    assignment_uid: CanonicalUuid7
    target_track_uid: CanonicalUuid7
    target_stack_index: int = Field(ge=0)
