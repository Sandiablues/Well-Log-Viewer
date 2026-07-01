"""Resolve canonical session fill definitions into renderer/export geometry."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from math import log10
from statistics import median

from app.curve_fill.models import (
    CurveFillResolveRequest,
    FillSample,
)
from app.curve_fill.service import CurveFillResolutionService
from app.identity.wdv_contract_v2 import (
    WdvCanonicalAssignment,
    WdvCanonicalCurveFill,
    WdvCanonicalSession,
    WdvCurveSampleRequest,
)
from app.inventory.canonical_curve_sample_service import CanonicalCurveSampleService
from app.wdv_session.canonical_service import CanonicalWdvSessionService

from .models import CurveFillRenderItem, CurveFillRenderPackage


@dataclass(frozen=True)
class _Series:
    samples: tuple[tuple[float, float], ...]
    unit: str | None

    @property
    def depths(self) -> tuple[float, ...]:
        return tuple(item[0] for item in self.samples)

    @property
    def gap_limit(self) -> float:
        if len(self.samples) < 3:
            return float("inf")
        steps = [
            self.samples[index + 1][0] - self.samples[index][0]
            for index in range(len(self.samples) - 1)
            if self.samples[index + 1][0] > self.samples[index][0]
        ]
        return median(steps) * 3.0 if steps else float("inf")


class CurveFillRenderPackageService:
    """Single backend authority used by both live WDV and export consumers."""

    def __init__(
        self,
        *,
        session_service: CanonicalWdvSessionService | None = None,
        sample_service: CanonicalCurveSampleService | None = None,
        resolution_service: CurveFillResolutionService | None = None,
        max_samples: int = 12000,
    ) -> None:
        self.session_service = session_service or CanonicalWdvSessionService()
        self.sample_service = sample_service or CanonicalCurveSampleService()
        self.resolution_service = resolution_service or CurveFillResolutionService()
        self.max_samples = max_samples

    def get_render_package(self, managed_well_uid: str) -> CurveFillRenderPackage:
        session = self.session_service.get_session(managed_well_uid)
        assignments = {
            assignment.assignment_uid: assignment
            for track in session.tracks
            for assignment in track.assignments
        }
        assignments_by_curve = {
            assignment.managed_curve_uid: assignment
            for track in session.tracks
            for assignment in track.assignments
        }
        series_cache: dict[str, _Series] = {}
        items: list[CurveFillRenderItem] = []

        for fill in session.curve_fills:
            if not fill.enabled:
                items.append(self._unresolved(fill, "disabled", "fill_disabled", "Curve fill is disabled"))
                continue
            try:
                owner = assignments[fill.owner_assignment_uid]
                aligned = self._aligned_samples(
                    session,
                    fill,
                    assignments_by_curve,
                    series_cache,
                )
                request = CurveFillResolveRequest(
                    fill_mode=fill.fill_mode,
                    operand_a=fill.operand_a,
                    operand_b=fill.operand_b,
                    condition=fill.condition,
                    comparison_basis=fill.comparison_basis,
                    overlay_policy_id=fill.overlay_policy_id,
                    overlay_policy_revision=fill.overlay_policy_revision,
                    style=fill.style,
                    deadband=fill.deadband,
                    minimum_interval=fill.minimum_interval,
                    depth_unit=fill.depth_unit,
                    samples=aligned,
                )
                geometry = self.resolution_service.resolve(request)
                items.append(
                    CurveFillRenderItem(
                        fill_uid=fill.fill_uid,
                        track_uid=fill.track_uid,
                        owner_assignment_uid=owner.assignment_uid,
                        status="resolved",
                        geometry=geometry,
                    )
                )
            except (KeyError, ValueError) as exc:
                items.append(self._unresolved(fill, "unresolved", "fill_resolution_failed", str(exc)))

        return CurveFillRenderPackage(
            managed_well_uid=session.managed_well_uid,
            session_uid=session.session_uid,
            session_revision=session.revision,
            display_policy_revision=session.display_policy_revision,
            fills=tuple(items),
        )

    @staticmethod
    def _unresolved(
        fill: WdvCanonicalCurveFill,
        status: str,
        reason_code: str,
        reason: str,
    ) -> CurveFillRenderItem:
        return CurveFillRenderItem(
            fill_uid=fill.fill_uid,
            track_uid=fill.track_uid,
            owner_assignment_uid=fill.owner_assignment_uid,
            status=status,
            reason_code=reason_code,
            reason=reason,
        )

    def _curve_series(
        self,
        session: WdvCanonicalSession,
        curve_uid: str,
        cache: dict[str, _Series],
    ) -> _Series:
        cached = cache.get(curve_uid)
        if cached is not None:
            return cached
        response = self.sample_service.get_curve_samples(
            WdvCurveSampleRequest(
                managed_well_uid=session.managed_well_uid,
                managed_curve_uid=curve_uid,
                max_samples=self.max_samples,
            )
        )
        series = _Series(samples=tuple(response.samples), unit=response.value_unit)
        cache[curve_uid] = series
        return series

    def _aligned_samples(
        self,
        session: WdvCanonicalSession,
        fill: WdvCanonicalCurveFill,
        assignments_by_curve: dict[str, WdvCanonicalAssignment],
        cache: dict[str, _Series],
    ) -> tuple[FillSample, ...]:
        curve_series: dict[str, _Series] = {}
        for operand in (fill.operand_a, fill.operand_b):
            if operand.type == "curve":
                curve_series[operand.curve_uid] = self._curve_series(session, operand.curve_uid, cache)
            elif operand.type == "derived_reference":
                raise ValueError(
                    f"Derived reference {operand.reference_uid} requires its registered backend policy resolver"
                )

        depth_values: set[float] = set()
        for series in curve_series.values():
            depth_values.update(series.depths)
        if not depth_values:
            raise ValueError("Curve fill has no measured-curve depth samples")

        result: list[FillSample] = []
        for depth in sorted(depth_values):
            a_value = self._operand_value(fill.operand_a, depth, curve_series)
            b_value = self._operand_value(fill.operand_b, depth, curve_series)
            a_assignment = (
                assignments_by_curve.get(fill.operand_a.curve_uid)
                if fill.operand_a.type == "curve"
                else assignments_by_curve.get(fill.operand_b.curve_uid)
            )
            b_assignment = (
                assignments_by_curve.get(fill.operand_b.curve_uid)
                if fill.operand_b.type == "curve"
                else a_assignment
            )
            if a_assignment is None or b_assignment is None:
                raise ValueError("Fill operands do not resolve to assigned track scales")
            result.append(
                FillSample(
                    depth=depth,
                    a_value=a_value,
                    b_value=b_value,
                    a_track_position=self._track_position(a_value, a_assignment),
                    b_track_position=self._track_position(b_value, b_assignment),
                )
            )
        return tuple(result)

    def _operand_value(self, operand, depth: float, series_by_curve: dict[str, _Series]) -> float | None:
        if operand.type == "curve":
            return self._interpolate(series_by_curve[operand.curve_uid], depth)
        if operand.type == "constant_reference":
            return float(operand.value)
        if operand.type == "stepped_reference":
            for interval in operand.intervals:
                if interval.top_depth <= depth <= interval.base_depth:
                    return float(interval.value)
            return None
        raise ValueError(f"Unsupported operand type: {operand.type}")

    @staticmethod
    def _interpolate(series: _Series, depth: float) -> float | None:
        if not series.samples:
            return None
        depths = series.depths
        index = bisect_left(depths, depth)
        if index < len(depths) and depths[index] == depth:
            return series.samples[index][1]
        if index == 0 or index >= len(series.samples):
            return None
        left_depth, left_value = series.samples[index - 1]
        right_depth, right_value = series.samples[index]
        if right_depth - left_depth > series.gap_limit:
            return None
        ratio = (depth - left_depth) / (right_depth - left_depth)
        return left_value + ratio * (right_value - left_value)

    @staticmethod
    def _track_position(value: float | None, assignment: WdvCanonicalAssignment) -> float | None:
        if value is None or assignment.scale_min is None or assignment.scale_max is None:
            return None
        left = float(assignment.scale_min)
        right = float(assignment.scale_max)
        if assignment.scale_direction == "reversed" and left < right:
            left, right = right, left
        if assignment.scale_type == "logarithmic":
            if value <= 0 or left <= 0 or right <= 0:
                return None
            numerator = log10(value) - log10(left)
            denominator = log10(right) - log10(left)
        else:
            numerator = value - left
            denominator = right - left
        if denominator == 0:
            return None
        position = numerator / denominator
        anchor_bias = {"left": -0.18, "center": 0.0, "right": 0.18}[assignment.position_anchor]
        position += anchor_bias + float(assignment.horizontal_offset_pct) / 100.0
        if assignment.clip_to_track:
            position = max(0.0, min(1.0, position))
        if not 0.0 <= position <= 1.0:
            return None
        return position
