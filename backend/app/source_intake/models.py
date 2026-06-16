"""WLV Source Intake domain models.

This module defines the backend-owned discovery layer for well-log source
folders. It intentionally stops before metadata parsing, QAQC, MSI promotion,
or WMDP staging. Those are later pipeline stages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


WLV_SOURCE_INTAKE_WORKFLOW_STEPS: tuple[str, ...] = (
    "Search & Discover",
    "Categorize",
    "QAQC",
    "Register to MSI / Managed Well Inventory",
    "Stage in WMDP",
    "Load selected data to WDV",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceIntakeRepositoryStatus(str, Enum):
    AVAILABLE = "available"
    SCANNED = "scanned"
    MISSING = "missing"
    ERROR = "error"


class SourceIntakeFileType(str, Enum):
    LAS = "LAS"
    DLIS = "DLIS"
    LIS = "LIS"
    CGM = "CGM"
    TIFF = "TIFF"
    IMAGE = "IMAGE"
    PDF = "PDF"
    WORD = "WORD"
    EXCEL = "EXCEL"
    TEXT = "TEXT"
    CSV = "CSV"
    UNKNOWN = "UNKNOWN"


class SourceIntakeCandidateRole(str, Enum):
    WELL_LOG_CANDIDATE = "well_log_candidate"
    RASTER_IMAGE_CANDIDATE = "raster_image_candidate"
    SUPPORTING_DOCUMENT_CANDIDATE = "supporting_document_candidate"
    TABULAR_CANDIDATE = "tabular_candidate"
    WELLBORE_GEOMETRY_CANDIDATE = "wellbore_geometry_candidate"
    OTHER_REVIEW_REQUIRED = "other_review_required"


class SourceIntakeParseStatus(str, Enum):
    # WLV-WSI-PARSE-STATUS-FILENAME-1: backend-owned parse lifecycle states.
    NOT_PARSED = "not_parsed"
    PARSED = "parsed"
    PARSED_WITH_WARNINGS = "parsed_with_warnings"
    PARSE_FAILED = "parse_failed"
    UNSUPPORTED = "unsupported"
    CONTAINER_PENDING_EXTRACTION = "container_pending_extraction"


class SourceIntakeQaqcStatus(str, Enum):
    NOT_CHECKED = "not_checked"
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    REVIEW_REQUIRED = "review_required"


class SourceIntakeQaqcSeverity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceIntakeQaqcCheck(BaseModel):
    check_id: str
    status: SourceIntakeQaqcStatus
    severity: SourceIntakeQaqcSeverity = SourceIntakeQaqcSeverity.NONE
    message: str
    field_name: Optional[str] = None
    review_required: bool = False


class SourceIntakeQaqcResult(BaseModel):
    status: SourceIntakeQaqcStatus = SourceIntakeQaqcStatus.NOT_CHECKED
    severity: SourceIntakeQaqcSeverity = SourceIntakeQaqcSeverity.NONE
    check_count: int = 0
    warning_count: int = 0
    failure_count: int = 0
    review_required: bool = False
    messages: list[str] = Field(default_factory=list)
    checks: list[SourceIntakeQaqcCheck] = Field(default_factory=list)




class SourceIntakeWellHeader(BaseModel):
    well_name: Optional[str] = None
    uwi: Optional[str] = None
    operator: Optional[str] = None
    field: Optional[str] = None
    block: Optional[str] = None
    country: Optional[str] = None
    depth_unit: Optional[str] = None


class SourceIntakeLogHeader(BaseModel):
    file_name: str
    file_type: SourceIntakeFileType
    run_date: Optional[str] = None
    run_number: Optional[str] = None
    service_company: Optional[str] = None
    start_depth: Optional[float] = None
    stop_depth: Optional[float] = None
    step: Optional[float] = None
    null_value: Optional[float] = None
    depth_unit: Optional[str] = None
    curve_count: int = 0


class SourceIntakeCurveHeader(BaseModel):
    mnemonic: str
    description: Optional[str] = None
    unit: Optional[str] = None
    source_curve_name: Optional[str] = None
    depth_unit: Optional[str] = None
    top_depth: Optional[float] = None
    base_depth: Optional[float] = None
    sample_count: Optional[int] = None


class SourceIntakeParsedMetadata(BaseModel):
    parser_id: str
    source_format: str
    well_header: SourceIntakeWellHeader = Field(default_factory=SourceIntakeWellHeader)
    log_header: Optional[SourceIntakeLogHeader] = None
    curve_headers: list[SourceIntakeCurveHeader] = Field(default_factory=list)
    evidence_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class SourceIntakeHealth(BaseModel):
    ok: bool = True
    service: str = "wlv-source-intake"
    scope: str = "source_intake_foundation"
    conversion_step_enabled: bool = False
    reserved_future_representation_step: bool = True
    workflow_steps: list[str] = Field(default_factory=lambda: list(WLV_SOURCE_INTAKE_WORKFLOW_STEPS))


class SourceRepositoryCreateRequest(BaseModel):
    root_path: str
    name: Optional[str] = None
    include_subfolders: bool = True


class SourceRepositoryRecord(BaseModel):
    repository_id: str
    name: str
    root_path: str
    include_subfolders: bool = True
    status: SourceIntakeRepositoryStatus = SourceIntakeRepositoryStatus.AVAILABLE
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    last_scan_id: Optional[str] = None
    last_scan_scope: Optional[str] = None
    file_count: int = 0
    well_log_candidate_count: int = 0
    raster_candidate_count: int = 0
    document_candidate_count: int = 0
    tabular_candidate_count: int = 0
    wellbore_geometry_candidate_count: int = 0
    unknown_file_count: int = 0
    review_required_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class SourceIntakeEvidenceRecord(BaseModel):
    field_name: str
    value: Optional[str] = None
    source: str
    source_path: Optional[str] = None
    confidence: str = "high"
    message: Optional[str] = None


class SourceIntakeDiagnosticPhase(str, Enum):
    PARSE = "parse"
    QAQC = "qaqc"
    MDP_READY = "mdp_ready"
    EVIDENCE = "evidence"


class SourceIntakeDiagnosticSeverity(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


class SourceIntakeDiagnosticFlag(BaseModel):
    phase: SourceIntakeDiagnosticPhase
    severity: SourceIntakeDiagnosticSeverity = SourceIntakeDiagnosticSeverity.INFO
    code: str
    title: str
    message: str
    field_name: Optional[str] = None
    evidence: list[SourceIntakeEvidenceRecord] = Field(default_factory=list)


class SourceIntakeDiagnosticAction(BaseModel):
    phase: SourceIntakeDiagnosticPhase
    action_key: str
    label: str
    enabled: bool = False
    reason: Optional[str] = None


class SourceIntakeCandidateDiagnosticSummary(BaseModel):
    candidate_id: str
    file_name: str
    relative_path: str
    original_path: Optional[str] = None
    detected_file_type: SourceIntakeFileType
    candidate_role: SourceIntakeCandidateRole
    well_name: Optional[str] = None
    curve_count: int = 0
    registration_status: str = "not_registered"
    managed_well_id: Optional[str] = None
    managed_well_name: Optional[str] = None


class SourceIntakeCandidateDiagnostics(BaseModel):
    # WLV-WSI-FLAGS-DETAIL-1: backend-owned candidate diagnostic detail contract.
    ok: bool = True
    service: str = "wlv-source-intake"
    candidate_id: str
    summary: SourceIntakeCandidateDiagnosticSummary
    parse_status: SourceIntakeParseStatus
    qaqc_status: SourceIntakeQaqcResult
    mdp_ready_status: str
    flags: list[SourceIntakeDiagnosticFlag] = Field(default_factory=list)
    actions: list[SourceIntakeDiagnosticAction] = Field(default_factory=list)


class SourceIntakeResolvedField(BaseModel):
    field_name: str
    value: Optional[str] = None
    source: str = "missing"
    confidence: str = "missing"
    review_required: bool = False
    evidence: list[SourceIntakeEvidenceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SourceIntakeResolvedMetadata(BaseModel):
    resolver_id: str = "wlv_source_intake_metadata_resolver_v1"
    well_name: SourceIntakeResolvedField
    uwi: SourceIntakeResolvedField
    operator: SourceIntakeResolvedField
    field: SourceIntakeResolvedField
    block: SourceIntakeResolvedField
    review_required: bool = False
    warning_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    evidence_count: int = 0


class SourceIntakeDeviationSurveyColumnMapping(BaseModel):
    measured_depth: Optional[str] = None
    inclination: Optional[str] = None
    azimuth: Optional[str] = None
    tvd: Optional[str] = None
    x_offset: Optional[str] = None
    y_offset: Optional[str] = None
    northing: Optional[str] = None
    easting: Optional[str] = None
    unmapped_headers: list[str] = Field(default_factory=list)


class SourceIntakeDeviationSurveyStationPreview(BaseModel):
    row_index: int
    md: float
    inclination: float
    azimuth: float
    tvd: Optional[float] = None
    x_offset: Optional[float] = None
    y_offset: Optional[float] = None
    northing: Optional[float] = None
    easting: Optional[float] = None


class SourceIntakeDeviationSurveyPreview(BaseModel):
    parser_id: str = "wlv_deviation_survey_parser_v1"
    source_format: str
    row_count: int
    station_count: int
    preview_station_count: int
    column_mapping: SourceIntakeDeviationSurveyColumnMapping
    md_min: float
    md_max: float
    tvd_min: Optional[float] = None
    tvd_max: Optional[float] = None
    warning_count: int = 0
    error_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    stations_preview: list[SourceIntakeDeviationSurveyStationPreview] = Field(default_factory=list)


class SourceFileCandidate(BaseModel):
    source_file_id: str
    repository_id: str
    scan_id: str
    file_name: str
    original_path: str
    relative_path: str
    file_extension: str
    detected_file_type: SourceIntakeFileType
    candidate_role: SourceIntakeCandidateRole
    size_bytes: int
    modified_at: str
    checksum: str
    fingerprint_status: str = "computed"
    parser_status: SourceIntakeParseStatus = SourceIntakeParseStatus.NOT_PARSED
    parsed_metadata: Optional[SourceIntakeParsedMetadata] = None
    geometry_preview: Optional[SourceIntakeDeviationSurveyPreview] = None
    resolved_metadata: Optional[SourceIntakeResolvedMetadata] = None
    qaqc_status: SourceIntakeQaqcResult = Field(default_factory=SourceIntakeQaqcResult)
    parse_error: Optional[str] = None
    review_required: bool = False
    warnings: list[str] = Field(default_factory=list)
    registration_status: str = "not_registered"
    managed_well_id: Optional[str] = None
    managed_well_name: Optional[str] = None
    wmdp_state: Optional[str] = None
    wdv_state: Optional[str] = None
    registered_product_count: int = 0
    registered_curve_count: int = 0


class SourceRepositoryScanResult(BaseModel):
    ok: bool
    repository: SourceRepositoryRecord
    scan_id: str
    scan_scope: str
    file_count: int
    candidates: list[SourceFileCandidate] = Field(default_factory=list)


class SourceIntakeWorkbenchSummary(BaseModel):
    repository_count: int
    file_count: int
    well_log_candidate_count: int
    raster_candidate_count: int
    document_candidate_count: int
    tabular_candidate_count: int
    wellbore_geometry_candidate_count: int = 0
    unknown_file_count: int
    review_required_count: int


class SourceIntakeWorkbench(BaseModel):
    ok: bool = True
    service: str = "wlv-source-intake"
    conversion_step_enabled: bool = False
    reserved_future_representation_step: bool = True
    workflow_steps: list[str] = Field(default_factory=lambda: list(WLV_SOURCE_INTAKE_WORKFLOW_STEPS))
    summary: SourceIntakeWorkbenchSummary
    repositories: list[SourceRepositoryRecord] = Field(default_factory=list)
    candidates: list[SourceFileCandidate] = Field(default_factory=list)


class SourceRepositoryRemoveResponse(BaseModel):
    # WLV-WSI-REMOVE-SOURCE-1: repository removal is backend-owned.
    ok: bool = True
    action: str = "remove_source_repository"
    destructive: bool = False
    repository_id: str
    repository_removed: bool = False
    candidate_rows_removed: int = 0
    message: str
    workbench: SourceIntakeWorkbench


class SourceIntakeApproval(BaseModel):
    approved_by: Optional[str] = None
    approval_note: Optional[str] = None


class SourceIntakeRegisterRequest(BaseModel):
    candidate_ids: list[str]
    approval: SourceIntakeApproval = Field(default_factory=SourceIntakeApproval)


class SourceIntakeRegisterResult(BaseModel):
    candidate_id: str
    status: str
    reason: Optional[str] = None
    managed_well_id: Optional[str] = None
    well_id: Optional[str] = None
    well_name: Optional[str] = None
    registered_product_count: int = 0
    registered_curve_count: int = 0
    action: Optional[str] = None


class SourceIntakeRegisterResponse(BaseModel):
    ok: bool = True
    action: str = "register_to_managed_well_inventory"
    destructive: bool = False
    registered_count: int = 0
    skipped_count: int = 0
    results: list[SourceIntakeRegisterResult] = Field(default_factory=list)
    workbench: Optional[SourceIntakeWorkbench] = None


class SourceIntakeClearRequest(BaseModel):
    # WLV-WSI-CLEAR-CANDIDATE-ROWS-1: candidate register clear is backend-owned.
    repository_id: Optional[str] = None
    candidate_ids: list[str] = Field(default_factory=list)


class SourceIntakeClearResponse(BaseModel):
    ok: bool = True
    action: str = "clear_workbench_selection"
    destructive: bool = False
    records_deleted: int = 0
    message: str = "Cleared active source-intake working selection only; discovered records were not deleted."
    workbench: SourceIntakeWorkbench


class SourceIntakeSnapshot(BaseModel):
    schema_version: str = "wlv_source_intake_v1"
    repositories: list[SourceRepositoryRecord] = Field(default_factory=list)
    candidates: list[SourceFileCandidate] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now_iso)
