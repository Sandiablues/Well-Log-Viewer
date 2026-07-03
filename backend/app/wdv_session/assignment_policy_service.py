"""Backend authority for WDV assignment display policy and range resolution."""

from __future__ import annotations

from collections.abc import Callable
import math
from typing import Any

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalAssignment, WdvCurveSampleRequest
from app.inventory.canonical_curve_sample_service import CanonicalCurveSampleService
from app.inventory.canonical_identity_resolver import CanonicalInventoryIdentityResolver
from app.inventory.curve_sample_service import CurveSampleServiceError
from app.wdv_display.policy_service import WdvCurveDisplayPolicyService


def format_wdv_range_value(value: float, significant_figures: int = 3) -> str:
    """Format a range endpoint for display without changing its numeric value."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("WDV range display labels require finite values")
    if number == 0:
        return "0"

    magnitude = abs(number)
    if magnitude >= 1_000_000 or magnitude < 0.0001:
        raw = f"{number:.{significant_figures - 1}e}"
        mantissa, exponent = raw.split("e")
        mantissa = mantissa.rstrip("0").rstrip(".")
        return f"{mantissa}e{int(exponent):+d}"

    decimal_places = max(
        0,
        significant_figures - 1 - math.floor(math.log10(magnitude)),
    )
    rounded = round(number, decimal_places)
    if rounded == 0:
        return "0"
    if decimal_places == 0:
        return f"{rounded:.0f}"
    return f"{rounded:.{decimal_places}f}".rstrip("0").rstrip(".")

SYSTEM_DEFAULT_MIN = 0.0
SYSTEM_DEFAULT_MAX = 150.0
SYSTEM_DEFAULT_TYPE = "linear"
SYSTEM_DEFAULT_DIRECTION = "normal"
SYSTEM_DEFAULT_WARNING_CODE = "NO_GOVERNED_DISPLAY_POLICY"
SYSTEM_DEFAULT_WARNING_MESSAGE = (
    "No approved curve-level or family display policy was resolved; "
    "the backend system-default display scale is in use."
)
FIT_WARNING_CODE = "FIT_TO_CURVE_UNAVAILABLE"
FIT_WARNING_MESSAGE = (
    "A valid curve-fitted range could not be resolved; the current governed "
    "range remains in use."
)


class CanonicalWdvAssignmentPolicyService:
    """Resolve governed policy, explicit range intent, and renderer-ready output."""

    def __init__(
        self,
        *,
        resolver: CanonicalInventoryIdentityResolver | None = None,
        display_policy_resolver: Callable[[object], dict[str, Any]] | None = None,
        curve_sample_service: CanonicalCurveSampleService | None = None,
    ) -> None:
        self.resolver = resolver or CanonicalInventoryIdentityResolver()
        self._display_policy_resolver = display_policy_resolver or WdvCurveDisplayPolicyService.resolve
        self.curve_sample_service = (
            curve_sample_service
            or CanonicalCurveSampleService(resolver=self.resolver)
        )

    def create_assignment(
        self,
        *,
        managed_well_uid: str,
        managed_curve_uid: str,
        track_uid: str,
        stack_index: int,
        assignment_source: str,
        visible: bool = True,
        color: str | None = None,
        line_style: str | None = None,
        line_width: float | None = None,
        fill_mode: str | None = None,
    ) -> WdvCanonicalAssignment:
        resolved = self.resolver.resolve_curve(managed_well_uid, managed_curve_uid)
        return self.create_assignment_from_resolved(
            resolved=resolved,
            track_uid=track_uid,
            stack_index=stack_index,
            assignment_source=assignment_source,
            visible=visible,
            color=color,
            line_style=line_style,
            line_width=line_width,
            fill_mode=fill_mode,
        )

    def create_assignment_from_resolved(
        self,
        *,
        resolved,
        track_uid: str,
        stack_index: int,
        assignment_source: str,
        visible: bool = True,
        color: str | None = None,
        line_style: str | None = None,
        line_width: float | None = None,
        fill_mode: str | None = None,
    ) -> WdvCanonicalAssignment:
        policy = self._materialize_policy(self._display_policy_resolver(resolved.product))
        return WdvCanonicalAssignment(
            assignment_uid=new_uuid7_str(),
            managed_curve_uid=resolved.managed_curve_uid,
            managed_product_uid=resolved.managed_product_uid,
            managed_well_uid=resolved.managed_well_uid,
            managed_wellbore_uid=resolved.managed_wellbore_uid,
            managed_source_uid=resolved.managed_source_uid,
            track_uid=track_uid,
            kr_curve_type_id=resolved.product.kr_curve_type_id,
            observed_mnemonic=(
                resolved.product.observed_mnemonic
                or resolved.product.curve_name
                or resolved.product.display_name
            ),
            normalized_mnemonic=resolved.product.normalized_mnemonic,
            display_name=resolved.product.display_name,
            curve_family=resolved.product.curve_family,
            unit=resolved.product.curve_unit,
            stack_index=stack_index,
            visible=visible,
            color=color,
            line_style=line_style,
            line_width=line_width,
            fill_mode=fill_mode,
            source=assignment_source,
            **policy,
        )

    def refresh_assignment(self, assignment: WdvCanonicalAssignment) -> WdvCanonicalAssignment:
        resolved = self.resolver.resolve_curve(
            assignment.managed_well_uid,
            assignment.managed_curve_uid,
        )
        governed = self._materialize_policy(self._display_policy_resolver(resolved.product))
        update = dict(governed)
        if assignment.scale_type_override is not None:
            update["scale_type"] = assignment.scale_type_override
        if assignment.scale_direction_override is not None:
            update["scale_direction"] = assignment.scale_direction_override
        update.update({
            "effective_range_source": assignment.range_override_mode,
            "override_warning_code": None,
            "override_warning_message": None,
        })
        if assignment.range_override_mode == "manual":
            update["scale_min"] = assignment.manual_scale_min
            update["scale_max"] = assignment.manual_scale_max
        elif assignment.range_override_mode in {
            "fit_to_curve",
            "fit_to_curve_p05_p95",
            "fit_to_curve_p01_p99",
        }:
            fitted = self._fit_bounds_from_canonical_samples(
                assignment,
                governed,
                assignment.range_override_mode,
            )
            if fitted is None:
                update["override_warning_code"] = FIT_WARNING_CODE
                update["override_warning_message"] = FIT_WARNING_MESSAGE
            else:
                update["scale_min"], update["scale_max"] = fitted

        update.update(self._range_edit_contract(
            update.get("scale_min"),
            update.get("scale_max"),
        ))
        effective_min = update.get("scale_min")
        effective_max = update.get("scale_max")
        if effective_min is not None and effective_max is not None:
            update["scale_min_label"] = format_wdv_range_value(effective_min)
            update["scale_max_label"] = format_wdv_range_value(effective_max)
        return assignment.model_copy(update=update)

    def _fit_bounds_from_canonical_samples(
        self,
        assignment: WdvCanonicalAssignment,
        governed: dict[str, Any],
        mode: str,
    ) -> tuple[float, float] | None:
        try:
            response = self.curve_sample_service.get_curve_samples(
                WdvCurveSampleRequest(
                    managed_well_uid=assignment.managed_well_uid,
                    managed_curve_uid=assignment.managed_curve_uid,
                    max_samples=12000,
                )
            )
        except (
            CurveSampleServiceError,
            FileNotFoundError,
            OSError,
            ValueError,
        ):
            return None

        if mode == "fit_to_curve_p05_p95":
            low = self._first_number(
                response.value_p05,
                response.value_p01,
                response.robust_value_min,
                response.value_min,
            )
            high = self._first_number(
                response.value_p95,
                response.value_p99,
                response.robust_value_max,
                response.value_max,
            )
        else:
            low = self._first_number(
                response.value_p01,
                response.robust_value_min,
                response.value_min,
            )
            high = self._first_number(
                response.value_p99,
                response.robust_value_max,
                response.value_max,
            )
        return self._fit_bounds_with_padding(low, high, governed)

    def _fit_bounds_with_padding(
        self,
        low: object,
        high: object,
        governed: dict[str, Any],
    ) -> tuple[float, float] | None:
        low_number = self._number(low)
        high_number = self._number(high)
        if low_number is None or high_number is None or low_number >= high_number:
            return None
        if governed["scale_type"] == "logarithmic":
            if low_number <= 0:
                return None
            log_low = math.log10(low_number)
            log_high = math.log10(high_number)
            # Percentile body occupies 60% of the drawable range.
            log_padding = (log_high - log_low) / 3.0
            padded_low = 10 ** (log_low - log_padding)
            padded_high = 10 ** (log_high + log_padding)
        else:
            # Percentile body occupies 60% of the drawable range.
            padding = (high_number - low_number) / 3.0
            padded_low = low_number - padding
            padded_high = high_number + padding
        if governed["scale_direction"] == "reversed":
            return padded_high, padded_low
        return padded_low, padded_high

    @classmethod
    def _range_edit_contract(cls, scale_min: object, scale_max: object) -> dict[str, Any]:
        left = cls._number(scale_min)
        right = cls._number(scale_max)
        if left is None or right is None or left == right:
            return {"range_edit_step": 1.0, "range_edit_precision": 0}
        span = abs(right - left)
        exponent = math.floor(math.log10(span))
        step = 10 ** (exponent - 1)
        precision = max(0, min(12, -math.floor(math.log10(step))))
        return {"range_edit_step": step, "range_edit_precision": precision}

    def _fit_bounds(self, product: object, governed: dict[str, Any]) -> tuple[float, float] | None:
        low = self._first_number(
            getattr(product, "robust_observed_min", None),
            getattr(product, "observed_min", None),
        )
        high = self._first_number(
            getattr(product, "robust_observed_max", None),
            getattr(product, "observed_max", None),
        )
        return self._fit_bounds_with_padding(low, high, governed)

    def _fit_bounds_from_values(
        self,
        robust_min: object,
        robust_max: object,
        observed_min: object,
        observed_max: object,
        governed: dict[str, Any],
    ) -> tuple[float, float] | None:
        low = self._first_number(robust_min, observed_min)
        high = self._first_number(robust_max, observed_max)
        if low is None or high is None or low >= high:
            return None
        if governed["scale_type"] == "logarithmic" and low <= 0:
            return None
        if governed["scale_direction"] == "reversed":
            return high, low
        return low, high

    @classmethod
    def _materialize_policy(cls, raw_policy: dict[str, Any] | None) -> dict[str, Any]:
        raw = dict(raw_policy or {})
        resolver_source = str(raw.get("source") or "").strip()
        scale_type = cls._scale_type(raw.get("type"))
        scale_direction = cls._scale_direction(raw.get("direction"))
        scale_min = cls._number(raw.get("min"))
        scale_max = cls._number(raw.get("max"))
        valid = (
            scale_min is not None and scale_max is not None and scale_min != scale_max
            and not (scale_type == "logarithmic" and (scale_min <= 0 or scale_max <= 0))
        )
        if resolver_source == "managed_knowledge_curve_rule" and valid:
            source = "curve"
        elif resolver_source == "managed_knowledge_family_default" and valid:
            source = "family"
        else:
            source = "system_default"
        if source == "system_default" and not valid:
            scale_min = SYSTEM_DEFAULT_MIN
            scale_max = SYSTEM_DEFAULT_MAX
            scale_type = SYSTEM_DEFAULT_TYPE
            scale_direction = SYSTEM_DEFAULT_DIRECTION
        system_default = source == "system_default"
        return {
            "scale_min": scale_min,
            "scale_max": scale_max,
            "scale_min_label": format_wdv_range_value(scale_min),
            "scale_max_label": format_wdv_range_value(scale_max),
            "scale_type": scale_type,
            "scale_direction": scale_direction,
            "display_policy_source": source,
            "display_review_required": system_default,
            "display_warning_code": SYSTEM_DEFAULT_WARNING_CODE if system_default else None,
            "display_warning_message": SYSTEM_DEFAULT_WARNING_MESSAGE if system_default else None,
        }

    @classmethod
    def _first_number(cls, *values: Any) -> float | None:
        for value in values:
            number = cls._number(value)
            if number is not None:
                return number
        return None

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number != number or number in {float("inf"), float("-inf")}:
            return None
        return number

    @staticmethod
    def _scale_type(value: Any) -> str:
        return "logarithmic" if str(value or "").strip().lower() in {"log", "logarithmic"} else "linear"

    @staticmethod
    def _scale_direction(value: Any) -> str:
        return "reversed" if str(value or "").strip().lower() in {"reverse", "reversed"} else "normal"
