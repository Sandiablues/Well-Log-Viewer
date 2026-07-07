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
    SourceIntakeCurrentDecision,
    SourceIntakeHumanDecision,
    SourceIntakeResolutionDecision,
    SourceIntakeResolutionResult,
    SourceIntakeResolutionState,
    SourceIntakeWellAssignmentMode,
    SourceIntakeOccurrenceAccounting,
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


def is_wmd_eligible(candidate: SourceFileCandidate) -> bool:
    """Return whether current review state permits transient WMD availability."""
    return candidate.resolution_state in {
        SourceIntakeResolutionState.AUTO_INGESTIBLE,
        SourceIntakeResolutionState.RESOLVED,
    }


def is_ingestible(candidate: SourceFileCandidate) -> bool:
    """Compatibility alias for callers not yet migrated to WMD terminology."""
    return is_wmd_eligible(candidate)


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
            # Source Intake candidate identity now represents one discovered
            # occurrence. Content identity remains separate in
            # content_fingerprint / duplicate_group_id.
            candidate.source_file_id = candidate.occurrence_id
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

    def reconcile_duplicate_groups(
        self,
        candidates: Iterable[SourceFileCandidate],
    ) -> list[SourceFileCandidate]:
        """Reconcile exact-content duplicate groups without erasing lifecycle truth.

        Duplicate status is based only on the content fingerprint. A registered
        occurrence is preferred as the canonical occurrence so a later scan of
        another repository cannot demote already-managed data.
        """
        rows = list(candidates)
        by_fingerprint: dict[str, list[SourceFileCandidate]] = {}
        for candidate in rows:
            fingerprint = candidate.content_fingerprint or candidate.checksum
            candidate.content_fingerprint = fingerprint
            candidate.duplicate_group_id = duplicate_group_identity(fingerprint)
            by_fingerprint.setdefault(fingerprint, []).append(candidate)

        protected_states = {
            SourceIntakeResolutionState.REGISTERED,
            SourceIntakeResolutionState.EXCLUDED,
            SourceIntakeResolutionState.HARD_FAILED,
        }

        for group in by_fingerprint.values():
            canonical = min(
                group,
                key=lambda item: (
                    0 if item.resolution_state == SourceIntakeResolutionState.REGISTERED else 1,
                    item.repository_id,
                    item.relative_path,
                    item.occurrence_id or "",
                ),
            )
            canonical.canonical_occurrence_id = canonical.occurrence_id
            if canonical.resolution_state == SourceIntakeResolutionState.DUPLICATE:
                canonical.resolution_state = classify_initial_resolution(canonical)

            for candidate in group:
                candidate.canonical_occurrence_id = canonical.occurrence_id
                if candidate is canonical:
                    continue
                if candidate.resolution_state not in protected_states:
                    candidate.resolution_state = SourceIntakeResolutionState.DUPLICATE

        return rows

    def reapply_current_decision(
        self,
        candidate: SourceFileCandidate,
    ) -> SourceFileCandidate:
        """Reapply only durable human intent to fresh scan evidence.

        Fresh parser output, inferred metadata, QAQC, and classifications remain
        authoritative after rescan. Only the current human decision is replayed.
        """
        decision = candidate.current_decision
        if decision is None:
            return candidate

        if (
            decision.decision == SourceIntakeHumanDecision.ACCEPT
            and decision.legacy_action
            == SourceIntakeResolutionAction.CONFIRM_SUGGESTION
        ):
            self._confirm_current_suggestions(candidate)

        if decision.corrected_values:
            self._apply_resolved_values(
                candidate,
                decision.corrected_values,
            )

        if (
            decision.decision == SourceIntakeHumanDecision.ASSIGN
            and decision.assignment_mode
            == SourceIntakeWellAssignmentMode.NEW_WELL
            and decision.new_well_values
        ):
            self._apply_resolved_values(
                candidate,
                decision.new_well_values,
            )

        if (
            decision.decision == SourceIntakeHumanDecision.ASSIGN
            and decision.legacy_action
            == SourceIntakeResolutionAction.CANONICAL_SELECTED
            and decision.assignment_target
        ):
            candidate.canonical_occurrence_id = decision.assignment_target

        return candidate

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

    def mark_available_to_wmd(
        self,
        candidate: SourceFileCandidate,
        *,
        actor: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Record transient WMD availability in the legacy resolution state slot."""
        if candidate.resolution_state == SourceIntakeResolutionState.REGISTERED:
            return
        if not is_wmd_eligible(candidate):
            raise SourceIntakeResolutionError(
                f"Candidate resolution state is not WMD-eligible: {candidate.resolution_state.value}."
            )
        now = utc_now_iso()
        # REGISTERED is retained only as the serialized compatibility value.
        candidate.resolution_state = SourceIntakeResolutionState.REGISTERED
        candidate.resolved_by = actor or candidate.resolved_by
        candidate.resolved_at = now
        candidate.resolution_reason = reason or candidate.resolution_reason
        candidate.resolution_version += 1

    def mark_registered(
        self,
        candidate: SourceFileCandidate,
        *,
        actor: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Compatibility alias for the former permanent-registration terminology."""
        self.mark_available_to_wmd(candidate, actor=actor, reason=reason)


    @staticmethod
    def accounting(candidates: Iterable[SourceFileCandidate]) -> SourceIntakeOccurrenceAccounting:
        rows = list(candidates)
        state_counts = {state.value: 0 for state in SourceIntakeResolutionState}
        for candidate in rows:
            state_counts[candidate.resolution_state.value] = (
                state_counts.get(candidate.resolution_state.value, 0) + 1
            )

        registered = state_counts.get(SourceIntakeResolutionState.REGISTERED.value, 0)
        excluded = state_counts.get(SourceIntakeResolutionState.EXCLUDED.value, 0)
        duplicate = state_counts.get(SourceIntakeResolutionState.DUPLICATE.value, 0)
        hard_failed = state_counts.get(SourceIntakeResolutionState.HARD_FAILED.value, 0)
        unresolved = state_counts.get(SourceIntakeResolutionState.UNRESOLVED.value, 0)
        ingestible = (
            state_counts.get(SourceIntakeResolutionState.AUTO_INGESTIBLE.value, 0)
            + state_counts.get(SourceIntakeResolutionState.RESOLVED.value, 0)
        )
        accounted = registered + excluded + duplicate + hard_failed + unresolved + ingestible
        total = len(rows)
        return SourceIntakeOccurrenceAccounting(
            total_occurrences=total,
            registered_count=registered,
            excluded_count=excluded,
            duplicate_count=duplicate,
            hard_failed_count=hard_failed,
            unresolved_count=unresolved,
            ingestible_count=ingestible,
            accounted_count=accounted,
            unaccounted_count=max(total - accounted, 0),
            balanced=accounted == total,
            state_counts=state_counts,
        )

    @staticmethod
    def _event_id_for_transition(
        candidate: SourceFileCandidate,
        action: SourceIntakeResolutionAction,
        occurred_at: str,
    ) -> str:
        seed = f"{candidate.occurrence_id}:{action.value}:{occurred_at}:{candidate.resolution_version}"
        return f"wlv-resolution-event:{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:20]}"

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
        self._validate_explicit_action(candidate, decision)
        next_state = self._next_state(candidate, decision, by_id)

        if decision.action == SourceIntakeResolutionAction.CONFIRM_SUGGESTION:
            self._confirm_current_suggestions(candidate)
        if decision.resolved_values:
            self._apply_resolved_values(candidate, decision.resolved_values)

        if (
            decision.action == SourceIntakeResolutionAction.WELL_ASSIGNED
            and decision.assignment_mode
            == SourceIntakeWellAssignmentMode.NEW_WELL
        ):
            self._apply_resolved_values(
                candidate,
                decision.new_well_values,
            )

        now = utc_now_iso()
        candidate.resolution_state = next_state
        candidate.resolved_by = decision.actor
        candidate.resolved_at = now
        candidate.resolution_reason = decision.reason
        candidate.resolution_version += 1
        candidate.current_decision = SourceIntakeCurrentDecision(
            decision=self._human_decision_kind(decision.action),
            actor=decision.actor,
            reason=decision.reason,
            decided_at=now,
            corrected_values=decision.resolved_values,
            accepted_finding_codes=decision.accepted_warning_codes,
            assignment_target=(
                decision.target_managed_well_id
                or decision.canonical_occurrence_id
            ),
            assignment_mode=decision.assignment_mode,
            new_well_values=decision.new_well_values,
            legacy_action=decision.action,
        )
        return SourceIntakeResolutionResult(
            occurrence_id=decision.occurrence_id,
            previous_state=previous,
            next_state=next_state,
            ingestible=is_wmd_eligible(candidate),
            message=f"Resolution state changed from {previous.value} to {next_state.value}.",
        )

    @staticmethod
    def _human_decision_kind(
        action: SourceIntakeResolutionAction,
    ) -> SourceIntakeHumanDecision:
        if action in {
            SourceIntakeResolutionAction.CONFIRM_SUGGESTION,
            SourceIntakeResolutionAction.WARNING_ACCEPTED,
            SourceIntakeResolutionAction.PROMOTE_WITH_EXCEPTION,
        }:
            return SourceIntakeHumanDecision.ACCEPT
        if action in {
            SourceIntakeResolutionAction.MANUAL_CORRECTION,
            SourceIntakeResolutionAction.METADATA_OVERRIDE,
        }:
            return SourceIntakeHumanDecision.CORRECT
        if action in {
            SourceIntakeResolutionAction.CANONICAL_SELECTED,
            SourceIntakeResolutionAction.WELL_ASSIGNED,
        }:
            return SourceIntakeHumanDecision.ASSIGN
        if action == SourceIntakeResolutionAction.EXCLUDED:
            return SourceIntakeHumanDecision.EXCLUDE
        if action == SourceIntakeResolutionAction.REOPENED:
            return SourceIntakeHumanDecision.CLEAR_DECISION
        raise SourceIntakeResolutionError(
            f"Unsupported human decision action: {action.value}"
        )

    def _next_state(self, candidate, decision, by_id):
        action = decision.action
        if action in {
            SourceIntakeResolutionAction.CONFIRM_SUGGESTION,
            SourceIntakeResolutionAction.MANUAL_CORRECTION,
            SourceIntakeResolutionAction.METADATA_OVERRIDE,
            SourceIntakeResolutionAction.WARNING_ACCEPTED,
            SourceIntakeResolutionAction.PROMOTE_WITH_EXCEPTION,
        }:
            if candidate.qaqc_status.failure_count > 0 or candidate.parse_error:
                raise SourceIntakeResolutionError("Hard failures cannot be overridden as ingestible.")
            return SourceIntakeResolutionState.RESOLVED
        if action == SourceIntakeResolutionAction.EXCLUDED:
            if not decision.reason:
                raise SourceIntakeResolutionError("Exclusion requires a reason.")
            return SourceIntakeResolutionState.EXCLUDED
        if action == SourceIntakeResolutionAction.WELL_ASSIGNED:
            if candidate.qaqc_status.failure_count > 0 or candidate.parse_error:
                raise SourceIntakeResolutionError(
                    "Hard failures cannot be assigned as ingestible."
                )
            return SourceIntakeResolutionState.RESOLVED
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
            candidate.current_decision = None
            return SourceIntakeResolutionState.UNRESOLVED
        raise SourceIntakeResolutionError(f"Unsupported resolution action: {action.value}")

    @staticmethod
    def _validate_explicit_action(
        candidate: SourceFileCandidate,
        decision: SourceIntakeResolutionDecision,
    ) -> None:
        action = decision.action

        if action == SourceIntakeResolutionAction.WELL_ASSIGNED:
            if decision.assignment_mode is None:
                raise SourceIntakeResolutionError(
                    "Well assignment requires assignment_mode."
                )
            if (
                decision.assignment_mode
                == SourceIntakeWellAssignmentMode.EXISTING_WELL
                and not decision.target_managed_well_id
            ):
                raise SourceIntakeResolutionError(
                    "Existing-well assignment requires target_managed_well_id."
                )
            if (
                decision.assignment_mode
                == SourceIntakeWellAssignmentMode.NEW_WELL
            ):
                well_name = decision.new_well_values.get("well_name")
                if not isinstance(well_name, str) or not well_name.strip():
                    raise SourceIntakeResolutionError(
                        "New-well assignment requires a non-empty well_name."
                    )
                allowed = {"well_name", "uwi", "operator", "field", "block"}
                unknown = set(decision.new_well_values) - allowed
                if unknown:
                    raise SourceIntakeResolutionError(
                        f"Unsupported new-well fields: {sorted(unknown)}"
                    )

        if action == SourceIntakeResolutionAction.CONFIRM_SUGGESTION:
            if candidate.resolved_metadata is None:
                raise SourceIntakeResolutionError("Candidate has no suggested metadata to confirm.")
            if not any(
                getattr(candidate.resolved_metadata, name).value
                for name in ("well_name", "uwi", "operator", "field", "block")
            ):
                raise SourceIntakeResolutionError(
                    "Candidate has no non-empty suggested metadata to confirm."
                )

        if action == SourceIntakeResolutionAction.MANUAL_CORRECTION:
            if not decision.resolved_values:
                raise SourceIntakeResolutionError(
                    "Manual correction requires at least one resolved value."
                )

        if action == SourceIntakeResolutionAction.PROMOTE_WITH_EXCEPTION:
            if not decision.reason:
                raise SourceIntakeResolutionError(
                    "Promotion with exception requires a reason."
                )
            if not decision.accepted_warning_codes:
                raise SourceIntakeResolutionError(
                    "Promotion with exception requires at least one accepted finding code."
                )

        if action in {
            SourceIntakeResolutionAction.CONFIRM_SUGGESTION,
            SourceIntakeResolutionAction.MANUAL_CORRECTION,
            SourceIntakeResolutionAction.PROMOTE_WITH_EXCEPTION,
        }:
            if candidate.qaqc_status.failure_count > 0 or candidate.parse_error:
                raise SourceIntakeResolutionError(
                    "Hard failures cannot be overridden as ingestible."
                )

    @staticmethod
    def _confirm_current_suggestions(candidate: SourceFileCandidate) -> None:
        if candidate.resolved_metadata is None:
            raise SourceIntakeResolutionError(
                "Candidate has no resolved metadata contract."
            )
        for name in ("well_name", "uwi", "operator", "field", "block"):
            field = getattr(candidate.resolved_metadata, name)
            if field.value is not None:
                field.source = "confirmed_suggestion"
                field.confidence = "reviewed"
                field.review_required = False
        candidate.resolved_metadata.review_required = any(
            getattr(candidate.resolved_metadata, name).review_required
            for name in ("well_name", "uwi", "operator", "field", "block")
        )

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
