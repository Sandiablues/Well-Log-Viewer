"""Backend-owned WDV template application-plan service.

This service converts a selected approved KR-backed recommendation into a
non-mutating application plan.  It does not apply a template, populate tracks,
or mutate WDV/MDP/inventory/session state.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.app.knowledge.managed_repository import ManagedKRRepository

from .models import (
    WdvTemplateApplicationPlanEnvelope,
    WdvTemplateApplicationPlanRequest,
    WdvTemplateApplicationPlanResponse,
    WdvTemplateApplicationTrackPlanResponse,
    WdvTemplateRecommendationRequest,
)
from .recommendation_service import WdvTemplateRecommendationService


class WdvTemplateApplicationPlanNotFoundError(KeyError):
    """Raised when the selected template is unavailable in the recommendation contract."""


class WdvTemplateApplicationPlanService:
    """Build non-mutating backend-owned WDV template application plans."""

    def __init__(self, repository: ManagedKRRepository) -> None:
        self._recommendation_service = WdvTemplateRecommendationService(repository=repository)

    def build_from_request(
        self,
        request: WdvTemplateApplicationPlanRequest,
    ) -> WdvTemplateApplicationPlanEnvelope:
        """Return a staged application plan for one selected template.

        The method intentionally re-evaluates recommendations from backend KR
        truth.  The frontend may request a template by key, but it cannot supply
        its own ranking/eligibility/curve-selection truth.
        """

        recommendation_request = WdvTemplateRecommendationRequest(
            loaded_curve_items=request.loaded_curve_items,
            workflow_context=request.workflow_context,
            selected_product_ids=request.selected_product_ids,
            include_ineligible=True,
        )
        recommendation_envelope = self._recommendation_service.recommend_from_request(
            recommendation_request,
        )
        selected = None
        for recommendation in recommendation_envelope.recommendations:
            if recommendation.template_key == request.template_key:
                selected = recommendation
                break
        if selected is None:
            raise WdvTemplateApplicationPlanNotFoundError(request.template_key)

        blocking_issues: list[str] = []
        warnings: list[str] = []
        if selected.missing_required_families:
            blocking_issues.append("missing_required_families")
        if not selected.is_eligible:
            blocking_issues.append("template_not_eligible_for_loaded_data")
        if not selected.selected_curves:
            warnings.append("no_representative_curves_selected")
        if selected.missing_preferred_families:
            warnings.append("missing_preferred_families")
        if selected.excluded_curve_count:
            warnings.append("loaded_curves_not_used_by_selected_template")

        plan_tracks = [
            WdvTemplateApplicationTrackPlanResponse(
                track_id=track.track_id,
                track_key=track.track_key,
                track_number=track.track_number,
                track_name=track.track_name,
                track_role=track.track_role,
                renderer_type=track.renderer_type,
                required_renderer_capability=track.required_renderer_capability,
                selected_curves=track.selected_curves,
                alternate_curves=track.alternate_curves,
                missing_curve_families=track.missing_curve_families,
                scale_defaults=track.scale_defaults,
            )
            for track in selected.tracks
        ]

        plan = WdvTemplateApplicationPlanResponse(
            application_plan_id=self._plan_id(request, selected.template_key),
            plan_status="ready_for_review" if not blocking_issues else "blocked_pending_review",
            template_key=selected.template_key,
            template_label=selected.template_label,
            workflow_context=selected.workflow_context,
            source_recommendation_rank=selected.rank,
            source_recommendation_score=selected.score,
            apply_eligible=not blocking_issues,
            blocking_issues=sorted(set(blocking_issues)),
            warnings=sorted(set(warnings)),
            selected_curve_count=selected.selected_curve_count,
            alternate_curve_count=selected.alternate_curve_count,
            excluded_curve_count=selected.excluded_curve_count,
            selected_curves=selected.selected_curves,
            alternate_curves=selected.alternate_curves,
            excluded_curves=selected.excluded_curves,
            tracks=plan_tracks,
            renderer_requirements=selected.renderer_requirements,
            missing_required_families=selected.missing_required_families,
            missing_preferred_families=selected.missing_preferred_families,
            reason_codes=selected.reason_codes,
        )

        return WdvTemplateApplicationPlanEnvelope(
            plan=plan,
            knowledge_policy=recommendation_envelope.knowledge_policy,
        )

    def _plan_id(
        self,
        request: WdvTemplateApplicationPlanRequest,
        template_key: str,
    ) -> str:
        payload: dict[str, Any] = {
            "template_key": template_key,
            "workflow_context": request.workflow_context,
            "selected_product_ids": sorted(request.selected_product_ids),
            "loaded_curve_items": [item.model_dump(mode="json") for item in request.loaded_curve_items],
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8"),
        ).hexdigest()[:16]
        return f"wdv_template_application_plan_{digest}"
