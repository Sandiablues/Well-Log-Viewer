"""
MultiViewer Well Log Viewer — MSI Well Adapter
WL-BUILD-001 scaffold

This adapter is the boundary between well-domain services and the
MSI / Managed Source Inventory.

MSI is the authority for:
- Dataset identity
- Source file identity
- Artifact identity
- Representation identity
- Lifecycle state (pending, available, failed, deleted)
- Viewer availability
- Delete/unload semantics
- Source-to-derived relationships

This adapter delegates all MSI registration and lifecycle operations to the
MSI backend. Well-domain services must not bypass it.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from .models import (
    MsiDatasetRef,
    MsiRepresentationRef,
    MsiSourceRef,
    Well,
    WellMultitrackV1,
)


# ---------------------------------------------------------------------------
# MSI lifecycle states — mirrored from the MSI contract for well domain use.
# The MSI backend owns the source of truth; this enum is for local typing only.
# ---------------------------------------------------------------------------


class MsiLifecycleState(str, Enum):
    PENDING = "pending"
    AVAILABLE = "available"
    FAILED = "failed"
    DELETED = "deleted"


class MsiWellRegistrationResult:
    """
    Value object returned after MSI registration of a well import.
    Contains the MSI-assigned references for downstream use.
    """

    def __init__(
        self,
        dataset_ref: MsiDatasetRef,
        source_ref: MsiSourceRef,
        representation_ref: MsiRepresentationRef,
        lifecycle_state: MsiLifecycleState,
    ) -> None:
        self.dataset_ref = dataset_ref
        self.source_ref = source_ref
        self.representation_ref = representation_ref
        self.lifecycle_state = lifecycle_state


class MsiWellAdapter:
    """
    Adapter between well-domain services and the MSI backend.

    Responsibilities:
    - Register a new well dataset with MSI after LAS import
    - Register the viewer package artifact with MSI
    - Query viewer availability from MSI
    - Delegate delete/unload to MSI (frontend must not own this)
    - Surface MSI lifecycle state to the API layer

    WL-BUILD-001: skeleton only.
    MSI client integration deferred to later sprint.
    """

    def register_well_import(
        self,
        well: Well,
        source_filename: str,
    ) -> MsiWellRegistrationResult:
        """
        Register a newly imported well with MSI.

        Creates dataset, source, and initial representation records.
        Returns MSI-assigned references for use by downstream services.

        WL-BUILD-001: not yet implemented — raises NotImplementedError.
        """
        raise NotImplementedError(
            "MSI well registration not yet implemented. "
            "Wire MSI client in a later sprint."
        )

    def register_viewer_package(
        self,
        registration: MsiWellRegistrationResult,
        viewer_package: WellMultitrackV1,
    ) -> None:
        """
        Register a generated well_multitrack_v1 viewer package as an
        MSI artifact attached to the given representation.

        WL-BUILD-001: not yet implemented — raises NotImplementedError.
        """
        raise NotImplementedError(
            "MSI viewer package registration not yet implemented."
        )

    def get_viewer_availability(
        self,
        dataset_id: str,
        representation_id: str,
    ) -> MsiLifecycleState:
        """
        Query MSI for the current lifecycle state / viewer availability
        of a well representation.

        Frontend must call this via the API layer; it must not hold its own
        lifecycle state.

        WL-BUILD-001: not yet implemented — raises NotImplementedError.
        """
        raise NotImplementedError(
            "MSI viewer availability query not yet implemented."
        )

    def delete_well(
        self,
        dataset_id: str,
        representation_id: Optional[str] = None,
    ) -> None:
        """
        Delegate delete/unload semantics to MSI.

        Frontend must not initiate delete without going through this adapter
        and the API layer.

        WL-BUILD-001: not yet implemented — raises NotImplementedError.
        """
        raise NotImplementedError(
            "MSI well delete not yet implemented."
        )

    def list_wells(self) -> list:
        """
        List all well datasets currently registered in MSI.

        Returns a list of MSI-registered well dataset records.
        The route delegates to this method; the route must not query MSI directly.

        WL-BUILD-001: not yet implemented — raises NotImplementedError.
        MSI client integration deferred to a later sprint.
        """
        raise NotImplementedError(
            "MSI well list not yet implemented. "
            "Wire MSI client in a later sprint."
        )
