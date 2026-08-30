"""Full-fidelity canonical UUIDv7 contracts for WDV v2.1.

Identity and functional payload are deliberately separated:

* Canonical UUIDv7 fields own entity identity.
* Typed display, layout, rendering, statistics, and provenance fields preserve
  the complete WDV behavior required by current consumers.
* Legacy identifiers are permitted only inside explicit ``legacy_ids`` alias
  records on managed catalogue references. They are never accepted as active
  curve, track, assignment, session, well, product, or source identity.

This module is a contract boundary only. Service conversion and persistence
migration are implemented in later bounded blocks.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.identity import LegacyIdentityAlias, parse_uuid7
from app.curve_fill_v2.models import CanonicalCurveFillRule


WDV_IDENTITY_CONTRACT_VERSION = "wdv_identity_v2_1"
WDV_SESSION_CONTRACT_VERSION = "wdv_session_layout_state_v2_1"
WDV_SAMPLE_CONTRACT_VERSION = "wdv_curve_samples_v2_1"


def _uuid7(value: str) -> str:
    return str(parse_uuid7(value))


def _non_blank(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must not be blank")
    return normalized


def _iso_datetime(value: str) -> str:
    normalized = value.strip()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("value must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return normalized


CanonicalUuid7 = Annotated[str, AfterValidator(_uuid7)]
NonBlankString = Annotated[str, AfterValidator(_non_blank)]
IsoDatetimeString = Annotated[str, AfterValidator(_iso_datetime)]
FiniteNumber = Annotated[float, Field(allow_inf_nan=False)]


class WdvCanonicalCurveReference(BaseModel):
    """One managed curve occurrence exposed to WDV."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["wdv_identity_v2_1"] = WDV_IDENTITY_CONTRACT_VERSION
    managed_curve_uid: CanonicalUuid7
    managed_product_uid: CanonicalUuid7
    managed_well_uid: CanonicalUuid7
    managed_wellbore_uid: CanonicalUuid7 | None = None
    managed_source_uid: CanonicalUuid7
    kr_curve_type_id: str | None = None
    observed_mnemonic: NonBlankString
    normalized_mnemonic: str | None = None
    display_name: NonBlankString
    unit: str | None = None
    curve_family: str | None = None
    description: str | None = None
    legacy_ids: tuple[LegacyIdentityAlias, ...] = ()


