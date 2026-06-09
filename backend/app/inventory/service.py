"""Managed Well Inventory service boundary."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from backend.app.wells.models import WellMultitrackV1
from backend.app.wells.seed_repository import SeedWellRepository

from .models import (
    InventoryValidationSeverity,
    ManagedInventoryHealth,
    ManagedInventoryLifecycleState,
    ManagedInventoryMaintenanceStatus,
    ManagedInventoryStatus,
    ManagedInventoryValidationIssue,
    ManagedInventoryValidationResult,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
    RegisterSeedWellResponse,
    ViewerPackageReference,
    utc_now_iso,
)
from .repository import ManagedWellInventoryRepository, ManagedWellNotFoundError


class ManagedWellInventoryService:
    def __init__(
        self,
        repository: ManagedWellInventoryRepository | None = None,
        seed_repository: SeedWellRepository | None = None,
    ) -> None:
        self.repository = repository or ManagedWellInventoryRepository()
        self.seed_repository = seed_repository or SeedWellRepository()

    def health(self) -> ManagedInventoryHealth:
        return ManagedInventoryHealth()

    def status(self) -> ManagedInventoryStatus:
        snapshot = self.repository.snapshot()
        records = snapshot.records
        return ManagedInventoryStatus(
            ok=True,
            storage_backend="local_json",
            storage_path=str(self.repository.storage_path),
            schema_version=snapshot.schema_version,
            managed_well_count=len(records),
            viewer_package_count=sum(len(record.viewer_packages) for record in records),
            source_reference_count=sum(len(record.source_references) for record in records),
            lifecycle_counts=self._lifecycle_counts(records),
        )

    def maintenance_status(self) -> ManagedInventoryMaintenanceStatus:
        status = self.status()
        return ManagedInventoryMaintenanceStatus(
            ok=True,
            storage_backend=status.storage_backend,
            storage_path=status.storage_path,
            managed_well_count=status.managed_well_count,
            lifecycle_counts=status.lifecycle_counts,
            notes=[
                "Non-destructive maintenance status only.",
                "Use inventory validation before future destructive lifecycle actions are enabled.",
                "Local JSON storage is isolated behind the repository boundary for later DB/object-storage migration.",
            ],
        )

    def list_wells(self) -> list[ManagedWellRecord]:
        return self.repository.list_records()

    def get_well(self, managed_well_id: str) -> ManagedWellRecord:
        return self.repository.get_record(managed_well_id)

    def list_viewer_packages(self) -> list[ViewerPackageReference]:
        packages: list[ViewerPackageReference] = []
        for record in self.repository.list_records():
            packages.extend(record.viewer_packages)
        return packages

    def upsert_managed_record(self, record: ManagedWellRecord) -> tuple[str, ManagedWellRecord]:
        """Upsert a managed well record built by another backend service.

        This preserves the inventory service as the write boundary while keeping
        ingestion/import logic outside the API route layer.
        """
        record.updated_at = utc_now_iso()
        return self.repository.upsert_record(record)

    def register_seed_well(self, well_id: str = SeedWellRepository.WELL_ID) -> RegisterSeedWellResponse:
        well = self.seed_repository.get_well(well_id)
        viewer_package = self.seed_repository.get_viewer_package(well_id)
        managed_well_id = f"managed-well:{well.well_id}"
        now = datetime.now(timezone.utc).isoformat()

        existing_created_at = now
        try:
            existing = self.repository.get_record(managed_well_id)
            existing_created_at = existing.created_at
        except ManagedWellNotFoundError:
            existing = None

        lifecycle_state = ManagedInventoryLifecycleState.VIEWER_READY
        record = ManagedWellRecord(
            managed_well_id=managed_well_id,
            well_id=well.well_id,
            well_name=well.well_name,
            wellbore_id=well.wellbore_id,
            wellbore_name=well.wellbore_name,
            operator=well.operator,
            field=well.field,
            country=well.country,
            depth_unit=well.depth_unit.value if hasattr(well.depth_unit, "value") else str(well.depth_unit),
            top_depth=well.depth_range.min,
            base_depth=well.depth_range.max,
            status=lifecycle_state,
            lifecycle_state=lifecycle_state,
            source_references=[
                ManagedSourceReference(
                    source_id=f"source:{well.well_id}:seed-las",
                    source_kind=ManagedSourceKind.SEED,
                    display_name=well.source_file or f"{well.well_name} seed source",
                    file_name=well.source_file,
                    file_format="LAS",
                    metadata={"source": "prototype_seed_repository"},
                )
            ],
            viewer_packages=[self._viewer_package_reference(viewer_package)],
            tags=["seed", "forge"],
            metadata={
                "api_number": well.api_number,
                "datum": well.datum,
                "kb_elevation": well.kb_elevation,
                "ground_elevation": well.ground_elevation,
            },
            lifecycle_notes=["Registered from deterministic seed repository."],
            created_at=existing_created_at,
            updated_at=now,
        )
        action, saved = self.repository.upsert_record(record)
        return RegisterSeedWellResponse(ok=True, action=action, record=saved)

    def validate_inventory(self) -> ManagedInventoryValidationResult:
        snapshot = self.repository.snapshot()
        records = snapshot.records
        issues: list[ManagedInventoryValidationIssue] = []

        managed_ids = Counter(record.managed_well_id for record in records)
        well_ids = Counter(record.well_id for record in records)
        viewer_package_ids = Counter(
            package.viewer_package_id for record in records for package in record.viewer_packages
        )
        source_ids = Counter(source.source_id for record in records for source in record.source_references)

        for managed_well_id, count in managed_ids.items():
            if count > 1:
                issues.append(self._issue("error", "duplicate_managed_well_id", f"Duplicate managed_well_id appears {count} times.", managed_well_id, "managed_well_id"))
        for well_id, count in well_ids.items():
            if count > 1:
                issues.append(self._issue("warning", "duplicate_well_id", f"well_id appears in {count} managed records.", well_id, "well_id"))
        for package_id, count in viewer_package_ids.items():
            if count > 1:
                issues.append(self._issue("error", "duplicate_viewer_package_id", f"viewer_package_id appears {count} times.", None, "viewer_package_id"))
        for source_id, count in source_ids.items():
            if count > 1:
                issues.append(self._issue("warning", "duplicate_source_id", f"source_id appears {count} times.", None, "source_id"))

        for record in records:
            issues.extend(self._validate_record(record))

        error_count = sum(1 for issue in issues if issue.severity == InventoryValidationSeverity.ERROR)
        warning_count = sum(1 for issue in issues if issue.severity == InventoryValidationSeverity.WARNING)
        return ManagedInventoryValidationResult(
            ok=error_count == 0,
            storage_backend="local_json",
            storage_path=str(self.repository.storage_path),
            schema_version=snapshot.schema_version,
            managed_well_count=len(records),
            viewer_package_count=sum(len(record.viewer_packages) for record in records),
            source_reference_count=sum(len(record.source_references) for record in records),
            lifecycle_counts=self._lifecycle_counts(records),
            issue_count=len(issues),
            error_count=error_count,
            warning_count=warning_count,
            issues=issues,
        )

    @staticmethod
    def _viewer_package_reference(viewer_package: WellMultitrackV1) -> ViewerPackageReference:
        return ViewerPackageReference(
            viewer_package_id=f"viewer-package:{viewer_package.representation_id}",
            viewer_package_version=viewer_package.viewer_package_version,
            dataset_id=viewer_package.dataset_id,
            representation_id=viewer_package.representation_id,
            well_id=viewer_package.well_id,
            endpoint=f"/api/wlv/wells/{viewer_package.well_id}/viewer-package",
            status=ManagedInventoryLifecycleState.VIEWER_READY,
        )

    @staticmethod
    def _lifecycle_counts(records: list[ManagedWellRecord]) -> dict[str, int]:
        counts = Counter(record.lifecycle_state.value for record in records)
        return dict(sorted(counts.items()))

    @staticmethod
    def _issue(
        severity: str,
        code: str,
        message: str,
        managed_well_id: str | None = None,
        field: str | None = None,
    ) -> ManagedInventoryValidationIssue:
        return ManagedInventoryValidationIssue(
            severity=InventoryValidationSeverity(severity),
            code=code,
            message=message,
            managed_well_id=managed_well_id,
            field=field,
        )

    def _validate_record(self, record: ManagedWellRecord) -> list[ManagedInventoryValidationIssue]:
        issues: list[ManagedInventoryValidationIssue] = []
        if not record.managed_well_id.strip():
            issues.append(self._issue("error", "missing_managed_well_id", "Managed well id is required.", field="managed_well_id"))
        if not record.well_id.strip():
            issues.append(self._issue("error", "missing_well_id", "Well id is required.", record.managed_well_id, "well_id"))
        if not record.well_name.strip():
            issues.append(self._issue("error", "missing_well_name", "Well name is required.", record.managed_well_id, "well_name"))
        if record.top_depth is not None and record.base_depth is not None and record.top_depth >= record.base_depth:
            issues.append(self._issue("error", "invalid_depth_range", "Top depth must be less than base depth.", record.managed_well_id, "depth_range"))
        if record.status != record.lifecycle_state:
            issues.append(self._issue("warning", "status_lifecycle_mismatch", "status and lifecycle_state should remain aligned.", record.managed_well_id, "status"))
        if record.lifecycle_state == ManagedInventoryLifecycleState.VIEWER_READY and not record.viewer_packages:
            issues.append(self._issue("error", "viewer_ready_without_package", "viewer_ready records require at least one viewer package.", record.managed_well_id, "viewer_packages"))
        if not record.source_references:
            issues.append(self._issue("warning", "missing_source_reference", "Managed record has no source references.", record.managed_well_id, "source_references"))
        for source in record.source_references:
            if not source.source_id.strip():
                issues.append(self._issue("error", "missing_source_id", "Source reference id is required.", record.managed_well_id, "source_id"))
            if not source.display_name.strip():
                issues.append(self._issue("warning", "missing_source_display_name", "Source display name is empty.", record.managed_well_id, "source_references.display_name"))
            if source.source_kind == ManagedSourceKind.LAS and not source.checksum:
                issues.append(self._issue("warning", "las_source_missing_checksum", "LAS source references should retain a source fingerprint/checksum.", record.managed_well_id, "source_references.checksum"))
        if "ingested-source" in record.tags or record.metadata.get("source_format") == "las":
            if not record.metadata.get("source_fingerprint"):
                issues.append(self._issue("warning", "ingested_source_missing_fingerprint", "Ingested sources should retain source fingerprint evidence.", record.managed_well_id, "metadata.source_fingerprint"))
            if not record.metadata.get("ingestion_evidence"):
                issues.append(self._issue("warning", "ingested_source_missing_evidence", "Ingested sources should retain extraction evidence records.", record.managed_well_id, "metadata.ingestion_evidence"))
            if not record.metadata.get("ingestion_qaqc_summary"):
                issues.append(self._issue("warning", "ingested_source_missing_qaqc_summary", "Ingested sources should retain an ingestion QAQC summary.", record.managed_well_id, "metadata.ingestion_qaqc_summary"))
        for package in record.viewer_packages:
            if not package.viewer_package_id.strip():
                issues.append(self._issue("error", "missing_viewer_package_id", "Viewer package id is required.", record.managed_well_id, "viewer_package_id"))
            if package.well_id != record.well_id:
                issues.append(self._issue("error", "viewer_package_well_mismatch", "Viewer package well_id does not match managed record well_id.", record.managed_well_id, "viewer_packages.well_id"))
            if not package.endpoint.startswith("/api/wlv/"):
                issues.append(self._issue("warning", "non_wlv_viewer_package_endpoint", "Viewer package endpoint should be a WLV API path.", record.managed_well_id, "viewer_packages.endpoint"))
        return issues
