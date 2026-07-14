"""Shadow-only classification decision gates. No persistence authority."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from app.wdv_display.policy_unit_contract import WdvPolicyUnitContract, UnitConversionStatus
from .contracts import ClassificationCandidate, ClassificationEvidence, CurveClassificationDecision, CurveClassificationRequest
from .family_registry import CanonicalCurveFamilyRegistry
from .semantic_context import BatchSeriesSupport, DescriptionSemanticResolver
from .context_resolver import ContextSupport, ToolFrameChannelContextResolver

POLICY_VERSION = "classification-decision-gates-v3"
EXACT_RUNTIME_SOURCES = {"runtime_standard_mnemonic", "runtime_alias", "runtime_canonical"}
CONTEXTUAL_RUNTIME_SOURCES = {"runtime_contextual_consensus"}

@dataclass(frozen=True)
class DecisionGateResult:
    curve_family_key: str
    curve_family_label: str
    classification_status: str
    confidence: float
    decision_source: str
    review_required: bool
    gate_outcomes: tuple[dict[str, Any], ...]
    candidates: tuple[ClassificationCandidate, ...]
    conflicts: tuple[str, ...] = ()
    policy_version: str = POLICY_VERSION
    def as_dict(self):
        return {"curve_family_key": self.curve_family_key,"curve_family_label": self.curve_family_label,
        "classification_status": self.classification_status,"confidence": self.confidence,"decision_source": self.decision_source,
        "review_required": self.review_required,"gate_outcomes": list(self.gate_outcomes),
        "candidates": [c.as_dict() for c in self.candidates],"conflicts": list(self.conflicts),"policy_version": self.policy_version}

def _candidate(d: CurveClassificationDecision, source: str) -> ClassificationCandidate:
    return ClassificationCandidate(d.curve_family_key,d.curve_family_label,float(d.confidence),
        (ClassificationEvidence("classifier_result",source,f"{d.decision_source}:{d.curve_family_label}",d.confidence),),tuple(d.conflicts))

def _unit_gate(request: CurveClassificationRequest, runtime: CurveClassificationDecision) -> tuple[bool|None,str]:
    expected=(runtime.legacy_payload or {}).get("default_unit")
    source=request.unit
    if not source or not expected: return None,"unit_evidence_unavailable"
    # Use conversion contract only to test dimensional compatibility; numeric 1 is irrelevant.
    r=WdvPolicyUnitContract.convert_value(1.0,source_unit=source,target_unit=expected)
    if r.status is UnitConversionStatus.INCOMPATIBLE_DIMENSIONS: return False,"incompatible_dimensions"
    if r.status is UnitConversionStatus.RESOLVED: return True,"compatible_dimensions"
    return None,r.reason or r.status.value

def evaluate_decision_gates(
    request: CurveClassificationRequest,
    runtime: CurveClassificationDecision,
    deterministic: CurveClassificationDecision,
    family_registry: CanonicalCurveFamilyRegistry | None = None,
    *,
    semantic_resolver: DescriptionSemanticResolver | None = None,
    batch_support: BatchSeriesSupport | None = None,
    context_support: ContextSupport | None = None,
) -> DecisionGateResult:
    gates=[]; conflicts=[]
    registry = family_registry or CanonicalCurveFamilyRegistry.default()
    r_class=runtime.curve_family_key!="unclassified" and runtime.classification_status=="resolved" and not runtime.review_required
    d_class=deterministic.curve_family_key!="unclassified" and deterministic.classification_status=="resolved" and not deterministic.review_required
    candidates=tuple(_candidate(d,s) for d,s in ((runtime,"runtime_kr"),(deterministic,"deterministic")) if d.curve_family_key!="unclassified")
    gates.append({"gate":"input_sufficiency","outcome":"go" if any([request.source_mnemonic,request.description,request.unit]) else "no_go"})
    compatible,reason=_unit_gate(request,runtime)
    gates.append({"gate":"hard_unit_compatibility","outcome":"go" if compatible is True else ("no_go" if compatible is False else "unknown"),"reason":reason})
    if compatible is False and r_class:
        conflicts.append(f"runtime_candidate_unit_conflict:{reason}")
        return DecisionGateResult("unclassified","Unclassified","requires_review",0.0,"decision_gate_conflict",True,tuple(gates),candidates,tuple(conflicts))
    same = r_class and d_class and runtime.curve_family_key==deterministic.curve_family_key
    governed_equivalent = (
        r_class
        and d_class
        and not same
        and registry.governed_measurement_matches_family(
            deterministic.curve_family_label,
            governed_family_value=runtime.curve_family_label,
            runtime_payload=dict(runtime.legacy_payload),
        )
    )
    if same or governed_equivalent:
        gates += (
            {
                "gate":"independent_evidence_agreement",
                "outcome":"go",
                "signals":2,
                "equivalence":"exact_family" if same else "governed_measurement_to_family",
            },
            {"gate":"conflict_resolution","outcome":"go"},
        )
        conf=max(runtime.confidence,deterministic.confidence)
        return DecisionGateResult(
            runtime.curve_family_key,
            runtime.curve_family_label,
            "resolved",
            conf,
            "decision_gate_consensus" if same else "decision_gate_governed_family_consensus",
            False,
            tuple(gates),
            candidates,
        )
    if r_class and d_class and runtime.curve_family_key!=deterministic.curve_family_key:
        conflicts.append(f"classifier_family_conflict:{runtime.curve_family_key}!={deterministic.curve_family_key}")
        gates += ({"gate":"independent_evidence_agreement","outcome":"no_go","signals":2},{"gate":"conflict_resolution","outcome":"no_go"})
        return DecisionGateResult("unclassified","Unclassified","requires_review",max(runtime.confidence,deterministic.confidence),"decision_gate_conflict",True,tuple(gates),candidates,tuple(conflicts))
    if r_class and runtime.decision_source in EXACT_RUNTIME_SOURCES:
        gates += ({"gate":"authoritative_governed_match","outcome":"go","source":runtime.decision_source},{"gate":"confidence_threshold","outcome":"go" if runtime.confidence>=.90 else "no_go"})
        if runtime.confidence>=.90:
            return DecisionGateResult(runtime.curve_family_key,runtime.curve_family_label,"resolved",runtime.confidence,"decision_gate_exact_runtime",False,tuple(gates),candidates)
    if r_class and runtime.decision_source in CONTEXTUAL_RUNTIME_SOURCES:
        gates += ({"gate":"contextual_evidence","outcome":"go"},{"gate":"conflict_resolution","outcome":"go"})
        return DecisionGateResult(runtime.curve_family_key,runtime.curve_family_label,"resolved",runtime.confidence,"decision_gate_contextual_runtime",False,tuple(gates),candidates)
    if r_class:
        gates.append({"gate":"runtime_candidate","outcome":"review"})
        return DecisionGateResult(runtime.curve_family_key,runtime.curve_family_label,"requires_review",runtime.confidence,"decision_gate_runtime_review",True,tuple(gates),candidates)
    if d_class:
        gates += ({"gate":"deterministic_only","outcome":"review"},{"gate":"independent_evidence_agreement","outcome":"no_go","signals":1})
        return DecisionGateResult(deterministic.curve_family_key,deterministic.curve_family_label,"requires_review",deterministic.confidence,"decision_gate_deterministic_review",True,tuple(gates),candidates)

    semantic = (semantic_resolver or DescriptionSemanticResolver(registry)).resolve(request)
    if semantic is not None:
        semantic_candidate = semantic.candidate
        candidates = tuple((*candidates, semantic_candidate))
        gates.append({
            "gate":"description_semantic_candidate",
            "outcome":"go",
            "rule_id":semantic.rule_id,
            "unit_outcome":semantic.unit_outcome,
            "confidence":semantic_candidate.confidence,
        })
        if batch_support is not None and batch_support.family_key == semantic_candidate.curve_family_key:
            gates.append({
                "gate":"batch_series_context",
                "outcome":"go",
                "member_count":batch_support.member_count,
                "series_key":batch_support.series_key,
            })
            combined_confidence=max(semantic_candidate.confidence,batch_support.confidence)
            return DecisionGateResult(
                semantic_candidate.curve_family_key,semantic_candidate.curve_family_label,
                "resolved",combined_confidence,"decision_gate_batch_series_semantic",False,
                tuple(gates),candidates,
            )
        if semantic_candidate.confidence >= 0.90 and semantic.unit_outcome == "compatible":
            gates.append({"gate":"semantic_unit_evidence","outcome":"go","signals":2})
            return DecisionGateResult(
                semantic_candidate.curve_family_key,semantic_candidate.curve_family_label,
                "resolved",semantic_candidate.confidence,"decision_gate_semantic_unit",False,
                tuple(gates),candidates,
            )
        gates.append({"gate":"semantic_unit_evidence","outcome":"review","signals":1})
        return DecisionGateResult(
            semantic_candidate.curve_family_key,semantic_candidate.curve_family_label,
            "requires_review",semantic_candidate.confidence,"decision_gate_semantic_review",True,
            tuple(gates),candidates,
        )

    if context_support is not None:
        family = registry.resolve(context_support.family_key)
        if family is not None:
            context_candidate = ClassificationCandidate(
                family.family_key,
                family.display_label,
                context_support.confidence,
                context_support.evidence,
            )
            candidates = tuple((*candidates, context_candidate))
            gates.append({
                "gate":"tool_frame_channel_context",
                "outcome":"go",
                "rule_id":context_support.rule_id,
                "signal_count":context_support.signal_count,
                "peer_support":context_support.peer_support,
                "context_key":list(context_support.context_key),
            })
            return DecisionGateResult(
                family.family_key,
                family.display_label,
                "resolved",
                context_support.confidence,
                "decision_gate_tool_frame_channel_context",
                False,
                tuple(gates),
                candidates,
            )

    gates.append({"gate":"candidate_generation","outcome":"no_go"})
    return DecisionGateResult("unclassified","Unclassified","requires_review",0.0,"decision_gate_unresolved",True,tuple(gates),candidates)


def evaluate_batch_decision_gates(
    items: list[tuple[CurveClassificationRequest, CurveClassificationDecision, CurveClassificationDecision]],
    family_registry: CanonicalCurveFamilyRegistry | None = None,
) -> tuple[DecisionGateResult, ...]:
    """Evaluate a source batch with non-authoritative repeated-series support."""
    from .semantic_context import BatchSeriesContextResolver

    registry = family_registry or CanonicalCurveFamilyRegistry.default()
    semantic = DescriptionSemanticResolver(registry)
    requests = [item[0] for item in items]
    support = BatchSeriesContextResolver().resolve_batch(requests, semantic)
    results = []
    for ordinal, (request, runtime, deterministic) in enumerate(items):
        identity = str(request.curve_id or request.channel_id or request.source_curve_index or f"ordinal:{ordinal}")
        results.append(evaluate_decision_gates(
            request,
            runtime,
            deterministic,
            registry,
            semantic_resolver=semantic,
            batch_support=support.get(identity),
        ))
    return tuple(results)


def evaluate_context_batch_decision_gates(
    items: list[tuple[CurveClassificationRequest, CurveClassificationDecision, CurveClassificationDecision]],
    family_registry: CanonicalCurveFamilyRegistry | None = None,
) -> tuple[DecisionGateResult, ...]:
    """Evaluate a source batch with semantic, series, and acquisition-context support."""
    registry = family_registry or CanonicalCurveFamilyRegistry.default()
    semantic = DescriptionSemanticResolver(registry)

    # Phase 9 preliminary decisions are authoritative only inside this shadow
    # evaluation. They are used as peer evidence, never persisted here.
    preliminary = evaluate_batch_decision_gates(items, registry)
    requests = [item[0] for item in items]
    resolved_peers: dict[str, str] = {}
    identities: list[str] = []
    for ordinal, (request, result) in enumerate(zip(requests, preliminary)):
        identity = str(request.curve_id or request.channel_id or request.source_curve_index or f"ordinal:{ordinal}")
        identities.append(identity)
        if not result.review_required and result.curve_family_key != "unclassified":
            resolved_peers[identity] = result.curve_family_key

    context_support = ToolFrameChannelContextResolver(registry).resolve_batch(
        requests,
        resolved_peers,
    )

    results = []
    for ordinal, ((request, runtime, deterministic), preliminary_result) in enumerate(zip(items, preliminary)):
        if not preliminary_result.review_required:
            results.append(preliminary_result)
            continue
        identity = identities[ordinal]
        results.append(evaluate_decision_gates(
            request,
            runtime,
            deterministic,
            registry,
            semantic_resolver=semantic,
            context_support=context_support.get(identity),
        ))
    return tuple(results)
