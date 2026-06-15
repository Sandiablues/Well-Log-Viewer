"""
Tests — MSI Well Adapter
WL-BUILD-001 scaffold

These tests validate:
- Module importability
- Adapter class and interface shape
- That all methods raise NotImplementedError in scaffold state
- That MSI lifecycle state enum is present
- That the adapter is the declared boundary for MSI operations
"""

import pytest

from app.wells.models import (
    MsiDatasetRef,
    MsiRepresentationRef,
    MsiSourceRef,
    Well,
    WellMultitrackV1,
    DepthRange,
    DepthUnit,
    DisplayDomain,
)
from app.wells.msi_well_adapter import (
    MsiLifecycleState,
    MsiWellAdapter,
    MsiWellRegistrationResult,
)


def _minimal_well() -> Well:
    return Well(
        well_id="well-001",
        well_name="Test Well 1",
        dataset_ref=MsiDatasetRef(dataset_id="ds-001"),
        source_ref=MsiSourceRef(source_id="src-001"),
    )


def _minimal_package() -> WellMultitrackV1:
    return WellMultitrackV1(
        dataset_id="ds-001",
        representation_id="rep-001",
        well_id="well-001",
        wellbore_id="wb-001",
        display_domain=DisplayDomain.MD,
        depth_unit=DepthUnit.METERS,
        depth_range=DepthRange(),
    )


class TestMsiWellAdapterScaffold:

    def test_module_importable(self):
        from app.wells import msi_well_adapter  # noqa: F401

    def test_adapter_class_exists(self):
        adapter = MsiWellAdapter()
        assert adapter is not None

    def test_lifecycle_state_enum_exists(self):
        assert MsiLifecycleState.PENDING
        assert MsiLifecycleState.AVAILABLE
        assert MsiLifecycleState.FAILED
        assert MsiLifecycleState.DELETED

    def test_register_well_import_raises_not_implemented(self):
        adapter = MsiWellAdapter()
        well = _minimal_well()
        with pytest.raises(NotImplementedError):
            adapter.register_well_import(well, "test.las")

    def test_register_viewer_package_raises_not_implemented(self):
        adapter = MsiWellAdapter()
        # Build a stub registration result for the call
        reg = MsiWellRegistrationResult(
            dataset_ref=MsiDatasetRef(dataset_id="ds-001"),
            source_ref=MsiSourceRef(source_id="src-001"),
            representation_ref=MsiRepresentationRef(representation_id="rep-001"),
            lifecycle_state=MsiLifecycleState.PENDING,
        )
        pkg = _minimal_package()
        with pytest.raises(NotImplementedError):
            adapter.register_viewer_package(reg, pkg)

    def test_get_viewer_availability_raises_not_implemented(self):
        adapter = MsiWellAdapter()
        with pytest.raises(NotImplementedError):
            adapter.get_viewer_availability("ds-001", "rep-001")

    def test_delete_well_raises_not_implemented(self):
        adapter = MsiWellAdapter()
        with pytest.raises(NotImplementedError):
            adapter.delete_well("ds-001")

    def test_list_wells_raises_not_implemented(self):
        """
        list_wells() must raise NotImplementedError in scaffold state.
        The route calls this method; the route must not raise 501 directly.
        """
        adapter = MsiWellAdapter()
        with pytest.raises(NotImplementedError):
            adapter.list_wells()

    def test_registration_result_holds_msi_refs(self):
        reg = MsiWellRegistrationResult(
            dataset_ref=MsiDatasetRef(dataset_id="ds-999"),
            source_ref=MsiSourceRef(source_id="src-999"),
            representation_ref=MsiRepresentationRef(representation_id="rep-999"),
            lifecycle_state=MsiLifecycleState.AVAILABLE,
        )
        assert reg.dataset_ref.dataset_id == "ds-999"
        assert reg.source_ref.source_id == "src-999"
        assert reg.representation_ref.representation_id == "rep-999"
        assert reg.lifecycle_state == MsiLifecycleState.AVAILABLE
