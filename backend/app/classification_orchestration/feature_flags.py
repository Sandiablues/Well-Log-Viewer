"""Classification-engine rollout policy and emergency feature flag."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os


class ClassificationEngineMode(str, Enum):
    LEGACY = "legacy"
    SHADOW = "shadow"
    ORCHESTRATED = "orchestrated"


@dataclass(frozen=True)
class ClassificationOrchestrationPolicy:
    mode: ClassificationEngineMode = ClassificationEngineMode.SHADOW
    fallback_to_legacy_on_error: bool = True
    emit_differential_report: bool = True
    policy_version: str = "classification-orchestration-policy-v1"

    @classmethod
    def from_environment(cls) -> "ClassificationOrchestrationPolicy":
        raw = os.getenv("WLV_CLASSIFICATION_ENGINE", ClassificationEngineMode.SHADOW.value).strip().lower()
        try:
            mode = ClassificationEngineMode(raw)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in ClassificationEngineMode)
            raise ValueError(f"Invalid WLV_CLASSIFICATION_ENGINE={raw!r}; expected one of: {allowed}") from exc
        return cls(mode=mode)
