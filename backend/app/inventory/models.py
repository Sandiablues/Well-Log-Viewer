"""Managed Well Inventory domain models.

These models intentionally avoid frontend-specific state. They describe durable
backend inventory records that can be backed by local JSON today and by a
relational database/object-storage catalog later without changing API contracts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ManagedInventoryHealth(BaseModel):
    ok: bool = True
    service: str = "wlv-managed-inventory"
    scope: str = "managed_well_inventory"
    storage_backend: str = "local_json"


class ManagedInventoryLifecycleState(str, Enum):
    REGISTERED = "registered"
    AVAILABLE = "available"
    VIEWER_READY = "viewer_ready"
    STALE = "stale"
    INVALID = "invalid"
    ARCHIVED = "archived"
    REVIEW_REQUIRED = "review_required"
    ERROR = "error"


# Backward-compatible alias for the BE-003 contract name. Keep API payloads as
# lifecycle-state strings while avoiding a breaking import for existing services
# and tests that still refer to ManagedWellStatus.
ManagedWellStatus = ManagedInventoryLifecycleState


class ManagedSourceKind(str, Enum):
    LAS = "las"
    CSV_INTERVALS = "csv_intervals"
    RASTER_LOG = "raster_log"
    DOCUMENT = "document"
    SEED = "seed"
    OTHER = "other"


class ManagedSourceReference(BaseModel):
    source_id: str
    source_kind: ManagedSourceKind
    display_name: str
    original_path: Optional[str] = None
    file_name: Optional[str] = None
    file_format: Optional[str] = None
    checksum: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ViewerPackageReference(BaseModel):
    viewer_package_id: str
    viewer_package_version: str
    dataset_id: str
    representation_id: str
    well_id: str
    uwi: str | None = None
    endpoint: str
    status: ManagedInventoryLifecycleState = ManagedInventoryLifecycleState.VIEWER_READY


class ManagedProductGroupItem(BaseModel):
    product_id: str
    display_name: str
    curve_name: str
    curve_type: str
    run_date: str = "—"
    run_interval: str = "—"
    run_number: str = "—"
    qa_flag: str = "Pending"
    selectable: bool = True
    source_kind: Optional[str] = None
    source_id: Optional[str] = None
    viewer_package_id: Optional[str] = None


class ManagedProductGroup(BaseModel):
    group_key: str
    group_label: str
    collapsed_by_default: bool = True
    items: list[ManagedProductGroupItem] = Field(default_factory=list)


class ManagedWellRecord(BaseModel):
    managed_well_id: str
    well_id: str
    well_name: str
    wellbore_id: Optional[str] = None
    wellbore_name: Optional[str] = None
    operator: Optional[str] = None
    field: Optional[str] = None
    block: Optional[str] = None
    country: Optional[str] = None
    depth_unit: str = "ft"
    top_depth: Optional[float] = None
    base_depth: Optional[float] = None
    status: ManagedInventoryLifecycleState = ManagedInventoryLifecycleState.REGISTERED
    lifecycle_state: ManagedInventoryLifecycleState = ManagedInventoryLifecycleState.REGISTERED
    source_references: list[ManagedSourceReference] = Field(default_factory=list)
    viewer_packages: list[ViewerPackageReference] = Field(default_factory=list)
    product_groups: list[ManagedProductGroup] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    lifecycle_notes: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class ManagedInventorySnapshot(BaseModel):
    schema_version: str = "wlv_managed_inventory_v2"
    records: list[ManagedWellRecord] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now_iso)


class ManagedInventoryStatus(BaseModel):
    ok: bool
    service: str = "wlv-managed-inventory"
    storage_backend: str
    storage_path: str
    schema_version: str
    managed_well_count: int
    viewer_package_count: int
    source_reference_count: int
    lifecycle_counts: dict[str, int] = Field(default_factory=dict)
    last_checked_at: str = Field(default_factory=utc_now_iso)


class RegisterSeedWellResponse(BaseModel):
    ok: bool
    action: str
    record: ManagedWellRecord


class InventoryValidationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ManagedInventoryValidationIssue(BaseModel):
    severity: InventoryValidationSeverity
    code: str
    message: str
    managed_well_id: Optional[str] = None
    field: Optional[str] = None


class ManagedInventoryValidationResult(BaseModel):
    ok: bool
    service: str = "wlv-managed-inventory"
    scope: str = "inventory_integrity"
    storage_backend: str
    storage_path: str
    schema_version: str
    checked_at: str = Field(default_factory=utc_now_iso)
    managed_well_count: int
    viewer_package_count: int
    source_reference_count: int
    lifecycle_counts: dict[str, int] = Field(default_factory=dict)
    issue_count: int
    error_count: int
    warning_count: int
    issues: list[ManagedInventoryValidationIssue] = Field(default_factory=list)


class ManagedInventoryMaintenanceStatus(BaseModel):
    ok: bool
    service: str = "wlv-managed-inventory"
    scope: str = "maintenance_status"
    destructive_actions_enabled: bool = False
    validate_endpoint: str = "/api/wlv/inventory/validate"
    storage_backend: str
    storage_path: str
    managed_well_count: int
    lifecycle_counts: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
