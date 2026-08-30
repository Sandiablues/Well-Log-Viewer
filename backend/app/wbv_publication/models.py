"""Durable backend contracts for publishing WDV content to WBV.

A publication is an independently persisted WBV package.  It retains the exact
canonical WDV session revision that was published and separates that immutable
snapshot from WBV-only presentation overrides.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.identity.wdv_contract_v2 import CanonicalUuid7, IsoDatetimeString, WdvCanonicalSession
from app.wbv.models import WbvCurveOverlayRenderContract

WBV_OVERLAY_PACKAGE_CONTRACT_VERSION = "wbv_overlay_package_v1"


class WbvTrackPresentationOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    track_uid: CanonicalUuid7
    destination_track_uid: CanonicalUuid7 | None = None
    visible: bool = True
    geometry_type: Literal["camera_ribbon", "radial_panel"] = "radial_panel"
    radial_lane: int | None = Field(default=None, ge=0)
    radial_offset: float | None = Field(default=None, ge=0.0)
    angular_position_deg: float | None = Field(default=None, ge=-360.0, le=360.0)
    radial_width: float | None = Field(default=None, gt=0)
    thickness: float | None = Field(default=None, gt=0)
    orientation_mode: Literal["follow_trajectory", "camera_facing"] = "follow_trajectory"
    opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    label_visible: bool | None = None


class WbvCurvePresentationOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assignment_uid: CanonicalUuid7
    visible: bool | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    line_width: float | None = Field(default=None, gt=0)
    radial_exaggeration: float | None = Field(default=None, ge=0.25, le=3.0)
    label_visible: bool | None = None
    label_content: Literal["mnemonic", "mnemonic_value", "scale", "mnemonic_scale"] | None = None
    label_anchor: Literal["top", "base", "custom_md"] | None = None
    label_custom_md: float | None = None
    label_size: float | None = Field(default=None, ge=0.5, le=2.5)
    label_weight: int | None = Field(default=None, ge=400, le=900, multiple_of=100)
    label_alignment: Literal["left", "center", "right"] | None = None
    label_position: Literal["on_track", "left", "right", "center"] | None = None
    label_horizontal_adjustment: float | None = Field(default=None, ge=-4.0, le=4.0)
    label_vertical_adjustment: float | None = Field(default=None, ge=-4.0, le=4.0)
    scale_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    scale_opacity: float | None = Field(default=None, ge=0.0, le=1.0)  # deprecated compatibility field
    scale_line_width: float | None = Field(default=None, ge=0.5, le=4.0)
    scale_size: float | None = Field(default=None, ge=0.5, le=2.0)


class WbvPresentationOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_visible: bool = True
    track_spacing: float | None = Field(default=None, gt=0)
    depth_clip_min: float | None = None
    depth_clip_max: float | None = None
    tracks: tuple[WbvTrackPresentationOverride, ...] = ()
    curves: tuple[WbvCurvePresentationOverride, ...] = ()

    @model_validator(mode="after")
    def validate_graph(self) -> "WbvPresentationOverrides":
        if self.depth_clip_min is not None and self.depth_clip_max is not None:
            if self.depth_clip_min >= self.depth_clip_max:
                raise ValueError("depth_clip_min must be less than depth_clip_max")
        if len({item.track_uid for item in self.tracks}) != len(self.tracks):
            raise ValueError("Duplicate WBV track presentation override")
        if len({item.assignment_uid for item in self.curves}) != len(self.curves):
            raise ValueError("Duplicate WBV curve presentation override")
        return self



class WbvPresentationOverridesUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_package_revision: int = Field(ge=1)
    overrides: WbvPresentationOverrides

class WbvPublicationProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    published_at: IsoDatetimeString
    published_by: str = Field(min_length=1)
    publication_command_uid: CanonicalUuid7
    source_session_uid: CanonicalUuid7
    source_revision: int = Field(ge=0)
    operation: Literal["publish_new", "update_existing"] = "publish_new"


class WbvOverlayPackageRevisionSnapshot(BaseModel):
    """Recoverable package state captured immediately before an explicit update."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    package_revision: int = Field(ge=1)
    source_wdv_session_uid: CanonicalUuid7
    source_wdv_revision: int = Field(ge=0)
    published_snapshot: WdvCanonicalSession
    source_wdv_view_revision: int | None = Field(default=None, ge=0)
    published_view_state: dict[str, Any] = Field(default_factory=dict)
    wbv_overrides: WbvPresentationOverrides
    provenance: WbvPublicationProvenance
    saved_at: IsoDatetimeString


