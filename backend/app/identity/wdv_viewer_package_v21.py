"""Canonical WDV viewer-package contract v2.1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.identity.wdv_contract_v2 import (
    CanonicalUuid7,
    FiniteNumber,
    NonBlankString,
    WdvCanonicalCurveReference,
    WdvCanonicalSession,
)

WDV_VIEWER_PACKAGE_CONTRACT_VERSION = "wdv_viewer_package_v2_1"


class WdvCanonicalDepthRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum: FiniteNumber | None = None
    maximum: FiniteNumber | None = None
    unit: NonBlankString

    @model_validator(mode="after")
    def validate_range(self) -> "WdvCanonicalDepthRange":
        if (self.minimum is None) != (self.maximum is None):
            raise ValueError("Depth minimum and maximum must be supplied together")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("Depth minimum cannot exceed maximum")
        return self




class WdvCanonicalCurveDisplayPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    curve_class: NonBlankString
    lattice: Literal["linear", "logarithmic"]
    scale_type: Literal["linear", "log"]
    display_min: FiniteNumber
    display_max: FiniteNumber
    scale_direction: Literal["normal", "reversed"]
    default_color: NonBlankString
    source: NonBlankString
    warnings: tuple[str, ...] = ()


class WdvCanonicalViewerCurve(WdvCanonicalCurveReference):
    display_policy: WdvCanonicalCurveDisplayPolicy

class WdvCanonicalViewerPackage(BaseModel):
    """Backend-owned package consumed by the canonical WDV frontend."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["wdv_viewer_package_v2_1"] = (
        WDV_VIEWER_PACKAGE_CONTRACT_VERSION
    )
    managed_well_uid: CanonicalUuid7
    managed_wellbore_uid: CanonicalUuid7 | None = None
    well_name: NonBlankString
    wellbore_name: str | None = None
    depth_range: WdvCanonicalDepthRange
    curves: tuple[WdvCanonicalViewerCurve, ...] = ()
    session: WdvCanonicalSession
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_package_graph(self) -> "WdvCanonicalViewerPackage":
        if self.session.managed_well_uid != self.managed_well_uid:
            raise ValueError(
                "Viewer package session managed_well_uid must match package"
            )

        curve_uids: set[str] = set()
        product_uids: set[str] = set()
        source_uids: set[str] = set()

        for curve in self.curves:
            if curve.managed_well_uid != self.managed_well_uid:
                raise ValueError(
                    "Every curve must reference the package managed_well_uid"
                )
            if curve.managed_curve_uid in curve_uids:
                raise ValueError(
                    f"Duplicate managed_curve_uid: {curve.managed_curve_uid}"
                )
            if curve.managed_product_uid in product_uids:
                raise ValueError(
                    f"Duplicate managed_product_uid: {curve.managed_product_uid}"
                )
            curve_uids.add(curve.managed_curve_uid)
            product_uids.add(curve.managed_product_uid)
            source_uids.add(curve.managed_source_uid)

        for track in self.session.tracks:
            for assignment in track.assignments:
                if assignment.managed_curve_uid not in curve_uids:
                    raise ValueError(
                        "Session assignment references a curve absent from package"
                    )
                if assignment.managed_product_uid not in product_uids:
                    raise ValueError(
                        "Session assignment references a product absent from package"
                    )
                if assignment.managed_source_uid not in source_uids:
                    raise ValueError(
                        "Session assignment references a source absent from package"
                    )
        return self
