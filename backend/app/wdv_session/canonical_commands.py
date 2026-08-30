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


class ClearCanvasCommand(RevisionGuardedCommand):
    """Remove every track from the active WDV canvas."""

    preserve_depth_tracks: bool = False


class BootstrapCurveAssignmentCommand(RevisionGuardedCommand):
    """Atomically create the first canonical curve track and assignment.

    This command is valid only when the canonical session contains no tracks.
    The backend issues both UUIDs and applies governed display policy.
    """

    managed_curve_uid: CanonicalUuid7
    track_name: NonBlankString | None = None
    renderer_type: str | None = None
    track_role: str | None = None
    width_px: int | None = Field(default=None, ge=1)
    color: str | None = None
    line_style: str | None = None
    line_width: FiniteNumber | None = Field(default=None, gt=0)
    fill_mode: str | None = None
    visible: bool = True
    source: NonBlankString = "canonical_empty_session_bootstrap"


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
    renderer_type: str | None = None
    track_role: str | None = None
    width_px: int | None = Field(default=None, ge=1)
    visible: bool | None = None
    lattice: Literal["linear", "logarithmic"] | None = None
    lattice_source: str | None = None
    lattice_override: bool | None = None
    scale_mode: Literal["shared", "per_curve", "dual", "normalized"] | None = None
    depth_basis: Literal["MD", "TVD", "TVDSS"] | None = None
    core_base_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    core_brightness: FiniteNumber | None = Field(default=None, ge=0.55, le=1.45)
    core_shading_mode: Literal["flat", "cylindrical"] | None = None
    core_shading_strength: FiniteNumber | None = Field(default=None, ge=0.0, le=1.0)
    core_description_overlay_enabled: bool | None = None
    core_description_overlay_position: Literal["left", "right"] | None = None
    core_description_overlay_width_pct: FiniteNumber | None = Field(default=None, ge=20.0, le=70.0)
    core_description_overlay_font_size: int | None = Field(default=None, ge=8, le=20)
    core_description_overlay_show_md: bool | None = None
    completion_schematic_position: Literal["left", "center", "right"] | None = None
    completion_schematic_width_px: int | None = Field(default=None, ge=20, le=100)
    completion_symbol_scale: FiniteNumber | None = Field(default=None, ge=0.5, le=2.0)
    completion_line_weight: FiniteNumber | None = Field(default=None, ge=0.5, le=6.0)
    completion_show_labels: bool | None = None
    completion_label_position: Literal["left", "right", "auto"] | None = None
    completion_label_font_size: int | None = Field(default=None, ge=9, le=14)
    completion_label_offset_px: int | None = Field(default=None, ge=0, le=60)
    completion_label_vertical_offset_px: int | None = Field(default=None, ge=-60, le=60)
    completion_label_max_width_px: int | None = Field(default=None, ge=60, le=260)
    completion_label_collision_mode: Literal["auto", "off"] | None = None
    completion_label_wrap: bool | None = None
    depth_range_locator_enabled: bool | None = None
    depth_range_locator_source_track_uid: CanonicalUuid7 | None = None
    depth_range_locator_mode: Literal["content_extent", "viewport_extent", "auto"] | None = None
    depth_range_locator_presentation: Literal["edge_arrows", "wall_bar", "data_bar"] | None = None
    depth_range_locator_side: Literal["auto", "left", "right"] | None = None
    macro_core_image_enabled: bool | None = None
    macro_core_image_top_md: FiniteNumber | None = None
    macro_core_image_base_md: FiniteNumber | None = None
    macro_core_image_placement: Literal["left", "center", "right"] | None = None
    macro_core_image_horizontal_offset_px: int | None = Field(default=None, ge=-60, le=60)

    @model_validator(mode="after")
    def require_patch(self) -> "UpdateTrackCommand":
        fields = (
            self.track_name,
            self.renderer_type,
            self.track_role,
            self.width_px,
            self.visible,
            self.lattice,
            self.lattice_source,
            self.lattice_override,
            self.scale_mode,
            self.depth_basis,
            self.core_base_color,
            self.core_brightness,
            self.core_shading_mode,
            self.core_shading_strength,
            self.core_description_overlay_enabled,
            self.core_description_overlay_position,
            self.core_description_overlay_width_pct,
            self.core_description_overlay_font_size,
            self.core_description_overlay_show_md,
            self.completion_schematic_position,
            self.completion_schematic_width_px,
            self.completion_symbol_scale,
            self.completion_line_weight,
            self.completion_show_labels,
            self.completion_label_position,
            self.completion_label_font_size,
            self.completion_label_offset_px,
            self.completion_label_vertical_offset_px,
            self.completion_label_max_width_px,
            self.completion_label_collision_mode,
            self.completion_label_wrap,
            self.depth_range_locator_enabled,
            self.depth_range_locator_source_track_uid,
            self.depth_range_locator_mode,
            self.depth_range_locator_presentation,
            self.depth_range_locator_side,
            self.macro_core_image_enabled,
            self.macro_core_image_top_md,
            self.macro_core_image_base_md,
            self.macro_core_image_placement,
            self.macro_core_image_horizontal_offset_px,
        )
        if all(value is None for value in fields):
            raise ValueError("UpdateTrackCommand requires at least one field")
        has_macro_core_image = any(value is not None for value in (
            self.macro_core_image_enabled,
            self.macro_core_image_top_md,
            self.macro_core_image_base_md,
            self.macro_core_image_placement,
            self.macro_core_image_horizontal_offset_px,
        ))
        if has_macro_core_image:
            if self.macro_core_image_top_md is None or self.macro_core_image_base_md is None:
                raise ValueError("Macro Core Image update requires Top MD and Base MD")
            if self.macro_core_image_base_md <= self.macro_core_image_top_md:
                raise ValueError("Macro Core Image Base MD must be greater than Top MD")
            if self.macro_core_image_placement is None:
                raise ValueError("Macro Core Image update requires placement")
            if self.macro_core_image_horizontal_offset_px is None:
                raise ValueError("Macro Core Image update requires horizontal offset")
        return self


