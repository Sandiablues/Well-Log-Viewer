"""Backend-owned Source Intake candidate resolution service.

This module owns durable post-scan review decisions. It is intentionally
independent from HTTP and inventory registration so the same rules govern
single-candidate, bulk, offline, and future enterprise workflows.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Iterable

from .models import (
    SourceFileCandidate,
    SourceIntakeBulkResolutionRequest,
    SourceIntakeBulkResolutionResponse,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionAuditEvent,
    SourceIntakeResolutionDecision,
    SourceIntakeResolutionResult,
    SourceIntakeResolutionState,
    utc_now_iso,
)


class SourceIntakeResolutionError(ValueError):
    pass


def occurrence_identity(*, repository_id: str, relative_path: str, checksum: str) -> str:
    """Return stable identity for one discovered occurrence, not its content."""
    payload = json.dumps(
        {
            "repository_id": repository_id,
            "relative_path": relative_path.replace("\\", "/"),
            "checksum": checksum,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"occ:{hashlib.sha256(payload).hexdigest()[:24]}"


def duplicate_group_identity(checksum: str) -> str:
    return f"dup:{checksum.lower()}"


def classify_initial_resolution(candidate: SourceFileCandidate) -> SourceIntakeResolutionState:
    if candidate.qaqc_status.failure_count > 0 or candidate.parse_error:
        return SourceIntakeResolutionState.HARD_FAILED
    if candidate.parser_status.value in {"parse_failed", "unsupported"}:
        return SourceIntakeResolutionState.HARD_FAILED
    if candidate.review_required or candidate.qaqc_status.review_required:
        return SourceIntakeResolutionState.UNRESOLVED
    return SourceIntakeResolutionState.AUTO_INGESTIBLE


def is_ingestible(candidate: SourceFileCandidate) -> bool:
    return candidate.resolution_state in {
        SourceIntakeResolutionState.AUTO_INGESTIBLE,
        SourceIntakeResolutionState.RESOLVED,
    }


class SourceIntakeResolutionService:
    def initialize_candidates(self, candidates: Iterable[SourceFileCandidate]) -> list[SourceFileCandidate]:
        initialized = [deepcopy(candidate) for candidate in candidates]
        by_fingerprint: dict[str, list[SourceFileCandidate]] = {}
        for candidate in initialized:
            fingerprint = candidate.content_fingerprint or candidate.checksum
            candidate.content_fingerprint = fingerprint
            candidate.occurrence_id = candidate.occurrence_id or occurrence_identity(
                repository_id=candidate.repository_id,
                relative_path=candidate.relative_path,
                checksum=fingerprint,
            )
            candidate.duplicate_group_id = duplicate_group_identity(fingerprint)
            candidate.resolution_state = classify_initial_resolution(candidate)
            by_fingerprint.setdefault(fingerprint, []).append(candidate)

        for group in by_fingerprint.values():
            canonical = min(group, key=lambda item: (item.repository_id, item.relative_path, item.occurrence_id or ""))
            canonical.canonical_occurrence_id = canonical.occurrence_id
            for candidate in group:
                if candidate is canonical:
                    continue
                candidate.canonical_occurrence_id = canonical.occurrence_id
                candidate.resolution_state = SourceIntakeResolutionState.DUPLICATE
        return initialized

    def apply_bulk(
        self,
        candidates: list[SourceFileCandidate],
        request: SourceIntakeBulkResolutionRequest,
    ) -> SourceIntakeBulkResolutionResponse:
        by_id = {candidate.occurrence_id: candidate for candidate in candidates if candidate.occurrence_id}
        results: list[SourceIntakeResolutionResult] = []
        for decision in request.decisions:
            candidate = by_id.get(decision.occurrence_id)
            if candidate is None:
                raise SourceIntakeResolutionError(f"Unknown occurrence_id: {decision.occurrence_id}")
            results.append(self._apply_decision(candidate, decision, by_id))
        return SourceIntakeBulkResolutionResponse(
            resolved_count=len(results),
            results=results,
        )

    def _apply_decision(
        self,
        candidate: SourceFileCandidate,
        decision: SourceIntakeResolutionDecision,
        by_id: dict[str, SourceFileCandidate],
    ) -> SourceIntakeResolutionResult:
        previous = candidate.resolution_state
        if previous == SourceIntakeResolutionState.REGISTERED:
            raise SourceIntakeResolutionError("Registered candidates cannot be modified through review resolution.")

        original_values = self._current_values(candidate)
        next_state = self._next_state(candidate, decision, by_id)
        if decision.resolved_values:
            self._apply_resolved_values(candidate, decision.resolved_values)

        now = utc_now_iso()
        candidate.resolution_state = next_state
        candidate.resolved_by = decision.actor
        candidate.resolved_at = now
        candidate.resolution_reason = decision.reason
        candidate.resolution_version += 1
        event = SourceIntakeResolutionAuditEvent(
            event_id=self._event_id(candidate, decision, now),
            action=decision.action,
            actor=decision.actor,
            reason=decision.reason,
            occurred_at=now,
            previous_state=previous,
            next_state=next_state,
            original_values=original_values,
            resolved_values=decision.resolved_values,
            accepted_warning_codes=decision.accepted_warning_codes,
        )
        candidate.resolution_history.append(event)
        return SourceIntakeResolutionResult(
            occurrence_id=decision.occurrence_id,
            previous_state=previous,
            next_state=next_state,
            ingestible=is_ingestible(candidate),
            message=f"Resolution state changed from {previous.value} to {next_state.value}.",
        )

    def _next_state(self, candidate, decision, by_id):
        action = decision.action
        if action in {SourceIntakeResolutionAction.METADATA_OVERRIDE, SourceIntakeResolutionAction.WARNING_ACCEPTED}:
            if candidate.qaqc_status.failure_count > 0 or candidate.parse_error:
                raise SourceIntakeResolutionError("Hard failures cannot be overridden as ingestible.")
            return SourceIntakeResolutionState.RESOLVED
        if action == SourceIntakeResolutionAction.EXCLUDED:
            if not decision.reason:
                raise SourceIntakeResolutionError("Exclusion requires a reason.")
            return SourceIntakeResolutionState.EXCLUDED
        if action == SourceIntakeResolutionAction.CANONICAL_SELECTED:
            canonical_id = decision.canonical_occurrence_id or decision.occurrence_id
            canonical = by_id.get(canonical_id)
            if canonical is None:
                raise SourceIntakeResolutionError(f"Unknown canonical occurrence: {canonical_id}")
            if canonical.content_fingerprint != candidate.content_fingerprint:
                raise SourceIntakeResolutionError("Canonical selection must remain within one content fingerprint group.")
            candidate.canonical_occurrence_id = canonical_id
            return SourceIntakeResolutionState.RESOLVED if canonical_id == decision.occurrence_id else SourceIntakeResolutionState.DUPLICATE
        if action == SourceIntakeResolutionAction.REOPENED:
            return SourceIntakeResolutionState.UNRESOLVED
        raise SourceIntakeResolutionError(f"Unsupported resolution action: {action.value}")

    @staticmethod
    def _apply_resolved_values(candidate: SourceFileCandidate, values: dict[str, object]) -> None:
        allowed = {"well_name", "uwi", "operator", "field", "block"}
        unknown = set(values) - allowed
        if unknown:
            raise SourceIntakeResolutionError(f"Unsupported resolved fields: {sorted(unknown)}")
        if candidate.resolved_metadata is None:
            raise SourceIntakeResolutionError("Candidate has no resolved metadata contract.")
        for field_name, value in values.items():
            field = getattr(candidate.resolved_metadata, field_name)
            field.value = None if value is None else str(value)
            field.source = "manual_resolution"
            field.confidence = "reviewed"
            field.review_required = False
        candidate.resolved_metadata.review_required = any(
            getattr(candidate.resolved_metadata, name).review_required
            for name in ("well_name", "uwi", "operator", "field", "block")
        )

    @staticmethod
    def _current_values(candidate: SourceFileCandidate) -> dict[str, object]:
        if candidate.resolved_metadata is None:
            return {}
        return {
            name: getattr(candidate.resolved_metadata, name).value
            for name in ("well_name", "uwi", "operator", "field", "block")
        }

    @staticmethod
    def _event_id(candidate, decision, timestamp):
        raw = f"{candidate.occurrence_id}|{decision.action.value}|{timestamp}|{candidate.resolution_version}"
        return f"res:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"
