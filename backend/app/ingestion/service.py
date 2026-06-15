"""Well Log Source Ingestion service boundary."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.inventory.models import (
    ManagedInventoryLifecycleState,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
)
from app.inventory.service import ManagedWellInventoryService

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
    WellFolderCandidate,
    WellFolderScanRequest,
    WellFolderScanResponse,
    WellFolderScanSummary,
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


    def scan_well_folder(self, request: WellFolderScanRequest) -> WellFolderScanResponse:
        parent_path = Path(request.parent_path).expanduser().resolve()
        if not parent_path.exists():
            raise SourceRegistrationError(f"Well folder does not exist: {parent_path}")
        if not parent_path.is_dir():
            raise SourceRegistrationError(f"Well folder path is not a directory: {parent_path}")

        files = self._iter_well_folder_files(parent_path, request.include_subfolders)
        summary = WellFolderScanSummary(total_files_seen=len(files))
        candidates: list[WellFolderCandidate] = []

        for file_path in files[: request.max_files]:
            detection = self.detect_format(
                FormatDetectionRequest(
                    file_name=file_path.name,
                    original_path=str(file_path),
                    metadata=request.metadata,
                )
            )
            candidate = self._build_folder_candidate(parent_path, file_path, detection)
            candidates.append(candidate)
            self._add_candidate_to_summary(summary, candidate)

        if len(files) > request.max_files:
            summary.skipped_count = len(files) - request.max_files

        summary.candidate_count = len(candidates)
        notes = [
            "Backend-owned folder scan only; no managed inventory records were created.",
            "Review and approval are required before registration/indexing/viewer-package generation.",
        ]
        if summary.skipped_count:
            notes.append(f"Scan stopped at max_files={request.max_files}; {summary.skipped_count} files were skipped.")

        return WellFolderScanResponse(
            parent_path=str(parent_path),
            include_subfolders=request.include_subfolders,
            summary=summary,
            candidates=candidates,
            notes=notes,
        )

    def _iter_well_folder_files(self, parent_path: Path, include_subfolders: bool) -> list[Path]:
        iterator = parent_path.rglob("*") if include_subfolders else parent_path.iterdir()
        files: list[Path] = []
        for item in iterator:
            if not item.is_file():
                continue
            if any(part.startswith(".") for part in item.relative_to(parent_path).parts):
                continue
            files.append(item)
        return sorted(files, key=lambda item: item.relative_to(parent_path).as_posix().lower())

    def _build_folder_candidate(
        self,
        parent_path: Path,
        file_path: Path,
        detection: FormatDetectionResult,
    ) -> WellFolderCandidate:
        relative_path = file_path.relative_to(parent_path).as_posix()
        candidate_kind, candidate_role, review_required, reasons = self._classify_folder_candidate(detection)
        digest = hashlib.sha256(str(file_path).encode("utf-8")).hexdigest()[:16]
        return WellFolderCandidate(
            candidate_id=f"well-folder-candidate:{digest}",
            relative_path=relative_path,
            file_name=file_path.name,
            original_path=str(file_path),
            byte_size=file_path.stat().st_size,
            detected_format=detection.detected_format,
            source_category=detection.source_category,
            confidence=detection.confidence,
            adapter_id=detection.adapter_id,
            adapter_status=detection.adapter_status,
            is_supported=detection.is_supported,
            candidate_kind=candidate_kind,
            candidate_role=candidate_role,
            classification_source="backend_ingestion_adapter_registry",
            classification_reasons=[*detection.reasons, *reasons],
            review_required=review_required,
            metadata={"parent_folder_relative_path": str(Path(relative_path).parent)},
        )

    def _classify_folder_candidate(self, detection: FormatDetectionResult) -> tuple[str, str, bool, list[str]]:
        source_format = detection.detected_format
        if source_format == WellLogSourceFormat.LAS:
            return "digital_log_source", "numeric_curve_las", False, ["LAS can be parsed as a numeric curve source."]
        if source_format == WellLogSourceFormat.DLIS:
            return "digital_log_source", "frame_channel_dlis", True, ["DLIS is identified but adapter implementation is planned."]
        if source_format == WellLogSourceFormat.CGM:
            return "raster_or_vector_log", "vector_log_cgm", True, ["CGM is identified as a future vector/raster log artifact."]
        if source_format == WellLogSourceFormat.TIFF:
            return "raster_log_artifact", "raster_log_tiff", True, ["TIFF is identified as a raster log/image artifact candidate."]
        if source_format == WellLogSourceFormat.PDF:
            return "supporting_document_or_raster_log", "pdf_document_or_field_print", True, ["PDF requires review to separate reports from raster log field prints."]
        return "unknown", "review_required_unknown", True, ["No supported well-log source adapter matched this file."]

    def _add_candidate_to_summary(self, summary: WellFolderScanSummary, candidate: WellFolderCandidate) -> None:
        if candidate.detected_format == WellLogSourceFormat.LAS:
            summary.las_count += 1
        elif candidate.detected_format == WellLogSourceFormat.DLIS:
            summary.dlis_count += 1
        elif candidate.detected_format in {WellLogSourceFormat.CGM, WellLogSourceFormat.TIFF}:
            summary.raster_log_count += 1
        elif candidate.detected_format == WellLogSourceFormat.PDF:
            summary.document_count += 1
        else:
            summary.unknown_count += 1
        if candidate.review_required:
            summary.review_required_count += 1

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
