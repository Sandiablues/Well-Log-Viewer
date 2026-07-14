"""Controlled authority router for Phase 13 cutover preparation.

This router is not wired into ingestion in Phase 13.  It is the tested backend
boundary that a later cutover package may call for *new ingestion only*.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .contracts import CurveClassificationDecision, CurveClassificationRequest
from .cutover_policy import ClassificationAuthorityPolicy
from .unified_result import UnifiedCurveClassificationResult


@dataclass(frozen=True)
class AuthorityRoutingResult:
    authoritative_kind: str
    legacy_decision: CurveClassificationDecision
    unified_result: UnifiedCurveClassificationResult | None
    cutover_eligible: bool
    used_legacy_fallback: bool
    blocked_reason: str | None
    routing_error: str | None
    policy_version: str

    def as_dict(self) -> dict[str, object]:
        return {
            "authoritative_kind": self.authoritative_kind,
            "legacy_decision": self.legacy_decision.as_dict(),
            "unified_result": self.unified_result.as_dict() if self.unified_result else None,
            "cutover_eligible": self.cutover_eligible,
            "used_legacy_fallback": self.used_legacy_fallback,
            "blocked_reason": self.blocked_reason,
            "routing_error": self.routing_error,
            "policy_version": self.policy_version,
        }


class NewIngestionClassificationAuthorityRouter:
    """Route only explicit new-ingestion candidates to orchestrated authority."""

    def __init__(self, policy: ClassificationAuthorityPolicy | None = None) -> None:
        self._policy = policy or ClassificationAuthorityPolicy.from_environment()

    def route(
        self,
        *,
        request: CurveClassificationRequest,
        legacy_decision: CurveClassificationDecision,
        build_unified: Callable[[], UnifiedCurveClassificationResult],
    ) -> AuthorityRoutingResult:
        lifecycle = str(request.context.get("ingestion_lifecycle") or "").strip().lower()

        if lifecycle != "new_ingestion":
            return AuthorityRoutingResult(
                authoritative_kind="legacy",
                legacy_decision=legacy_decision,
                unified_result=None,
                cutover_eligible=False,
                used_legacy_fallback=False,
                blocked_reason="not_new_ingestion",
                routing_error=None,
                policy_version=self._policy.policy_version,
            )

        if not self._policy.permits_new_ingestion_authority():
            return AuthorityRoutingResult(
                authoritative_kind="legacy",
                legacy_decision=legacy_decision,
                unified_result=None,
                cutover_eligible=False,
                used_legacy_fallback=False,
                blocked_reason="cutover_not_enabled",
                routing_error=None,
                policy_version=self._policy.policy_version,
            )

        try:
            unified = build_unified()
        except Exception as exc:
            if not self._policy.fallback_to_legacy_on_error:
                raise
            return AuthorityRoutingResult(
                authoritative_kind="legacy",
                legacy_decision=legacy_decision,
                unified_result=None,
                cutover_eligible=True,
                used_legacy_fallback=True,
                blocked_reason="orchestrated_error",
                routing_error=f"{type(exc).__name__}: {exc}",
                policy_version=self._policy.policy_version,
            )

        if self._policy.require_resolved_unified_result and (
            unified.review_required or unified.overall_status != "resolved"
        ):
            return AuthorityRoutingResult(
                authoritative_kind="legacy",
                legacy_decision=legacy_decision,
                unified_result=unified,
                cutover_eligible=True,
                used_legacy_fallback=False,
                blocked_reason="unified_result_requires_review",
                routing_error=None,
                policy_version=self._policy.policy_version,
            )

        return AuthorityRoutingResult(
            authoritative_kind="orchestrated",
            legacy_decision=legacy_decision,
            unified_result=unified,
            cutover_eligible=True,
            used_legacy_fallback=False,
            blocked_reason=None,
            routing_error=None,
            policy_version=self._policy.policy_version,
        )