class WdvCanonicalAssignment(BaseModel):
    """One backend-governed curve-to-track assignment with display state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assignment_uid: CanonicalUuid7
    managed_curve_uid: CanonicalUuid7
    managed_product_uid: CanonicalUuid7
    managed_well_uid: CanonicalUuid7
    managed_wellbore_uid: CanonicalUuid7 | None = None
    managed_source_uid: CanonicalUuid7
    track_uid: CanonicalUuid7

    # Classification and labels are payload metadata, never identity.
    kr_curve_type_id: str | None = None
    observed_mnemonic: NonBlankString
    normalized_mnemonic: str | None = None
    display_name: NonBlankString
    curve_family: str | None = None
    unit: str | None = None

    # Assignment/render state.
    stack_index: int = Field(default=0, ge=0)
    visible: bool = True
    scale_min: FiniteNumber | None = None
    scale_max: FiniteNumber | None = None
    scale_min_label: str | None = None
    scale_max_label: str | None = None
    scale_type: Literal["linear", "logarithmic"] | None = None
    scale_direction: Literal["normal", "reversed"] | None = None
    scale_type_override: Literal["linear", "logarithmic"] | None = None
    scale_direction_override: Literal["normal", "reversed"] | None = None
    # User intent is explicit. Effective scale_* fields are backend outputs.
    range_override_mode: Literal["governed", "manual", "fit_to_curve", "fit_to_curve_p05_p95", "fit_to_curve_p01_p99"] = "governed"
    manual_scale_min: FiniteNumber | None = None
    manual_scale_max: FiniteNumber | None = None
    effective_range_source: Literal["governed", "manual", "fit_to_curve", "fit_to_curve_p05_p95", "fit_to_curve_p01_p99"] = "governed"
    override_warning_code: str | None = None
    override_warning_message: str | None = None
    range_edit_step: FiniteNumber = Field(default=1.0, gt=0)
    range_edit_precision: int = Field(default=0, ge=0, le=12)
    color: str | None = None
    line_style: str | None = None
    line_width: FiniteNumber | None = Field(default=None, gt=0)
    line_visible: bool = True
    line_opacity: int = Field(default=100, ge=0, le=100)
    range_mode: Literal["auto", "fixed"] = "fixed"
    position_anchor: Literal["left", "center", "right"] = "center"
    horizontal_offset_pct: FiniteNumber = Field(default=0.0, ge=-100, le=100)
    clip_to_track: bool = True
    fill_mode: str | None = None
    fill_side: Literal["none", "left", "right", "between"] = "none"
    fill_color: str | None = None
    fill_opacity: int = Field(default=55, ge=0, le=100)
    infill_source: Literal["solid", "lithology", "curve_pair"] = "solid"
    infill_pattern: str = "solid"
    infill_interval_column: str = "lithology"
    paired_managed_curve_uid: CanonicalUuid7 | None = None
    display_priority: Literal["background", "normal", "foreground"] = "normal"
    show_qaqc_warnings: bool = True
    show_null_gaps: bool = True
    show_out_of_range: bool = True
    source: NonBlankString = "manual_or_backend_owned"

    # Display-policy provenance is deliberately separate from assignment source.
    # None preserves compatibility for assignments created before this contract
    # extension; later bounded work will populate these fields on every path.
    display_policy_source: Literal[
        "curve", "family", "system_default"
    ] | None = None
    display_review_required: bool = False
    display_warning_code: str | None = None
    display_warning_message: str | None = None

    @model_validator(mode="after")
    def validate_scale(self) -> "WdvCanonicalAssignment":
        if (self.scale_min is None) != (self.scale_max is None):
            raise ValueError("scale_min and scale_max must be supplied together")
        if self.scale_min is not None and self.scale_max is not None:
            if self.scale_min == self.scale_max:
                raise ValueError("scale_min and scale_max must differ")
            if self.scale_type == "logarithmic" and (
                self.scale_min <= 0 or self.scale_max <= 0
            ):
                raise ValueError("logarithmic scales require positive limits")
        if self.range_override_mode == "manual":
            if self.manual_scale_min is None or self.manual_scale_max is None:
                raise ValueError("manual mode requires manual_scale_min and manual_scale_max")
            if self.manual_scale_min == self.manual_scale_max:
                raise ValueError("manual scale limits must differ")
            if self.scale_type == "logarithmic" and (
                self.manual_scale_min <= 0 or self.manual_scale_max <= 0
            ):
                raise ValueError("manual logarithmic ranges require positive limits")
        elif self.manual_scale_min is not None or self.manual_scale_max is not None:
            raise ValueError("manual scale limits are valid only in manual mode")
        if self.effective_range_source != self.range_override_mode:
            raise ValueError("effective_range_source must match range_override_mode")
        if (self.override_warning_code is None) != (self.override_warning_message is None):
            raise ValueError("override warning code and message must be supplied together")
        if self.display_policy_source == "system_default":
            if not self.display_review_required:
                raise ValueError(
                    "system-default display policy requires manual review"
                )
            if not self.display_warning_code or not self.display_warning_message:
                raise ValueError(
                    "system-default display policy requires warning details"
                )
        elif self.display_review_required:
            raise ValueError(
                "display_review_required is valid only for system-default policy"
            )
        elif self.display_warning_code is not None or self.display_warning_message is not None:
            raise ValueError(
                "display warning details are valid only for system-default policy"
            )
        return self


_TEXT_BOX_ALLOWED_TAG = re.compile(
    r"</?(?:div|p|br|b|strong|i|em|u)\s*/?>",
    flags=re.IGNORECASE,
)


class WdvTextOverlay(BaseModel):
    """One depth-anchored rich text box owned by a WDV track."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    overlay_uid: str = Field(min_length=1, max_length=128)
    # `text` remains optional for backward compatibility with the abandoned
    # single-line V1 payload. New writes use content_html.
    text: str | None = Field(default=None, max_length=240)
    content_html: str = Field(default="<div>Text</div>", min_length=1, max_length=6000)
    md: FiniteNumber
    horizontal_anchor: Literal["left", "center", "right"] = "center"
    horizontal_offset: int = Field(default=0, ge=-100, le=100)
    vertical_offset: int = Field(default=0, ge=-100, le=100)
    width_percent: int = Field(default=70, ge=25, le=100)
    font_size: int = Field(default=11, ge=9, le=14)
    color: str = Field(default="#1f2937", pattern=r"^#[0-9a-fA-F]{6}$")
    background: Literal["none", "light"] = "none"
    text_align: Literal["left", "center", "right"] = "left"

    @model_validator(mode="after")
    def validate_rich_text_box(self) -> "WdvTextOverlay":
        html = self.content_html.strip()
        # No HTML attributes are accepted; the editor stores only a deliberately
        # tiny formatting subset: paragraphs/line breaks + B/I/U.
        if re.search(r"\bon\w+\s*=|\bstyle\s*=|javascript:", html, re.IGNORECASE):
            raise ValueError("Text Box HTML contains unsupported attributes")
        residual = _TEXT_BOX_ALLOWED_TAG.sub("", html)
        if "<" in residual or ">" in residual:
            raise ValueError("Text Box HTML contains unsupported markup")
        plain = re.sub(r"<[^>]+>", "", html).replace("&nbsp;", " ").strip()
        if not plain:
            raise ValueError("Text Box content must not be empty")
        return self


