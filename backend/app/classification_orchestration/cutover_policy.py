"""Phase 13 cutover-preparation policy.

Authority requires two independent controls:
1. WLV_CLASSIFICATION_ENGINE=orchestrated
2. WLV_CLASSIFICATION_CUTOVER_SCOPE=new_ingestion

Existing managed data is never eligible through this boundary.  The default
scope is disabled, so installing this module cannot change authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os

from .feature_flags import ClassificationEngineMode, ClassificationOrchestrationPolicy


class ClassificationCutoverScope(str, Enum):
    DISABLED = "disabled"
    NEW_INGESTION = "new_ingestion"


@dataclass(frozen=True)
class ClassificationAuthorityPolicy:
    engine_policy: ClassificationOrchestrationPolicy
    cutover_scope: ClassificationCutoverScope = ClassificationCutoverScope.DISABLED
    require_resolved_unified_result: bool = True
    fallback_to_legacy_on_error: bool = True
    policy_version: str = "classification-authority-cutover-policy-v1"

    @classmethod
    def from_environment(cls) -> "ClassificationAuthorityPolicy":
        engine_policy = ClassificationOrchestrationPolicy.from_environment()
        raw_scope = os.getenv(
            "WLV_CLASSIFICATION_CUTOVER_SCOPE",
            ClassificationCutoverScope.DISABLED.value,
        ).strip().lower()
        try:
            scope = ClassificationCutoverScope(raw_scope)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in ClassificationCutoverScope)
            raise ValueError(
                f"Invalid WLV_CLASSIFICATION_CUTOVER_SCOPE={raw_scope!r}; "
                f"expected one of: {allowed}"
            ) from exc
        return cls(engine_policy=engine_policy, cutover_scope=scope)

    def permits_new_ingestion_authority(self) -> bool:
        return (
            self.engine_policy.mode is ClassificationEngineMode.ORCHESTRATED
            and self.cutover_scope is ClassificationCutoverScope.NEW_INGESTION
        )