class WbvOverlayPackage(BaseModel):
    """One independently retained WBV overlay package."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["wbv_overlay_package_v1"] = WBV_OVERLAY_PACKAGE_CONTRACT_VERSION
    package_uid: CanonicalUuid7
    managed_well_uid: CanonicalUuid7
    package_name: str = Field(min_length=1)
    package_revision: int = Field(default=1, ge=1)
    status: Literal["active", "inactive", "archived"] = "inactive"
    source_wdv_session_uid: CanonicalUuid7
    source_wdv_revision: int = Field(ge=0)
    published_snapshot: WdvCanonicalSession
    source_wdv_view_revision: int | None = Field(default=None, ge=0)
    published_view_state: dict[str, Any] = Field(default_factory=dict)
    wbv_overrides: WbvPresentationOverrides = WbvPresentationOverrides()
    provenance: WbvPublicationProvenance
    revision_history: tuple[WbvOverlayPackageRevisionSnapshot, ...] = ()
    created_at: IsoDatetimeString
    updated_at: IsoDatetimeString

    @model_validator(mode="after")
    def validate_package(self) -> "WbvOverlayPackage":
        snapshot = self.published_snapshot
        if snapshot.managed_well_uid != self.managed_well_uid:
            raise ValueError("Published WDV snapshot belongs to a different managed well")
        if snapshot.session_uid != self.source_wdv_session_uid:
            raise ValueError("source_wdv_session_uid must match the published snapshot")
        if snapshot.revision != self.source_wdv_revision:
            raise ValueError("source_wdv_revision must match the published snapshot")
        if self.provenance.source_session_uid != self.source_wdv_session_uid:
            raise ValueError("Publication provenance source session mismatch")
        if self.provenance.source_revision != self.source_wdv_revision:
            raise ValueError("Publication provenance source revision mismatch")

        track_uids = {track.track_uid for track in snapshot.tracks}
        assignment_uids = {
            assignment.assignment_uid
            for track in snapshot.tracks
            for assignment in track.assignments
        }
        unknown_tracks = [item.track_uid for item in self.wbv_overrides.tracks if item.track_uid not in track_uids]
        if unknown_tracks:
            raise ValueError("WBV track overrides must reference tracks in the published snapshot")
        unknown_curves = [item.assignment_uid for item in self.wbv_overrides.curves if item.assignment_uid not in assignment_uids]
        if unknown_curves:
            raise ValueError("WBV curve overrides must reference assignments in the published snapshot")
        return self


class WbvPublishedTrackPresentationContract(BaseModel):
    """Renderer-neutral WDV presentation snapshot retained by one WBV publication."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["wbv_published_track_presentation_v1"] = "wbv_published_track_presentation_v1"
    managed_well_uid: CanonicalUuid7
    package_uid: CanonicalUuid7
    package_revision: int = Field(ge=1)
    source_wdv_session_uid: CanonicalUuid7
    source_wdv_revision: int = Field(ge=0)
    source_wdv_view_revision: int | None = Field(default=None, ge=0)
    presentation_state: dict[str, Any] = Field(default_factory=dict)
    selected_formation_top_ids: tuple[str, ...] = ()
    selected_lithology_interval_ids: tuple[str, ...] = ()
    formation_top_overlay_styles_by_track_id: dict[str, Any] = Field(default_factory=dict)
    track_order_uids: tuple[str, ...] = ()
    track_widths_by_uid: dict[str, float] = Field(default_factory=dict)
    curve_render_package: WbvCurveOverlayRenderContract


class WbvPublishPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_name: str = Field(min_length=1)
    published_by: str = Field(default="local_user", min_length=1)


class WbvPublishPreview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    managed_well_uid: CanonicalUuid7
    source_session_uid: CanonicalUuid7
    source_revision: int
    track_count: int
    assignment_count: int
    fill_rule_count: int
    warnings: tuple[str, ...] = ()
    publishable: bool


class WbvPublishAsNewRequest(WbvPublishPreviewRequest):
    command_uid: CanonicalUuid7
    activate: bool = False


class WbvUpdateExistingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_uid: CanonicalUuid7
    expected_package_revision: int = Field(ge=1)
    published_by: str = Field(default="local_user", min_length=1)
    activate: bool = True


class WbvPackageChangeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_revision_from: int = Field(ge=0)
    source_revision_to: int = Field(ge=0)
    tracks_added: tuple[CanonicalUuid7, ...] = ()
    tracks_removed: tuple[CanonicalUuid7, ...] = ()
    tracks_changed: tuple[CanonicalUuid7, ...] = ()
    assignments_added: tuple[CanonicalUuid7, ...] = ()
    assignments_removed: tuple[CanonicalUuid7, ...] = ()
    assignments_changed: tuple[CanonicalUuid7, ...] = ()
    fills_added: tuple[str, ...] = ()
    fills_removed: tuple[str, ...] = ()
    fills_changed: tuple[str, ...] = ()
    retained_track_override_count: int = Field(ge=0)
    dropped_track_override_count: int = Field(ge=0)
    retained_curve_override_count: int = Field(ge=0)
    dropped_curve_override_count: int = Field(ge=0)


class WbvUpdatePreview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    managed_well_uid: CanonicalUuid7
    package_uid: CanonicalUuid7
    package_revision: int = Field(ge=1)
    source_session_uid: CanonicalUuid7
    source_revision: int = Field(ge=0)
    update_available: bool
    publishable: bool
    warnings: tuple[str, ...] = ()
    changes: WbvPackageChangeSummary


class WbvUpdateExistingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package: WbvOverlayPackage
    changes: WbvPackageChangeSummary


class WbvPackageLifecycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_package_revision: int = Field(ge=1)
    action: Literal["archive", "restore"]


class WbvOverlayPackageList(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    managed_well_uid: CanonicalUuid7
    packages: tuple[WbvOverlayPackage, ...] = ()
