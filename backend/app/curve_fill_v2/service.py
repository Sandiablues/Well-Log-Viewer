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
    DepthExtent,
    FillPolygon,
    FillVertex,
    RuleType,
    ScaleDirection,
    ScaleType,
    ResolvedFillPaint,
    SeparationMode,
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
        envelope_series: tuple[CurveSeries, ...] = (),
        envelope_transforms: tuple[CurveTransform, ...] = (),
    ) -> CurveFillGeometry:
        started = perf_counter()
        self._validate_inputs(rule, series_a, transform_a, series_b, transform_b, envelope_series, envelope_transforms)
        dependency_key = self._dependency_key(rule, series_a, transform_a, series_b, transform_b, envelope_series, envelope_transforms)

        if not rule.enabled:
            return self._response(rule, series_a.depth_unit, dependency_key, (), ())

        if rule.rule_type == RuleType.CROSSOVER:
            CurveFillPolicyRegistry.require(rule.overlay_policy_uid or "", rule.overlay_policy_revision or "")

        points = self._aligned_points(rule, series_a, transform_a, series_b, transform_b, envelope_series, envelope_transforms)
        points = self._clip_to_depth_extent(rule, points)
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
    def _validate_inputs(rule, series_a, transform_a, series_b, transform_b, envelope_series, envelope_transforms):
        if series_a.managed_well_uid != rule.managed_well_uid:
            raise CurveFillResolutionError("Curve A belongs to a different managed well")
        if series_a.managed_curve_uid != rule.curve_a_uid:
            raise CurveFillResolutionError("Curve A identity does not match the rule")
        if transform_a.managed_curve_uid != rule.curve_a_uid:
            raise CurveFillResolutionError("Curve A transform identity mismatch")
        pair_types = {RuleType.CONDITIONAL, RuleType.CROSSOVER, RuleType.BETWEEN_CURVES, RuleType.SEPARATION}
        if rule.rule_type in pair_types:
            if series_b is None or transform_b is None:
                raise CurveFillResolutionError("Curve B series and transform are required")
            if series_b.managed_well_uid != rule.managed_well_uid:
                raise CurveFillResolutionError("Curve B belongs to a different managed well")
            if series_b.managed_curve_uid != rule.curve_b_uid or transform_b.managed_curve_uid != rule.curve_b_uid:
                raise CurveFillResolutionError("Curve B identity does not match the rule")
            if series_a.depth_unit.strip().lower() != series_b.depth_unit.strip().lower():
                raise CurveFillResolutionError("Curve operands require one depth unit")
        if rule.rule_type == RuleType.CURVE_ENVELOPE:
            if len(envelope_series) != len(envelope_transforms) or len(envelope_series) < 2:
                raise CurveFillResolutionError("Curve envelope requires at least two resolved operands")
            if tuple(item.managed_curve_uid for item in envelope_series) != rule.curve_operand_uids:
                raise CurveFillResolutionError("Curve envelope identities do not match the rule")
            for series, transform in zip(envelope_series, envelope_transforms):
                if series.managed_well_uid != rule.managed_well_uid or transform.managed_curve_uid != series.managed_curve_uid:
                    raise CurveFillResolutionError("Curve envelope operand identity mismatch")
                if series.depth_unit.strip().lower() != series_a.depth_unit.strip().lower():
                    raise CurveFillResolutionError("Curve envelope operands require one depth unit")
        widths = [transform_a.track_width_px]
        if transform_b is not None:
            widths.append(transform_b.track_width_px)
        widths.extend(item.track_width_px for item in envelope_transforms)
        if len(set(widths)) != 1:
            raise CurveFillResolutionError("All operands must resolve in the same track width")

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

    def _aligned_points(self, rule, a, ta, b, tb, envelope_series, envelope_transforms):
        if rule.rule_type == RuleType.TO_BOUNDARY:
            boundary_x = ta.horizontal_padding_px if rule.boundary == Boundary.LEFT else ta.track_width_px - ta.horizontal_padding_px
            return tuple(
                _Point(depth=d, delta=1.0, x_a=x, x_b=boundary_x)
                for d, v in a.samples
                if (x := self.value_to_x(v, ta)) is not None
            )
        if rule.rule_type == RuleType.VALUE_BAND:
            x_min = self.value_to_x(rule.band_min_value, ta)
            x_max = self.value_to_x(rule.band_max_value, ta)
            if x_min is None or x_max is None:
                raise CurveFillResolutionError("Value band cannot be resolved on this scale")
            left, right = min(x_min, x_max), max(x_min, x_max)
            return tuple(_Point(depth=d, delta=1.0, x_a=left, x_b=right) for d, _ in a.samples)
        if rule.rule_type in {RuleType.CURVE_TO_VALUE, RuleType.THRESHOLD}:
            ref_x = self.value_to_x(rule.reference_value, ta)
            if ref_x is None:
                raise CurveFillResolutionError("Reference value cannot be resolved on this scale")
            fill_anchor_x = ref_x
            if rule.rule_type == RuleType.THRESHOLD and rule.boundary is not None:
                fill_anchor_x = (
                    ta.horizontal_padding_px
                    if rule.boundary == Boundary.LEFT
                    else ta.track_width_px - ta.horizontal_padding_px
                )
            return tuple(
                _Point(
                    depth=d,
                    delta=(v - rule.reference_value if rule.rule_type == RuleType.THRESHOLD else 1.0),
                    x_a=x,
                    x_b=fill_anchor_x,
                )
                for d, v in a.samples
                if (x := self.value_to_x(v, ta)) is not None
            )
        if rule.rule_type == RuleType.CURVE_ENVELOPE:
            depths = sorted(set().union(*(set(item[0] for item in series.samples) for series in envelope_series)))
            depth_arrays = [tuple(item[0] for item in series.samples) for series in envelope_series]
            gap_limits = [self._gap_limit(series) for series in envelope_series]
            result = []
            for depth in depths:
                xs = []
                for series, transform, depth_array, gap_limit in zip(envelope_series, envelope_transforms, depth_arrays, gap_limits):
                    value = self._interpolate(series.samples, depth_array, depth, gap_limit)
                    if value is None:
                        continue
                    x = self.value_to_x(value, transform)
                    if x is not None:
                        xs.append(x)
                if len(xs) < 2:
                    result.append(None)
                else:
                    result.append(_Point(depth=depth, delta=1.0, x_a=min(xs), x_b=max(xs)))
            return tuple(result)

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
            delta = xa - xb
            if rule.rule_type == RuleType.SEPARATION:
                if rule.separation_mode == SeparationMode.ABSOLUTE:
                    delta = abs(delta) - rule.minimum_separation_px
                elif rule.separation_mode == SeparationMode.A_RIGHT_OF_B:
                    delta = delta - rule.minimum_separation_px
                else:
                    delta = (-delta) - rule.minimum_separation_px
            result.append(_Point(depth=depth, delta=delta, x_a=xa, x_b=xb))
        return tuple(result)


    @staticmethod
    def _interpolate_point(left: _Point, right: _Point, depth: float) -> _Point:
        if right.depth == left.depth:
            return left
        ratio = (depth - left.depth) / (right.depth - left.depth)
        return _Point(
            depth=depth,
            delta=left.delta + ratio * (right.delta - left.delta),
            x_a=left.x_a + ratio * (right.x_a - left.x_a),
            x_b=left.x_b + ratio * (right.x_b - left.x_b),
        )

    def _clip_to_depth_extent(self, rule, points):
        if rule.depth_extent == DepthExtent.ENTIRE_TRACK:
            return points
        top = rule.interval_from_md
        base = rule.interval_to_md
        if top is None or base is None:
            raise CurveFillResolutionError(
                "specified interval requires From MD and To MD"
            )

        valid = [point for point in points if point is not None]
        if not valid or base < valid[0].depth or top > valid[-1].depth:
            return ()

        clipped = []
        previous = None
        for point in points:
            if point is None:
                if clipped and clipped[-1] is not None:
                    clipped.append(None)
                previous = None
                continue

            if previous is not None and previous.depth < top < point.depth:
                clipped.append(self._interpolate_point(previous, point, top))
            if top <= point.depth <= base:
                clipped.append(point)
            if previous is not None and previous.depth < base < point.depth:
                clipped.append(self._interpolate_point(previous, point, base))
                break
            previous = point

        while clipped and clipped[-1] is None:
            clipped.pop()
        return tuple(clipped)

    @staticmethod
    def _gap_limit(series: CurveSeries) -> float:
        """Bridge short sampling dropouts while preserving material data gaps.

        The displayed curve renderer joins short missing-sample intervals. Curve
        Fill must use the same continuity expectation or it fragments one fill
        into many small polygons and exposes triangular white gaps. Eight normal
        sample intervals bridges brief logging dropouts while retaining genuine
        gaps as separate fill segments.
        """
        intervals = [
            series.samples[i + 1][0] - series.samples[i][0]
            for i in range(len(series.samples) - 1)
            if series.samples[i + 1][0] > series.samples[i][0]
        ]
        if not intervals:
            return 0.0
        return median(intervals) * 8.0

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
        if rule.rule_type in {RuleType.BETWEEN_CURVES, RuleType.CURVE_ENVELOPE, RuleType.VALUE_BAND, RuleType.CURVE_TO_VALUE}:
            return self._between_curve_segments(points)

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

    def _between_curve_segments(self, points):
        """Return non-self-intersecting polygons split at every crossing and gap."""
        result = []
        active = []
        previous = None
        for point in points:
            if point is None:
                if len(active) >= 2:
                    result.append(active)
                active = []
                previous = None
                continue
            if previous is None:
                active = [point]
                previous = point
                continue

            crossed = (previous.delta < 0 < point.delta) or (previous.delta > 0 > point.delta)
            touched = previous.delta != 0 and point.delta == 0
            if crossed or touched:
                crossing = self._crossing(previous, point)
                active.append(crossing)
                if len(active) >= 2:
                    result.append(active)
                active = [crossing]
                if point.depth != crossing.depth:
                    active.append(point)
            else:
                active.append(point)
            previous = point

        if len(active) >= 2:
            result.append(active)
        return result

    @staticmethod
    def _truth(rule, delta):
        if rule.rule_type in {RuleType.TO_BOUNDARY, RuleType.BETWEEN_CURVES, RuleType.VALUE_BAND, RuleType.CURVE_TO_VALUE, RuleType.CURVE_ENVELOPE}:
            return True
        if rule.rule_type in {RuleType.CROSSOVER, RuleType.SEPARATION}:
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
    def _dependency_key(rule, a, ta, b, tb, envelope_series=(), envelope_transforms=()):
        payload = {
            "rule": rule.model_dump(mode="json"),
            "series_a": [a.managed_curve_uid, a.sample_revision],
            "transform_a": ta.model_dump(mode="json"),
            "series_b": None if b is None else [b.managed_curve_uid, b.sample_revision],
            "transform_b": None if tb is None else tb.model_dump(mode="json"),
            "envelope_series": [[item.managed_curve_uid, item.sample_revision] for item in envelope_series],
            "envelope_transforms": [item.model_dump(mode="json") for item in envelope_transforms],
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
