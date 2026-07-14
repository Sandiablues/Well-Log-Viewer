"""Adapters from current production classifiers into the unified Phase 1 contract."""
from __future__ import annotations

from dataclasses import asdict
from typing import Protocol

from app.classification.well_log_classifier import classify_well_log_curve
from app.knowledge.runtime_classification_service import (
    CurveClassificationInput,
    RuntimeCurveClassificationService,
)

from .contracts import ClassificationEvidence, CurveClassificationDecision, CurveClassificationRequest
from .family_registry import CanonicalCurveFamilyRegistry


class ClassificationEngine(Protocol):
    def classify_curve(self, request: CurveClassificationRequest) -> CurveClassificationDecision: ...


class DeterministicWellLogLegacyAdapter:
    """Adapter for the classifier still used by managed inventory ingestion."""

    def __init__(self, family_registry: CanonicalCurveFamilyRegistry) -> None:
        self._family_registry = family_registry

    def classify_curve(self, request: CurveClassificationRequest) -> CurveClassificationDecision:
        context_terms = [request.source_kind, request.tool_name]
        context_terms.extend(str(value) for value in request.context.values() if value is not None)
        result = classify_well_log_curve(
            mnemonic=request.source_mnemonic,
            description=request.description,
            unit=request.unit,
            context_terms=context_terms,
        )
        canonical = self._family_registry.resolve(result.curve_family)
        if canonical is None:
            canonical = self._family_registry.unclassified()
            review_required = True
            status = "requires_review"
            conflicts = (f"Legacy family is not registered: {result.curve_family}",)
        else:
            review_required = result.review_required
            status = "requires_review" if review_required else "resolved"
            conflicts = ()
        confidence = {"high": 0.90, "medium": 0.75, "low": 0.40}.get(result.classification_confidence, 0.0)
        evidence = tuple(
            ClassificationEvidence(
                evidence_type="legacy_reason",
                source=result.classification_source,
                summary=reason,
            )
            for reason in result.classification_reasons
        )
        return CurveClassificationDecision(
            curve_id=request.curve_id,
            source_curve_index=request.source_curve_index,
            source_mnemonic=request.source_mnemonic,
            curve_family_key=canonical.family_key,
            curve_family_label=canonical.display_label,
            classification_status=status,
            confidence=confidence,
            decision_source=result.classification_source,
            review_required=review_required,
            evidence=evidence,
            conflicts=conflicts,
            legacy_payload=asdict(result),
        )


class RuntimeKrLegacyAdapter:
    """Adapter for the approved-KR runtime classifier used by LAS/source intake."""

    def __init__(self, service: RuntimeCurveClassificationService, family_registry: CanonicalCurveFamilyRegistry) -> None:
        self._service = service
        self._family_registry = family_registry

    def classify_curve(self, request: CurveClassificationRequest) -> CurveClassificationDecision:
        result = self._service.classify_curve(
            CurveClassificationInput(
                source_mnemonic=request.source_mnemonic,
                curve_id=request.curve_id,
                unit=request.unit,
                description=request.description,
                source_curve_index=request.source_curve_index,
                context=dict(request.context),
            )
        )
        canonical = self._family_registry.resolve(result.family)
        conflicts: tuple[str, ...] = ()
        if canonical is None:
            canonical = self._family_registry.unclassified()
            review_required = True
            status = "requires_review"
            conflicts = (f"Runtime KR family is not registered: {result.family}",) if result.family else ()
        else:
            review_required = result.requires_review
            status = "requires_review" if review_required else ("resolved" if result.resolved else "unknown")
        evidence = tuple(
            ClassificationEvidence(
                evidence_type="runtime_kr",
                source=result.resolution_source,
                summary=warning,
                record_id=result.knowledge_record_id,
            )
            for warning in result.warnings
        )
        return CurveClassificationDecision(
            curve_id=request.curve_id,
            source_curve_index=request.source_curve_index,
            source_mnemonic=request.source_mnemonic,
            curve_family_key=canonical.family_key,
            curve_family_label=canonical.display_label,
            classification_status=status,
            confidence=result.confidence,
            decision_source=result.resolution_source,
            review_required=review_required,
            evidence=evidence,
            conflicts=conflicts,
            legacy_payload=result.as_dict(),
        )
