"""Well Log Source Ingestion service boundary."""

from __future__ import annotations

from pathlib import Path

from backend.app.inventory.models import (
    ManagedInventoryLifecycleState,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
)
from backend.app.inventory.service import ManagedWellInventoryService

from .adapters import IngestionAdapterRegistry
from .las_adapter import LasAdapterError, LasSourceAdapter
from .models import (
    FormatDetectionRequest,
    FormatDetectionResult,
    IngestionHealth,
    NormalizedWellLogPackage,
    SourceRegistrationRequest,
    SourceRegistrationResponse,
    SupportedIngestionFormat,
    WellLogSourceFormat,
)


class SourceRegistrationError(ValueError):
    """Raised when a source cannot be registered through ingestion."""


class WellLogSourceIngestionService:
    def __init__(
        self,
        registry: IngestionAdapterRegistry | None = None,
        las_adapter: LasSourceAdapter | None = None,
        inventory_service: ManagedWellInventoryService | None = None,
    ) -> None:
        self._registry = registry or IngestionAdapterRegistry()
        self._las_adapter = las_adapter or LasSourceAdapter()
        self._inventory_service = inventory_service or ManagedWellInventoryService()

    def health(self) -> IngestionHealth:
        formats = self._registry.list_supported_formats()
        return IngestionHealth(
            adapter_count=len(formats),
            supported_formats=[item.source_format for item in formats],
        )

    def supported_formats(self) -> list[SupportedIngestionFormat]:
        return self._registry.list_supported_formats()

    def detect_format(self, request: FormatDetectionRequest) -> FormatDetectionResult:
        return self._registry.detect_format(request)

    def register_source(self, request: SourceRegistrationRequest) -> SourceRegistrationResponse:
        source_path = Path(request.original_path).expanduser().resolve()
        detection = self.detect_format(
            FormatDetectionRequest(
                file_name=source_path.name,
                original_path=str(source_path),
                metadata=request.metadata,
            )
        )
        detected_format = request.declared_format or detection.detected_format
        if detected_format != WellLogSourceFormat.LAS:
            raise SourceRegistrationError(
                f"Source registration is implemented for LAS in this block; detected {detected_format.value}."
            )
        try:
            package = self._las_adapter.parse_path(
                source_path,
                display_name=request.display_name,
                metadata=request.metadata,
            )
        except LasAdapterError as exc:
            raise SourceRegistrationError(str(exc)) from exc

        managed_record = None
        action = "parsed"
        notes = ["LAS parsed through format-neutral ingestion adapter."]
        if request.register_to_inventory:
            action, managed = self._register_package_in_inventory(package)
            managed_record = managed.model_dump(mode="json")
            notes.append("Managed Well Inventory registration completed through backend service boundary.")
        return SourceRegistrationResponse(
            ok=True,
            action=action,
            detected_format=WellLogSourceFormat.LAS,
            source_file=package.source_file,
            normalized_package=package,
            managed_record=managed_record,
            evidence=package.evidence,
            qaqc_summary=package.qaqc_summary,
            notes=notes,
        )

    def _register_package_in_inventory(self, package: NormalizedWellLogPackage) -> tuple[str, ManagedWellRecord]:
        checksum = package.source_file.checksum or package.source_file.source_file_id.replace("source:sha256:", "")
        managed_well_id = f"managed-well:las:{checksum[:16]}"
        lifecycle_state = ManagedInventoryLifecycleState.AVAILABLE
        source_ref = ManagedSourceReference(
            source_id=package.source_file.source_file_id,
            source_kind=ManagedSourceKind.LAS,
            display_name=package.source_file.display_name,
            original_path=package.source_file.original_path,
            file_name=package.source_file.file_name,
            file_format=package.source_file.source_format.value,
            checksum=package.source_file.checksum,
            metadata={
                "source_category": package.source_file.source_category.value,
                "adapter_id": package.metadata.get("adapter_id"),
                "curve_count": package.metadata.get("curve_count"),
                "sample_count": package.metadata.get("sample_count"),
                "null_value": package.metadata.get("null_value"),
                "normalized_package_id": package.package_id,
                "source_fingerprint_evidence": package.qaqc_summary.source_fingerprint_available,
                "ingestion_evidence_count": package.qaqc_summary.evidence_count,
                "ingestion_qaqc_error_count": package.qaqc_summary.error_count,
                "ingestion_qaqc_warning_count": package.qaqc_summary.warning_count,
                "ingestion_qaqc_summary": package.qaqc_summary.model_dump(mode="json"),
            },
        )
        record = ManagedWellRecord(
            managed_well_id=managed_well_id,
            well_id=package.well_id or managed_well_id,
            well_name=package.well_name or package.source_file.display_name,
            depth_unit=str(package.metadata.get("depth_unit") or "ft"),
            top_depth=package.metadata.get("top_depth"),
            base_depth=package.metadata.get("base_depth"),
            status=lifecycle_state,
            lifecycle_state=lifecycle_state,
            source_references=[source_ref],
            viewer_packages=[],
            tags=["las", "ingested-source"],
            metadata={
                "source_format": package.source_file.source_format.value,
                "source_fingerprint": package.metadata.get("source_fingerprint"),
                "curve_count": package.metadata.get("curve_count"),
                "curve_mnemonics": [curve.mnemonic for curve in package.curve_channels],
                "qaqc_findings": [finding.model_dump(mode="json") for finding in package.qaqc_findings],
                "ingestion_evidence": [item.model_dump(mode="json") for item in package.evidence],
                "ingestion_qaqc_summary": package.qaqc_summary.model_dump(mode="json"),
                "normalized_package": package.model_dump(mode="json"),
            },
            lifecycle_notes=["Registered from LAS ingestion adapter. Viewer package generation is deferred."],
        )
        return self._inventory_service.upsert_managed_record(record)
