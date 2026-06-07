"""
MultiViewer Well Log Viewer — Domain Models
WL-BUILD-001 scaffold

These models represent the backend-owned canonical well-log data contract.
The frontend must render these contracts through an adapter.
Equinor ViDEx props must NOT become the backend API contract.

Canonical viewer package: well_multitrack_v1
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class DepthUnit(str, Enum):
    METERS = "m"
    FEET = "ft"


class DisplayDomain(str, Enum):
    """
    Depth display domain for well log tracks.

    Active in WL-BUILD-001:
      MD — Measured Depth. The only active rendering domain in Phase 1.

    Reserved for future sprints (not active in WL-BUILD-001):
      TVD   — True Vertical Depth. Requires backend TVD transform service.
      TVDSS — True Vertical Depth Sub-Sea. Requires backend TVDSS transform service.

    Backend owns domain transforms. Frontend must not compute TVD/TVDSS
    independently. These values are present in the enum so the backend contract
    remains forward-compatible, but no frontend UI must expose them as
    selectable options until the transform services are wired.
    """
    MD = "MD"
    # Reserved — do not expose in frontend UI until TVD transform service is wired:
    TVD = "TVD"
    TVDSS = "TVDSS"


class ScaleType(str, Enum):
    LINEAR = "linear"
    LOG = "log"


class TrackType(str, Enum):
    """
    Track rendering type.

    Active in WL-BUILD-001:
      CURVE — Curve/log track. The only active rendering scope in Phase 1.
      DEPTH — Depth axis track.

    Reserved for future sprints (not active in WL-BUILD-001):
      IMAGE — Raster/core image track. Deferred; do not render in WL-BUILD-001.
    """
    CURVE = "curve"
    DEPTH = "depth"
    # Reserved — raster/core image track rendering deferred to a later sprint:
    IMAGE = "image"


class QaqcSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# ---------------------------------------------------------------------------
# MSI reference models
# These are references into the MSI-managed inventory.
# The MSI backend owns registration, lifecycle, and delete semantics.
# ---------------------------------------------------------------------------


class MsiDatasetRef(BaseModel):
    """Reference to an MSI-managed dataset."""
    dataset_id: str
    display_name: Optional[str] = None


class MsiSourceRef(BaseModel):
    """Reference to an MSI-managed source file record."""
    source_id: str
    filename: Optional[str] = None


class MsiRepresentationRef(BaseModel):
    """Reference to an MSI-managed representation."""
    representation_id: str
    representation_type: Optional[str] = None


# ---------------------------------------------------------------------------
# Well / wellbore domain models
# ---------------------------------------------------------------------------


class Well(BaseModel):
    well_id: str
    well_name: str
    dataset_ref: MsiDatasetRef
    source_ref: MsiSourceRef


class Wellbore(BaseModel):
    wellbore_id: str
    well_id: str
    wellbore_name: str
    representation_ref: MsiRepresentationRef


# ---------------------------------------------------------------------------
# Curve domain models
# ---------------------------------------------------------------------------


class CurveScale(BaseModel):
    type: ScaleType = ScaleType.LINEAR
    min: float = 0.0
    max: float = 150.0


class Curve(BaseModel):
    curve_id: str
    mnemonic: str
    normalized_name: Optional[str] = None
    unit: Optional[str] = None
    # Backend-owned samples URL — frontend fetches samples via this URL.
    # Frontend must not parse LAS or construct samples independently.
    samples_url: str
    scale: CurveScale = Field(default_factory=CurveScale)


class CurveMetadata(BaseModel):
    """Curve metadata as extracted and owned by the backend LAS import service."""
    mnemonic: str
    unit: Optional[str] = None
    description: Optional[str] = None
    null_value: Optional[float] = None


# ---------------------------------------------------------------------------
# Track domain model
# ---------------------------------------------------------------------------


class Track(BaseModel):
    track_id: str
    track_type: TrackType = TrackType.CURVE
    title: str
    curves: List[Curve] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# QAQC finding model
# Backend owns all QAQC logic and finding generation.
# Frontend displays findings; it must not infer them.
# ---------------------------------------------------------------------------


class QaqcFinding(BaseModel):
    finding_id: str
    severity: QaqcSeverity
    code: str
    object_type: str
    object_id: str
    message: str


# ---------------------------------------------------------------------------
# well_multitrack_v1 — canonical backend-owned viewer package
#
# This is the authoritative data contract the frontend must consume.
# The frontend adapter translates this into ViDEx-facing props.
# The ViDEx internal data shape must not become this contract.
# ---------------------------------------------------------------------------


class DepthRange(BaseModel):
    min: float = 0.0
    max: float = 0.0


class WellMultitrackV1(BaseModel):
    """
    Canonical backend-owned viewer package.
    Version: well_multitrack_v1

    Lifecycle:
      Generated by well_viewer_package_service.
      Registered with MSI via msi_well_adapter.
      Fetched by frontend; rendered through equinorWellLogAdapter.
    """
    viewer_package_version: str = "well_multitrack_v1"
    dataset_id: str
    representation_id: str
    well_id: str
    wellbore_id: str
    display_domain: DisplayDomain = DisplayDomain.MD
    depth_unit: DepthUnit = DepthUnit.METERS
    depth_range: DepthRange = Field(default_factory=DepthRange)
    tracks: List[Track] = Field(default_factory=list)
    qaqc_findings: List[QaqcFinding] = Field(default_factory=list)
