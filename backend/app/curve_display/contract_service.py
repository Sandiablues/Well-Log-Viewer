"""Viewer-neutral backend authority for effective curve display contracts.

This service is the single backend boundary for curve scale range, scale type,
direction, clipping semantics, and provenance consumed by renderers.  It may
read backend-persisted operator intent and governed Knowledge Repository policy;
it never accepts viewer-computed percentile ranges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.inventory.models import ManagedProductGroupItem, ManagedWellRecord
from app.wdv_display.policy_service import WdvCurveDisplayPolicyService
from app.wdv_session.canonical_service import CanonicalWdvSessionService


@dataclass(frozen=True)
class BackendCurveDisplayIntent:
    """Backend-persisted operator intent, independent of any viewer renderer."""

    range_mode: str = "governed"
    minimum: float | None = None
    maximum: float | None = None
    scale_type: str | None = None
    direction_override: str | None = None
    clamp: bool = True
    intent_source: str = "backend_persisted_curve_intent"


@dataclass(frozen=True)
class BackendCurveDisplayContract:
    managed_well_uid: str | None
    managed_curve_uid: str | None
    minimum: float
    maximum: float
    scale_type: str
    direction: str
    clamp: bool
    range_source: str
    policy_revision: str | None
    provenance: dict[str, Any]
    requires_review: bool


class BackendCurveDisplayContractService:
    """Resolve one effective curve-display contract inside the backend."""

    def __init__(self, session_service: CanonicalWdvSessionService | None = None) -> None:
        self.session_service = session_service or CanonicalWdvSessionService()

    def resolve(
        self,
        *,
        record: ManagedWellRecord,
        item: ManagedProductGroupItem,
        statistics: dict[str, Any],
        intent: BackendCurveDisplayIntent | None = None,
    ) -> BackendCurveDisplayContract:
        """Resolve one effective backend contract.

        Explicit backend-persisted range intent is authoritative. A canonical
        assignment is consulted only when no explicit range intent is supplied.
        """
        mode = str(intent.range_mode if intent else "governed").strip().lower()
        explicit_range = mode in {"robust_p5_p95", "manual"}
        if not explicit_range:
            assignment_contract = self._assignment_contract(record=record, item=item)
            if assignment_contract is not None:
                if intent and intent.direction_override is not None:
                    return self._with_direction(assignment_contract, intent.direction_override)
                return assignment_contract

        policy = WdvCurveDisplayPolicyService.resolve(item, statistics)
        policy_low = self._number(policy.get("min"))
        policy_high = self._number(policy.get("max"))
        policy_scale_type = self._scale_type(policy.get("type"))
        policy_direction = self._direction(policy.get("direction"))
        policy_source = str(policy.get("source") or "").strip()

        if mode == "robust_p5_p95":
            low = self._number(statistics.get("observed_p05"))
            high = self._number(statistics.get("observed_p95"))
            if low is None or high is None or low == high:
                raise ValueError(
                    f"Backend P5/P95 intent has no usable percentile range for curve product: {item.product_id}"
                )
            scale_type = policy_scale_type
            source = "backend_observed_p05_p95"
            provenance = {
                "authority": "backend_curve_display_contract",
                "policy_scope": "backend_persisted_curve_intent",
                "intent_source": intent.intent_source if intent else "backend_persisted_curve_intent",
                "range_mode": "robust_p5_p95",
                "statistics_source": "backend_curve_sample_service",
                "governed_scale_type_source": policy_source,
            }
            requires_review = False
        elif mode == "manual":
            low = self._number(intent.minimum if intent else None)
            high = self._number(intent.maximum if intent else None)
            if low is None or high is None or low == high:
                raise ValueError(
                    f"Backend manual display intent has no usable range for curve product: {item.product_id}"
                )
            scale_type = self._scale_type(intent.scale_type if intent else policy_scale_type)
            source = "backend_manual_range"
            provenance = {
                "authority": "backend_curve_display_contract",
                "policy_scope": "backend_persisted_curve_intent",
                "intent_source": intent.intent_source if intent else "backend_persisted_curve_intent",
                "range_mode": "manual",
            }
            requires_review = False
        else:
            low = policy_low
            high = policy_high
            scale_type = policy_scale_type
            source = policy_source
            governed = source in {
                "managed_knowledge_curve_rule",
                "managed_knowledge_family_default",
            }
            provenance = {
                "authority": "backend_curve_display_contract",
                "policy_scope": "knowledge_repository_or_system",
                "policy_source": source,
            }
            requires_review = not governed

        if low is None or high is None or low == high:
            raise ValueError(
                f"Backend display policy has no usable range for curve product: {item.product_id}"
            )
        numeric_low, numeric_high = sorted((low, high))
        if scale_type == "logarithmic" and numeric_low <= 0:
            raise ValueError(
                f"Backend logarithmic display policy is non-positive for curve product: {item.product_id}"
            )
        if not source:
            raise ValueError(
                f"Backend display policy has no provenance source for curve product: {item.product_id}"
            )
        direction = (
            self._direction(intent.direction_override)
            if intent and intent.direction_override is not None
            else policy_direction
        )
        return BackendCurveDisplayContract(
            managed_well_uid=str(record.managed_well_uid) if record.managed_well_uid else None,
            managed_curve_uid=str(item.managed_curve_uid) if item.managed_curve_uid else None,
            minimum=numeric_low,
            maximum=numeric_high,
            scale_type=scale_type,
            direction=direction,
            clamp=bool(intent.clamp) if intent else True,
            range_source=source,
            policy_revision=None,
            provenance=provenance,
            requires_review=requires_review,
        )

    @staticmethod
    def _with_direction(
        contract: BackendCurveDisplayContract, direction: str
    ) -> BackendCurveDisplayContract:
        return BackendCurveDisplayContract(
            managed_well_uid=contract.managed_well_uid,
            managed_curve_uid=contract.managed_curve_uid,
            minimum=contract.minimum,
            maximum=contract.maximum,
            scale_type=contract.scale_type,
            direction=BackendCurveDisplayContractService._direction(direction),
            clamp=contract.clamp,
            range_source=contract.range_source,
            policy_revision=contract.policy_revision,
            provenance={**contract.provenance, "direction_source": "backend_manual_override"},
            requires_review=contract.requires_review,
        )

    def _assignment_contract(
        self,
        *,
        record: ManagedWellRecord,
        item: ManagedProductGroupItem,
    ) -> BackendCurveDisplayContract | None:
        if record.managed_well_uid is None or item.managed_curve_uid is None:
            return None
        session = self.session_service.get_session(str(record.managed_well_uid))
        matches = [
            assignment
            for track in session.tracks
            for assignment in track.assignments
            if str(assignment.managed_well_uid) == str(record.managed_well_uid)
            and str(assignment.managed_curve_uid) == str(item.managed_curve_uid)
        ]
        if not matches:
            return None
        signatures = {
            (
                assignment.scale_min,
                assignment.scale_max,
                assignment.scale_type,
                assignment.scale_direction,
                assignment.effective_range_source,
            )
            for assignment in matches
        }
        if len(signatures) != 1:
            raise ValueError(
                "Conflicting backend display assignments exist for managed curve "
                f"{item.managed_curve_uid}"
            )
        assignment = matches[0]
        low = self._number(assignment.scale_min)
        high = self._number(assignment.scale_max)
        if low is None or high is None or low == high:
            raise ValueError(
                "Backend assignment has no usable effective range for managed curve "
                f"{item.managed_curve_uid}"
            )
        numeric_low, numeric_high = sorted((low, high))
        scale_type = self._scale_type(assignment.scale_type)
        if scale_type == "logarithmic" and numeric_low <= 0:
            raise ValueError(
                "Backend assignment has a non-positive logarithmic range for managed curve "
                f"{item.managed_curve_uid}"
            )
        direction = self._direction(assignment.scale_direction)
        return BackendCurveDisplayContract(
            managed_well_uid=str(record.managed_well_uid),
            managed_curve_uid=str(item.managed_curve_uid),
            minimum=numeric_low,
            maximum=numeric_high,
            scale_type=scale_type,
            direction=direction,
            clamp=bool(assignment.clip_to_track),
            range_source=str(assignment.effective_range_source),
            policy_revision=session.display_policy_revision,
            provenance={
                "authority": "backend_curve_display_contract",
                "policy_scope": "backend_persisted_assignment",
                "assignment_uid": str(assignment.assignment_uid),
                "track_uid": str(assignment.track_uid),
                "assignment_source": assignment.source,
                "display_policy_source": assignment.display_policy_source,
            },
            requires_review=bool(assignment.display_review_required),
        )

    @staticmethod
    def _number(value: Any) -> float | None:
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
    def _direction(value: Any) -> str:
        return "reversed" if str(value or "").strip().lower() in {"reverse", "reversed"} else "normal"
