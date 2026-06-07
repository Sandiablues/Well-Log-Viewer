"""
MultiViewer Well Log Viewer — LAS Import Service
WL-BUILD-001 scaffold

Backend owns all LAS parsing and curve extraction.
Frontend must never parse LAS files or construct curve samples independently.

This service is a placeholder skeleton for WL-BUILD-001.
Full LAS parsing (e.g. via lasio) will be wired in a later sprint.
"""

from __future__ import annotations

from typing import List, Optional

from .models import CurveMetadata, MsiSourceRef, Well


class LasImportError(Exception):
    """Raised when LAS import fails at any stage."""


class LasImportResult:
    """
    Value object returned by a successful LAS import.

    Populated by the backend parser; never constructed on the frontend.
    """

    def __init__(
        self,
        well: Well,
        curve_metadata: List[CurveMetadata],
        depth_unit: str,
        null_value: Optional[float],
        raw_header: dict,
    ) -> None:
        self.well = well
        self.curve_metadata = curve_metadata
        self.depth_unit = depth_unit
        self.null_value = null_value
        self.raw_header = raw_header


class LasImportService:
    """
    Backend-owned service responsible for:
    - Receiving a LAS source file (path or bytes)
    - Parsing well header and curve sections
    - Extracting curve metadata
    - Returning a LasImportResult for downstream MSI registration

    WL-BUILD-001: skeleton only.
    LAS parsing implementation (lasio integration) deferred to later sprint.
    """

    def import_from_path(self, file_path: str, source_ref: MsiSourceRef) -> LasImportResult:
        """
        Import a LAS file from a filesystem path.

        Args:
            file_path: Path to the LAS source file on the backend filesystem.
            source_ref: MSI source reference for this file, already registered
                        by the caller before invoking this service.

        Returns:
            LasImportResult containing well, curve metadata, and header info.

        Raises:
            LasImportError: If parsing fails for any reason.

        WL-BUILD-001: not yet implemented — raises NotImplementedError.
        """
        raise NotImplementedError(
            "LAS import not yet implemented. "
            "Wire lasio integration in the next sprint."
        )

    def import_from_bytes(self, file_bytes: bytes, source_ref: MsiSourceRef) -> LasImportResult:
        """
        Import a LAS file from raw bytes (e.g. from an upload stream).

        WL-BUILD-001: not yet implemented — raises NotImplementedError.
        """
        raise NotImplementedError(
            "LAS import from bytes not yet implemented."
        )
