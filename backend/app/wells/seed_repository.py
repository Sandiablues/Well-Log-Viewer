"""Empty compatibility repository.

Live WLV runtime data must come only from backend-owned WSI/WMD records.
"""

from __future__ import annotations

from .models import Curve, IntervalColumn, WellDetail, WellMultitrackV1, WellSummary


class WellNotFoundError(KeyError):
    """Raised when a requested well id is not present in the repository."""


class SeedWellRepository:
    """Compatibility boundary with no embedded wells."""

    # Retained only because older service signatures reference this symbol at
    # import time. It is deliberately empty and does not identify any well.
    WELL_ID = ""

    def list_wells(self) -> list[WellSummary]:
        return []

    def get_well(self, well_id: str) -> WellDetail:
        raise WellNotFoundError(well_id)

    def list_curves(self, well_id: str) -> list[Curve]:
        raise WellNotFoundError(well_id)

    def list_interval_columns(self, well_id: str) -> list[IntervalColumn]:
        raise WellNotFoundError(well_id)

    def get_viewer_package(self, well_id: str) -> WellMultitrackV1:
        raise WellNotFoundError(well_id)
