"""Managed Well Inventory domain models.

These models intentionally avoid frontend-specific state. They describe durable
backend inventory records that can be backed by local JSON today and by a
relational database/object-storage catalog later without changing API contracts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal, Optional

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.identity import IdentityAssignmentMetadata, LegacyIdentityAlias, parse_uuid7


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_uuid7(value: str) -> str:
    """Validate and normalize a persisted canonical UUIDv7 string."""

    return str(parse_uuid7(value))


CanonicalUuid7 = Annotated[str, AfterValidator(_canonical_uuid7)]


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




class ManagedWmdpState(str, Enum):
    REGISTERED = "registered"
    STAGED_IN_WMDP = "staged_in_wmdp"
    HIDDEN_FROM_WMDP = "hidden_from_wmdp"
    REMOVED_FROM_WMDP = "removed_from_wmdp"


class ManagedWdvState(str, Enum):
    NOT_LOADED = "not_loaded"
    LOADED_TO_WDV = "loaded_to_wdv"


class WmdWorkingState(str, Enum):
    """Backend-owned transient WMD working-data lifecycle."""

    AVAILABLE = "available"
    LOADED = "loaded"
    IN_USE = "in_use"
    UNREFERENCED = "unreferenced"
    ELIGIBLE_FOR_CLEANUP = "eligible_for_cleanup"
    CLEARED = "cleared"


class WmdRetentionState(str, Enum):
    """Retention projection for application-owned WMD derived data."""

    ACTIVE = "active"
    UNREFERENCED = "unreferenced"
    ELIGIBLE_FOR_CLEANUP = "eligible_for_cleanup"
    CLEARED = "cleared"


class WmdSourceRecoveryState(str, Enum):
    """Observed state of the authoritative source used for WMD rebuild."""

    AVAILABLE = "available"
    MISSING = "missing"
    CHANGED = "changed"
    INACCESSIBLE = "inaccessible"


class WmdReferenceType(str, Enum):
    """Explicit consumers that retain transient WMD working data."""

    WMD = "wmd"
    WDV = "wdv"
    WBV = "wbv"
    EXPORT = "export"
    SAVED_WORKSPACE = "saved_workspace"


class WmdReferenceBinding(BaseModel):
    reference_uid: CanonicalUuid7
    reference_type: WmdReferenceType
    owner_id: str
    reason: str | None = None
    acquired_at: str = Field(default_factory=utc_now_iso)


class ManagedSourceKind(str, Enum):
    LAS = "las"
    DLIS = "dlis"
    CSV_INTERVALS = "csv_intervals"
    RASTER_LOG = "raster_log"
    DOCUMENT = "document"
    SEED = "seed"
    OTHER = "other"


class ManagedSourceReference(BaseModel):
    source_id: str
    managed_source_uid: Optional[CanonicalUuid7] = None
    source_occurrence_uid: Optional[CanonicalUuid7] = None
    identity_assignment: Optional[IdentityAssignmentMetadata] = None
    legacy_ids: list[LegacyIdentityAlias] = Field(default_factory=list)
    source_kind: ManagedSourceKind
    display_name: str
    original_path: Optional[str] = None
    file_name: Optional[str] = None
    file_format: Optional[str] = None
    checksum: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ViewerPackageReference(BaseModel):
    viewer_package_id: str
    viewer_package_uid: Optional[CanonicalUuid7] = None
    representation_uid: Optional[CanonicalUuid7] = None
    identity_assignment: Optional[IdentityAssignmentMetadata] = None
    legacy_ids: list[LegacyIdentityAlias] = Field(default_factory=list)
    viewer_package_version: str
    dataset_id: str
    representation_id: str
    well_id: str
    uwi: str | None = None
    endpoint: str
    status: ManagedInventoryLifecycleState = ManagedInventoryLifecycleState.VIEWER_READY


class ManagedProductGroupItem(BaseModel):
    product_id: str
    managed_product_uid: Optional[CanonicalUuid7] = None
    managed_curve_uid: Optional[CanonicalUuid7] = None
    managed_wellbore_uid: Optional[CanonicalUuid7] = None
    managed_source_uid: Optional[CanonicalUuid7] = None
    identity_assignment: Optional[IdentityAssignmentMetadata] = None
    legacy_ids: list[LegacyIdentityAlias] = Field(default_factory=list)
    curve_uid: Optional[str] = None
    well_uid: Optional[str] = None
    source_uid: Optional[str] = None
    kr_curve_type_id: Optional[str] = None
    observed_mnemonic: Optional[str] = None
    normalized_mnemonic: Optional[str] = None
    display_name: str
    curve_name: str
    curve_type: str
    curve_description: str | None = None
    curve_unit: str | None = None
    product_category: str = "other_review_required"
    product_subgroup_key: str | None = None
    product_subgroup_label: str | None = None
    curve_family: str = "Unclassified"
    classification_confidence: str = "low"
    classification_source: str = "unclassified"
    classification_reasons: list[str] = Field(default_factory=list)
    review_required: bool = True
    run_date: str = "—"
    run_interval: str = "—"
    run_number: str = "—"
    qa_flag: str = "Pending"
    selectable: bool = True
    source_kind: Optional[str] = None
    source_id: Optional[str] = None
    viewer_package_id: Optional[str] = None
    wmdp_state: ManagedWmdpState = ManagedWmdpState.REGISTERED
    wdv_state: ManagedWdvState = ManagedWdvState.NOT_LOADED
    wmd_working_state: WmdWorkingState = WmdWorkingState.AVAILABLE
    wmd_retention_state: WmdRetentionState = WmdRetentionState.ACTIVE
    wmd_cleanup_eligible: bool = False
    wmd_retention_reason: str = "available_in_wmd"
    wmd_references: list[WmdReferenceBinding] = Field(default_factory=list)
    wmd_source_recovery_state: WmdSourceRecoveryState = WmdSourceRecoveryState.AVAILABLE
    wmd_source_checked_at: Optional[str] = None
    wmd_source_recovery_message: Optional[str] = None
    wmd_observed_source_fingerprint: Optional[str] = None
    source_intake_candidate_id: Optional[str] = None
    display_layer_type: Optional[str] = None
    depth_reference: Optional[str] = None
    depth_units: Optional[str] = None
    depth_start: Optional[float] = None
    depth_end: Optional[float] = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class ManagedProductGroup(BaseModel):
    group_key: str
    group_label: str
    collapsed_by_default: bool = True
    items: list[ManagedProductGroupItem] = Field(default_factory=list)


class ManagedWellRecord(BaseModel):
    managed_well_id: str
    managed_well_uid: Optional[CanonicalUuid7] = None
    managed_wellbore_uid: Optional[CanonicalUuid7] = None
    identity_assignment: Optional[IdentityAssignmentMetadata] = None
    legacy_ids: list[LegacyIdentityAlias] = Field(default_factory=list)
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
    wmdp_state: ManagedWmdpState = ManagedWmdpState.REGISTERED
    wdv_state: ManagedWdvState = ManagedWdvState.NOT_LOADED
    wmd_working_state: WmdWorkingState = WmdWorkingState.AVAILABLE
    wmd_retention_state: WmdRetentionState = WmdRetentionState.ACTIVE
    wmd_cleanup_eligible: bool = False
    wmd_retention_reason: str = "available_in_wmd"
    wmd_references: list[WmdReferenceBinding] = Field(default_factory=list)
    wmd_source_recovery_state: WmdSourceRecoveryState = WmdSourceRecoveryState.AVAILABLE
    wmd_source_checked_at: Optional[str] = None
    wmd_source_recovery_message: Optional[str] = None
    wmd_observed_source_fingerprint: Optional[str] = None
    source_intake_candidate_id: Optional[str] = None
    wmdp_available: bool = True
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    loaded_product_count: int = 0
    viewer_curve_count: int = 0
    displayable_curve_count: int = 0


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




class ExecuteWmdCleanupRequest(BaseModel):
    managed_well_uid: CanonicalUuid7 | None = None
    managed_well_id: str | None = None
    managed_product_uids: list[CanonicalUuid7] = Field(default_factory=list)
    product_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_well_reference(self) -> "ExecuteWmdCleanupRequest":
        if not self.managed_well_uid and not str(self.managed_well_id or "").strip():
            raise ValueError("managed_well_uid or managed_well_id is required")
        return self

    @property
    def well_reference(self) -> str:
        return str(self.managed_well_uid or self.managed_well_id)

    @property
    def product_references(self) -> list[str]:
        return [*[str(value) for value in self.managed_product_uids], *self.product_ids]


class ExecuteWmdCleanupResult(BaseModel):
    managed_well_id: str
    cleared_product_ids: list[str] = Field(default_factory=list)
    cleared_record_payload: bool = False
    external_sources_touched: bool = False


class ExecuteWmdCleanupResponse(BaseModel):
    ok: bool = True
    action: str = "wmd_transient_data_cleared"
    result: ExecuteWmdCleanupResult
    record: ManagedWellRecord


class RebuildWmdPayloadRequest(BaseModel):
    managed_well_uid: CanonicalUuid7 | None = None
    managed_well_id: str | None = None
    managed_product_uids: list[CanonicalUuid7] = Field(default_factory=list)
    product_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_well_reference(self) -> "RebuildWmdPayloadRequest":
        if not self.managed_well_uid and not str(self.managed_well_id or "").strip():
            raise ValueError("managed_well_uid or managed_well_id is required")
        return self

    @property
    def well_reference(self) -> str:
        return str(self.managed_well_uid or self.managed_well_id)

    @property
    def product_references(self) -> list[str]:
        return [*[str(value) for value in self.managed_product_uids], *self.product_ids]


class RebuildWmdPayloadResult(BaseModel):
    managed_well_id: str
    rebuilt_product_ids: list[str] = Field(default_factory=list)
    source_fingerprints_verified: list[str] = Field(default_factory=list)
    identities_preserved: bool = True
    external_sources_touched: bool = False


class RebuildWmdPayloadResponse(BaseModel):
    ok: bool = True
    action: str = "wmd_transient_payload_rebuilt"
    result: RebuildWmdPayloadResult
    record: ManagedWellRecord




class WmdDownstreamRecoveryStatus(BaseModel):
    managed_well_id: str
    source_recovery_state: WmdSourceRecoveryState
    payload_available: bool
    wdv_load_allowed: bool
    wbv_load_allowed: bool
    export_allowed: bool
    saved_workspace_resume_allowed: bool
    blocked_product_ids: list[str] = Field(default_factory=list)
    recovery_message: str | None = None

class LoadManagedWellToWdvRequest(BaseModel):
    managed_well_uid: CanonicalUuid7 | None = None
    managed_well_id: str | None = None
    managed_product_uids: list[CanonicalUuid7] = Field(default_factory=list)
    product_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_well_reference(self) -> "LoadManagedWellToWdvRequest":
        if not self.managed_well_uid and not str(self.managed_well_id or "").strip():
            raise ValueError("managed_well_uid or managed_well_id is required")
        return self

    @property
    def well_reference(self) -> str:
        return str(self.managed_well_uid or self.managed_well_id)

    @property
    def product_references(self) -> list[str]:
        return [*[str(value) for value in self.managed_product_uids], *self.product_ids]


class LoadManagedWellToWdvResult(BaseModel):
    managed_well_id: str
    loaded_product_ids: list[str] = Field(default_factory=list)
    unloaded_managed_well_ids: list[str] = Field(default_factory=list)
    wdv_state: ManagedWdvState = ManagedWdvState.LOADED_TO_WDV
    active_viewer_package_id: Optional[str] = None


class LoadManagedWellToWdvResponse(BaseModel):
    ok: bool = True
    action: str = "loaded_to_wdv"
    result: LoadManagedWellToWdvResult
    record: ManagedWellRecord


class BulkLoadWdvWellSelection(BaseModel):
    managed_well_uid: CanonicalUuid7 | None = None
    managed_well_id: str | None = None
    managed_product_uids: list[CanonicalUuid7] = Field(default_factory=list)
    product_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_well_reference(self) -> "BulkLoadWdvWellSelection":
        if not self.managed_well_uid and not str(self.managed_well_id or "").strip():
            raise ValueError("managed_well_uid or managed_well_id is required")
        return self

    @property
    def well_reference(self) -> str:
        return str(self.managed_well_uid or self.managed_well_id)

    @property
    def product_references(self) -> list[str]:
        return [*[str(value) for value in self.managed_product_uids], *self.product_ids]


class BulkLoadWdvWorkspaceRequest(BaseModel):
    selections: list[BulkLoadWdvWellSelection] = Field(min_length=1)


class BulkLoadWdvWellResult(BaseModel):
    managed_well_id: str
    managed_well_uid: CanonicalUuid7 | None = None
    well_name: str
    status: str
    loaded_product_ids: list[str] = Field(default_factory=list)


WDV_WORKSPACE_CONTRACT_VERSION = "wdv_workspace_v2"


class WdvWorkspaceLoadedWellSummary(BaseModel):
    managed_well_id: str
    managed_well_uid: CanonicalUuid7
    well_name: str
    loaded_product_ids: list[str] = Field(default_factory=list)
    loaded_product_count: int = 0
    viewer_curve_count: int = 0
    displayable_curve_count: int = 0
    loaded_curve_count: int = 0
    viewer_package_endpoint: str | None = None


class SetCommonDepthUnitRequest(BaseModel):
    common_depth_unit: Literal["m", "ft"]


class WdvWorkspaceStateResponse(BaseModel):
    service: str = "wdv_workspace_service"
    contract_version: str = WDV_WORKSPACE_CONTRACT_VERSION
    workspace_id: str = "default"
    revision: int = 0
    active_managed_well_id: str | None = None
    active_managed_well_uid: CanonicalUuid7 | None = None
    common_depth_unit: Literal["m", "ft"] = "m"
    loaded_wells: list[WdvWorkspaceLoadedWellSummary] = Field(default_factory=list)
    active_aoi: dict[str, Any] | None = None
    updated_at: str = Field(default_factory=utc_now_iso)


class BulkLoadWdvWorkspaceResponse(BaseModel):
    ok: bool = True
    action: str = "bulk_loaded_to_wdv"
    requested_count: int
    loaded_count: int
    already_loaded_count: int
    failed_count: int = 0
    results: list[BulkLoadWdvWellResult] = Field(default_factory=list)
    workspace: WdvWorkspaceStateResponse


class BulkUnloadWdvWorkspaceRequest(BaseModel):
    selections: list[BulkLoadWdvWellSelection] = Field(min_length=1)


class BulkUnloadWdvWellResult(BaseModel):
    managed_well_id: str
    managed_well_uid: CanonicalUuid7 | None = None
    well_name: str
    status: str
    unloaded_product_ids: list[str] = Field(default_factory=list)
    remaining_loaded_product_ids: list[str] = Field(default_factory=list)


class BulkUnloadWdvWorkspaceResponse(BaseModel):
    ok: bool = True
    action: str = "bulk_unloaded_from_wdv"
    requested_count: int
    unloaded_count: int
    already_unloaded_count: int
    failed_count: int = 0
    results: list[BulkUnloadWdvWellResult] = Field(default_factory=list)
    workspace: WdvWorkspaceStateResponse


class SetActiveWdvWellRequest(BaseModel):
    managed_well_uid: CanonicalUuid7 | None = None
    managed_well_id: str | None = None

    @model_validator(mode="after")
    def require_well_reference(self) -> "SetActiveWdvWellRequest":
        if not self.managed_well_uid and not str(self.managed_well_id or "").strip():
            raise ValueError("managed_well_uid or managed_well_id is required")
        return self

    @property
    def well_reference(self) -> str:
        return str(self.managed_well_uid or self.managed_well_id)


class UnloadManagedWellFromWdvRequest(BaseModel):
    managed_well_uid: CanonicalUuid7 | None = None
    managed_well_id: str | None = None
    managed_product_uids: list[CanonicalUuid7] = Field(default_factory=list)
    product_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_well_reference(self) -> "UnloadManagedWellFromWdvRequest":
        if not self.managed_well_uid and not str(self.managed_well_id or "").strip():
            raise ValueError("managed_well_uid or managed_well_id is required")
        return self

    @property
    def well_reference(self) -> str:
        return str(self.managed_well_uid or self.managed_well_id)

    @property
    def product_references(self) -> list[str]:
        return [*[str(value) for value in self.managed_product_uids], *self.product_ids]


class UnloadManagedWellFromWdvResult(BaseModel):
    managed_well_id: str
    unloaded_product_ids: list[str] = Field(default_factory=list)
    remaining_loaded_product_ids: list[str] = Field(default_factory=list)
    wdv_state: ManagedWdvState = ManagedWdvState.NOT_LOADED


class UnloadManagedWellFromWdvResponse(BaseModel):
    ok: bool = True
    action: str = "unloaded_from_wdv"
    result: UnloadManagedWellFromWdvResult
    record: ManagedWellRecord


class RemoveManagedDataFromMdpRequest(BaseModel):
    managed_well_uids: list[CanonicalUuid7] = Field(default_factory=list)
    managed_well_ids: list[str] = Field(default_factory=list)
    managed_product_uids: list[CanonicalUuid7] = Field(default_factory=list)
    product_ids: list[str] = Field(default_factory=list)

    @property
    def well_references(self) -> list[str]:
        return [*[str(value) for value in self.managed_well_uids], *self.managed_well_ids]

    @property
    def product_references(self) -> list[str]:
        return [*[str(value) for value in self.managed_product_uids], *self.product_ids]


class RemoveManagedDataFromMdpResult(BaseModel):
    removed_managed_well_ids: list[str] = Field(default_factory=list)
    removed_product_ids: list[str] = Field(default_factory=list)
    unloaded_managed_well_ids: list[str] = Field(default_factory=list)
    retained_msi_records: bool = True


class RemoveManagedDataFromMdpResponse(BaseModel):
    ok: bool = True
    action: str = "removed_from_mdp"
    result: RemoveManagedDataFromMdpResult
    records: list[ManagedWellRecord] = Field(default_factory=list)


class RestoreManagedDataToMdpResult(BaseModel):
    restored_managed_well_ids: list[str] = Field(default_factory=list)
    restored_product_ids: list[str] = Field(default_factory=list)
    already_visible_managed_well_ids: list[str] = Field(default_factory=list)
    already_visible_product_ids: list[str] = Field(default_factory=list)
    missing_source_candidate_ids: list[str] = Field(default_factory=list)


class RestoreManagedDataToMdpResponse(BaseModel):
    ok: bool = True
    action: str = "restored_to_mdp"
    result: RestoreManagedDataToMdpResult
    records: list[ManagedWellRecord] = Field(default_factory=list)


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


class WmdConsumerSelection(BaseModel):
    well_reference: str
    product_references: list[str] = Field(default_factory=list)


class ReconcileExportReferencesRequest(BaseModel):
    export_uid: CanonicalUuid7
    selections: list[WmdConsumerSelection] = Field(default_factory=list)


class ReleaseConsumerReferencesRequest(BaseModel):
    owner_uid: str


class ResetViewerSessionRequest(BaseModel):
    owner_id: str = "wbv-session:default"


class ReconcileStaleConsumerReferencesRequest(BaseModel):
    active_export_owner_ids: list[str] = Field(default_factory=list)
    active_saved_workspace_owner_ids: list[str] = Field(default_factory=list)
    active_wbv_owner_ids: list[str] = Field(default_factory=lambda: ["wbv-session:default"])


class WmdReferenceReconciliationResponse(BaseModel):
    owner_id: str | None = None
    touched_well_ids: list[str] = Field(default_factory=list)
    released_binding_count: int = 0
    acquired_binding_count: int = 0
