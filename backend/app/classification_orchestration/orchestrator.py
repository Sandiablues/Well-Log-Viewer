"""Safe Phase 1 curve-classification orchestration and fallback boundary."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .adapters import ClassificationEngine
from .contracts import CurveClassificationDecision, CurveClassificationRequest
from .differential import ClassificationDifferential, compare_classifications
from .feature_flags import ClassificationEngineMode, ClassificationOrchestrationPolicy


ORCHESTRATOR_VERSION = "classification-orchestrator-phase1"


@dataclass(frozen=True)
class ClassificationOrchestrationResult:
    authoritative: CurveClassificationDecision
    mode: str
    used_legacy_fallback: bool
    shadow: Optional[CurveClassificationDecision] = None
    differential: Optional[ClassificationDifferential] = None
    orchestration_error: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "orchestrator_version": ORCHESTRATOR_VERSION,
            "mode": self.mode,
            "used_legacy_fallback": self.used_legacy_fallback,
            "orchestration_error": self.orchestration_error,
            "authoritative": self.authoritative.as_dict(),
            "shadow": self.shadow.as_dict() if self.shadow else None,
            "differential": self.differential.as_dict() if self.differential else None,
        }


class CurveClassificationOrchestrator:
    """Coordinates authoritative legacy and non-authoritative shadow engines.

    No production caller is wired here in Phase 1.  When integrated later:
      * legacy mode returns legacy authority only;
      * shadow mode returns legacy authority and records shadow comparison;
      * orchestrated mode returns the orchestrated result, with tested legacy
        fallback on exception.
    """

    def __init__(
        self,
        *,
        legacy_engine: ClassificationEngine,
        orchestrated_engine: ClassificationEngine,
        policy: ClassificationOrchestrationPolicy | None = None,
    ) -> None:
        self._legacy_engine = legacy_engine
        self._orchestrated_engine = orchestrated_engine
        self._policy = policy or ClassificationOrchestrationPolicy.from_environment()

    def classify_curve(self, request: CurveClassificationRequest) -> ClassificationOrchestrationResult:
        legacy = self._legacy_engine.classify_curve(request)

        if self._policy.mode is ClassificationEngineMode.LEGACY:
            return ClassificationOrchestrationResult(
                authoritative=legacy,
                mode=self._policy.mode.value,
                used_legacy_fallback=False,
            )

        try:
            shadow = self._orchestrated_engine.classify_curve(request)
        except Exception as exc:
            if not self._policy.fallback_to_legacy_on_error:
                raise
            return ClassificationOrchestrationResult(
                authoritative=legacy,
                mode=self._policy.mode.value,
                used_legacy_fallback=True,
                orchestration_error=f"{type(exc).__name__}: {exc}",
            )

        differential = compare_classifications(legacy, shadow) if self._policy.emit_differential_report else None

        if self._policy.mode is ClassificationEngineMode.SHADOW:
            authoritative = legacy
        elif self._policy.mode is ClassificationEngineMode.ORCHESTRATED:
            authoritative = shadow
        else:  # Enum exhaustiveness guard.
            raise RuntimeError(f"Unsupported classification engine mode: {self._policy.mode}")

        return ClassificationOrchestrationResult(
            authoritative=authoritative,
            mode=self._policy.mode.value,
            used_legacy_fallback=False,
            shadow=shadow,
            differential=differential,
        )

    def classify_batch(self, requests: list[CurveClassificationRequest]) -> tuple[ClassificationOrchestrationResult, ...]:
        return tuple(self.classify_curve(request) for request in requests)
