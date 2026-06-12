"""WLV KR-7 — Backend Curve Classification Service.

Backend-owned service that accepts raw curve inventory from a well/log import
context and returns backend-owned classification results.

Architecture contract
---------------------
* Backend owns classification truth.
* Classification consumes KR-6 resolution service — no resolution logic is
  duplicated here.
* Frontend renders backend contracts only.
* Only production-eligible knowledge (status in {SEED, APPROVED}) participates
  in classification; candidate, rejected, and deprecated records are excluded
  by the underlying KR-6 resolution service.
* The service is offline-capable: no network calls, no external deps.
* Storage is replaceable — the service depends only on KnowledgeResolutionService,
  which depends only on ManagedKRRepository.
* Input order is strictly preserved in classification results.
* Source curve identity (curve_id, source_curve_index) is preserved throughout.

Classification status values
-----------------------------
  classified      — resolved=True, no review flag
  unclassified    — resolved=False, review_required=True
  review_required — reserved for future ambiguity handling; not used in KR-7

Dependency chain
-----------------
  CurveClassificationService
    uses KnowledgeResolutionService        (KR-6)
      uses ManagedKRRepository             (KR-5)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .resolution_service import (
    CurveResolveInput,
    DisplayRuleResult,
    KnowledgeResolutionService,
)

KR7_VERSION = "kr-7"

# ---------------------------------------------------------------------------
# Classification status constants
# ---------------------------------------------------------------------------

_STATUS_CLASSIFIED = "classified"
_STATUS_UNCLASSIFIED = "unclassified"
_STATUS_REVIEW_REQUIRED = "review_required"


# ---------------------------------------------------------------------------
# Input dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CurveClassifyInput:
    """Input contract for a single raw curve to be classified.

    Preserves source identity fields so the caller can correlate results back
    to the original import inventory.
    """

    curve_id: str
    mnemonic: str
    unit: Optional[str] = None
    description: Optional[str] = None
    source_curve_index: Optional[int] = None


@dataclass
class ClassificationSource:
    """Optional import source context for a classification batch."""

    source_type: str
    source_file: Optional[str] = None
    import_batch_id: Optional[str] = None


@dataclass
class CurveClassificationRequest:
    """Full classification request for a batch of curves from a single import context."""

    curves: list[CurveClassifyInput]
    well_id: Optional[str] = None
    source: Optional[ClassificationSource] = None


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CurveClassificationResult:
    """Classification result for a single raw curve.

    When resolved=True / classification_status="classified", all knowledge
    fields (canonical_curve_id, display_name, family, product_group, …) are
    populated.  When resolved=False, only curve_id, mnemonic,
    normalized_mnemonic, classification_status, review_required, and warnings
    are meaningful.
    """

    curve_id: str
    mnemonic: str
    normalized_mnemonic: str

    resolved: bool
    classification_status: str     # one of: classified, unclassified, review_required

    # Source identity preservation
    source_curve_index: Optional[int]

    # Knowledge fields (populated when resolved=True)
    canonical_curve_id: Optional[str] = None
    display_name: Optional[str] = None
    family: Optional[str] = None
    product_group: Optional[str] = None
    product_subgroup: Optional[str] = None
    default_unit: Optional[str] = None
    confidence: float = 0.0
    resolution_source: str = "unresolved"
    knowledge_record_id: Optional[str] = None
    display_rule: Optional[DisplayRuleResult] = None

    review_required: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class CurveClassificationBatchResult:
    """Classification result for a full batch of curves.

    Includes aggregate counts and the ordered list of per-curve results.
    Input order is strictly preserved.
    """

    kr_version: str
    well_id: Optional[str]
    source: Optional[ClassificationSource]

    curve_count: int
    classified_count: int
    unclassified_count: int
    review_required_count: int

    classifications: list[CurveClassificationResult]


# ---------------------------------------------------------------------------
# CurveClassificationService
# ---------------------------------------------------------------------------


class CurveClassificationService:
    """Backend-owned curve classification service (KR-7).

    Accepts a batch of raw imported curves, resolves each via the KR-6
    resolution service, and returns ordered classification results.

    Only production-eligible knowledge (status in {SEED, APPROVED}) affects
    classification.  Candidate, rejected, and deprecated records are excluded
    by the underlying resolution service.

    Usage::

        service = CurveClassificationService(resolution_service)
        result  = service.classify_curves(request)
    """

    def __init__(self, resolution_service: KnowledgeResolutionService) -> None:
        self._resolver = resolution_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_curves(
        self,
        request: CurveClassificationRequest,
    ) -> CurveClassificationBatchResult:
        """Classify a batch of raw curves.

        Input order is strictly preserved.  Each curve is independently
        classified; one unresolvable mnemonic does not affect others.
        Never raises; unresolvable curves are marked unclassified.
        """
        classifications: list[CurveClassificationResult] = [
            self._classify_one(curve) for curve in request.curves
        ]

        classified_count = sum(
            1 for r in classifications if r.classification_status == _STATUS_CLASSIFIED
        )
        unclassified_count = sum(
            1 for r in classifications if r.classification_status == _STATUS_UNCLASSIFIED
        )
        review_required_count = sum(1 for r in classifications if r.review_required)

        return CurveClassificationBatchResult(
            kr_version=KR7_VERSION,
            well_id=request.well_id,
            source=request.source,
            curve_count=len(classifications),
            classified_count=classified_count,
            unclassified_count=unclassified_count,
            review_required_count=review_required_count,
            classifications=classifications,
        )

    # ------------------------------------------------------------------
    # Internal classification logic
    # ------------------------------------------------------------------

    def _classify_one(self, curve: CurveClassifyInput) -> CurveClassificationResult:
        """Resolve and classify a single curve input.

        Delegates resolution entirely to KR-6.  Does not duplicate
        resolution logic.
        """
        resolve_input = CurveResolveInput(
            mnemonic=curve.mnemonic,
            unit=curve.unit,
            description=curve.description,
        )
        resolve_result = self._resolver.resolve_curve(resolve_input)

        if resolve_result.resolved:
            classification_status = _STATUS_CLASSIFIED
            review_required = False
        else:
            classification_status = _STATUS_UNCLASSIFIED
            review_required = True

        return CurveClassificationResult(
            curve_id=curve.curve_id,
            mnemonic=resolve_result.mnemonic,
            normalized_mnemonic=resolve_result.normalized_mnemonic,
            resolved=resolve_result.resolved,
            classification_status=classification_status,
            source_curve_index=curve.source_curve_index,
            canonical_curve_id=resolve_result.canonical_curve_id,
            display_name=resolve_result.display_name,
            family=resolve_result.family,
            product_group=resolve_result.product_group,
            product_subgroup=resolve_result.product_subgroup,
            default_unit=resolve_result.default_unit,
            confidence=resolve_result.confidence,
            resolution_source=resolve_result.resolution_source,
            knowledge_record_id=resolve_result.record_id,
            display_rule=resolve_result.display_rule,
            review_required=review_required,
            warnings=resolve_result.warnings,
        )