class ReorderTracksCommand(RevisionGuardedCommand):
    track_uids: tuple[CanonicalUuid7, ...]


class UpdateCurveLineStyleCommand(RevisionGuardedCommand):
    """Replace the complete user-owned curve line style atomically."""

    assignment_uid: CanonicalUuid7
    line_visible: bool
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    line_width: FiniteNumber = Field(gt=0, le=8)
    line_style: Literal["solid", "dash", "dot"]
    line_opacity: int = Field(ge=0, le=100)


class UpdateCurveAssignmentCommand(RevisionGuardedCommand):
    assignment_uid: CanonicalUuid7
    visible: bool | None = None
    scale_type: Literal["linear", "logarithmic"] | None = None
    scale_direction: Literal["normal", "reversed"] | None = None
    range_override_mode: Literal["governed", "manual", "fit_to_curve", "fit_to_curve_p05_p95", "fit_to_curve_p01_p99"] | None = None
    manual_scale_min: FiniteNumber | None = None
    manual_scale_max: FiniteNumber | None = None
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
    display_priority: Literal["background", "normal", "foreground"] | None = None
    show_qaqc_warnings: bool | None = None
    show_null_gaps: bool | None = None
    show_out_of_range: bool | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> "UpdateCurveAssignmentCommand":
        if (self.manual_scale_min is None) != (self.manual_scale_max is None):
            raise ValueError(
                "manual_scale_min and manual_scale_max must be supplied together"
            )
        if self.range_override_mode == "manual":
            if self.manual_scale_min is None or self.manual_scale_max is None:
                raise ValueError("manual mode requires manual scale limits")
            if self.manual_scale_min == self.manual_scale_max:
                raise ValueError("manual scale limits must differ")
        elif self.manual_scale_min is not None or self.manual_scale_max is not None:
            raise ValueError(
                "manual scale limits require range_override_mode='manual'"
            )

        fields = (
            self.visible,
            self.scale_type,
            self.scale_direction,
            self.range_override_mode,
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
        ):
            raise ValueError(
                "UpdateCurveAssignmentCommand requires at least one field"
            )
        return self


class MoveCurveAssignmentCommand(RevisionGuardedCommand):
    assignment_uid: CanonicalUuid7
    target_track_uid: CanonicalUuid7
    target_stack_index: int = Field(ge=0)
