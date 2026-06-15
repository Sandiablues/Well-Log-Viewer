"""
Tests — Well QAQC Service
WL-BUILD-001 scaffold

These tests validate:
- Module importability
- QaqcCode enum existence and initial codes
- Service class and interface shape
- That run_qaqc returns a list (empty in scaffold state)
- That QAQC ownership is backend-side only
"""

import pytest

from app.wells.models import (
    DepthRange,
    DepthUnit,
    DisplayDomain,
    QaqcFinding,
    QaqcSeverity,
    WellMultitrackV1,
)
from app.wells.well_qaqc_service import QaqcCode, WellQaqcService


def _minimal_package() -> WellMultitrackV1:
    return WellMultitrackV1(
        dataset_id="ds-001",
        representation_id="rep-001",
        well_id="well-001",
        wellbore_id="wb-001",
        display_domain=DisplayDomain.MD,
        depth_unit=DepthUnit.METERS,
        depth_range=DepthRange(min=0.0, max=1000.0),
    )


class TestWellQaqcServiceScaffold:

    def test_module_importable(self):
        from app.wells import well_qaqc_service  # noqa: F401

    def test_service_class_exists(self):
        svc = WellQaqcService()
        assert svc is not None

    def test_qaqc_code_enum_has_initial_codes(self):
        """Initial finding codes must be defined."""
        assert QaqcCode.CURVE_ALL_NULL
        assert QaqcCode.CURVE_EXCESSIVE_NULL
        assert QaqcCode.WELL_MISSING_DEPTH_CURVE
        assert QaqcCode.LAS_NULL_VALUE_NOT_SET

    def test_run_qaqc_returns_list(self):
        svc = WellQaqcService()
        pkg = _minimal_package()
        findings = svc.run_qaqc(pkg)
        assert isinstance(findings, list)

    def test_run_qaqc_scaffold_returns_empty(self):
        """WL-BUILD-001: QAQC rules not yet implemented; empty list expected."""
        svc = WellQaqcService()
        pkg = _minimal_package()
        findings = svc.run_qaqc(pkg)
        assert findings == []

    def test_attach_findings_returns_package(self):
        svc = WellQaqcService()
        pkg = _minimal_package()
        finding = QaqcFinding(
            finding_id="f-001",
            severity=QaqcSeverity.WARNING,
            code=QaqcCode.CURVE_ALL_NULL,
            object_type="curve",
            object_id="curve-001",
            message="All samples are null.",
        )
        updated = svc.attach_findings_to_package(pkg, [finding])
        assert len(updated.qaqc_findings) == 1
        assert updated.qaqc_findings[0].code == QaqcCode.CURVE_ALL_NULL

    def test_qaqc_finding_model_matches_contract(self):
        """QaqcFinding fields must match the well_multitrack_v1 contract shape."""
        f = QaqcFinding(
            finding_id="f-002",
            severity=QaqcSeverity.ERROR,
            code="CURVE_DEPTH_RANGE_MISMATCH",
            object_type="curve",
            object_id="curve-002",
            message="Depth range mismatch.",
        )
        assert f.severity == QaqcSeverity.ERROR
        assert f.finding_id == "f-002"

    def test_get_findings_for_representation_raises_not_implemented(self):
        """
        get_findings_for_representation() must raise NotImplementedError.
        This is the route-facing delegation point for the QAQC endpoint.
        The endpoint calls this method; the route converts NotImplementedError
        to HTTP 501 — no business logic lives in the route.
        """
        svc = WellQaqcService()
        with pytest.raises(NotImplementedError):
            svc.get_findings_for_representation("ds-001", "rep-001")
