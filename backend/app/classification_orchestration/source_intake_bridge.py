"""Phase 14 Source Intake authority bridge.

This module wires the Phase 13 authority router to one verified new-ingestion
boundary: Source Intake registration.

Safety properties:
- new Source Intake registration uses orchestrated authority by default;
- an explicit environment override can force legacy/shadow/disabled behavior;
- the bridge returns no authority outcomes unless the resolved controls permit it;
- only requests explicitly marked ``new_ingestion`` are eligible;
- review-required unified results retain legacy authority;
- resolved non-WDV domain routes are persisted as first-class routing decisions;
- existing managed data and reclassification never pass through this bridge.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Iterable, Sequence

from app.knowledge.managed_repository import ManagedKRRepository
from app.knowledge.runtime_classification_service import (
    CurveClassificationInput,
    CurveClassificationResult,
    RuntimeCurveClassificationService,
)
from app.knowledge.runtime_resolver import ApprovedKnowledgeRuntimeResolver

from .adapters import DeterministicWellLogLegacyAdapter
from .authority_router import NewIngestionClassificationAuthorityRouter
from .contracts import (
    ClassificationEvidence,
    CurveClassificationDecision,
    CurveClassificationRequest,
)
from .cutover_policy import ClassificationAuthorityPolicy, ClassificationCutoverScope
from .feature_flags import ClassificationEngineMode, ClassificationOrchestrationPolicy
from .family_registry import CanonicalCurveFamilyRegistry
from .unified_result import UnifiedCurveClassificationResult, build_unified_batch_results

SOURCE_INTAKE_BRIDGE_VERSION = "classification-source-intake-authority-bridge-v1"


@dataclass(frozen=True)
class SourceIntakeAuthorityOutcome:
    curve_index: int
    authoritative_kind: str
    legacy_decision: CurveClassificationDecision
    unified_result: UnifiedCurveClassificationResult | None
    blocked_reason: str | None
    used_legacy_fallback: bool
    bridge_version: str = SOURCE_INTAKE_BRIDGE_VERSION

    @property
    def orchestrated(self) -> bool:
        return self.authoritative_kind == "orchestrated" and self.unified_result is not None


def _curve_value(curve: object, name: str, default: Any = None) -> Any:
    return getattr(curve, name, default)


def _build_requests(
    curve_headers: Sequence[object],
    *,
    context_terms: Iterable[str | None],
    source_kind: str,
    source_uid: str,
) -> list[CurveClassificationRequest]:
    shared_terms = [str(term) for term in context_terms if term]
    requests: list[CurveClassificationRequest] = []
    for index, curve in enumerate(curve_headers, start=1):
        mnemonic = str(_curve_value(curve, "mnemonic", "") or "")
        description = _curve_value(curve, "description")
        unit = _curve_value(curve, "unit")
        requests.append(
            CurveClassificationRequest(
                source_mnemonic=mnemonic,
                curve_id=mnemonic or f"curve-{index}",
                unit=unit,
                description=description,
                source_curve_index=index,
                source_kind=source_kind,
                source_uid=source_uid,
                context={
                    "ingestion_lifecycle": "new_ingestion",
                    "source_intake_context_terms": shared_terms,
                },
            )
        )
    return requests


def source_intake_authority_policy_from_environment() -> ClassificationAuthorityPolicy:
    """Resolve the production Source Intake authority policy.

    New ingestion is orchestrated by default after cutover, persistence,
    parity, and live-canary validation. Emergency fallback:
        WLV_CLASSIFICATION_ENGINE=legacy
    """
    raw_engine = os.getenv(
        "WLV_CLASSIFICATION_ENGINE",
        ClassificationEngineMode.ORCHESTRATED.value,
    ).strip().lower()
    raw_scope = os.getenv(
        "WLV_CLASSIFICATION_CUTOVER_SCOPE",
        ClassificationCutoverScope.NEW_INGESTION.value,
    ).strip().lower()

    try:
        engine_mode = ClassificationEngineMode(raw_engine)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ClassificationEngineMode)
        raise ValueError(
            f"Invalid WLV_CLASSIFICATION_ENGINE={raw_engine!r}; expected one of: {allowed}"
        ) from exc

    try:
        cutover_scope = ClassificationCutoverScope(raw_scope)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ClassificationCutoverScope)
        raise ValueError(
            f"Invalid WLV_CLASSIFICATION_CUTOVER_SCOPE={raw_scope!r}; expected one of: {allowed}"
        ) from exc

    return ClassificationAuthorityPolicy(
        engine_policy=ClassificationOrchestrationPolicy(mode=engine_mode),
        cutover_scope=cutover_scope,
    )

def build_source_intake_authority_outcomes(
    *,
    curve_headers: Sequence[object],
    context_terms: Iterable[str | None],
    source_kind: str,
    source_uid: str,
    policy: ClassificationAuthorityPolicy | None = None,
    runtime_classifications: Sequence[CurveClassificationResult] | None = None,
) -> tuple[SourceIntakeAuthorityOutcome, ...]:
    """Return authority outcomes for one new Source Intake batch.

    The function remains lazy when authority is explicitly disabled. The
    production default for new Source Intake registration is orchestrated;
    legacy remains an explicit emergency override.
    """
    authority_policy = policy or source_intake_authority_policy_from_environment()
    if not authority_policy.permits_new_ingestion_authority():
        return ()

    requests = _build_requests(
        curve_headers,
        context_terms=context_terms,
        source_kind=source_kind,
        source_uid=source_uid,
    )
    if not requests:
        return ()

    registry = CanonicalCurveFamilyRegistry.default()
    deterministic_adapter = DeterministicWellLogLegacyAdapter(registry)

    if runtime_classifications is not None:
        runtime_results = tuple(runtime_classifications)
        if len(runtime_results) != len(requests):
            raise ValueError(
                "Source Intake authority runtime classification count does not match curve count: "
                f"{len(runtime_results)} != {len(requests)}"
            )
    else:
        runtime_resolver = ApprovedKnowledgeRuntimeResolver(ManagedKRRepository())
        runtime_service = RuntimeCurveClassificationService(runtime_resolver)
        runtime_inputs = [
            CurveClassificationInput(
                source_mnemonic=request.source_mnemonic,
                curve_id=request.curve_id,
                unit=request.unit,
                description=request.description,
                source_curve_index=request.source_curve_index,
                context=dict(request.context),
            )
            for request in requests
        ]
        runtime_results = runtime_service.classify_curves(runtime_inputs).classifications

    def runtime_decision(
        request: CurveClassificationRequest,
        result: CurveClassificationResult,
    ) -> CurveClassificationDecision:
        canonical = registry.resolve(result.family)
        conflicts: tuple[str, ...] = ()
        if canonical is None:
            canonical = registry.unclassified()
            review_required = True
            status = "requires_review"
            if result.family:
                conflicts = (f"Runtime KR family is not registered: {result.family}",)
        else:
            review_required = result.requires_review
            status = (
                "requires_review"
                if review_required
                else ("resolved" if result.resolved else "unknown")
            )
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

    items: list[
        tuple[CurveClassificationRequest, CurveClassificationDecision, CurveClassificationDecision]
    ] = []
    legacy_decisions: list[CurveClassificationDecision] = []

    # Runtime classification has already performed one batched shadow comparison.
    # Suppress duplicate nested observer work while producing the deterministic
    # comparison decisions used by the orchestration gates.
    from .live_shadow_observer import suppress_shadow_observer

    with suppress_shadow_observer():
        for request, runtime_result in zip(requests, runtime_results):
            runtime = runtime_decision(request, runtime_result)
            deterministic = deterministic_adapter.classify_curve(request)
            items.append((request, runtime, deterministic))
            legacy_decisions.append(runtime if runtime.resolved else deterministic)

    unified_results = build_unified_batch_results(items, family_registry=registry)
    router = NewIngestionClassificationAuthorityRouter(authority_policy)

    outcomes: list[SourceIntakeAuthorityOutcome] = []
    for index, (request, legacy, unified) in enumerate(
        zip(requests, legacy_decisions, unified_results),
        start=1,
    ):
        routed = router.route(
            request=request,
            legacy_decision=legacy,
            build_unified=lambda unified=unified: unified,
        )

        outcomes.append(
            SourceIntakeAuthorityOutcome(
                curve_index=index,
                authoritative_kind=routed.authoritative_kind,
                legacy_decision=legacy,
                unified_result=routed.unified_result,
                blocked_reason=routed.blocked_reason,
                used_legacy_fallback=routed.used_legacy_fallback,
            )
        )

    return tuple(outcomes)



def apply_source_intake_authority_outcome(
    legacy_payload: dict[str, object],
    outcome: SourceIntakeAuthorityOutcome | None,
) -> dict[str, object]:
    """Merge Phase 18 authority without erasing an accepted runtime-KR result.

    Accepted runtime-KR authority remains authoritative for family presentation,
    provenance, confidence, reasons, and review state. Phase 18 contributes the
    backend-owned GENERAL CURVE FAMILY grouping key and routing fields.
    """
    if outcome is None or not outcome.orchestrated:
        return legacy_payload

    unified = outcome.unified_result
    assert unified is not None

    payload = dict(legacy_payload)
    payload["measurement_domain_key"] = unified.measurement_domain_key
    payload["measurement_domain_label"] = unified.measurement_domain_label
    payload["destination_key"] = unified.destination_key
    payload["destination_owner"] = unified.destination_owner
    payload["display_in_wdv"] = unified.display_in_wdv
    payload["classification_contract_version"] = unified.contract_version

    if unified.curve_family_key:
        payload["curve_family_key"] = unified.curve_family_key

    existing_source = str(legacy_payload.get("classification_source") or "").strip()
    existing_family = str(legacy_payload.get("curve_family") or "").strip()
    existing_review_required = bool(legacy_payload.get("review_required", True))
    existing_runtime_authority = (
        existing_source.startswith("runtime_")
        and bool(existing_family)
        and existing_family.lower() not in {"unclassified", "unknown"}
        and not existing_review_required
    )

    if existing_runtime_authority:
        return payload

    if unified.curve_family_label:
        payload["curve_family"] = unified.curve_family_label
        payload["classification_confidence"] = (
            "high" if unified.family_confidence >= 0.9
            else "medium" if unified.family_confidence >= 0.6
            else "low"
        )
        payload["classification_source"] = f"orchestrated:{unified.family_decision_source}"
    else:
        payload["classification_confidence"] = (
            "high" if unified.domain_confidence >= 0.9
            else "medium" if unified.domain_confidence >= 0.6
            else "low"
        )
        payload["classification_source"] = f"orchestrated:{unified.domain_decision_source}"

    reasons = [
        *list(legacy_payload.get("classification_reasons") or []),
        f"Authoritative new-ingestion classification from {unified.contract_version}.",
        f"Measurement domain: {unified.measurement_domain_label}.",
        f"Destination: {unified.destination_owner} ({unified.destination_key}).",
        f"WDV eligibility: {unified.display_in_wdv}.",
    ]
    if unified.curve_family_label:
        reasons.append(
            f"Canonical general family: {unified.curve_family_label} ({unified.curve_family_key})."
        )
    payload["classification_reasons"] = reasons
    payload["review_required"] = False
    return payload

