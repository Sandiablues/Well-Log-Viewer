"""Backend-owned canonical Curve Fill geometry resolution and incremental deltas."""
from __future__ import annotations

from hashlib import sha256
import json

from pydantic import BaseModel, ConfigDict, Field

from app.curve_fill_v2.models import (
    CanonicalCurveFillRule,
    CurveFillGeometry,
    CurveFillRule,
    CurveFillRuleState,
    CurveSeries,
    CurveTransform,
    ScaleDirection,
    ScaleType,
)
from app.curve_fill_v2.service import CurveFillResolutionError, CurveFillResolutionService
from app.curve_fill_v2.models import FillAppearance, ResolvedFillPaint, ResolvedRasterPaint
from app.curve_fill_v2.paint_catalog import pattern_by_uid, raster_by_uid
from app.identity.wdv_contract_v2 import WdvCanonicalAssignment, WdvCanonicalSession, WdvCurveSampleRequest
from app.inventory.canonical_curve_sample_service import CanonicalCurveSampleService
from app.wdv_session.canonical_service import CanonicalWdvSessionService


class CurveFillGeometryCommandError(ValueError):
    pass


class ResolveCurveFillGeometryCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected_revision: int = Field(ge=0)
    rule_uid: str = Field(min_length=1)
    max_samples: int = Field(default=100000, ge=2, le=100000)


