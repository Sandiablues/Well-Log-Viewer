"""Unified additive shadow result for curve-family and domain governance.

This contract does not replace production persistence in Phase 12. It composes:
- the governed curve-family decision-gate result;
- measurement-domain placement;
- destination ownership;
- evidence, conflicts, review state, and versioning.

A valid non-WDV channel may be fully placed without a curve family. WDV-eligible
channels still require a resolved family before the unified result is considered
fully resolved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import CurveClassificationDecision, CurveClassificationRequest
from .domain_governance import DomainPlacementDecision, MeasurementDomainResolver

UNIFIED_RESULT_CONTRACT_VERSION = "curve-classification-unified-shadow-v1"


@dataclass(frozen=True)
class UnifiedCurveClassificationResult:
    curve_id: str | None
    source_curve_index: int | None
    source_mnemonic: str

    curve_family_key: str | None
    curve_family_label: str | None
    family_status: str
    family_confidence: float
    family_decision_source: str

    measurement_domain_key: str
    measurement_domain_label: str
    destination_key: str
    destination_owner: str
    display_in_wdv: bool
    domain_status: str
    domain_confidence: float
    domain_decision_source: str

    overall_status: str
    review_required: bool
    review_reason: str | None

    family_evidence: tuple[Mapping[str, Any], ...] = ()
    family_conflicts: tuple[str, ...] = ()
    family_candidates: tuple[Mapping[str, Any], ...] = ()
    domain_evidence: tuple[str, ...] = ()

    classifier_version: str = "classification-orchestrator-phase12-shadow"
    policy_version: str = "classification-orchestration-policy-v1"
    ontology_version: str = "measurement-domain-ontology-v1"
    contract_version: str = UNIFIED_RESULT_CONTRACT_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "curve_id": self.curve_id,
            "source_curve_index": self.source_curve_index,
            "source_mnemonic": self.source_mnemonic,
            "curve_family_key": self.curve_family_key,
            "curve_family_label": self.curve_family_label,
            "family_status": self.family_status,
            "family_confidence": self.family_confidence,
            "family_decision_source": self.family_decision_source,
            "measurement_domain_key": self.measurement_domain_key,
            "measurement_domain_label": self.measurement_domain_label,
            "destination_key": self.destination_key,
            "destination_owner": self.destination_owner,
            "display_in_wdv": self.display_in_wdv,
            "domain_status": self.domain_status,
            "domain_confidence": self.domain_confidence,
            "domain_decision_source": self.domain_decision_source,
            "overall_status": self.overall_status,
            "review_required": self.review_required,
            "review_reason": self.review_reason,
            "family_evidence": [dict(item) for item in self.family_evidence],
            "family_conflicts": list(self.family_conflicts),
            "family_candidates": [dict(item) for item in self.family_candidates],
            "domain_evidence": list(self.domain_evidence),
            "classifier_version": self.classifier_version,
            "policy_version": self.policy_version,
            "ontology_version": self.ontology_version,
            "contract_version": self.contract_version,
        }


def _family_decision_from_gate(
    request: CurveClassificationRequest,
    gate_result: Any | None,
    authoritative: CurveClassificationDecision,
) -> CurveClassificationDecision:
    if gate_result is None:
        return authoritative
    return CurveClassificationDecision(
        curve_id=request.curve_id,
        source_curve_index=request.source_curve_index,
        source_mnemonic=request.source_mnemonic,
        curve_family_key=gate_result.curve_family_key,
        curve_family_label=gate_result.curve_family_label,
        classification_status=gate_result.classification_status,
        confidence=float(gate_result.confidence),
        decision_source=gate_result.decision_source,
        review_required=bool(gate_result.review_required),
        evidence=(),
        conflicts=(),
        candidates=(),
        classifier_version="classification-decision-gates-phase12-shadow",
        policy_version="classification-orchestration-policy-v1",
    )


def build_unified_result(
    request: CurveClassificationRequest,
    authoritative: CurveClassificationDecision,
    gate_result: Any | None,
    domain_resolver: MeasurementDomainResolver | None = None,
) -> UnifiedCurveClassificationResult:
    family = _family_decision_from_gate(request, gate_result, authoritative)
    domain = (domain_resolver or MeasurementDomainResolver()).resolve(request, family)

    family_resolved = (
        family.classification_status == "resolved"
        and not family.review_required
        and family.curve_family_key != "unclassified"
    )
    domain_resolved = domain.status == "resolved"

    if not domain_resolved:
        overall_status = "requires_review"
        review_required = True
        review_reason = "measurement_domain_unresolved"
    elif domain.display_in_wdv and not family_resolved:
        overall_status = "requires_review"
        review_required = True
        review_reason = "wdv_destination_requires_resolved_curve_family"
    else:
        overall_status = "resolved"
        review_required = False
        review_reason = None

    if gate_result is not None:
        family_evidence = tuple(
            item.as_dict() if hasattr(item, "as_dict") else dict(item)
            for candidate in getattr(gate_result, "candidates", ())
            for item in getattr(candidate, "evidence", ())
        )
        family_conflicts = tuple(
            str(conflict)
            for candidate in getattr(gate_result, "candidates", ())
            for conflict in getattr(candidate, "conflicts", ())
        )
        family_candidates = tuple(
            candidate.as_dict() if hasattr(candidate, "as_dict") else dict(candidate)
            for candidate in getattr(gate_result, "candidates", ())
        )
    else:
        family_evidence = tuple(item.as_dict() for item in authoritative.evidence)
        family_conflicts = tuple(authoritative.conflicts)
        family_candidates = tuple(item.as_dict() for item in authoritative.candidates)

    curve_family_key = family.curve_family_key if family_resolved else None
    curve_family_label = family.curve_family_label if family_resolved else None

    return UnifiedCurveClassificationResult(
        curve_id=request.curve_id,
        source_curve_index=request.source_curve_index,
        source_mnemonic=request.source_mnemonic,
        curve_family_key=curve_family_key,
        curve_family_label=curve_family_label,
        family_status=family.classification_status,
        family_confidence=float(family.confidence),
        family_decision_source=family.decision_source,
        measurement_domain_key=domain.measurement_domain_key,
        measurement_domain_label=domain.measurement_domain_label,
        destination_key=domain.destination_key,
        destination_owner=domain.destination_owner,
        display_in_wdv=domain.display_in_wdv,
        domain_status=domain.status,
        domain_confidence=float(domain.confidence),
        domain_decision_source=domain.decision_source,
        overall_status=overall_status,
        review_required=review_required,
        review_reason=review_reason,
        family_evidence=family_evidence,
        family_conflicts=family_conflicts,
        family_candidates=family_candidates,
        domain_evidence=tuple(domain.evidence),
        classifier_version=family.classifier_version,
        policy_version=family.policy_version,
        ontology_version=domain.ontology_version,
    )


def build_unified_batch_results(
    items: list[tuple[CurveClassificationRequest, CurveClassificationDecision, CurveClassificationDecision]],
    family_registry: Any | None = None,
    domain_resolver: MeasurementDomainResolver | None = None,
) -> tuple[UnifiedCurveClassificationResult, ...]:
    """Compose full context-aware unified results for one governed source batch.

    The batch decision API preserves Phase 10 semantics: semantic, series, and
    tool/frame/channel context are evaluated before domain placement. This API
    is additive in Phase 12 and is not wired as production authority.
    """
    from .decision_gates import evaluate_context_batch_decision_gates

    gate_results = evaluate_context_batch_decision_gates(items, family_registry)
    resolver = domain_resolver or MeasurementDomainResolver()
    return tuple(
        build_unified_result(request, runtime, gate_result, resolver)
        for (request, runtime, _deterministic), gate_result in zip(items, gate_results)
    )