class WdvCanonicalTrack(BaseModel):
    """One backend-governed WDV track with complete layout state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    track_uid: CanonicalUuid7
    managed_well_uid: CanonicalUuid7
    track_key: str | None = None
    track_number: int | None = Field(default=None, ge=0)
    track_name: NonBlankString
    track_type: Literal["depth", "curve", "image", "annotation"] = "curve"
    renderer_type: str | None = None
    track_role: str | None = None
    width_px: int | None = Field(default=None, ge=1)
    lattice: str | None = None
    lattice_source: str | None = None
    source_template_key: str | None = None
    source_application_plan_uid: CanonicalUuid7 | None = None
    visible: bool = True
    scale_mode: Literal["shared", "per_curve", "dual", "normalized"] = "per_curve"
    lattice_override: bool = False
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
    text_overlays: tuple[WdvTextOverlay, ...] = ()
    assignments: tuple[WdvCanonicalAssignment, ...] = ()

    @model_validator(mode="after")
    def validate_track_graph(self) -> "WdvCanonicalTrack":
        invalid = [
            item.assignment_uid
            for item in self.assignments
            if item.track_uid != self.track_uid
        ]
        if invalid:
            raise ValueError(
                "Every WDV assignment must reference its containing track_uid"
            )

        if any(item.managed_well_uid != self.managed_well_uid for item in self.assignments):
            raise ValueError(
                "Every WDV assignment must reference its containing track managed_well_uid"
            )

        assignment_uids = [item.assignment_uid for item in self.assignments]
        if len(assignment_uids) != len(set(assignment_uids)):
            raise ValueError("Duplicate assignment_uid in WDV track")

        if self.track_type == "depth" and self.assignments:
            raise ValueError("Depth tracks cannot contain curve assignments")
        has_core_appearance = any(value is not None for value in (
            self.core_base_color,
            self.core_brightness,
            self.core_shading_mode,
            self.core_shading_strength,
            self.core_description_overlay_enabled,
            self.core_description_overlay_position,
            self.core_description_overlay_width_pct,
            self.core_description_overlay_font_size,
            self.core_description_overlay_show_md,
        ))
        if has_core_appearance and not (
            self.track_type == "image" and self.renderer_type == "core_image"
        ):
            raise ValueError("Core appearance fields are valid only for core_image tracks")
        has_macro_core_image = any(value is not None for value in (
            self.macro_core_image_enabled,
            self.macro_core_image_top_md,
            self.macro_core_image_base_md,
            self.macro_core_image_placement,
            self.macro_core_image_horizontal_offset_px,
        ))
        if has_macro_core_image:
            if self.macro_core_image_top_md is None or self.macro_core_image_base_md is None:
                raise ValueError("Macro Core Image requires Top MD and Base MD")
            if self.macro_core_image_base_md <= self.macro_core_image_top_md:
                raise ValueError("Macro Core Image Base MD must be greater than Top MD")
            if self.macro_core_image_placement is None:
                raise ValueError("Macro Core Image requires placement")
            if self.macro_core_image_horizontal_offset_px is None:
                raise ValueError("Macro Core Image requires horizontal offset")
        has_completion_appearance = any(value is not None for value in (
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
        ))
        if has_completion_appearance and not (
            self.track_type == "annotation"
            and self.renderer_type == "completion_components"
        ):
            raise ValueError(
                "Completion appearance fields are valid only for completion_components tracks"
            )
        return self


class WdvCanonicalSession(BaseModel):
    """Durable backend-owned WDV session/layout contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["wdv_session_layout_state_v2_1"] = (
        WDV_SESSION_CONTRACT_VERSION
    )
    session_uid: CanonicalUuid7
    managed_well_uid: CanonicalUuid7
    revision: int = Field(default=0, ge=0)
    display_policy_revision: str | None = None
    state_status: Literal["empty", "active", "cleared"] = "empty"
    source: NonBlankString = "backend_owned_session_state"
    selected_track_uid: CanonicalUuid7 | None = None
    tracks: tuple[WdvCanonicalTrack, ...] = ()
    curve_fills: tuple[CanonicalCurveFillRule, ...] = ()
    warnings: tuple[str, ...] = ()
    updated_at: IsoDatetimeString

    @model_validator(mode="after")
    def validate_session_graph(self) -> "WdvCanonicalSession":
        track_uids = [item.track_uid for item in self.tracks]
        track_uid_set = set(track_uids)
        if len(track_uids) != len(track_uid_set):
            raise ValueError("Duplicate track_uid in WDV session")

        assignment_uids = [
            assignment.assignment_uid
            for track in self.tracks
            for assignment in track.assignments
        ]
        if len(assignment_uids) != len(set(assignment_uids)):
            raise ValueError("Duplicate assignment_uid in WDV session")

        if (
            self.selected_track_uid is not None
            and self.selected_track_uid not in track_uid_set
        ):
            raise ValueError(
                "selected_track_uid must reference a track in the WDV session"
            )

        track_by_uid = {item.track_uid: item for item in self.tracks}
        for target_track in self.tracks:
            if not target_track.depth_range_locator_enabled:
                continue
            source_uid = target_track.depth_range_locator_source_track_uid
            if source_uid is None:
                raise ValueError("Enabled Depth Range Locator requires a source track")
            if source_uid == target_track.track_uid:
                raise ValueError("Depth Range Locator source track cannot equal target track")
            source_track = track_by_uid.get(source_uid)
            if source_track is None:
                raise ValueError("Depth Range Locator source track must exist in the WDV session")
            if source_track.managed_well_uid != target_track.managed_well_uid:
                raise ValueError("Depth Range Locator source and target must belong to the same managed well")
            if target_track.depth_range_locator_mode is None:
                raise ValueError("Enabled Depth Range Locator requires a range mode")
            if target_track.depth_range_locator_presentation is None:
                raise ValueError("Enabled Depth Range Locator requires a presentation")
            if target_track.depth_range_locator_side is None:
                raise ValueError("Enabled Depth Range Locator requires a side")

        assignment_by_uid = {
            assignment.assignment_uid: assignment
            for track in self.tracks
            for assignment in track.assignments
        }
        fill_uids = [rule.rule_uid for rule in self.curve_fills]
        if len(fill_uids) != len(set(fill_uids)):
            raise ValueError("Duplicate rule_uid in WDV session")
        rules_by_track: dict[str, list[CanonicalCurveFillRule]] = {}
        for rule in self.curve_fills:
            track = next((item for item in self.tracks if item.track_uid == rule.track_uid), None)
            if track is None or track.track_type != "curve":
                raise ValueError("Curve Fill rule must reference a curve track in the session")
            assignment_a = assignment_by_uid.get(rule.curve_a_assignment_uid)
            if assignment_a is None or assignment_a.track_uid != rule.track_uid:
                raise ValueError("Curve Fill Curve A assignment must belong to the rule track")
            # A shared multi-well canvas is projected through whichever well is
            # currently active.  Session.managed_well_uid therefore identifies
            # the working registry, not ownership of every assignment on the
            # canvas.  Curve Fill ownership follows its referenced assignments.
            if rule.managed_well_uid != assignment_a.managed_well_uid:
                raise ValueError(
                    "Curve Fill rule managed well must match Curve A assignment"
                )
            if rule.curve_b_assignment_uid is not None:
                assignment_b = assignment_by_uid.get(rule.curve_b_assignment_uid)
                if assignment_b is None or assignment_b.track_uid != rule.track_uid:
                    raise ValueError("Curve Fill Curve B assignment must belong to the rule track")
                if assignment_b.managed_well_uid != rule.managed_well_uid:
                    raise ValueError(
                        "Curve Fill Curve B assignment must belong to the rule managed well"
                    )
            rules_by_track.setdefault(rule.track_uid, []).append(rule)
        for rules in rules_by_track.values():
            orders = sorted(rule.order for rule in rules)
            if orders != list(range(len(rules))):
                raise ValueError("Curve Fill rule order must be contiguous per track")

        if self.state_status == "active" and not self.tracks:
            raise ValueError("Active WDV sessions must contain at least one track")
        if self.state_status in {"empty", "cleared"}:
            if self.tracks:
                raise ValueError(
                    "Empty or cleared WDV sessions cannot contain tracks"
                )
            if self.selected_track_uid is not None:
                raise ValueError(
                    "Empty or cleared WDV sessions cannot select a track"
                )
            if self.curve_fills:
                raise ValueError("Empty or cleared WDV sessions cannot contain Curve Fill rules")
        return self


