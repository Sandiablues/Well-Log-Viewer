"""Canonical backend-owned WDV workspace aggregate contract.

This is the single validated read boundary for one well's WDV state.  It
combines the managed curve registry and canonical session and rejects any
cross-well, unresolved, duplicated, or internally inconsistent graph before
it reaches a frontend consumer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

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
                curve = curve_by_uid.get(assignment.managed_curve_uid)
                if curve is None:
                    raise WdvWorkspaceInvariantError(
                        "Assignment references a curve absent from the workspace registry"
                    )
                if assignment.managed_well_uid != self.managed_well_uid:
                    raise WdvWorkspaceInvariantError(
                        "Assignment managed_well_uid must match workspace"
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
