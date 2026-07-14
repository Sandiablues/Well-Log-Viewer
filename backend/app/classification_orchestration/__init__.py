"""Backend-owned curve classification orchestration boundary.

Phase 1 is intentionally non-authoritative: no existing ingestion or viewer
caller is routed through this package yet.  The package provides the unified
result contract, canonical family registry, feature-flag policy, legacy
adapters, shadow comparison, and differential reporting required for a safe
later cutover.
"""

from .contracts import (
    ClassificationCandidate,
    ClassificationEvidence,
    CurveClassificationDecision,
    CurveClassificationRequest,
)
from .family_registry import CanonicalCurveFamily, CanonicalCurveFamilyRegistry
from .feature_flags import ClassificationEngineMode, ClassificationOrchestrationPolicy
from .orchestrator import CurveClassificationOrchestrator, ClassificationOrchestrationResult

__all__ = [
    "ClassificationCandidate",
    "ClassificationEvidence",
    "CurveClassificationDecision",
    "CurveClassificationRequest",
    "CanonicalCurveFamily",
    "CanonicalCurveFamilyRegistry",
    "ClassificationEngineMode",
    "ClassificationOrchestrationPolicy",
    "CurveClassificationOrchestrator",
    "ClassificationOrchestrationResult",
]
