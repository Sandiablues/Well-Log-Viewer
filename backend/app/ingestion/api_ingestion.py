"""Well Log Source Ingestion API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from .models import (
    FormatDetectionRequest,
    FormatDetectionResult,
    IngestionHealth,
    SourceRegistrationRequest,
    SourceRegistrationResponse,
    SupportedIngestionFormat,
)
from .service import SourceRegistrationError, WellLogSourceIngestionService

router = APIRouter(prefix="/api/wlv/ingestion", tags=["wlv-ingestion"])
_service = WellLogSourceIngestionService()


@router.get("/health", response_model=IngestionHealth, summary="Well Log Source Ingestion health")
def health() -> IngestionHealth:
    return _service.health()


@router.get(
    "/supported-formats",
    response_model=list[SupportedIngestionFormat],
    summary="List supported well log source formats",
)
def supported_formats() -> list[SupportedIngestionFormat]:
    return _service.supported_formats()


@router.post(
    "/detect-format",
    response_model=FormatDetectionResult,
    summary="Detect a well log source file format",
)
def detect_format(request: FormatDetectionRequest) -> FormatDetectionResult:
    return _service.detect_format(request)


@router.post(
    "/sources/register",
    response_model=SourceRegistrationResponse,
    summary="Register a well log source through the format-neutral ingestion service",
)
def register_source(request: SourceRegistrationRequest) -> SourceRegistrationResponse:
    try:
        return _service.register_source(request)
    except SourceRegistrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
