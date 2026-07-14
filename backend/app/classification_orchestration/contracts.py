"""Unified contracts for backend-owned curve classification orchestration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class CurveClassificationRequest:
    """Schema-stable evidence envelope for one source curve.

    Raw source values are preserved.  Normalisation is performed by individual
    resolvers for lookup only and must not overwrite these fields.
    """

    source_mnemonic: str
    curve_id: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    source_curve_index: Optional[int] = None
    source_kind: Optional[str] = None
    source_uid: Optional[str] = None
    source_checksum: Optional[str] = None
    logical_file_id: Optional[str] = None
    frame_id: Optional[str] = None
    channel_id: Optional[str] = None
    tool_name: Optional[str] = None
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClassificationEvidence:
    evidence_type: str
    source: str
    summary: str
    weight: Optional[float] = None
    record_id: Optional[str] = None
    authoritative: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_type": self.evidence_type,
            "source": self.source,
            "summary": self.summary,
            "weight": self.weight,
            "record_id": self.record_id,
            "authoritative": self.authoritative,
        }


@dataclass(frozen=True)
class ClassificationCandidate:
    curve_family_key: str
    curve_family_label: str
    confidence: float
    evidence: tuple[ClassificationEvidence, ...] = ()
    conflicts: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "curve_family_key": self.curve_family_key,
            "curve_family_label": self.curve_family_label,
            "confidence": self.confidence,
            "evidence": [item.as_dict() for item in self.evidence],
            "conflicts": list(self.conflicts),
        }


@dataclass(frozen=True)
class CurveClassificationDecision:
    """Unified orchestration result.

    This contract is additive in Phase 1 and is not yet persisted by existing
    production ingestion paths.
    """

    curve_id: Optional[str]
    source_curve_index: Optional[int]
    source_mnemonic: str
    curve_family_key: str
    curve_family_label: str
    classification_status: str
    confidence: float
    decision_source: str
    review_required: bool
    evidence: tuple[ClassificationEvidence, ...] = ()
    conflicts: tuple[str, ...] = ()
    candidates: tuple[ClassificationCandidate, ...] = ()
    classifier_version: str = "classification-orchestrator-phase1"
    policy_version: str = "classification-orchestration-policy-v1"
    review_provenance: Mapping[str, Any] = field(default_factory=dict)
    legacy_payload: Mapping[str, Any] = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return self.classification_status == "resolved" and not self.review_required

    def as_dict(self) -> dict[str, Any]:
        return {
            "curve_id": self.curve_id,
            "source_curve_index": self.source_curve_index,
            "source_mnemonic": self.source_mnemonic,
            "curve_family_key": self.curve_family_key,
            "curve_family_label": self.curve_family_label,
            "classification_status": self.classification_status,
            "confidence": self.confidence,
            "decision_source": self.decision_source,
            "review_required": self.review_required,
            "evidence": [item.as_dict() for item in self.evidence],
            "conflicts": list(self.conflicts),
            "candidates": [item.as_dict() for item in self.candidates],
            "classifier_version": self.classifier_version,
            "policy_version": self.policy_version,
            "review_provenance": dict(self.review_provenance),
            "legacy_payload": dict(self.legacy_payload),
        }
