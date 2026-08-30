"""Canonical backend-owned WDV workspace aggregate contract.

This is the single validated read boundary for one well's WDV state.  It
combines the managed curve registry and canonical session and rejects any
cross-well, unresolved, duplicated, or internally inconsistent graph before
it reaches a frontend consumer.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.identity.wdv_contract_v2 import CanonicalUuid7, NonBlankString, WdvCanonicalSession
from app.identity.wdv_viewer_package_v21 import (
    WdvCanonicalDepthRange,
    WdvCanonicalViewerCurve,
)

WDV_WORKSPACE_CONTRACT_VERSION = "wdv_workspace_v1"


class WdvWorkspaceInvariantError(ValueError):
    """Raised when a canonical workspace graph violates an invariant."""


class WdvCanonicalWorkspace(BaseModel):
    """One authoritative, fully resolved WDV workspace for one managed well."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["wdv_workspace_v1"] = WDV_WORKSPACE_CONTRACT_VERSION
    managed_well_uid: CanonicalUuid7
    managed_wellbore_uid: CanonicalUuid7 | None = None
    well_name: NonBlankString
    wellbore_name: str | None = None
    depth_range: WdvCanonicalDepthRange
    curve_registry: tuple[WdvCanonicalViewerCurve, ...] = ()
    session: WdvCanonicalSession
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_workspace_graph(self) -> "WdvCanonicalWorkspace":
        if self.session.managed_well_uid != self.managed_well_uid:
            raise WdvWorkspaceInvariantError(
                "Workspace session managed_well_uid must match workspace"
            )

        curve_by_uid: dict[str, WdvCanonicalViewerCurve] = {}
        product_uids: set[str] = set()
        for curve in self.curve_registry:
            if curve.managed_well_uid != self.managed_well_uid:
                raise WdvWorkspaceInvariantError(
                    "Every registry curve must belong to the workspace well"
                )
            if curve.managed_curve_uid in curve_by_uid:
                raise WdvWorkspaceInvariantError(
                    f"Duplicate managed_curve_uid: {curve.managed_curve_uid}"
                )
            if curve.managed_product_uid in product_uids:
                raise WdvWorkspaceInvariantError(
                    f"Duplicate managed_product_uid: {curve.managed_product_uid}"
                )
            curve_by_uid[curve.managed_curve_uid] = curve
            product_uids.add(curve.managed_product_uid)

        track_uids = {track.track_uid for track in self.session.tracks}
        for track in self.session.tracks:
            stack_indices = [item.stack_index for item in track.assignments]
            if stack_indices != list(range(len(stack_indices))):
                raise WdvWorkspaceInvariantError(
                    f"Track {track.track_uid} assignment stack_index values must be contiguous"
                )

            for assignment in track.assignments:
                if assignment.track_uid not in track_uids:
                    raise WdvWorkspaceInvariantError(
                        "Assignment references a track absent from the workspace"
                    )
                # curve_registry is intentionally scoped to the current working
                # well. The shared canonical session may also contain tracks
                # owned by other wells; those assignments are validated against
                # their own registry when that well is selected.
                if assignment.managed_well_uid != self.managed_well_uid:
                    continue
                curve = curve_by_uid.get(assignment.managed_curve_uid)
                if curve is None:
                    raise WdvWorkspaceInvariantError(
                        "Assignment references a curve absent from the workspace registry"
                    )
                if assignment.managed_product_uid != curve.managed_product_uid:
                    raise WdvWorkspaceInvariantError(
                        "Assignment managed_product_uid must match registry curve"
                    )
                if assignment.managed_source_uid != curve.managed_source_uid:
                    raise WdvWorkspaceInvariantError(
                        "Assignment managed_source_uid must match registry curve"
                    )
                if assignment.managed_wellbore_uid != curve.managed_wellbore_uid:
                    raise WdvWorkspaceInvariantError(
                        "Assignment managed_wellbore_uid must match registry curve"
                    )
                if (
                    assignment.paired_managed_curve_uid is not None
                    and assignment.paired_managed_curve_uid not in curve_by_uid
                ):
                    raise WdvWorkspaceInvariantError(
                        "Paired curve reference is absent from the workspace registry"
                    )

        return self


class WdvSavedDepthViewport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min: float
    max: float

    @model_validator(mode="after")
    def validate_range(self) -> "WdvSavedDepthViewport":
        if self.min >= self.max:
            raise ValueError("Saved viewport min must be less than max")
        return self




class WdvSavedViewportTieGroup(BaseModel):
    """Backend-validated committed viewport Tie relationship."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: NonBlankString
    leader_track_uid: CanonicalUuid7
    member_track_uids: tuple[CanonicalUuid7, ...]
    viewport: WdvSavedDepthViewport

    @field_validator("member_track_uids")
    @classmethod
    def validate_members(cls, members: tuple[CanonicalUuid7, ...]) -> tuple[CanonicalUuid7, ...]:
        if len(members) < 2:
            raise ValueError("Viewport Tie must contain at least two tracks")
        if len(set(members)) != len(members):
            raise ValueError("Viewport Tie members must be unique")
        return members

    @model_validator(mode="after")
    def validate_leader(self) -> "WdvSavedViewportTieGroup":
        if self.leader_track_uid not in self.member_track_uids:
            raise ValueError("Viewport Tie leader must be a Tie member")
        return self


class WdvSavedViewState(BaseModel):
    """Frontend-owned view/group state paired with a canonical session snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    depth_unit: Literal["m", "ft"] = "m"
    global_viewport: WdvSavedDepthViewport
    group_viewport: WdvSavedDepthViewport | None = None
    active_track_uids: tuple[CanonicalUuid7, ...] = ()
    highlighted_track_uids: tuple[CanonicalUuid7, ...] = ()
    locked_track_uids: tuple[CanonicalUuid7, ...] = ()
    locked_viewports_by_track_uid: dict[str, WdvSavedDepthViewport] = {}
    # Committed per-track viewport state is durable independently of Lock.
    # This prevents unlock/restart from reconstructing a track from a global
    # viewport merely because the track is not currently locked.
    track_viewports_by_track_uid: dict[str, WdvSavedDepthViewport] = {}
    viewport_tie_groups: tuple[WdvSavedViewportTieGroup, ...] = ()
    viewport_tie_suspended_track_uids: tuple[CanonicalUuid7, ...] = ()
    presentation_state: dict[str, Any] = {}


class WdvSaveWorkspaceSnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_revision: int
    view_state: WdvSavedViewState




class WdvPersistCommittedViewRequest(BaseModel):
    """Persist an exact already-committed view into Save or Recovery."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_revision: int
    expected_view_revision: int

class WdvRestoreWorkspaceSnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_revision: int

class WdvCommitViewStateRequest(BaseModel):
    """Revision-guarded durable commit of viewport/relationship state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_session_revision: int
    expected_view_revision: int
    view_state: WdvSavedViewState

