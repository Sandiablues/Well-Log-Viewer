"""Deterministic, incremental backend Curve Fill v2 geometry engine."""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from hashlib import sha256
import json
from math import log10
from statistics import median
from time import perf_counter

from .models import (
    Boundary,
    Comparison,
    CurveFillGeometry,
    CurveFillRule,
    CurveSeries,
    CurveTransform,
    FillPolygon,
    FillVertex,
    RuleType,
    ScaleDirection,
    ScaleType,
    ResolvedFillPaint,
)
from .policy import CurveFillPolicyRegistry


@dataclass(frozen=True)
class _Point:
    depth: float
    delta: float
    x_a: float
    x_b: float


class CurveFillResolutionError(ValueError):
    pass


class CurveFillResolutionService:
    """Resolve one rule only; unrelated tracks and curves are never touched."""

    def resolve(
        self,
        *,
        rule: CurveFillRule,
        series_a: CurveSeries,
        transform_a: CurveTransform,
        series_b: CurveSeries | None = None,
        transform_b: CurveTransform | None = None,
    ) -> CurveFillGeometry:
        started = perf_counter()
        self._validate_inputs(rule, series_a, transform_a, series_b, transform_b)
        dependency_key = self._dependency_key(rule, series_a, transform_a, series_b, transform_b)

        if not rule.enabled:
            return self._response(rule, series_a.depth_unit, dependency_key, (), ())

        if rule.rule_type == RuleType.CROSSOVER:
            CurveFillPolicyRegistry.require(rule.overlay_policy_uid or "", rule.overlay_policy_revision or "")

        points = self._aligned_points(rule, series_a, transform_a, series_b, transform_b)
        raw_segments = self._segments(rule, points)
        polygons = tuple(
            FillPolygon(
                polygon_uid=f"{rule.rule_uid}:{index}",
                top_depth=segment[0].depth,
                base_depth=segment[-1].depth,
                vertices=tuple(FillVertex(depth=p.depth, x_a_px=p.x_a, x_b_px=p.x_b) for p in segment),
            )
            for index, segment in enumerate(raw_segments)
            if len(segment) >= 2 and segment[-1].depth - segment[0].depth >= rule.minimum_interval
        )
        elapsed_ms = (perf_counter() - started) * 1000.0
        warnings = () if elapsed_ms <= 150.0 else (f"resolution_exceeded_150ms:{elapsed_ms:.3f}",)
        return self._response(rule, series_a.depth_unit, dependency_key, polygons, warnings)

    @staticmethod
    def _response(rule, depth_unit, dependency_key, polygons, warnings):
        geometry_revision = sha256(
            json.dumps(
                {
                    "dependency_key": dependency_key,
                    "polygon_count": len(polygons),
                    "bounds": [(p.top_depth, p.base_depth, len(p.vertices)) for p in polygons],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return CurveFillGeometry(
            rule_uid=rule.rule_uid,
            order=rule.order,
            dependency_key=dependency_key,
            geometry_revision=geometry_revision,
            managed_well_uid=rule.managed_well_uid,
            track_uid=rule.track_uid,
            depth_unit=depth_unit,
            style=rule.style,
            paint=ResolvedFillPaint(appearance=rule.style.appearance, pattern_uid=rule.style.pattern_uid, pattern_scale=rule.style.pattern_scale),
            polygons=polygons,
            warnings=warnings,
        )

    @staticmethod
    def _validate_inputs(rule, series_a, transform_a, series_b, transform_b):
        if series_a.managed_well_uid != rule.managed_well_uid:
            raise CurveFillResolutionError("Curve A belongs to a different managed well")
        if series_a.managed_curve_uid != rule.curve_a_uid:
            raise CurveFillResolutionError("Curve A identity does not match the rule")
        if transform_a.managed_curve_uid != rule.curve_a_uid:
            raise CurveFillResolutionError("Curve A transform identity mismatch")
        if rule.rule_type != RuleType.TO_BOUNDARY:
            if series_b is None or transform_b is None:
                raise CurveFillResolutionError("Curve B series and transform are required")
            if series_b.managed_well_uid != rule.managed_well_uid:
                raise CurveFillResolutionError("Curve B belongs to a different managed well")
            if series_b.managed_curve_uid != rule.curve_b_uid or transform_b.managed_curve_uid != rule.curve_b_uid:
                raise CurveFillResolutionError("Curve B identity does not match the rule")
            if series_a.depth_unit.strip().lower() != series_b.depth_unit.strip().lower():
                raise CurveFillResolutionError("Curve operands require one depth unit")
            if rule.rule_type == RuleType.CONDITIONAL:
                ua = (series_a.value_unit or "").strip().lower()
                ub = (series_b.value_unit or "").strip().lower()
                if ua and ub and ua != ub:
                    raise CurveFillResolutionError("Conditional comparison requires compatible engineering units")
        if transform_a.track_width_px != (transform_b.track_width_px if transform_b else transform_a.track_width_px):
            raise CurveFillResolutionError("Both operands must resolve in the same track width")

    @staticmethod
    def value_to_x(value: float, transform: CurveTransform) -> float | None:
        left = transform.scale_min
        right = transform.scale_max
        if transform.scale_direction == ScaleDirection.REVERSED and left < right:
            left, right = right, left
        drawable = transform.track_width_px - 2.0 * transform.horizontal_padding_px
        if transform.scale_type == ScaleType.LOGARITHMIC:
            if value <= 0 or left <= 0 or right <= 0:
                return None
            bounded = min(max(value, min(left, right)), max(left, right)) if transform.clip_to_track else value
            t = (log10(bounded) - log10(left)) / (log10(right) - log10(left))
        else:
            bounded = min(max(value, min(left, right)), max(left, right)) if transform.clip_to_track else value
            t = (bounded - left) / (right - left)
        if transform.clip_to_track:
            t = min(max(t, 0.0), 1.0)
        anchor = {"left": -0.18, "center": 0.0, "right": 0.18}[transform.position_anchor]
        x = transform.horizontal_padding_px + t * drawable + anchor * drawable + (transform.horizontal_offset_pct / 100.0) * drawable
        if transform.clip_to_track:
            x = min(max(x, transform.horizontal_padding_px), transform.track_width_px - transform.horizontal_padding_px)
        return x

    def _aligned_points(self, rule, a, ta, b, tb):
        if rule.rule_type == RuleType.TO_BOUNDARY:
            boundary_x = ta.horizontal_padding_px if rule.boundary == Boundary.LEFT else ta.track_width_px - ta.horizontal_padding_px
            return tuple(
                _Point(depth=d, delta=1.0, x_a=x, x_b=boundary_x)
                for d, v in a.samples
                if (x := self.value_to_x(v, ta)) is not None
            )
        assert b is not None and tb is not None
        depths_a = tuple(item[0] for item in a.samples)
        depths_b = tuple(item[0] for item in b.samples)
        depths = sorted(set(depths_a) | set(depths_b))
        gap_a = self._gap_limit(a)
        gap_b = self._gap_limit(b)
        result = []
        for depth in depths:
            av = self._interpolate(a.samples, depths_a, depth, gap_a)
            bv = self._interpolate(b.samples, depths_b, depth, gap_b)
            if av is None or bv is None:
                result.append(None)
                continue
            xa = self.value_to_x(av, ta)
            xb = self.value_to_x(bv, tb)
            if xa is None or xb is None:
                result.append(None)
                continue
            if rule.rule_type == RuleType.CONDITIONAL:
                delta = av - bv
            elif rule.rule_type == RuleType.BETWEEN_CURVES:
                delta = 1.0
            else:
                delta = xa - xb
            result.append(_Point(depth=depth, delta=delta, x_a=xa, x_b=xb))
        return tuple(result)

    @staticmethod
    def _gap_limit(series: CurveSeries) -> float:
        intervals = [series.samples[i + 1][0] - series.samples[i][0] for i in range(len(series.samples) - 1)]
        return median(intervals) * 1.5

    @staticmethod
    def _interpolate(samples, depths, depth, gap_limit):
        index = bisect_left(depths, depth)
        if index < len(samples) and samples[index][0] == depth:
            return samples[index][1]
        if index == 0 or index >= len(samples):
            return None
        ld, lv = samples[index - 1]
        rd, rv = samples[index]
        if rd - ld > gap_limit:
            return None
        ratio = (depth - ld) / (rd - ld)
        return lv + ratio * (rv - lv)

    def _segments(self, rule, points):
        result = []
        active = []
        previous = None
        previous_true = False
        for point in points:
            if point is None:
                if len(active) >= 2:
                    result.append(active)
                active = []
                previous = None
                previous_true = False
                continue
            current_true = self._truth(rule, point.delta)
            if previous is None:
                if current_true:
                    active = [point]
                previous, previous_true = point, current_true
                continue
            if current_true != previous_true:
                crossing = self._crossing(previous, point)
                if previous_true:
                    active.append(crossing)
                    if len(active) >= 2:
                        result.append(active)
                    active = []
                else:
                    active = [crossing, point]
            elif current_true:
                if not active:
                    active = [previous]
                active.append(point)
            previous, previous_true = point, current_true
        if len(active) >= 2:
            result.append(active)
        return result

    @staticmethod
    def _truth(rule, delta):
        if rule.rule_type == RuleType.TO_BOUNDARY:
            return True
        if rule.rule_type == RuleType.BETWEEN_CURVES:
            return True
        if rule.rule_type == RuleType.CROSSOVER:
            return delta > rule.deadband
        if rule.comparison == Comparison.GREATER_THAN:
            return delta > rule.deadband
        return delta < -rule.deadband

    @staticmethod
    def _crossing(left, right):
        denominator = right.delta - left.delta
        ratio = 0.5 if denominator == 0 else -left.delta / denominator
        ratio = min(max(ratio, 0.0), 1.0)
        return _Point(
            depth=left.depth + ratio * (right.depth - left.depth),
            delta=0.0,
            x_a=left.x_a + ratio * (right.x_a - left.x_a),
            x_b=left.x_b + ratio * (right.x_b - left.x_b),
        )

    @staticmethod
    def _dependency_key(rule, a, ta, b, tb):
        payload = {
            "rule": rule.model_dump(mode="json"),
            "series_a": [a.managed_curve_uid, a.sample_revision],
            "transform_a": ta.model_dump(mode="json"),
            "series_b": None if b is None else [b.managed_curve_uid, b.sample_revision],
            "transform_b": None if tb is None else tb.model_dump(mode="json"),
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
