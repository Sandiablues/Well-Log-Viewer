"""Single backend authority for canonical WDV assignment display policy."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalAssignment
from app.inventory.canonical_identity_resolver import (
    CanonicalInventoryIdentityResolver,
)
from app.wdv_display.policy_service import WdvCurveDisplayPolicyService


SYSTEM_DEFAULT_MIN = 0.0
SYSTEM_DEFAULT_MAX = 150.0
SYSTEM_DEFAULT_TYPE = "linear"
SYSTEM_DEFAULT_DIRECTION = "normal"
SYSTEM_DEFAULT_WARNING_CODE = "NO_GOVERNED_DISPLAY_POLICY"
SYSTEM_DEFAULT_WARNING_MESSAGE = (
    "No approved curve-level or family display policy was resolved; "
    "the backend system-default display scale is in use."
)


class CanonicalWdvAssignmentPolicyService:
    """Resolve identity and materialize a complete canonical assignment policy.

    This service owns the conversion from a managed curve occurrence and the
    display-policy resolver result into a renderer-ready canonical assignment.
    Assignment creation source remains separate from display-policy provenance.
    """

    def __init__(
        self,
        *,
        resolver: CanonicalInventoryIdentityResolver | None = None,
        display_policy_resolver: Callable[[object], dict[str, Any]] | None = None,
    ) -> None:
        self.resolver = resolver or CanonicalInventoryIdentityResolver()
        self._display_policy_resolver = (
            display_policy_resolver
            if display_policy_resolver is not None
            else WdvCurveDisplayPolicyService.resolve
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
        resolved = self.resolver.resolve_curve(
            managed_well_uid,
            managed_curve_uid,
        )
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
        policy = self._materialize_policy(
            self._display_policy_resolver(resolved.product)
        )
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
            scale_min=policy["scale_min"],
            scale_max=policy["scale_max"],
            scale_type=policy["scale_type"],
            scale_direction=policy["scale_direction"],
            color=color,
            line_style=line_style,
            line_width=line_width,
            fill_mode=fill_mode,
            source=assignment_source,
            display_policy_source=policy["display_policy_source"],
            display_review_required=policy["display_review_required"],
            display_warning_code=policy["display_warning_code"],
            display_warning_message=policy["display_warning_message"],
        )

    def refresh_assignment(
        self,
        assignment: WdvCanonicalAssignment,
    ) -> WdvCanonicalAssignment:
        """Refresh backend policy without changing assignment identity or styling."""
        if assignment.display_policy_source == "user_override":
            return assignment

        resolved = self.resolver.resolve_curve(
            assignment.managed_well_uid,
            assignment.managed_curve_uid,
        )
        policy = self._materialize_policy(
            self._display_policy_resolver(resolved.product)
        )
        return assignment.model_copy(
            update={
                "scale_min": policy["scale_min"],
                "scale_max": policy["scale_max"],
                "scale_type": policy["scale_type"],
                "scale_direction": policy["scale_direction"],
                "display_policy_source": policy["display_policy_source"],
                "display_review_required": policy["display_review_required"],
                "display_warning_code": policy["display_warning_code"],
                "display_warning_message": policy["display_warning_message"],
            }
        )

    @classmethod
    def _materialize_policy(
        cls,
        raw_policy: dict[str, Any] | None,
    ) -> dict[str, Any]:
        raw = dict(raw_policy or {})
        resolver_source = str(raw.get("source") or "").strip()

        scale_type = cls._scale_type(raw.get("type"))
        scale_direction = cls._scale_direction(raw.get("direction"))
        scale_min = cls._number(raw.get("min"))
        scale_max = cls._number(raw.get("max"))

        valid_bounds = (
            scale_min is not None
            and scale_max is not None
            and scale_min != scale_max
            and not (
                scale_type == "logarithmic"
                and (scale_min <= 0 or scale_max <= 0)
            )
        )

        if resolver_source == "managed_knowledge_curve_rule" and valid_bounds:
            policy_source = "curve"
        elif (
            resolver_source == "managed_knowledge_family_default"
            and valid_bounds
        ):
            policy_source = "family"
        else:
            policy_source = "system_default"

        if policy_source == "system_default" and not valid_bounds:
            scale_min = SYSTEM_DEFAULT_MIN
            scale_max = SYSTEM_DEFAULT_MAX
            scale_type = SYSTEM_DEFAULT_TYPE
            scale_direction = SYSTEM_DEFAULT_DIRECTION

        is_system_default = policy_source == "system_default"
        return {
            "scale_min": scale_min,
            "scale_max": scale_max,
            "scale_type": scale_type,
            "scale_direction": scale_direction,
            "display_policy_source": policy_source,
            "display_review_required": is_system_default,
            "display_warning_code": (
                SYSTEM_DEFAULT_WARNING_CODE if is_system_default else None
            ),
            "display_warning_message": (
                SYSTEM_DEFAULT_WARNING_MESSAGE if is_system_default else None
            ),
        }

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
        key = str(value or "").strip().lower()
        return "logarithmic" if key in {"log", "logarithmic"} else "linear"

    @staticmethod
    def _scale_direction(value: Any) -> str:
        key = str(value or "").strip().lower()
        return (
            "reversed"
            if key in {
                "reverse",
                "reversed",
                "right_to_left",
                "decreasing",
            }
            else "normal"
        )
