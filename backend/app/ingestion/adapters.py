"""Well Log Source Ingestion adapter registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import (
    FormatDetectionRequest,
    FormatDetectionResult,
    IngestionAdapterStatus,
    IngestionCapability,
    SupportedIngestionFormat,
    WellLogSourceCategory,
    WellLogSourceFormat,
)


@dataclass(frozen=True)
class IngestionAdapter:
    adapter_id: str
    source_format: WellLogSourceFormat
    source_category: WellLogSourceCategory
    extensions: tuple[str, ...]
    status: IngestionAdapterStatus
    capabilities: tuple[IngestionCapability, ...]
    notes: tuple[str, ...] = ()

    def supported_contract(self) -> SupportedIngestionFormat:
        return SupportedIngestionFormat(
            source_format=self.source_format,
            source_category=self.source_category,
            adapter_id=self.adapter_id,
            adapter_status=self.status,
            capabilities=list(self.capabilities),
            notes=list(self.notes),
        )

    def detect(self, request: FormatDetectionRequest) -> FormatDetectionResult | None:
        candidate = _candidate_name(request)
        if not candidate:
            return None
        suffix = Path(candidate).suffix.lower().lstrip(".")
        if suffix not in self.extensions:
            return None
        return FormatDetectionResult(
            detected_format=self.source_format,
            source_category=self.source_category,
            confidence=0.95,
            detection_source="file_extension",
            adapter_id=self.adapter_id,
            adapter_status=self.status,
            is_supported=True,
            reasons=[f"Matched .{suffix} extension."],
            capabilities=list(self.capabilities),
        )


def _candidate_name(request: FormatDetectionRequest) -> str | None:
    if request.file_name:
        return request.file_name
    if request.original_path:
        return Path(request.original_path).name
    return None


BASE_DETECTION_CAPABILITY = (IngestionCapability.DETECT_FORMAT, IngestionCapability.REGISTER_SOURCE)

ADAPTERS: tuple[IngestionAdapter, ...] = (
    IngestionAdapter(
        adapter_id="las_numeric_curve_adapter_v1",
        source_format=WellLogSourceFormat.LAS,
        source_category=WellLogSourceCategory.NUMERIC_CURVE,
        extensions=("las",),
        status=IngestionAdapterStatus.ACTIVE,
        capabilities=BASE_DETECTION_CAPABILITY
        + (IngestionCapability.EXTRACT_METADATA, IngestionCapability.EXTRACT_CURVE_INVENTORY),
        notes=("First concrete numeric-curve adapter. Parses LAS headers and curve inventory through backend-owned ingestion services.",),
    ),
    IngestionAdapter(
        adapter_id="dlis_frame_channel_adapter_v1",
        source_format=WellLogSourceFormat.DLIS,
        source_category=WellLogSourceCategory.FRAME_CHANNEL,
        extensions=("dlis",),
        status=IngestionAdapterStatus.PLANNED,
        capabilities=BASE_DETECTION_CAPABILITY,
        notes=("Future frame/channel/run adapter. Do not force DLIS into a LAS-only model.",),
    ),
    IngestionAdapter(
        adapter_id="cgm_vector_log_adapter_v1",
        source_format=WellLogSourceFormat.CGM,
        source_category=WellLogSourceCategory.VECTOR_LOG,
        extensions=("cgm",),
        status=IngestionAdapterStatus.PLANNED,
        capabilities=BASE_DETECTION_CAPABILITY,
        notes=("Future raster/vector log artifact adapter, not numeric curve extraction by default.",),
    ),
    IngestionAdapter(
        adapter_id="tiff_raster_log_adapter_v1",
        source_format=WellLogSourceFormat.TIFF,
        source_category=WellLogSourceCategory.RASTER_LOG,
        extensions=("tif", "tiff"),
        status=IngestionAdapterStatus.PLANNED,
        capabilities=BASE_DETECTION_CAPABILITY,
        notes=("Future raster log/image artifact adapter with optional depth calibration.",),
    ),
    IngestionAdapter(
        adapter_id="pdf_log_document_adapter_v1",
        source_format=WellLogSourceFormat.PDF,
        source_category=WellLogSourceCategory.DOCUMENT,
        extensions=("pdf",),
        status=IngestionAdapterStatus.PLANNED,
        capabilities=BASE_DETECTION_CAPABILITY,
        notes=("Future document/raster log path for PDF field prints and supporting documents.",),
    ),
)


class IngestionAdapterRegistry:
    def __init__(self, adapters: tuple[IngestionAdapter, ...] = ADAPTERS) -> None:
        self._adapters = adapters

    def list_supported_formats(self) -> list[SupportedIngestionFormat]:
        return [adapter.supported_contract() for adapter in self._adapters]

    def detect_format(self, request: FormatDetectionRequest) -> FormatDetectionResult:
        for adapter in self._adapters:
            result = adapter.detect(request)
            if result is not None:
                return result
        return FormatDetectionResult(
            detected_format=WellLogSourceFormat.UNKNOWN,
            source_category=WellLogSourceCategory.UNKNOWN,
            confidence=0.0,
            detection_source="none",
            adapter_id="unknown_source_review_adapter_v1",
            adapter_status=IngestionAdapterStatus.STUB,
            is_supported=False,
            reasons=["No supported file extension or detection hint matched."],
            capabilities=[IngestionCapability.DETECT_FORMAT, IngestionCapability.REGISTER_SOURCE],
        )