class CurveFillGeometryDelta(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: str = "wdv_curve_fill_geometry_delta_v2"
    managed_well_uid: str
    session_revision: int = Field(ge=0)
    upsert: tuple[CurveFillGeometry, ...] = ()
    remove: tuple[str, ...] = ()


class CanonicalCurveFillGeometryService:
    def __init__(
        self,
        *,
        session_service: CanonicalWdvSessionService | None = None,
        sample_service: CanonicalCurveSampleService | None = None,
        resolution_service: CurveFillResolutionService | None = None,
    ) -> None:
        self.session_service = session_service or CanonicalWdvSessionService()
        self.sample_service = sample_service or CanonicalCurveSampleService()
        self.resolution_service = resolution_service or CurveFillResolutionService()

    def resolve_rule(
        self,
        managed_well_uid: str,
        command: ResolveCurveFillGeometryCommand,
    ) -> CurveFillGeometryDelta:
        session = self.session_service.get_session(managed_well_uid)
        if session.revision != command.expected_revision:
            from app.wdv_session.canonical_service import CanonicalSessionRevisionConflict
            raise CanonicalSessionRevisionConflict(
                f"Expected revision {command.expected_revision}, found {session.revision}"
            )
        rule = next((r for r in session.curve_fills if r.rule_uid == command.rule_uid), None)
        if rule is None:
            raise CurveFillGeometryCommandError(f"Unknown rule_uid: {command.rule_uid}")
        if not rule.enabled:
            return CurveFillGeometryDelta(
                managed_well_uid=managed_well_uid,
                session_revision=session.revision,
                remove=(rule.rule_uid,),
            )

        try:
            geometry = self._resolve(session, rule, command.max_samples)
        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            updated = self._update_rule_state(
                managed_well_uid,
                session.revision,
                rule.rule_uid,
                state=CurveFillRuleState.INVALID,
                state_reason=reason,
                geometry_revision=None,
            )
            raise CurveFillGeometryCommandError(reason) from exc

        updated = self._update_rule_state(
            managed_well_uid,
            session.revision,
            rule.rule_uid,
            state=CurveFillRuleState.RESOLVED,
            state_reason=None,
            geometry_revision=geometry.geometry_revision,
        )
        return CurveFillGeometryDelta(
            managed_well_uid=managed_well_uid,
            session_revision=updated.revision,
            upsert=(geometry,),
        )

    def invalidate_rule(
        self,
        managed_well_uid: str,
        *,
        expected_revision: int,
        rule_uid: str,
    ) -> CurveFillGeometryDelta:
        updated = self._update_rule_state(
            managed_well_uid,
            expected_revision,
            rule_uid,
            state=CurveFillRuleState.PENDING_GEOMETRY,
            state_reason=None,
            geometry_revision=None,
        )
        return CurveFillGeometryDelta(
            managed_well_uid=managed_well_uid,
            session_revision=updated.revision,
            remove=(rule_uid,),
        )

    def _resolve(
        self,
        session: WdvCanonicalSession,
        canonical: CanonicalCurveFillRule,
        max_samples: int,
    ) -> CurveFillGeometry:
        track = next((t for t in session.tracks if t.track_uid == canonical.track_uid), None)
        if track is None:
            raise CurveFillGeometryCommandError("Rule track is absent")
        assignments = {a.assignment_uid: a for a in track.assignments}
        a = assignments.get(canonical.curve_a_assignment_uid)
        b = assignments.get(canonical.curve_b_assignment_uid) if canonical.curve_b_assignment_uid else None
        if a is None or (canonical.curve_b_assignment_uid and b is None):
            raise CurveFillGeometryCommandError("Rule assignment is absent")

        series_a = self._series(session.managed_well_uid, a, max_samples)
        series_b = self._series(session.managed_well_uid, b, max_samples) if b else None
        width = track.width_px or 180
        transform_a = self._transform(a, width, session.display_policy_revision)
        transform_b = self._transform(b, width, session.display_policy_revision) if b else None
        if canonical.style.appearance == FillAppearance.PATTERN:
            pattern_by_uid(canonical.style.pattern_uid or "")
        elif canonical.style.appearance == FillAppearance.RASTER:
            raster_by_uid(session.managed_well_uid, canonical.style.raster_asset_uid or "")
        runtime_rule = CurveFillRule(
            rule_uid=canonical.rule_uid,
            managed_well_uid=canonical.managed_well_uid,
            track_uid=canonical.track_uid,
            order=canonical.order,
            enabled=canonical.enabled,
            rule_type=canonical.rule_type,
            curve_a_uid=a.managed_curve_uid,
            curve_b_uid=b.managed_curve_uid if b else None,
            comparison=canonical.comparison,
            boundary=canonical.boundary,
            overlay_policy_uid=canonical.overlay_policy_uid,
            overlay_policy_revision=canonical.overlay_policy_revision,
            deadband=canonical.deadband,
            minimum_interval=canonical.minimum_interval,
            style=canonical.style,
        )
        geometry = self.resolution_service.resolve(
            rule=runtime_rule,
            series_a=series_a,
            transform_a=transform_a,
            series_b=series_b,
            transform_b=transform_b,
        )
        if canonical.style.appearance == FillAppearance.RASTER:
            asset = raster_by_uid(session.managed_well_uid, canonical.style.raster_asset_uid or "")
            paint = ResolvedFillPaint(
                appearance=FillAppearance.RASTER,
                pattern_scale=canonical.style.pattern_scale,
                raster=ResolvedRasterPaint(**asset.model_dump()),
            )
        else:
            paint = ResolvedFillPaint(
                appearance=canonical.style.appearance,
                pattern_uid=canonical.style.pattern_uid,
                pattern_scale=canonical.style.pattern_scale,
            )
        return geometry.model_copy(update={"paint": paint})

    def _series(self, well_uid: str, assignment: WdvCanonicalAssignment, max_samples: int) -> CurveSeries:
        response = self.sample_service.get_curve_samples(
            WdvCurveSampleRequest(
                managed_well_uid=well_uid,
                managed_curve_uid=assignment.managed_curve_uid,
                max_samples=max_samples,
            )
        )
        revision = response.sample_revision or response.provenance.checksum or sha256(
            json.dumps(response.samples, separators=(",", ":")).encode()
        ).hexdigest()
        return CurveSeries(
            managed_well_uid=well_uid,
            managed_curve_uid=assignment.managed_curve_uid,
            sample_revision=revision,
            depth_unit=response.depth_unit,
            value_unit=response.value_unit,
            samples=response.samples,
        )

    @staticmethod
    def _transform(
        assignment: WdvCanonicalAssignment | None,
        width: int,
        display_policy_revision: str | None,
    ) -> CurveTransform | None:
        if assignment is None:
            return None
        if assignment.scale_min is None or assignment.scale_max is None:
            raise CurveFillGeometryCommandError(
                f"Assignment {assignment.assignment_uid} has no backend-resolved scale"
            )
        payload = {
            "assignment_uid": assignment.assignment_uid,
            "scale_min": assignment.scale_min,
            "scale_max": assignment.scale_max,
            "scale_type": assignment.scale_type,
            "scale_direction": assignment.scale_direction,
            "position_anchor": assignment.position_anchor,
            "horizontal_offset_pct": assignment.horizontal_offset_pct,
            "clip_to_track": assignment.clip_to_track,
            "width": width,
            "display_policy_revision": display_policy_revision,
        }
        revision = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return CurveTransform(
            assignment_uid=assignment.assignment_uid,
            managed_curve_uid=assignment.managed_curve_uid,
            transform_revision=revision,
            track_width_px=width,
            horizontal_padding_px=10.0,
            scale_min=assignment.scale_min,
            scale_max=assignment.scale_max,
            scale_type=ScaleType(assignment.scale_type or "linear"),
            scale_direction=ScaleDirection(assignment.scale_direction or "normal"),
            position_anchor=assignment.position_anchor,
            horizontal_offset_pct=assignment.horizontal_offset_pct,
            clip_to_track=assignment.clip_to_track,
        )

    def _update_rule_state(
        self,
        managed_well_uid: str,
        expected_revision: int,
        rule_uid: str,
        *,
        state: CurveFillRuleState,
        state_reason: str | None,
        geometry_revision: str | None,
    ) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            found = False
            rules = []
            for rule in session.curve_fills:
                if rule.rule_uid != rule_uid:
                    rules.append(rule)
                    continue
                found = True
                rules.append(rule.model_copy(update={
                    "state": state,
                    "state_reason": state_reason,
                    "geometry_revision": geometry_revision,
                }))
            if not found:
                raise CurveFillGeometryCommandError(f"Unknown rule_uid: {rule_uid}")
            return session.model_copy(update={"curve_fills": tuple(rules)})
        return self.session_service.mutate_session_transactionally(
            managed_well_uid,
            expected_revision=expected_revision,
            mutation=mutate,
        )
