"""Backend-owned WDV curve display policy."""

from __future__ import annotations

import math
import re
from typing import Any

from app.inventory.models import ManagedProductGroupItem


class WdvCurveDisplayPolicyService:
    """Single backend authority for default curve display behaviour."""

    _COLORS = {
        "gamma": "#2f80ed",
        "borehole": "#27ae60",
        "resistivity": "#eb5757",
        "density": "#9b51e0",
        "neutron": "#00a6a6",
        "sonic": "#f2994a",
        "porosity": "#f2c94c",
        "generic": "#2f80ed",
    }

    @classmethod
    def resolve(
        cls,
        item: ManagedProductGroupItem,
        sample_stats: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        stats = sample_stats or {}
        key = (
            f"{item.curve_name} {item.curve_family} {item.curve_type} "
            f"{item.curve_description} {item.curve_unit}"
        ).lower()
        warnings: list[str] = []
        if int(stats.get("rejected_sample_count") or 0) > 0:
            warnings.append("invalid_samples_rejected")

        observed_min = cls._float_or_none(
            stats.get("robust_observed_min", stats.get("observed_min"))
        )
        observed_max = cls._float_or_none(
            stats.get("robust_observed_max", stats.get("observed_max"))
        )
        observed_p05 = cls._float_or_none(stats.get("observed_p05"))
        observed_p95 = cls._float_or_none(stats.get("observed_p95"))
        has_stats = (
            observed_min is not None
            and observed_max is not None
            and observed_max > observed_min
        )
        is_derived = cls._is_derived_or_correction_curve(item)
        curve_class = cls._curve_class(key)

        def finalize(scale: dict[str, Any]) -> dict[str, Any]:
            enriched = cls._add_visual_variation_diagnostics(
                scale,
                observed_min,
                observed_max,
                observed_p05,
                observed_p95,
            )
            enriched["curve_class"] = curve_class
            enriched["default_color"] = cls._COLORS[curve_class]
            enriched["lattice"] = (
                "logarithmic" if enriched.get("type") == "log" else "linear"
            )
            return enriched

        if "resist" in key or "ohmm" in key or "ohm" in key:
            if has_stats and observed_min is not None and observed_min <= 0:
                warnings.append("non_positive_values_for_log_scale")
            return finalize({
                "type": "log",
                "min": 0.2,
                "max": 2000.0,
                "direction": "normal",
                "source": "template_default",
                "warnings": warnings,
            })

        if "gamma" in key or "gapi" in key or re.search(r"\bapi\b", key):
            return finalize({
                "type": "linear",
                "min": 0.0,
                "max": 200.0,
                "direction": "normal",
                "source": "template_default",
                "warnings": warnings,
            })

        if "density" in key or "g/c" in key or "g/cc" in key:
            if is_derived and has_stats:
                low, high = cls._padded_observed_domain(
                    float(observed_min), float(observed_max)
                )
                warnings.append("suspected_correction_or_delta_curve")
                return finalize({
                    "type": "linear",
                    "min": low,
                    "max": high,
                    "direction": "normal",
                    "source": "observed_statistics",
                    "warnings": warnings,
                })
            if has_stats and not cls._domain_overlaps(
                float(observed_min), float(observed_max), 1.0, 4.0
            ):
                low, high = cls._padded_observed_domain(
                    float(observed_min), float(observed_max)
                )
                warnings.append("density_default_not_supported_by_observed_values")
                return finalize({
                    "type": "linear",
                    "min": low,
                    "max": high,
                    "direction": "normal",
                    "source": "observed_statistics",
                    "warnings": warnings,
                })
            return finalize({
                "type": "linear",
                "min": 1.95,
                "max": 2.95,
                "direction": "normal",
                "source": "template_default",
                "warnings": warnings,
            })

        if (
            "neutron" in key
            or "porosity" in key
            or "cfcf" in key
            or "v/v" in key
        ):
            if is_derived and has_stats:
                low, high = cls._padded_observed_domain(
                    float(observed_min), float(observed_max)
                )
                warnings.append("suspected_correction_or_delta_curve")
                return finalize({
                    "type": "linear",
                    "min": high,
                    "max": low,
                    "direction": "reversed",
                    "source": "observed_statistics",
                    "warnings": warnings,
                })
            if has_stats and not cls._domain_overlaps(
                float(observed_min), float(observed_max), -0.25, 0.75
            ):
                low, high = cls._padded_observed_domain(
                    float(observed_min), float(observed_max)
                )
                warnings.append("neutron_default_not_supported_by_observed_values")
                return finalize({
                    "type": "linear",
                    "min": high,
                    "max": low,
                    "direction": "reversed",
                    "source": "observed_statistics",
                    "warnings": warnings,
                })
            return finalize({
                "type": "linear",
                "min": 0.45,
                "max": -0.15,
                "direction": "reversed",
                "source": "template_default",
                "warnings": warnings,
            })

        if "sonic" in key or "delta-t" in key or "us/f" in key or "us/ft" in key:
            return finalize({
                "type": "linear",
                "min": 140.0,
                "max": 40.0,
                "direction": "reversed",
                "source": "template_default",
                "warnings": warnings,
            })

        if "caliper" in key or " in" in key:
            return finalize({
                "type": "linear",
                "min": 6.0,
                "max": 16.0,
                "direction": "normal",
                "source": "template_default",
                "warnings": warnings,
            })

        if "pressure" in key or "psi" in key:
            return finalize({
                "type": "linear",
                "min": 0.0,
                "max": 10000.0,
                "direction": "normal",
                "source": "template_default",
                "warnings": warnings,
            })

        if "temperature" in key or "deg" in key:
            return finalize({
                "type": "linear",
                "min": 0.0,
                "max": 500.0,
                "direction": "normal",
                "source": "template_default",
                "warnings": warnings,
            })

        if has_stats:
            low, high = cls._padded_observed_domain(
                float(observed_min), float(observed_max)
            )
            return finalize({
                "type": "linear",
                "min": low,
                "max": high,
                "direction": "normal",
                "source": "observed_statistics",
                "warnings": warnings,
            })

        return finalize({
            "type": "linear",
            "min": 0.0,
            "max": 150.0,
            "direction": "normal",
            "source": "template_default",
            "warnings": warnings,
        })

    @staticmethod
    def _curve_class(key: str) -> str:
        if "gamma" in key or "gapi" in key or re.search(r"\bapi\b", key):
            return "gamma"
        if "caliper" in key or "borehole" in key:
            return "borehole"
        if "resist" in key or "ohm" in key:
            return "resistivity"
        if "density" in key or "g/cc" in key:
            return "density"
        if "neutron" in key:
            return "neutron"
        if "sonic" in key or "delta-t" in key or "us/ft" in key:
            return "sonic"
        if "porosity" in key or "cfcf" in key or "v/v" in key:
            return "porosity"
        return "generic"

    @staticmethod
    def _is_derived_or_correction_curve(item: ManagedProductGroupItem) -> bool:
        key = (
            f"{item.curve_name} {item.curve_family} {item.curve_type} "
            f"{item.curve_description} {item.display_name}"
        ).lower()
        return any(
            token in key
            for token in (
                "correction",
                "difference",
                "delta",
                "standoff",
                "stand-off",
                "stand off",
                "apparent",
                "ratio",
                "from back scatter",
                "back scatter",
                "inversion",
            )
        )

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _domain_overlaps(
        low: float,
        high: float,
        reference_low: float,
        reference_high: float,
    ) -> bool:
        return max(low, reference_low) <= min(high, reference_high)

    @staticmethod
    def _padded_observed_domain(low: float, high: float) -> tuple[float, float]:
        if high < low:
            low, high = high, low
        span = high - low
        if span <= 0:
            pad = max(abs(low) * 0.05, 0.1)
            return low - pad, high + pad
        pad = max(span * 0.08, 0.05)
        return low - pad, high + pad

    @classmethod
    def _add_visual_variation_diagnostics(
        cls,
        scale: dict[str, Any],
        observed_min: float | None,
        observed_max: float | None,
        observed_p05: float | None,
        observed_p95: float | None,
    ) -> dict[str, Any]:
        scale.setdefault("display_mode", scale.get("source") or "template_default")
        scale.setdefault(
            "recommended_display_mode",
            scale.get("display_mode"),
        )
        scale.setdefault("standard_type", scale.get("type"))
        scale.setdefault("standard_min", scale.get("min"))
        scale.setdefault("standard_max", scale.get("max"))
        scale.setdefault("standard_direction", scale.get("direction"))

        def set_render_semantics(
            prefix: str,
            left: Any,
            right: Any,
            direction: str,
        ) -> None:
            left_value = cls._float_or_none(left)
            right_value = cls._float_or_none(right)
            if left_value is None or right_value is None:
                return
            numeric_low = min(left_value, right_value)
            numeric_high = max(left_value, right_value)
            if prefix:
                scale[f"{prefix}_display_left_value"] = left_value
                scale[f"{prefix}_display_right_value"] = right_value
                scale[f"{prefix}_numeric_min"] = numeric_low
                scale[f"{prefix}_numeric_max"] = numeric_high
            else:
                scale["display_left_value"] = left_value
                scale["display_right_value"] = right_value
                scale["numeric_min"] = numeric_low
                scale["numeric_max"] = numeric_high
            if direction in {"reverse", "reversed"} and left_value < right_value:
                if prefix:
                    scale[f"{prefix}_display_left_value"] = right_value
                    scale[f"{prefix}_display_right_value"] = left_value
                else:
                    scale["display_left_value"] = right_value
                    scale["display_right_value"] = left_value

        direction = str(scale.get("direction") or "normal")
        set_render_semantics(
            "standard",
            scale.get("standard_min"),
            scale.get("standard_max"),
            str(scale.get("standard_direction") or direction),
        )

        if (
            observed_min is not None
            and observed_max is not None
            and observed_max > observed_min
        ):
            use_p_domain = (
                observed_p05 is not None
                and observed_p95 is not None
                and observed_p95 > observed_p05
            )
            if use_p_domain:
                low, high = cls._padded_observed_domain(
                    float(observed_p05), float(observed_p95)
                )
                scale["robust_observed_domain_source"] = "p05_p95"
            else:
                low, high = cls._padded_observed_domain(
                    float(observed_min), float(observed_max)
                )
                scale["robust_observed_domain_source"] = "observed_min_max"
            scale["robust_observed_numeric_min"] = low
            scale["robust_observed_numeric_max"] = high
            if direction in {"reverse", "reversed"}:
                scale["robust_observed_min"] = high
                scale["robust_observed_max"] = low
                scale["robust_observed_display_left_value"] = high
                scale["robust_observed_display_right_value"] = low
                scale["robust_observed_direction"] = "reversed"
            else:
                scale["robust_observed_min"] = low
                scale["robust_observed_max"] = high
                scale["robust_observed_display_left_value"] = low
                scale["robust_observed_display_right_value"] = high
                scale["robust_observed_direction"] = "normal"
            scale["robust_observed_type"] = scale.get("type") or "linear"

        try:
            display_span = abs(
                float(scale.get("standard_max", scale.get("max")))
                - float(scale.get("standard_min", scale.get("min")))
            )
        except (TypeError, ValueError):
            set_render_semantics("", scale.get("min"), scale.get("max"), direction)
            return scale
        if display_span <= 0 or observed_p05 is None or observed_p95 is None:
            set_render_semantics("", scale.get("min"), scale.get("max"), direction)
            return scale

        observed_span = abs(float(observed_p95) - float(observed_p05))
        ratio = observed_span / display_span if display_span else None
        scale["visual_span_ratio"] = ratio
        if (
            ratio is not None
            and ratio < 0.08
            and scale.get("source") == "template_default"
        ):
            warnings = list(scale.get("warnings") or [])
            if "low_visual_variation_on_standard_scale" not in warnings:
                warnings.append("low_visual_variation_on_standard_scale")
            scale["warnings"] = warnings

            robust_left = scale.get(
                "robust_observed_display_left_value",
                scale.get("robust_observed_min"),
            )
            robust_right = scale.get(
                "robust_observed_display_right_value",
                scale.get("robust_observed_max"),
            )
            if (
                robust_left is not None
                and robust_right is not None
                and robust_left != robust_right
            ):
                scale["min"] = robust_left
                scale["max"] = robust_right
                scale["source"] = "robust_observed_statistics"
                scale["display_mode"] = "robust_observed"
                scale["recommended_display_mode"] = "robust_observed"
                scale["mode_reason"] = "low_visual_variation_on_standard_scale"

        set_render_semantics("", scale.get("min"), scale.get("max"), direction)
        return scale
