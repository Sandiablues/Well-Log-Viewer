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


class ManagedInventoryHealth(BaseModel):
    ok: bool = True
    service: str = "wlv-managed-inventory"
    scope: str = "managed_well_inventory"
    storage_backend: str = "local_json"


class ManagedWellStatus(str, Enum):
    REGISTERED = "registered"
    AVAILABLE = "available"
    REVIEW_REQUIRED = "review_required"
    ERROR = "error"


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
    endpoint: str
    status: ManagedWellStatus = ManagedWellStatus.AVAILABLE


class ManagedWellRecord(BaseModel):
    managed_well_id: str
    well_id: str
    well_name: str
    wellbore_id: Optional[str] = None
    wellbore_name: Optional[str] = None
    operator: Optional[str] = None
    field: Optional[str] = None
    country: Optional[str] = None
    depth_unit: str = "ft"
    top_depth: Optional[float] = None
    base_depth: Optional[float] = None
    status: ManagedWellStatus = ManagedWellStatus.REGISTERED
    source_references: list[ManagedSourceReference] = Field(default_factory=list)
    viewer_packages: list[ViewerPackageReference] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ManagedInventorySnapshot(BaseModel):
    schema_version: str = "wlv_managed_inventory_v1"
    records: list[ManagedWellRecord] = Field(default_factory=list)


class ManagedInventoryStatus(BaseModel):
    ok: bool
    service: str = "wlv-managed-inventory"
    storage_backend: str
    storage_path: str
    managed_well_count: int
    viewer_package_count: int
    source_reference_count: int


class RegisterSeedWellResponse(BaseModel):
    ok: bool
    action: str
    record: ManagedWellRecord
