"""
MultiViewer Well Log Viewer — Well Viewer Package Service
WL-BUILD-001 scaffold

This service generates the well_multitrack_v1 viewer package from
backend-owned MSI representations.

The viewer package is the canonical contract the frontend fetches and renders.
Equinor ViDEx props must not become this contract.
"""

from __future__ import annotations

from .models import (
    DepthRange,
    DepthUnit,
    DisplayDomain,
    MsiRepresentationRef,
    WellMultitrackV1,
)


class ViewerPackageGenerationError(Exception):
    """Raised when viewer package generation fails."""


class WellViewerPackageService:
    """
    Backend-owned service responsible for:
    - Assembling a well_multitrack_v1 viewer package
    - Sourcing all data from MSI-registered representations
    - Exposing the package for frontend consumption

    The frontend must fetch the result of this service via the API.
    The frontend must not construct or duplicate this package shape independently.

    WL-BUILD-001: skeleton only.
    Full assembly logic (tracks, curves, samples URLs) deferred to later sprint.
    """

    def generate(
        self,
        dataset_id: str,
        representation_ref: MsiRepresentationRef,
        well_id: str,
        wellbore_id: str,
        depth_unit: DepthUnit = DepthUnit.METERS,
        display_domain: DisplayDomain = DisplayDomain.MD,
        depth_range: DepthRange | None = None,
    ) -> WellMultitrackV1:
        """
        Generate a well_multitrack_v1 viewer package.

        Args:
            dataset_id: MSI dataset identifier.
            representation_ref: MSI representation being rendered.
            well_id: Well identifier.
            wellbore_id: Wellbore identifier.
            depth_unit: Depth unit (m or ft), sourced from LAS header.
            display_domain: Depth domain for display (MD, TVD, TVDSS).
            depth_range: Depth range; if None a default empty range is used.

        Returns:
            WellMultitrackV1 viewer package ready for MSI registration
            and frontend consumption.

        WL-BUILD-001: returns a minimal placeholder package.
        Track and curve population deferred to later sprint.
        """
        if depth_range is None:
            depth_range = DepthRange()

        return WellMultitrackV1(
            viewer_package_version="well_multitrack_v1",
            dataset_id=dataset_id,
            representation_id=representation_ref.representation_id,
            well_id=well_id,
            wellbore_id=wellbore_id,
            display_domain=display_domain,
            depth_unit=depth_unit,
            depth_range=depth_range,
            tracks=[],          # populated in WL-BUILD-002+
            qaqc_findings=[],   # populated by WellQaqcService
        )

    def generate_for_representation(
        self,
        dataset_id: str,
        representation_id: str,
    ) -> WellMultitrackV1:
        """
        Route-facing delegation point: generate a well_multitrack_v1 viewer
        package given only the MSI dataset and representation identifiers.

        In a wired implementation this method will:
          1. Resolve well_id, wellbore_id, depth_unit, and depth_range from
             the MSI representation record.
          2. Call self.generate() with the resolved parameters.

        The API route calls this method rather than generate() directly,
        because the route only holds dataset_id and representation_id from
        the request path. The service is responsible for resolving the rest
        from the MSI-registered representation.

        WL-BUILD-001: not yet implemented — raises NotImplementedError.
        Full wiring deferred to the LAS import and package assembly sprint.
        """
        raise NotImplementedError(
            f"Viewer package generation not yet implemented for "
            f"dataset_id={dataset_id!r}, representation_id={representation_id!r}. "
            "Wire MSI representation resolution and generate() call in a later sprint."
        )
