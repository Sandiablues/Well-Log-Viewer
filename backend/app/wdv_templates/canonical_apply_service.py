"""Canonical backend-owned governed WDV template application."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import (
    CanonicalUuid7,
    NonBlankString,
    WdvCanonicalAssignment,
    WdvCanonicalSession,
    WdvCanonicalTrack,
)
from app.inventory.canonical_identity_resolver import (
    CanonicalIdentityResolutionError,
    CanonicalInventoryIdentityResolver,
)
from app.wdv_display.policy_service import (
    WdvCurveDisplayPolicyService,
    compute_display_policy_revision,
)
from app.wdv_session.assignment_policy_service import (
    CanonicalWdvAssignmentPolicyService,
)
from app.wdv_session.canonical_service import CanonicalWdvSessionService
from app.wdv_workspace.service import CanonicalWdvWorkspaceService
from app.wdv_workspace.transaction_service import CanonicalWdvWorkspaceTransactionService
from app.wells.canonical_viewer_package_service import CanonicalViewerPackageService
from app.wdv_templates.application_plan_service import (
    WdvTemplateApplicationPlanNotFoundError,
    WdvTemplateApplicationPlanService,
)
from app.wdv_templates.models import (
    WdvLoadedCurveRecommendationInput,
    WdvRecommendedCurveResponse,
    WdvTemplateApplicationPlanRequest,
    WdvTemplateApplicationTrackPlanResponse,
)


class ApplyGovernedTemplateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_revision: int
    command_id: CanonicalUuid7 | None = None
    template_key: NonBlankString
    workflow_context: str | None = None


class CanonicalTemplateApplyError(ValueError):
    pass


class CanonicalTemplateApplyBlockedError(CanonicalTemplateApplyError):
    def __init__(
        self,
        template_key: str,
        blocking_issues: list[str],
    ) -> None:
        self.template_key = template_key
        self.blocking_issues = blocking_issues
        super().__init__(
            f"Canonical template application blocked for {template_key}: "
            + ", ".join(blocking_issues or ["not eligible"])
        )


class CanonicalWdvTemplateApplyService:
    def __init__(
        self,
        *,
        plan_service: WdvTemplateApplicationPlanService,
        resolver: CanonicalInventoryIdentityResolver | None = None,
        session_service: CanonicalWdvSessionService | None = None,
        transaction_service: CanonicalWdvWorkspaceTransactionService | None = None,
    ) -> None:
        self.plan_service = plan_service
        self.resolver = resolver or CanonicalInventoryIdentityResolver()
        self.assignment_policy_service = CanonicalWdvAssignmentPolicyService(
            resolver=self.resolver,
            display_policy_resolver=WdvCurveDisplayPolicyService.resolve,
        )
        self.session_service = session_service or CanonicalWdvSessionService()
        if transaction_service is None:
            workspace_service = None
            if isinstance(self.resolver, CanonicalInventoryIdentityResolver):
                viewer_package_service = CanonicalViewerPackageService(
                    resolver=self.resolver,
                    session_service=self.session_service,
                )
                workspace_service = CanonicalWdvWorkspaceService(
                    viewer_package_service=viewer_package_service,
                    session_service=self.session_service,
                )
            transaction_service = CanonicalWdvWorkspaceTransactionService(
                session_service=self.session_service,
                workspace_service=workspace_service,
            )
        self.transaction_service = transaction_service

    def apply(
        self,
        managed_well_uid: str,
        command: ApplyGovernedTemplateCommand,
    ) -> WdvCanonicalSession:
        well = self.resolver.resolve_well(managed_well_uid)
        loaded_items = self._loaded_curve_items(well)

        plan_envelope = self.plan_service.build_from_request(
            WdvTemplateApplicationPlanRequest(
                template_key=command.template_key,
                loaded_curve_items=loaded_items,
                workflow_context=command.workflow_context,
                selected_product_ids=[],
                include_ineligible_recommendations=True,
            )
        )
        plan = plan_envelope.plan

        if not plan.apply_eligible:
            raise CanonicalTemplateApplyBlockedError(
                plan.template_key,
                list(plan.blocking_issues or ["template_application_not_eligible"]),
            )

        application_plan_uid = new_uuid7_str()

        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            tracks = self._tracks_from_plan(
                managed_well_uid=managed_well_uid,
                template_key=plan.template_key,
                application_plan_uid=application_plan_uid,
                planned_tracks=plan.tracks,
            )
            warnings = tuple(sorted(set(plan.warnings or [])))
            if not any(track.assignments for track in tracks):
                warnings = tuple(sorted(set((*warnings, "template_applied_without_curve_assignments"))))
            retained = tuple(
                track for track in session.tracks
                if track.managed_well_uid != managed_well_uid
            )
            combined = tuple(
                track.model_copy(update={"track_number": index})
                for index, track in enumerate((*retained, *tracks))
            )
            return session.model_copy(
                update={
                    "state_status": "active" if combined else "empty",
                    "source": f"canonical_template_apply:{plan.template_key}",
                    "tracks": combined,
                    "selected_track_uid": (tracks[0].track_uid if tracks else session.selected_track_uid),
                    "warnings": warnings,
                    "display_policy_revision": compute_display_policy_revision(),
                }
            )

        return self.transaction_service.execute(
            managed_well_uid,
            expected_revision=command.expected_revision,
            command_name=command.__class__.__name__,
            command_payload=command.model_dump(
                mode="json",
                exclude={"expected_revision", "command_id"},
            ),
            command_id=command.command_id,
            mutation=mutate,
        )

    def _loaded_curve_items(self, well) -> list[WdvLoadedCurveRecommendationInput]:
        items: list[WdvLoadedCurveRecommendationInput] = []
        for group in well.product_groups:
            for product in group.items:
                if not product.selectable:
                    continue
                # Overlay/dataset products remain selectable in WDV inventory but
                # are not curve candidates for governed template recommendations.
                if product.managed_curve_uid is None and product.display_layer_type:
                    continue
                if product.managed_curve_uid is None:
                    raise CanonicalIdentityResolutionError(
                        f"Product {product.product_id} has no managed_curve_uid"
                    )
                if product.managed_product_uid is None:
                    raise CanonicalIdentityResolutionError(
                        f"Product {product.product_id} has no managed_product_uid"
                    )
                if product.managed_source_uid is None:
                    raise CanonicalIdentityResolutionError(
                        f"Product {product.product_id} has no managed_source_uid"
                    )

                items.append(
                    WdvLoadedCurveRecommendationInput(
                        product_id=str(product.managed_product_uid),
                        curve_uid=str(product.managed_curve_uid),
                        well_uid=str(well.managed_well_uid),
                        source_uid=str(product.managed_source_uid),
                        kr_curve_type_id=product.kr_curve_type_id,
                        observed_mnemonic=(
                            product.observed_mnemonic
                            or product.curve_name
                            or product.display_name
                        ),
                        normalized_mnemonic=product.normalized_mnemonic,
                        curve_id=str(product.managed_curve_uid),
                        display_curve_id=str(product.managed_curve_uid),
                        mnemonic=(
                            product.observed_mnemonic
                            or product.curve_name
                            or product.display_name
                        ),
                        display_name=product.display_name,
                        curve_family=product.curve_family,
                        track_family=None,
                        unit=product.curve_unit,
                        is_renderable=True,
                        support_status="supported",
                        source_id=str(product.managed_source_uid),
                    )
                )
        return items

    def _tracks_from_plan(
        self,
        *,
        managed_well_uid: str,
        template_key: str,
        application_plan_uid: str,
        planned_tracks: list[WdvTemplateApplicationTrackPlanResponse],
    ) -> tuple[WdvCanonicalTrack, ...]:
        tracks: list[WdvCanonicalTrack] = []
        ordered = sorted(
            planned_tracks,
            key=lambda item: (
                item.track_number if item.track_number is not None else 9999,
                item.track_key,
            ),
        )

        for index, planned in enumerate(ordered):
            track_uid = new_uuid7_str()
            track_type = self._track_type(planned)
            assignments = (
                ()
                if track_type == "depth"
                else self._assignments_for_track(
                    managed_well_uid=managed_well_uid,
                    track_uid=track_uid,
                    planned=planned,
                )
            )
            lattice = self._track_lattice(planned, assignments)
            tracks.append(
                WdvCanonicalTrack(
                    track_uid=track_uid,
                    managed_well_uid=managed_well_uid,
                    track_key=planned.track_key or planned.track_id,
                    track_number=(
                        planned.track_number
                        if planned.track_number is not None
                        else index
                    ),
                    track_name=(
                        planned.track_name
                        or planned.track_key
                        or f"Track {index + 1}"
                    ),
                    track_type=track_type,
                    renderer_type=planned.renderer_type,
                    track_role=planned.track_role,
                    width_px=65 if track_type == "depth" else 220,
                    lattice=lattice,
                    lattice_source="governed_template",
                    source_template_key=template_key,
                    source_application_plan_uid=application_plan_uid,
                    visible=True,
                    scale_mode="per_curve",
                    lattice_override=False,
                    depth_basis="MD" if track_type == "depth" else None,
                    assignments=assignments,
                )
            )
        return tuple(tracks)

    def _assignments_for_track(
        self,
        *,
        managed_well_uid: str,
        track_uid: str,
        planned: WdvTemplateApplicationTrackPlanResponse,
    ) -> tuple[WdvCanonicalAssignment, ...]:
        assignments: list[WdvCanonicalAssignment] = []
        for stack_index, curve in enumerate(planned.selected_curves or []):
            managed_curve_uid = self._selected_curve_uid(curve)
            resolved = self.resolver.resolve_curve(
                managed_well_uid,
                managed_curve_uid,
            )
            display = WdvCurveDisplayPolicyService.resolve(
                resolved.product,
                {},
            )
            scale = self._scale_for_curve(planned.scale_defaults or [], curve)

            scale_min = self._number(
                scale.get("scale_min"),
                default=display["min"],
            )
            scale_max = self._number(
                scale.get("scale_max"),
                default=display["max"],
            )
            scale_type = self._scale_type(
                scale.get("scale_type"),
                default=display["type"],
            )
            scale_direction = self._scale_direction(
                scale.get("display_direction"),
                default=display["direction"],
            )

            base_assignment = (
                self.assignment_policy_service.create_assignment_from_resolved(
                    resolved=resolved,
                    track_uid=track_uid,
                    stack_index=stack_index,
                    assignment_source="canonical_governed_template_apply",
                    visible=True,
                    color=display["default_color"],
                    line_style="solid",
                    line_width=1.8,
                    fill_mode=None,
                )
            )
            assignments.append(
                base_assignment.model_copy(
                    update={
                        "scale_min": scale_min,
                        "scale_max": scale_max,
                        "scale_type": scale_type,
                        "scale_direction": scale_direction,
                        "line_visible": True,
                        "line_opacity": 100,
                        "range_mode": "fixed",
                        "position_anchor": "center",
                        "horizontal_offset_pct": 0.0,
                        "clip_to_track": True,
                        "fill_side": "none",
                        "fill_color": display["default_color"],
                        "fill_opacity": 55,
                        "infill_source": "solid",
                        "infill_pattern": "solid",
                        "infill_interval_column": "lithology",
                        "paired_managed_curve_uid": None,
                        "display_priority": "normal",
                        "show_qaqc_warnings": True,
                        "show_null_gaps": True,
                        "show_out_of_range": True,
                    }
                )
            )
        return tuple(assignments)

    @staticmethod
    def _selected_curve_uid(curve: WdvRecommendedCurveResponse) -> str:
        value = str(curve.curve_uid or "").strip()
        if not value:
            raise CanonicalTemplateApplyError(
                "Governed plan selected a curve without managed_curve_uid"
            )
        return value

    @staticmethod
    def _track_type(
        planned: WdvTemplateApplicationTrackPlanResponse,
    ) -> Literal["depth", "curve"]:
        renderer = CanonicalWdvTemplateApplyService._key(planned.renderer_type)
        key = CanonicalWdvTemplateApplyService._key(
            planned.track_key or planned.track_id or planned.track_name
        )
        role = CanonicalWdvTemplateApplyService._key(planned.track_role)
        if (
            not planned.selected_curves
            and (
                "depth" in key
                or "reference" in key
                or "event" in renderer
                or "event" in role
            )
        ):
            return "depth"
        return "curve"

    @staticmethod
    def _track_lattice(
        planned: WdvTemplateApplicationTrackPlanResponse,
        assignments: tuple[WdvCanonicalAssignment, ...],
    ) -> str:
        renderer = CanonicalWdvTemplateApplyService._key(planned.renderer_type)
        if "log" in renderer:
            return "logarithmic"
        if any(item.scale_type == "logarithmic" for item in assignments):
            return "logarithmic"
        return "linear"

    @staticmethod
    def _scale_for_curve(
        defaults: list[dict],
        curve: WdvRecommendedCurveResponse,
    ) -> dict:
        family = CanonicalWdvTemplateApplyService._key(
            curve.curve_family or curve.raw_curve_family
        )
        for item in defaults:
            if CanonicalWdvTemplateApplyService._key(
                item.get("curve_family")
            ) == family:
                return item
        return defaults[0] if defaults else {}

    @staticmethod
    def _number(value, *, default: "float | None") -> "float | None":
        if value is None or value == "":
            if default is None:
                return None
            try:
                return float(default)
            except (TypeError, ValueError):
                return None
        try:
            return float(value)
        except (TypeError, ValueError):
            if default is None:
                return None
            try:
                return float(default)
            except (TypeError, ValueError):
                return None

    @staticmethod
    def _scale_type(value, *, default: str) -> str:
        key = CanonicalWdvTemplateApplyService._key(value)
        if key in {"log", "logarithmic"}:
            return "logarithmic"
        if key == "linear":
            return "linear"
        return "logarithmic" if default in {"log", "logarithmic"} else "linear"

    @staticmethod
    def _scale_direction(value, *, default: str) -> str:
        key = CanonicalWdvTemplateApplyService._key(value)
        if key in {"reverse", "reversed", "right_to_left", "decreasing"}:
            return "reversed"
        if key in {"normal", "left_to_right", "increasing"}:
            return "normal"
        return "reversed" if default in {"reverse", "reversed"} else "normal"

    @staticmethod
    def _key(value) -> str:
        return (
            str(value or "")
            .strip()
            .lower()
            .replace("-", "_")
            .replace("/", "_")
            .replace(" ", "_")
        )
