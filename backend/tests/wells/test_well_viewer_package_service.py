"""
Tests — Well Viewer Package Service
WL-BUILD-001 scaffold

These tests validate:
- Module importability
- Service class and interface shape
- That generate() returns a WellMultitrackV1 with correct version string
- That the contract shape matches well_multitrack_v1
- That the package is not ViDEx-shaped
"""

import pytest

from app.wells.models import (
    DepthRange,
    DepthUnit,
    DisplayDomain,
    MsiRepresentationRef,
    WellMultitrackV1,
)
from app.wells.well_viewer_package_service import WellViewerPackageService


class TestWellViewerPackageServiceScaffold:

    def test_module_importable(self):
        from app.wells import well_viewer_package_service  # noqa: F401

    def test_service_class_exists(self):
        svc = WellViewerPackageService()
        assert svc is not None

    def test_generate_returns_well_multitrack_v1(self):
        svc = WellViewerPackageService()
        rep_ref = MsiRepresentationRef(representation_id="rep-001")
        pkg = svc.generate(
            dataset_id="ds-001",
            representation_ref=rep_ref,
            well_id="well-001",
            wellbore_id="wb-001",
        )
        assert isinstance(pkg, WellMultitrackV1)

    def test_package_version_string_is_canonical(self):
        """viewer_package_version must be 'well_multitrack_v1'."""
        svc = WellViewerPackageService()
        rep_ref = MsiRepresentationRef(representation_id="rep-001")
        pkg = svc.generate(
            dataset_id="ds-001",
            representation_ref=rep_ref,
            well_id="well-001",
            wellbore_id="wb-001",
        )
        assert pkg.viewer_package_version == "well_multitrack_v1"

    def test_package_preserves_msi_ids(self):
        svc = WellViewerPackageService()
        rep_ref = MsiRepresentationRef(representation_id="rep-abc")
        pkg = svc.generate(
            dataset_id="ds-xyz",
            representation_ref=rep_ref,
            well_id="well-xyz",
            wellbore_id="wb-xyz",
        )
        assert pkg.dataset_id == "ds-xyz"
        assert pkg.representation_id == "rep-abc"
        assert pkg.well_id == "well-xyz"
        assert pkg.wellbore_id == "wb-xyz"

    def test_scaffold_package_has_empty_tracks(self):
        """WL-BUILD-001: tracks are empty; population deferred to later sprint."""
        svc = WellViewerPackageService()
        rep_ref = MsiRepresentationRef(representation_id="rep-001")
        pkg = svc.generate(
            dataset_id="ds-001",
            representation_ref=rep_ref,
            well_id="well-001",
            wellbore_id="wb-001",
        )
        assert pkg.tracks == []

    def test_package_depth_unit_default(self):
        svc = WellViewerPackageService()
        rep_ref = MsiRepresentationRef(representation_id="rep-001")
        pkg = svc.generate(
            dataset_id="ds-001",
            representation_ref=rep_ref,
            well_id="well-001",
            wellbore_id="wb-001",
        )
        assert pkg.depth_unit == DepthUnit.METERS

    def test_package_accepts_depth_range(self):
        svc = WellViewerPackageService()
        rep_ref = MsiRepresentationRef(representation_id="rep-001")
        dr = DepthRange(min=100.0, max=4500.0)
        pkg = svc.generate(
            dataset_id="ds-001",
            representation_ref=rep_ref,
            well_id="well-001",
            wellbore_id="wb-001",
            depth_range=dr,
        )
        assert pkg.depth_range.min == 100.0
        assert pkg.depth_range.max == 4500.0

    def test_package_has_no_videx_fields(self):
        """
        The viewer package must not contain ViDEx-internal field names.
        ViDEx translation is the adapter's responsibility.
        """
        svc = WellViewerPackageService()
        rep_ref = MsiRepresentationRef(representation_id="rep-001")
        pkg = svc.generate(
            dataset_id="ds-001",
            representation_ref=rep_ref,
            well_id="well-001",
            wellbore_id="wb-001",
        )
        pkg_dict = pkg.model_dump()
        videx_internal_keys = {"logData", "plotOptions", "wellpickSets", "primaryAxis"}
        overlap = set(pkg_dict.keys()) & videx_internal_keys
        assert overlap == set(), (
            f"Viewer package contains ViDEx-internal keys: {overlap}. "
            "ViDEx translation belongs in the frontend adapter only."
        )

    def test_generate_for_representation_raises_not_implemented(self):
        """
        generate_for_representation() must raise NotImplementedError.
        This is the route-facing delegation point for the viewer package endpoint.
        The route calls this method with only dataset_id and representation_id
        (the parameters available in the request path); the service is responsible
        for resolving well_id, wellbore_id, and depth metadata from MSI.
        The route converts NotImplementedError to HTTP 501.
        """
        svc = WellViewerPackageService()
        with pytest.raises(NotImplementedError):
            svc.generate_for_representation("ds-001", "rep-001")
