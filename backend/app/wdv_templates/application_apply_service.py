"""Backend-owned WDV template application service.

This service is the mutation boundary between KR-backed template planning and
canonical WDV session/layout state.
"""

from __future__ import annotations

from typing import Any

from app.knowledge.managed_repository import ManagedKRRepository
from app.wdv_session.models import (
    WdvSessionCurveAssignmentState,
    WdvSessionLayoutPutRequest,
    WdvSessionTrackLayoutState,
)
from app.wdv_session.service import WdvSessionLayoutStateService

from .application_plan_service import WdvTemplateApplicationPlanService
from .models import (
    WdvRecommendedCurveResponse,
    WdvTemplateApplicationApplyEnvelope,
    WdvTemplateApplicationApplyRequest,
    WdvTemplateApplicationApplySummary,
    WdvTemplateApplicationTrackPlanResponse,
)


class WdvTemplateApplicationApplyBlockedError(ValueError):
    """Raised when a plan is not eligible for backend-owned application."""

    def __init__(self, template_key: str, blocking_issues: list[str]) -> None:
        self.template_key = template_key
        self.blocking_issues = blocking_issues
        super().__init__(f"WDV template application blocked for {template_key}: {', '.join(blocking_issues) or 'not eligible'}")


class WdvTemplateApplicationApplyService:
    """Apply KR-backed WDV templates to backend-owned WDV session layout."""

    def __init__(
        self,
        repository: ManagedKRRepository | None = None,
        layout_service: WdvSessionLayoutStateService | None = None,
        plan_service: WdvTemplateApplicationPlanService | None = None,
    ) -> None:
        if plan_service is None and repository is None:
            raise ValueError("repository is required when plan_service is not supplied")
        self._plan_service = plan_service or WdvTemplateApplicationPlanService(repository=repository)
        self._layout_service = layout_service or WdvSessionLayoutStateService()

    def apply_from_request(
        self,
        request: WdvTemplateApplicationApplyRequest,
    ) -> WdvTemplateApplicationApplyEnvelope:
        plan_envelope = self._plan_service.build_from_request(request)
        plan = plan_envelope.plan

        if not plan.apply_eligible:
            raise WdvTemplateApplicationApplyBlockedError(
                template_key=plan.template_key,
                blocking_issues=plan.blocking_issues or ["template_application_not_eligible"],
            )

        session_tracks = self._session_tracks_from_plan(plan.tracks, plan.template_key, plan.application_plan_id)
        selected_track_id = session_tracks[0].track_id if session_tracks else None
        layout = self._layout_service.put_layout(
            request.managed_well_id,
            WdvSessionLayoutPutRequest(
                selected_track_id=selected_track_id,
                tracks=session_tracks,
                source=f"backend_template_apply:{plan.template_key}",
            ),
        )

        curve_count = sum(len(track.curves) for track in session_tracks)
        warnings = list(plan.warnings or [])
        if not curve_count:
            warnings.append("template_applied_without_curve_assignments")

        return WdvTemplateApplicationApplyEnvelope(
            managed_well_id=request.managed_well_id,
            template_key=plan.template_key,
            application_plan_id=plan.application_plan_id,
            layout=layout.model_dump(mode="json"),
            apply_summary=WdvTemplateApplicationApplySummary(
                track_count=len(session_tracks),
                curve_assignment_count=curve_count,
                warnings=sorted(set(warnings)),
            ),
            knowledge_policy=plan_envelope.knowledge_policy,
        )

    def _session_tracks_from_plan(
        self,
        tracks: list[WdvTemplateApplicationTrackPlanResponse],
        template_key: str,
        application_plan_id: str,
    ) -> list[WdvSessionTrackLayoutState]:
        out: list[WdvSessionTrackLayoutState] = []
        for index, track in enumerate(sorted(tracks, key=lambda item: item.track_number if item.track_number is not None else 9999)):
            track_type = self._session_track_type(track)
            assignments = [] if track_type == "depth" else self._assignments_for_track(track, list(track.selected_curves or []))
            out.append(
                WdvSessionTrackLayoutState(
                    track_id=self._stable_track_id(track, index),
                    track_key=track.track_key or track.track_id,
                    track_number=track.track_number if track.track_number is not None else index,
                    track_name=track.track_name or track.track_key or f"Track {index + 1}",
                    track_type=track_type,
                    renderer_type=track.renderer_type,
                    track_role=track.track_role,
                    width_px=65 if track_type == "depth" else 220,
                    lattice="logarithmic" if self._track_uses_log_lattice(track) else "linear",
                    lattice_source="backend_template_default",
                    curves=assignments,
                    source_template_key=template_key,
                    source_application_plan_id=application_plan_id,
                )
            )
        return out

    def _assignments_for_track(
        self,
        track: WdvTemplateApplicationTrackPlanResponse,
        curves: list[WdvRecommendedCurveResponse],
    ) -> list[WdvSessionCurveAssignmentState]:
        assignments: list[WdvSessionCurveAssignmentState] = []
        for stack_index, curve in enumerate(curves):
            scale = self._scale_for_curve(track.scale_defaults or [], curve)
            curve_id = curve.curve_id or curve.product_id
            product_id = curve.product_id or curve_id
            curve_uid = curve.curve_uid or product_id
            assignments.append(
                WdvSessionCurveAssignmentState(
                    assignment_id=self._stable_assignment_id(track, curve, stack_index),
                    curve_uid=curve_uid,
                    well_uid=curve.well_uid,
                    source_uid=curve.source_uid,
                    kr_curve_type_id=curve.kr_curve_type_id,
                    observed_mnemonic=curve.observed_mnemonic or curve.mnemonic,
                    normalized_mnemonic=curve.normalized_mnemonic or curve.mnemonic,
                    curve_id=curve_id,
                    product_id=product_id,
                    display_curve_id=curve_id,
                    mnemonic=curve.mnemonic,
                    display_name=curve.display_name or curve.mnemonic or curve_id,
                    curve_family=curve.curve_family or curve.raw_curve_family,
                    unit=curve.unit,
                    stack_index=stack_index,
                    visible=True,
                    scale_min=self._scale_number(scale.get("scale_min")),
                    scale_max=self._scale_number(scale.get("scale_max")),
                    scale_type=self._scale_type(scale.get("scale_type")),
                    scale_direction=self._scale_direction(scale.get("display_direction")),
                    color=None,
                    source="backend_template_apply",
                )
            )
        return assignments

    def _session_track_type(self, track: WdvTemplateApplicationTrackPlanResponse) -> str:
        renderer = self._key(track.renderer_type)
        key = self._key(track.track_key or track.track_id or track.track_name)
        role = self._key(track.track_role)
        if not track.selected_curves and ("depth" in key or "reference" in key or "event" in renderer or "event" in role):
            return "depth"
        return "curve"

    def _track_uses_log_lattice(self, track: WdvTemplateApplicationTrackPlanResponse) -> bool:
        renderer = self._key(track.renderer_type)
        if "log" in renderer:
            return True
        for scale in track.scale_defaults or []:
            if self._scale_type(scale.get("scale_type")) == "log":
                return True
        return False

    def _scale_for_curve(self, scale_defaults: list[dict[str, Any]], curve: WdvRecommendedCurveResponse) -> dict[str, Any]:
        curve_family = self._key(curve.curve_family or curve.raw_curve_family)
        for scale in scale_defaults:
            if self._key(scale.get("curve_family")) == curve_family:
                return scale
        return scale_defaults[0] if scale_defaults else {}

    def _stable_track_id(self, track: WdvTemplateApplicationTrackPlanResponse, index: int) -> str:
        base = track.track_id or track.track_key or track.track_name or f"track_{index + 1}"
        return f"wdv_template_track:{self._key(base) or index + 1}"

    def _stable_assignment_id(
        self,
        track: WdvTemplateApplicationTrackPlanResponse,
        curve: WdvRecommendedCurveResponse,
        stack_index: int,
    ) -> str:
        track_key = self._key(track.track_id or track.track_key or track.track_name) or "track"
        curve_key = self._key(curve.curve_uid or curve.product_id or curve.curve_id or curve.mnemonic) or f"curve_{stack_index}"
        return f"wdv_template_assignment:{track_key}:{curve_key}:{stack_index}"

    @staticmethod
    def _scale_number(value: Any) -> float | int | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _scale_type(value: Any) -> str | None:
        key = WdvTemplateApplicationApplyService._key(value)
        if key in {"log", "logarithmic"}:
            return "log"
        if key == "linear":
            return "linear"
        return None

    @staticmethod
    def _scale_direction(value: Any) -> str:
        key = WdvTemplateApplicationApplyService._key(value)
        if key in {"reverse", "reversed", "right_to_left", "decreasing"}:
            return "reverse"
        return "normal"

    @staticmethod
    def _key(value: Any) -> str:
        return str(value or "").strip().lower().replace("-", "_").replace("/", "_").replace(" ", "_")
