"""Well Log Source Ingestion service boundary."""

from __future__ import annotations

from .adapters import IngestionAdapterRegistry
from .models import FormatDetectionRequest, FormatDetectionResult, IngestionHealth, SupportedIngestionFormat


class WellLogSourceIngestionService:
    def __init__(self, registry: IngestionAdapterRegistry | None = None) -> None:
        self._registry = registry or IngestionAdapterRegistry()

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
