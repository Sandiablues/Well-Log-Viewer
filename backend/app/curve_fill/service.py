"""Deterministic geometry resolution for backend-owned curve fill."""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    ComparisonBasis,
    ComparisonCondition,
    CurveFillResolveRequest,
    CurveFillResolveResponse,
    FillSample,
    FillVertex,
    ResolvedFillSegment,
)


@dataclass(frozen=True)
class _ResolvedPoint:
    depth: float
    delta: float
    a_position: float
    b_position: float


class CurveFillResolutionService:
    """Resolve exact fill lobes from a backend-aligned sample stream."""

    def resolve(self, request: CurveFillResolveRequest) -> CurveFillResolveResponse:
        raw_segments: list[list[_ResolvedPoint]] = []
        active: list[_ResolvedPoint] = []
        previous: _ResolvedPoint | None = None
        previous_true = False

        for sample in request.samples:
            point = self._point(request, sample)
            if point is None:
                self._close(raw_segments, active)
                active = []
                previous = None
                previous_true = False
                continue

            current_true = self._is_true(request, point.delta)
            if previous is None:
                if current_true:
                    active = [point]
                previous = point
                previous_true = current_true
                continue

            if current_true != previous_true:
                crossing = self._crossing(previous, point)
                if previous_true:
                    active.append(crossing)
                    self._close(raw_segments, active)
                    active = []
                else:
                    active = [crossing, point]
            elif current_true:
                if not active:
                    active = [previous]
                active.append(point)

            previous = point
            previous_true = current_true

        self._close(raw_segments, active)

        minimum_interval = request.minimum_interval or 0.0
        segments = tuple(
            ResolvedFillSegment(
                top_depth=points[0].depth,
                base_depth=points[-1].depth,
                vertices=tuple(
                    FillVertex(
                        depth=point.depth,
                        a_track_position=point.a_position,
                        b_track_position=point.b_position,
                    )
                    for point in points
                ),
            )
            for points in raw_segments
            if len(points) >= 2 and points[-1].depth - points[0].depth >= minimum_interval
        )

        return CurveFillResolveResponse(
            managed_well_uid=request.operand_a.managed_well_uid,
            depth_domain_uid=request.operand_a.depth_domain_uid,
            fill_mode=request.fill_mode,
            comparison_basis=request.comparison_basis,
            style=request.style,
            depth_unit=request.depth_unit,
            segments=segments,
        )

    @staticmethod
    def _point(request: CurveFillResolveRequest, sample: FillSample) -> _ResolvedPoint | None:
        if sample.a_track_position is None or sample.b_track_position is None:
            return None
        if request.comparison_basis == ComparisonBasis.ENGINEERING_VALUE:
            if sample.a_value is None or sample.b_value is None:
                return None
            delta = sample.a_value - sample.b_value
        else:
            delta = sample.a_track_position - sample.b_track_position
        return _ResolvedPoint(
            depth=sample.depth,
            delta=delta,
            a_position=sample.a_track_position,
            b_position=sample.b_track_position,
        )

    @staticmethod
    def _is_true(request: CurveFillResolveRequest, delta: float) -> bool:
        deadband = request.deadband or 0.0
        if request.fill_mode.value == "crossover":
            # Approved overlay policy defines expected A-before-B order. A positive
            # normalized-position delta is the policy-resolved reversal.
            return delta > deadband
        if request.condition == ComparisonCondition.A_GREATER_THAN_B:
            return delta > deadband
        return delta < -deadband

    @staticmethod
    def _crossing(left: _ResolvedPoint, right: _ResolvedPoint) -> _ResolvedPoint:
        denominator = right.delta - left.delta
        ratio = 0.5 if denominator == 0 else -left.delta / denominator
        ratio = max(0.0, min(1.0, ratio))
        return _ResolvedPoint(
            depth=left.depth + ratio * (right.depth - left.depth),
            delta=0.0,
            a_position=left.a_position + ratio * (right.a_position - left.a_position),
            b_position=left.b_position + ratio * (right.b_position - left.b_position),
        )

    @staticmethod
    def _close(target: list[list[_ResolvedPoint]], active: list[_ResolvedPoint]) -> None:
        if len(active) >= 2 and active[-1].depth > active[0].depth:
            target.append(active.copy())
