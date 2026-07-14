"""Non-authoritative live shadow observer for existing classification entry points."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from app.classification_orchestration.contracts import CurveClassificationDecision, CurveClassificationRequest
from app.classification_orchestration.differential import compare_classifications
from app.classification_orchestration.family_registry import CanonicalCurveFamilyRegistry
from app.classification_orchestration.feature_flags import ClassificationEngineMode, ClassificationOrchestrationPolicy
from app.classification_orchestration.decision_gates import evaluate_decision_gates
from app.classification_orchestration.unified_result import build_unified_result

_ACTIVE: ContextVar[bool] = ContextVar("classification_shadow_observer_active", default=False)


def _report_path() -> Path:
    configured = os.getenv("WLV_CLASSIFICATION_SHADOW_REPORT_PATH", "").strip()
    return (
        Path(configured).expanduser()
        if configured
        else Path(__file__).resolve().parents[2] / "data/diagnostics/classification_shadow_differentials.jsonl"
    )


def _append(record: dict[str, Any]) -> None:
    _append_many([record])


def _append_many(records: list[dict[str, Any]]) -> None:
    if not records:
        return
    path = _report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


@contextmanager
def suppress_shadow_observer():
    """Suppress nested/duplicate observer work without changing authority results."""
    token = _ACTIVE.set(True)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def _approved_runtime_resolver():
    from app.knowledge.managed_repository import ManagedKRRepository
    from app.knowledge.runtime_resolver import ApprovedKnowledgeRuntimeResolver
    return ApprovedKnowledgeRuntimeResolver(ManagedKRRepository())


def _registry(runtime_resolver=None) -> CanonicalCurveFamilyRegistry:
    return CanonicalCurveFamilyRegistry.default(runtime_resolver=runtime_resolver)


def _family(value, registry: CanonicalCurveFamilyRegistry):
    return registry.resolve(value) or registry.unclassified()


def legacy_decision(request, result, registry: CanonicalCurveFamilyRegistry | None = None):
    registry = registry or _registry()
    family = _family(result.curve_family, registry)
    confidence = {"high": .90, "medium": .75, "low": .40}.get(result.classification_confidence, 0.0)
    return CurveClassificationDecision(
        curve_id=request.curve_id,
        source_curve_index=request.source_curve_index,
        source_mnemonic=request.source_mnemonic,
        curve_family_key=family.family_key,
        curve_family_label=family.display_label,
        classification_status="requires_review" if result.review_required else "resolved",
        confidence=confidence,
        decision_source=result.classification_source,
        review_required=result.review_required,
        legacy_payload=asdict(result),
    )


def runtime_decision(request, result, registry: CanonicalCurveFamilyRegistry | None = None):
    registry = registry or _registry()
    # A result emitted by RuntimeCurveClassificationService has already passed
    # the approved runtime-KR boundary. If the independently rebuilt registry is
    # unavailable or stale, retain that authoritative family in the diagnostic
    # contract rather than silently collapsing it to Unclassified.
    if result.family and registry.resolve(result.family) is None:
        registry.register_source_family(result.family)
    family = _family(result.family, registry)
    status = "requires_review" if result.requires_review else ("resolved" if result.resolved else "unknown")
    return CurveClassificationDecision(
        curve_id=request.curve_id,
        source_curve_index=request.source_curve_index,
        source_mnemonic=request.source_mnemonic,
        curve_family_key=family.family_key,
        curve_family_label=family.display_label,
        classification_status=status,
        confidence=float(result.confidence or 0.0),
        decision_source=result.resolution_source,
        review_required=result.requires_review,
        legacy_payload=result.as_dict(),
    )


def _record(entrypoint, authoritative, shadow=None, error=None, request=None, registry=None):
    gate_result = evaluate_decision_gates(
        request,
        authoritative if entrypoint == "runtime_kr_classifier" else shadow,
        shadow if entrypoint == "runtime_kr_classifier" else authoritative,
        registry,
    ) if request is not None and shadow is not None else None
    unified_result = build_unified_result(
        request,
        authoritative,
        gate_result,
    ) if request is not None else None
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "observer_version": "classification-live-shadow-v2",
        "entrypoint": entrypoint,
        "mode": ClassificationOrchestrationPolicy.from_environment().mode.value,
        "authoritative_unchanged": True,
        "authoritative": authoritative.as_dict(),
        "shadow": shadow.as_dict() if shadow else None,
        "differential": compare_classifications(authoritative, shadow).as_dict() if shadow else None,
        "shadow_error": error,
        "decision_gate": gate_result.as_dict() if gate_result else None,
        "unified_result": unified_result.as_dict() if unified_result else None,
    }


def _emit(entrypoint, authoritative, shadow=None, error=None, request=None, registry=None):
    _append(_record(entrypoint, authoritative, shadow, error, request, registry))


def observe_deterministic_authoritative(*, mnemonic, description, unit, context_terms, authoritative_result):
    try:
        if ClassificationOrchestrationPolicy.from_environment().mode is ClassificationEngineMode.LEGACY or _ACTIVE.get():
            return
        token = _ACTIVE.set(True)
        try:
            request = CurveClassificationRequest(
                source_mnemonic=mnemonic or "",
                unit=unit,
                description=description,
                context={"context_terms": [value for value in context_terms if value]},
            )
            resolver = None
            registry = _registry()
            shadow = None
            error = None
            try:
                resolver = _approved_runtime_resolver()
                registry = _registry(resolver)
                from app.knowledge.runtime_classification_service import CurveClassificationInput, RuntimeCurveClassificationService
                service = RuntimeCurveClassificationService(resolver)
                shadow_raw = service.classify_curve(CurveClassificationInput(
                    source_mnemonic=request.source_mnemonic,
                    unit=unit,
                    description=description,
                    context=dict(request.context),
                ))
                shadow = runtime_decision(request, shadow_raw, registry)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            authoritative = legacy_decision(request, authoritative_result, registry)
            _emit("deterministic_well_log_classifier", authoritative, shadow, error, request, registry)
        finally:
            _ACTIVE.reset(token)
    except Exception:
        return


def observe_runtime_authoritative(*, curve, authoritative_result, runtime_resolver=None):
    try:
        if ClassificationOrchestrationPolicy.from_environment().mode is ClassificationEngineMode.LEGACY or _ACTIVE.get():
            return
        token = _ACTIVE.set(True)
        try:
            request = CurveClassificationRequest(
                source_mnemonic=curve.source_mnemonic or "",
                curve_id=curve.curve_id,
                unit=curve.unit,
                description=curve.description,
                source_curve_index=curve.source_curve_index,
                context=dict(curve.context),
            )
            error = None
            try:
                resolver = runtime_resolver or _approved_runtime_resolver()
                registry = _registry(resolver)
            except Exception as exc:
                registry = _registry()
                error = f"registry:{type(exc).__name__}: {exc}"
            authoritative = runtime_decision(request, authoritative_result, registry)
            shadow = None
            try:
                from app.classification.well_log_classifier import classify_well_log_curve
                raw = classify_well_log_curve(
                    mnemonic=request.source_mnemonic,
                    description=curve.description,
                    unit=curve.unit,
                    context_terms=tuple(str(value) for value in curve.context.values() if value is not None),
                )
                shadow = legacy_decision(request, raw, registry)
            except Exception as exc:
                shadow_error = f"{type(exc).__name__}: {exc}"
                error = f"{error}; {shadow_error}" if error else shadow_error
            _emit("runtime_kr_classifier", authoritative, shadow, error, request, registry)
        finally:
            _ACTIVE.reset(token)
    except Exception:
        return


def observe_runtime_batch_authoritative(*, curves, authoritative_results, runtime_resolver):
    """Observe one runtime classification batch with one shared KR resolver/registry.

    The observer remains non-authoritative. Nested deterministic observers are
    suppressed while the batch computes its legacy shadow so the same curves
    are not cross-classified recursively. Diagnostic JSONL records retain the
    existing per-curve schema but are written with one file open.
    """
    try:
        if ClassificationOrchestrationPolicy.from_environment().mode is ClassificationEngineMode.LEGACY or _ACTIVE.get():
            return
        token = _ACTIVE.set(True)
        try:
            try:
                registry = _registry(runtime_resolver)
                registry_error = None
            except Exception as exc:
                registry = _registry()
                registry_error = f"registry:{type(exc).__name__}: {exc}"

            records: list[dict[str, Any]] = []
            from app.classification.well_log_classifier import classify_well_log_curve

            for curve, authoritative_result in zip(curves, authoritative_results):
                request = CurveClassificationRequest(
                    source_mnemonic=curve.source_mnemonic or "",
                    curve_id=curve.curve_id,
                    unit=curve.unit,
                    description=curve.description,
                    source_curve_index=curve.source_curve_index,
                    context=dict(curve.context),
                )
                authoritative = runtime_decision(request, authoritative_result, registry)
                shadow = None
                error = registry_error
                try:
                    raw = classify_well_log_curve(
                        mnemonic=request.source_mnemonic,
                        description=curve.description,
                        unit=curve.unit,
                        context_terms=tuple(str(value) for value in curve.context.values() if value is not None),
                    )
                    shadow = legacy_decision(request, raw, registry)
                except Exception as exc:
                    shadow_error = f"{type(exc).__name__}: {exc}"
                    error = f"{error}; {shadow_error}" if error else shadow_error
                records.append(_record(
                    "runtime_kr_classifier", authoritative, shadow, error, request, registry
                ))
            _append_many(records)
        finally:
            _ACTIVE.reset(token)
    except Exception:
        return
