"""
MultiViewer Well Log Viewer — LAS Import Service
WL-BUILD-001 scaffold

Backend owns all LAS parsing and curve extraction.
Frontend must never parse LAS files or construct curve samples independently.

This service is a placeholder skeleton for WL-BUILD-001.
Full LAS parsing (e.g. via lasio) will be wired in a later sprint.
"""

from __future__ import annotations

from typing import Any, List, Optional

from backend.app.knowledge.managed_repository import ManagedKRRepository
from backend.app.knowledge.runtime_classification_service import (
    CurveClassificationBatchResult,
    CurveClassificationInput,
    RuntimeCurveClassificationService,
)
from backend.app.knowledge.runtime_resolver import ApprovedKnowledgeRuntimeResolver

from .models import CurveMetadata, MsiSourceRef, Well


class LasImportError(Exception):
    """Raised when LAS import fails at any stage."""


class LasCurveInventoryClassificationResult:
    """Backend-owned classified LAS curve inventory contract.

    This object is produced from LAS curve metadata after parsing.  It is the
    integration boundary between LAS import/session inventory and KR runtime
    classification.  It does not parse LAS, does not mutate KR, and does not
    use candidate knowledge because classification is delegated to
    RuntimeCurveClassificationService.
    """

    def __init__(
        self,
        curve_metadata: List[CurveMetadata],
        classification_batch: CurveClassificationBatchResult,
    ) -> None:
        if len(curve_metadata) != classification_batch.curve_count:
            raise LasImportError(
                "Curve metadata and classification result counts do not match."
            )
        self.curve_metadata = list(curve_metadata)
        self.classification_batch = classification_batch

    @property
    def curve_count(self) -> int:
        return self.classification_batch.curve_count

    @property
    def resolved_count(self) -> int:
        return self.classification_batch.resolved_count

    @property
    def unknown_count(self) -> int:
        return self.classification_batch.unknown_count

    @property
    def review_required_count(self) -> int:
        return self.classification_batch.review_required_count

    @property
    def knowledge_policy(self) -> dict[str, Any]:
        return dict(self.classification_batch.knowledge_policy)

    def as_dict(self) -> dict[str, Any]:
        curves: list[dict[str, Any]] = []
        for metadata, classification in zip(
            self.curve_metadata,
            self.classification_batch.classifications,
        ):
            curves.append(
                {
                    "metadata": {
                        "mnemonic": metadata.mnemonic,
                        "unit": metadata.unit,
                        "description": metadata.description,
                        "null_value": metadata.null_value,
                    },
                    "classification": classification.as_dict(),
                }
            )
        return {
            "curve_count": self.curve_count,
            "resolved_count": self.resolved_count,
            "unknown_count": self.unknown_count,
            "review_required_count": self.review_required_count,
            "knowledge_policy": self.knowledge_policy,
            "curves": curves,
        }


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
    - Classifying extracted curve metadata through approved-only KR runtime

    WL-BUILD-001: parsing skeleton only.
    KR-LAS-1: adds the classification bridge for extracted curve metadata.
    LAS parsing implementation (lasio integration) remains deferred to a later
    sprint; frontend still must not parse LAS.
    """

    def __init__(
        self,
        classification_service: Optional[RuntimeCurveClassificationService] = None,
    ) -> None:
        self._classification_service = (
            classification_service
            if classification_service is not None
            else RuntimeCurveClassificationService(
                ApprovedKnowledgeRuntimeResolver(ManagedKRRepository())
            )
        )

    def classify_curve_metadata(
        self,
        curve_metadata: List[CurveMetadata],
    ) -> LasCurveInventoryClassificationResult:
        """Classify extracted LAS curve metadata through approved-only KR.

        This method is the KR-LAS-1 backend boundary.  It can be called by the
        future LAS parser after curve metadata has been extracted.  Input order
        is preserved so downstream MSI/session inventory can correlate each
        classification to its source curve.

        Candidate/rejected/deprecated knowledge cannot influence the result
        because RuntimeCurveClassificationService depends on
        ApprovedKnowledgeRuntimeResolver.
        """
        if curve_metadata is None:
            raise LasImportError("curve_metadata is required")

        inputs: list[CurveClassificationInput] = []
        for index, metadata in enumerate(curve_metadata):
            mnemonic = (metadata.mnemonic or "").strip()
            inputs.append(
                CurveClassificationInput(
                    curve_id=mnemonic or f"las_curve_{index}",
                    source_mnemonic=mnemonic,
                    unit=metadata.unit,
                    description=metadata.description,
                    source_curve_index=index,
                    context={"null_value": metadata.null_value},
                )
            )

        batch = self._classification_service.classify_curves(inputs)
        return LasCurveInventoryClassificationResult(
            curve_metadata=list(curve_metadata),
            classification_batch=batch,
        )

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
