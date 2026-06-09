"""Format-neutral Well Log Source Ingestion contracts.

These contracts keep the ingestion layer independent from any single well-log
format. LAS is the first implemented numeric-curve adapter, while DLIS, CGM,
TIFF, PDF, and unknown sources remain first-class contract cases for later
adapters.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class WellLogSourceFormat(str, Enum):
    LAS = "las"
    DLIS = "dlis"
    CGM = "cgm"
    TIFF = "tiff"
    PDF = "pdf"
    UNKNOWN = "unknown"


class WellLogSourceCategory(str, Enum):
    NUMERIC_CURVE = "numeric_curve"
    FRAME_CHANNEL = "frame_channel"
    RASTER_LOG = "raster_log"
    VECTOR_LOG = "vector_log"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class IngestionCapability(str, Enum):
    DETECT_FORMAT = "detect_format"
    REGISTER_SOURCE = "register_source"
    EXTRACT_METADATA = "extract_metadata"
    EXTRACT_CURVE_INVENTORY = "extract_curve_inventory"
    EXTRACT_RASTER_ARTIFACT = "extract_raster_artifact"
    BUILD_VIEWER_PACKAGE = "build_viewer_package"


class IngestionAdapterStatus(str, Enum):
    ACTIVE = "active"
    STUB = "stub"
    PLANNED = "planned"


class IngestionEvidenceKind(str, Enum):
    SOURCE_FINGERPRINT = "source_fingerprint"
    FORMAT_DETECTION = "format_detection"
    METADATA_HEADER = "metadata_header"
    CURVE_INVENTORY = "curve_inventory"
    DEPTH_SAMPLES = "depth_samples"
    NULL_VALUE = "null_value"
    UNIT = "unit"
    QAQC_CHECK = "qaqc_check"
    VIEWER_PACKAGE_REFERENCE = "viewer_package_reference"


class IngestionEvidenceRecord(BaseModel):
    evidence_id: str
    evidence_kind: IngestionEvidenceKind
    source: str
    field_path: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    value: Optional[Any] = None
    message: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionQaqcSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class IngestionQaqcFinding(BaseModel):
    finding_id: str
    severity: IngestionQaqcSeverity
    code: str
    message: str
    field_path: Optional[str] = None
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionQaqcSummary(BaseModel):
    ok: bool = True
    evidence_count: int = 0
    finding_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    source_fingerprint_available: bool = False
    depth_range_available: bool = False
    curve_inventory_available: bool = False
    viewer_package_available: bool = False


class SourceFileRegistration(BaseModel):
    source_file_id: str
    display_name: str
    source_format: WellLogSourceFormat = WellLogSourceFormat.UNKNOWN
    source_category: WellLogSourceCategory = WellLogSourceCategory.UNKNOWN
    original_path: Optional[str] = None
    file_name: Optional[str] = None
    content_type: Optional[str] = None
    byte_size: Optional[int] = None
    checksum: Optional[str] = None
    storage_uri: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FormatDetectionRequest(BaseModel):
    file_name: Optional[str] = None
    original_path: Optional[str] = None
    content_type: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FormatDetectionResult(BaseModel):
    detected_format: WellLogSourceFormat
    source_category: WellLogSourceCategory
    confidence: float = Field(ge=0.0, le=1.0)
    detection_source: str
    adapter_id: str
    adapter_status: IngestionAdapterStatus
    is_supported: bool
    reasons: list[str] = Field(default_factory=list)
    capabilities: list[IngestionCapability] = Field(default_factory=list)


class SupportedIngestionFormat(BaseModel):
    source_format: WellLogSourceFormat
    source_category: WellLogSourceCategory
    adapter_id: str
    adapter_status: IngestionAdapterStatus
    capabilities: list[IngestionCapability] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CurveChannelArtifact(BaseModel):
    artifact_id: str
    mnemonic: str
    display_name: Optional[str] = None
    unit: Optional[str] = None
    depth_unit: Optional[str] = None
    top_depth: Optional[float] = None
    base_depth: Optional[float] = None
    sample_count: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RasterLogArtifact(BaseModel):
    artifact_id: str
    display_name: str
    source_format: WellLogSourceFormat
    depth_calibrated: bool = False
    top_depth: Optional[float] = None
    base_depth: Optional[float] = None
    depth_unit: Optional[str] = None
    page_count: Optional[int] = None
    image_count: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedWellLogPackage(BaseModel):
    package_id: str
    source_file: SourceFileRegistration
    well_id: Optional[str] = None
    well_name: Optional[str] = None
    curve_channels: list[CurveChannelArtifact] = Field(default_factory=list)
    raster_artifacts: list[RasterLogArtifact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence: list[IngestionEvidenceRecord] = Field(default_factory=list)
    qaqc_findings: list[IngestionQaqcFinding] = Field(default_factory=list)
    qaqc_summary: IngestionQaqcSummary = Field(default_factory=IngestionQaqcSummary)


class SourceRegistrationRequest(BaseModel):
    original_path: str
    display_name: Optional[str] = None
    declared_format: Optional[WellLogSourceFormat] = None
    register_to_inventory: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceRegistrationResponse(BaseModel):
    ok: bool
    action: str
    detected_format: WellLogSourceFormat
    source_file: SourceFileRegistration
    normalized_package: NormalizedWellLogPackage
    managed_record: Optional[dict[str, Any]] = None
    evidence: list[IngestionEvidenceRecord] = Field(default_factory=list)
    qaqc_summary: IngestionQaqcSummary = Field(default_factory=IngestionQaqcSummary)
    notes: list[str] = Field(default_factory=list)


class WellFolderScanRequest(BaseModel):
    parent_path: str
    include_subfolders: bool = True
    max_files: int = Field(default=5000, ge=1, le=50000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WellFolderCandidate(BaseModel):
    candidate_id: str
    relative_path: str
    file_name: str
    original_path: str
    byte_size: int
    detected_format: WellLogSourceFormat
    source_category: WellLogSourceCategory
    confidence: float = Field(ge=0.0, le=1.0)
    adapter_id: str
    adapter_status: IngestionAdapterStatus
    is_supported: bool
    candidate_kind: str
    candidate_role: str
    classification_source: str
    classification_reasons: list[str] = Field(default_factory=list)
    review_required: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class WellFolderScanSummary(BaseModel):
    total_files_seen: int = 0
    candidate_count: int = 0
    las_count: int = 0
    dlis_count: int = 0
    raster_log_count: int = 0
    document_count: int = 0
    unknown_count: int = 0
    review_required_count: int = 0
    skipped_count: int = 0


class WellFolderScanResponse(BaseModel):
    ok: bool = True
    action: str = "scanned"
    parent_path: str
    include_subfolders: bool
    summary: WellFolderScanSummary
    candidates: list[WellFolderCandidate] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class IngestionHealth(BaseModel):
    ok: bool = True
    service: str = "wlv-source-ingestion"
    scope: str = "format_neutral_ingestion_architecture"
    adapter_count: int
    supported_formats: list[WellLogSourceFormat]