class WdvCurveSampleRequest(BaseModel):
    """Canonical WDV sample request addressed only by managed curve identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["wdv_curve_samples_v2_1"] = (
        WDV_SAMPLE_CONTRACT_VERSION
    )
    managed_well_uid: CanonicalUuid7
    managed_curve_uid: CanonicalUuid7
    sample_revision: str | None = None
    target_depth_unit: Literal["m", "ft"] | None = None
    max_samples: int = Field(default=12000, ge=2, le=100000)


class WdvCurveSampleProvenance(BaseModel):
    """Typed source evidence for a returned curve sample set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_source: NonBlankString
    source_path: str | None = None
    source_intake_candidate_id: str | None = None
    checksum: str | None = None
    generated_at: IsoDatetimeString | None = None


class WdvCurveSampleResponse(BaseModel):
    """Full renderer-ready sample response keyed by managed curve identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["wdv_curve_samples_v2_1"] = (
        WDV_SAMPLE_CONTRACT_VERSION
    )
    managed_well_uid: CanonicalUuid7
    managed_curve_uid: CanonicalUuid7
    managed_product_uid: CanonicalUuid7
    managed_source_uid: CanonicalUuid7

    sample_revision: str | None = None
    observed_mnemonic: NonBlankString
    normalized_mnemonic: str | None = None
    display_name: NonBlankString
    curve_family: str | None = None

    depth_unit: NonBlankString
    value_unit: str | None = None
    depth_min: FiniteNumber
    depth_max: FiniteNumber
    value_min: FiniteNumber
    value_max: FiniteNumber
    robust_value_min: FiniteNumber | None = None
    robust_value_max: FiniteNumber | None = None
    value_p01: FiniteNumber | None = None
    value_p05: FiniteNumber | None = None
    value_p50: FiniteNumber | None = None
    value_p95: FiniteNumber | None = None
    value_p99: FiniteNumber | None = None

    sample_count: int = Field(ge=0)
    returned_sample_count: int = Field(ge=0)
    raw_numeric_sample_count: int | None = Field(default=None, ge=0)
    rejected_sample_count: int = Field(default=0, ge=0)
    rejected_null_count: int = Field(default=0, ge=0)
    rejected_sentinel_count: int = Field(default=0, ge=0)
    rejected_nonfinite_count: int = Field(default=0, ge=0)
    rejected_plausibility_count: int = Field(default=0, ge=0)
    rejected_row_count: int = Field(default=0, ge=0)
    decimation_stride: int = Field(default=1, ge=1)

    provenance: WdvCurveSampleProvenance
    samples: tuple[tuple[FiniteNumber, FiniteNumber], ...] = ()

    @model_validator(mode="after")
    def validate_sample_payload(self) -> "WdvCurveSampleResponse":
        if self.depth_min > self.depth_max:
            raise ValueError("depth_min cannot exceed depth_max")
        if self.value_min > self.value_max:
            raise ValueError("value_min cannot exceed value_max")
        if (
            self.robust_value_min is not None
            and self.robust_value_max is not None
            and self.robust_value_min > self.robust_value_max
        ):
            raise ValueError(
                "robust_value_min cannot exceed robust_value_max"
            )

        if self.returned_sample_count != len(self.samples):
            raise ValueError(
                "returned_sample_count must equal the number of returned samples"
            )
        if self.returned_sample_count > self.sample_count:
            raise ValueError(
                "returned_sample_count cannot exceed sample_count"
            )
        if self.sample_count and not self.samples:
            raise ValueError(
                "A non-empty sample set must return at least one sample"
            )

        rejection_parts = (
            self.rejected_null_count
            + self.rejected_sentinel_count
            + self.rejected_nonfinite_count
            + self.rejected_plausibility_count
            + self.rejected_row_count
        )
        if self.rejected_sample_count != rejection_parts:
            raise ValueError(
                "rejected_sample_count must equal the sum of rejection categories"
            )

        if self.samples:
            returned_depths = [point[0] for point in self.samples]
            if min(returned_depths) < self.depth_min:
                raise ValueError("Returned sample depth is below depth_min")
            if max(returned_depths) > self.depth_max:
                raise ValueError("Returned sample depth is above depth_max")
        return self
