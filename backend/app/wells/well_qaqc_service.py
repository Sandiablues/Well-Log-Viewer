"""
MultiViewer Well Log Viewer — Well QAQC Service
WL-BUILD-001 scaffold

Backend owns all QAQC logic and finding generation.
Frontend must display findings only; it must not infer them.

This service is a placeholder skeleton for WL-BUILD-001.
Full deterministic QAQC rules will be wired in a later sprint.
"""

from __future__ import annotations

from enum import Enum
from typing import List

from .models import QaqcFinding, QaqcSeverity, WellMultitrackV1


# ---------------------------------------------------------------------------
# Initial QAQC finding codes
# Defined by backend; surfaced to frontend as opaque strings.
# ---------------------------------------------------------------------------


class QaqcCode(str, Enum):
    """
    Well-log QAQC finding codes.
    Owned by the backend QAQC service.
    Frontend treats these as opaque identifiers for display only.
    """
    # Curve-level
    CURVE_ALL_NULL = "CURVE_ALL_NULL"
    CURVE_EXCESSIVE_NULL = "CURVE_EXCESSIVE_NULL"
    CURVE_DEPTH_RANGE_MISMATCH = "CURVE_DEPTH_RANGE_MISMATCH"
    CURVE_UNIT_UNRECOGNIZED = "CURVE_UNIT_UNRECOGNIZED"
    CURVE_DUPLICATE_MNEMONIC = "CURVE_DUPLICATE_MNEMONIC"

    # Well/wellbore-level
    WELL_MISSING_DEPTH_CURVE = "WELL_MISSING_DEPTH_CURVE"
    WELL_HEADER_INCOMPLETE = "WELL_HEADER_INCOMPLETE"

    # LAS header-level
    LAS_NULL_VALUE_NOT_SET = "LAS_NULL_VALUE_NOT_SET"
    LAS_VERSION_UNSUPPORTED = "LAS_VERSION_UNSUPPORTED"


class WellQaqcService:
    """
    Backend-owned service responsible for:
    - Running deterministic QAQC checks against imported well data
    - Generating QaqcFinding records
    - Attaching findings to the viewer package

    WL-BUILD-001: skeleton only.
    Full rule implementation deferred to later sprint.
    """

    def run_qaqc(self, viewer_package: WellMultitrackV1) -> List[QaqcFinding]:
        """
        Run QAQC checks against a well_multitrack_v1 viewer package.

        Returns a list of QaqcFinding records.
        Findings are owned by this service; frontend renders them, not infers them.

        WL-BUILD-001: returns empty list — rules not yet implemented.
        """
        findings: List[QaqcFinding] = []
        # TODO (WL-BUILD-002+): implement deterministic rules per QaqcCode entries above.
        return findings

    def attach_findings_to_package(
        self,
        viewer_package: WellMultitrackV1,
        findings: List[QaqcFinding],
    ) -> WellMultitrackV1:
        """
        Return a new viewer package with the provided findings attached.

        WL-BUILD-001: passthrough — wiring deferred.
        """
        return viewer_package.model_copy(update={"qaqc_findings": findings})

    def get_findings_for_representation(
        self,
        dataset_id: str,
        representation_id: str,
    ) -> List[QaqcFinding]:
        """
        Route-facing delegation point: return QAQC findings for a given
        MSI dataset and representation, without requiring a pre-assembled
        viewer package as input.

        In a wired implementation this method will:
          1. Retrieve the persisted QAQC findings from the MSI-attached
             QAQC artifact for this representation.
          2. Return them as a list of QaqcFinding records.

        The QAQC endpoint calls this method rather than run_qaqc() directly,
        because the endpoint does not assemble a full viewer package — it
        only returns findings. The service resolves findings from the
        MSI-registered representation record.

        WL-BUILD-001: not yet implemented — raises NotImplementedError.
        Full wiring deferred to the QAQC service sprint.
        """
        raise NotImplementedError(
            f"QAQC findings retrieval not yet implemented for "
            f"dataset_id={dataset_id!r}, representation_id={representation_id!r}. "
            "Wire MSI QAQC artifact retrieval in a later sprint."
        )
