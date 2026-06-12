"""WLV KR-8 — Backend Display Recommendation Service.

Backend-owned service that accepts classified or raw curve inventory and
returns backend-owned display recommendations.

Architecture contract
---------------------
* Backend owns display recommendation truth.
* Display recommendation consumes KR-7 classification service — no
  classification or resolution logic is duplicated here.
* Frontend renders backend contracts only.
* Only production-eligible display rules (status in {SEED, APPROVED})
  participate in recommendations; candidate, rejected, and deprecated
  display rules are excluded by the underlying services.
* The service is offline-capable: no network calls, no external deps.
* Storage is replaceable — the service depends only on
  CurveClassificationService, which depends on KnowledgeResolutionService,
  which depends on ManagedKRRepository.
* Input order is strictly preserved in recommendation results.
* Source curve identity (curve_id, source_curve_index) is preserved.
* The service never mutates storage, does not alter WDV state, and does
  not alter MDP state.

Recommendation status values
------------------------------
  recommended    — classified AND approved/seed display rule found
  unrecommended  — unclassified (no recommendation possible)
  review_required — classified but no display rule found

Decision rules
--------------
  classified + display rule found  → recommended
  classified + no display rule     → review_required
  unclassified                     → unrecommended + review_required

Dependency chain
-----------------
  DisplayRecommendationService
    uses CurveClassificationService         (KR-7)
      uses KnowledgeResolutionService       (KR-6)
        uses ManagedKRRepository            (KR-5)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .classification_service import (
    ClassificationSource,
    CurveClassificationRequest,
    CurveClassificationResult,
    CurveClassificationService,
    CurveClassifyInput,
)

KR8_VERSION = "kr-8"

# ---------------------------------------------------------------------------
# Recommendation status constants
# ---------------------------------------------------------------------------

_STATUS_RECOMMENDED = "recommended"
_STATUS_UNRECOMMENDED = "unrecommended"
_STATUS_REVIEW_REQUIRED = "review_required"

# ---------------------------------------------------------------------------
# Classification status passthrough constants (mirrors KR-7 values)
# ---------------------------------------------------------------------------

_CLASSIFIED = "classified"
_UNCLASSIFIED = "unclassified"


# ---------------------------------------------------------------------------
# Input dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CurveRecommendInput:
    """Input contract for a single curve to receive a display recommendation.

    Preserves source identity fields so the caller can correlate results back
    to the original import inventory.  This is the same shape as
    CurveClassifyInput — KR-8 accepts raw curves and classifies internally.
    """

    curve_id: str
    mnemonic: str
    unit: Optional[str] = None
    description: Optional[str] = None
    source_curve_index: Optional[int] = None


@dataclass
class DisplayRecommendationRequest:
    """Full recommendation request for a batch of curves from a single context."""

    curves: list[CurveRecommendInput]
    well_id: Optional[str] = None
    source: Optional[ClassificationSource] = None


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CurveDisplayRecommendation:
    """Display recommendation result for a single curve.

    When recommendation_status="recommended", all display fields are populated.
    When recommendation_status="unrecommended" (unclassified curve), display
    fields are None.
    When recommendation_status="review_required" (classified, no display rule),
    classification fields are populated but display scale fields are None.
    """

    curve_id: str
    mnemonic: str
    normalized_mnemonic: str
    canonical_curve_id: Optional[str]
    classification_status: str
    recommendation_status: str

    # Source identity preservation
    source_curve_index: Optional[int]

    # Classification / knowledge fields (populated when classified)
    display_name: Optional[str] = None
    product_group: Optional[str] = None
    product_subgroup: Optional[str] = None
    display_family: Optional[str] = None

    # Display rule fields (populated when recommended)
    scale_type: Optional[str] = None
    recommended_min: Optional[float] = None
    recommended_max: Optional[float] = None
    unit: Optional[str] = None
    preferred_track_group: Optional[str] = None

    review_required: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class DisplayRecommendationBatchResult:
    """Display recommendation result for a full batch of curves.

    Includes aggregate counts and the ordered list of per-curve results.
    Input order is strictly preserved.
    """

    kr_version: str
    well_id: Optional[str]

    curve_count: int
    recommended_count: int
    unrecommended_count: int
    review_required_count: int

    recommendations: list[CurveDisplayRecommendation]


# ---------------------------------------------------------------------------
# DisplayRecommendationService
# ---------------------------------------------------------------------------


class DisplayRecommendationService:
    """Backend-owned display recommendation service (KR-8).

    Accepts a batch of raw curves, classifies each via the KR-7 classification
    service, then applies approved/seed display rules to return ordered display
    recommendations.

    Only production-eligible display rules (status ∈ {SEED, APPROVED}) affect
    recommendations.  Candidate, rejected, and deprecated display rules are
    excluded by the underlying KR-6 resolution service.

    Usage::

        service = DisplayRecommendationService(classification_service)
        result  = service.recommend_display(request)
    """

    def __init__(self, classification_service: CurveClassificationService) -> None:
        self._classifier = classification_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend_display(
        self,
        request: DisplayRecommendationRequest,
    ) -> DisplayRecommendationBatchResult:
        """Return display recommendations for a batch of raw curves.

        Input order is strictly preserved.  Each curve is independently
        processed; one unresolvable mnemonic does not affect others.
        Never raises; unclassified or rule-missing curves are marked
        appropriately.

        Does not mutate storage, alter WDV state, or alter MDP state.
        """
        classify_inputs: list[CurveClassifyInput] = [
            CurveClassifyInput(
                curve_id=c.curve_id,
                mnemonic=c.mnemonic,
                unit=c.unit,
                description=c.description,
                source_curve_index=c.source_curve_index,
            )
            for c in request.curves
        ]

        classification_request = CurveClassificationRequest(
            curves=classify_inputs,
            well_id=request.well_id,
            source=request.source,
        )
        classification_result = self._classifier.classify_curves(classification_request)

        recommendations: list[CurveDisplayRecommendation] = [
            self._make_recommendation(c)
            for c in classification_result.classifications
        ]

        recommended_count = sum(
            1 for r in recommendations if r.recommendation_status == _STATUS_RECOMMENDED
        )
        unrecommended_count = sum(
            1 for r in recommendations if r.recommendation_status == _STATUS_UNRECOMMENDED
        )
        review_required_count = sum(1 for r in recommendations if r.review_required)

        return DisplayRecommendationBatchResult(
            kr_version=KR8_VERSION,
            well_id=request.well_id,
            curve_count=len(recommendations),
            recommended_count=recommended_count,
            unrecommended_count=unrecommended_count,
            review_required_count=review_required_count,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Internal recommendation logic
    # ------------------------------------------------------------------

    def _make_recommendation(
        self,
        classification: CurveClassificationResult,
    ) -> CurveDisplayRecommendation:
        """Apply recommendation rules to a single classification result.

        Decision rules:
          unclassified                     → unrecommended + review_required
          classified + no display rule     → review_required
          classified + display rule found  → recommended
        """
        # Rule: unclassified → unrecommended + review_required
        if not classification.resolved:
            return CurveDisplayRecommendation(
                curve_id=classification.curve_id,
                mnemonic=classification.mnemonic,
                normalized_mnemonic=classification.normalized_mnemonic,
                canonical_curve_id=None,
                classification_status=_UNCLASSIFIED,
                recommendation_status=_STATUS_UNRECOMMENDED,
                source_curve_index=classification.source_curve_index,
                review_required=True,
                warnings=["No display recommendation because curve is unclassified"],
            )

        dr = classification.display_rule

        # Rule: classified + no display rule → review_required
        if dr is None:
            return CurveDisplayRecommendation(
                curve_id=classification.curve_id,
                mnemonic=classification.mnemonic,
                normalized_mnemonic=classification.normalized_mnemonic,
                canonical_curve_id=classification.canonical_curve_id,
                classification_status=_CLASSIFIED,
                recommendation_status=_STATUS_REVIEW_REQUIRED,
                source_curve_index=classification.source_curve_index,
                display_name=classification.display_name,
                product_group=classification.product_group,
                product_subgroup=classification.product_subgroup,
                display_family=classification.family,
                review_required=True,
                warnings=["Curve is classified but no approved display rule was found"],
            )

        # Rule: classified + display rule found → recommended
        return CurveDisplayRecommendation(
            curve_id=classification.curve_id,
            mnemonic=classification.mnemonic,
            normalized_mnemonic=classification.normalized_mnemonic,
            canonical_curve_id=classification.canonical_curve_id,
            classification_status=_CLASSIFIED,
            recommendation_status=_STATUS_RECOMMENDED,
            source_curve_index=classification.source_curve_index,
            display_name=classification.display_name,
            product_group=classification.product_group,
            product_subgroup=classification.product_subgroup,
            display_family=classification.family,
            scale_type=dr.scale_type,
            recommended_min=dr.recommended_min,
            recommended_max=dr.recommended_max,
            unit=dr.unit,
            preferred_track_group=dr.preferred_track_family,
            review_required=False,
            warnings=[],
        )
