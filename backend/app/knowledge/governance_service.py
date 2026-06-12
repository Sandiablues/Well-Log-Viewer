"""KR-4 Governance Service.

Backend-owned service that exposes controlled governance actions for managed
KR records: list, lookup, approve, reject, deprecate, and production-eligible
listing.

All governance actions enforce the status transition rules defined in
governance.py.  Invalid transitions fail deterministically with
``GovernanceTransitionError``.  Unknown record IDs raise ``RecordNotFoundError``.

Audit contract
--------------
Every approve/reject/deprecate action appends an entry to the record's
``governance_history`` list (added in KR-4).  Each entry records:
  - action      : the transition performed ("approved" / "rejected" / "deprecated")
  - actor       : who performed the action (caller-supplied string)
  - timestamp   : UTC ISO-8601 timestamp
  - previous_status : status before the transition
  - new_status  : status after the transition
  - reason      : caller-supplied reason (required for reject/deprecate; optional for approve)
  - notes       : optional free-text notes

This provides durable evidence to answer:
  Who changed the record? (actor)
  When was it changed? (timestamp)
  What transition happened? (previous_status → new_status)
  Why was it changed? (reason)

Additionally, the existing ``approved_by`` / ``approved_at`` / ``deprecated_at``
/ ``change_reason`` fields on the model are kept in sync where they exist,
preserving backward compatibility with KR-2/KR-3 field expectations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .governance import (
    GovernanceStatus,
    is_production_eligible,
    is_valid_transition,
)
from .managed_models import KR4_VERSION
from .managed_repository import GovernedRecord, ManagedKRRepository


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RecordNotFoundError(Exception):
    """Raised when a record_id does not exist in the repository."""

    def __init__(self, record_id: str) -> None:
        self.record_id = record_id
        super().__init__(f"Record not found: {record_id!r}")


class GovernanceTransitionError(Exception):
    """Raised when a requested status transition is not permitted.

    Attributes:
        record_id     : the record that was being acted on
        from_status   : the record's current status
        to_status     : the requested (disallowed) target status
    """

    def __init__(
        self,
        record_id: str,
        from_status: GovernanceStatus,
        to_status: GovernanceStatus,
    ) -> None:
        self.record_id = record_id
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Invalid governance transition {from_status.value!r} → {to_status.value!r} "
            f"for record {record_id!r}."
        )


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------


def _serialize_record(record: GovernedRecord) -> dict[str, Any]:
    """Convert a governed record dataclass to a JSON-serialisable dict.

    Handles datetime → ISO string and GovernanceStatus → string.value.
    """
    import dataclasses

    def _convert(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, GovernanceStatus):
            return obj.value
        if isinstance(obj, list):
            return [_convert(item) for item in obj]
        if isinstance(obj, dict):
            return {k: _convert(v) for k, v in obj.items()}
        return obj

    raw = dataclasses.asdict(record)
    return {k: _convert(v) for k, v in raw.items()}


# ---------------------------------------------------------------------------
# GovernanceService
# ---------------------------------------------------------------------------


class GovernanceService:
    """KR-4 governance service.

    Wraps ManagedKRRepository and enforces all governance lifecycle rules.

    Intended usage::

        service = GovernanceService(repository)
        result  = service.approve_record("some_id", actor="manual_review", reason="Verified")

    The service does NOT own or replace the repository — it is a thin
    governance layer on top of it.
    """

    def __init__(self, repository: ManagedKRRepository) -> None:
        self._repo = repository

    # ------------------------------------------------------------------
    # List / query
    # ------------------------------------------------------------------

    def list_records(
        self,
        status: GovernanceStatus | None = None,
        record_type: str | None = None,
    ) -> list[GovernedRecord]:
        """Return governed records, optionally filtered by status and/or record_type."""
        return self._repo.list_records(record_type=record_type, status=status)

    def get_record(self, record_id: str) -> GovernedRecord:
        """Return a governed record by ID.

        Raises:
            RecordNotFoundError: if no record with this ID exists.
        """
        record = self._repo.get_by_id(record_id)
        if record is None:
            raise RecordNotFoundError(record_id)
        return record

    def list_production_eligible_records(
        self,
        record_type: str | None = None,
    ) -> list[GovernedRecord]:
        """Return records that are production-eligible (seed + approved).

        Optionally filtered by record_type.
        """
        records = self._repo.list_production_eligible()
        if record_type is not None:
            records = [r for r in records if r.record_type == record_type]
        return records

    # ------------------------------------------------------------------
    # Governance actions
    # ------------------------------------------------------------------

    def approve_record(
        self,
        record_id: str,
        actor: str,
        reason: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Approve a candidate or seed record.

        Valid source statuses: candidate, seed → approved.

        Returns:
            Governance action result dict (see module docstring for shape).

        Raises:
            RecordNotFoundError: if record_id does not exist.
            GovernanceTransitionError: if the transition is not permitted.
        """
        record = self._get_mutable_or_raise(record_id)
        previous_status = record.status  # type: ignore[union-attr]
        self._validate_transition(record, record_id, previous_status, GovernanceStatus.APPROVED)

        now = datetime.now(tz=timezone.utc)
        record.status = GovernanceStatus.APPROVED  # type: ignore[union-attr]
        # Keep legacy fields in sync where they exist on the model
        if hasattr(record, "approved_by"):
            record.approved_by = actor  # type: ignore[union-attr]
        if hasattr(record, "approved_at"):
            record.approved_at = now  # type: ignore[union-attr]
        if reason and hasattr(record, "change_reason"):
            record.change_reason = reason  # type: ignore[union-attr]
        if hasattr(record, "updated_at"):
            record.updated_at = now  # type: ignore[union-attr]

        self._append_history(record, "approved", actor, previous_status, GovernanceStatus.APPROVED, reason, notes, now)
        self._repo.persist()  # KR-5: persist after governance transition

        return self._action_response(record, record_id, previous_status, GovernanceStatus.APPROVED)

    def reject_record(
        self,
        record_id: str,
        actor: str,
        reason: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Reject a candidate record.

        Valid source statuses: candidate → rejected.

        Returns:
            Governance action result dict.

        Raises:
            RecordNotFoundError: if record_id does not exist.
            GovernanceTransitionError: if the transition is not permitted.
        """
        record = self._get_mutable_or_raise(record_id)
        previous_status = record.status  # type: ignore[union-attr]
        self._validate_transition(record, record_id, previous_status, GovernanceStatus.REJECTED)

        now = datetime.now(tz=timezone.utc)
        record.status = GovernanceStatus.REJECTED  # type: ignore[union-attr]
        if reason and hasattr(record, "change_reason"):
            record.change_reason = reason  # type: ignore[union-attr]
        if hasattr(record, "updated_at"):
            record.updated_at = now  # type: ignore[union-attr]

        self._append_history(record, "rejected", actor, previous_status, GovernanceStatus.REJECTED, reason, notes, now)
        self._repo.persist()  # KR-5: persist after governance transition

        return self._action_response(record, record_id, previous_status, GovernanceStatus.REJECTED)

    def deprecate_record(
        self,
        record_id: str,
        actor: str,
        reason: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Deprecate a seed or approved record.

        Valid source statuses: seed → deprecated, approved → deprecated.
        candidate → deprecated is BLOCKED.

        Returns:
            Governance action result dict.

        Raises:
            RecordNotFoundError: if record_id does not exist.
            GovernanceTransitionError: if the transition is not permitted.
        """
        record = self._get_mutable_or_raise(record_id)
        previous_status = record.status  # type: ignore[union-attr]
        self._validate_transition(record, record_id, previous_status, GovernanceStatus.DEPRECATED)

        now = datetime.now(tz=timezone.utc)
        record.status = GovernanceStatus.DEPRECATED  # type: ignore[union-attr]
        if hasattr(record, "deprecated_at"):
            record.deprecated_at = now  # type: ignore[union-attr]
        if reason and hasattr(record, "change_reason"):
            record.change_reason = reason  # type: ignore[union-attr]
        if hasattr(record, "updated_at"):
            record.updated_at = now  # type: ignore[union-attr]

        self._append_history(record, "deprecated", actor, previous_status, GovernanceStatus.DEPRECATED, reason, notes, now)
        self._repo.persist()  # KR-5: persist after governance transition

        return self._action_response(record, record_id, previous_status, GovernanceStatus.DEPRECATED)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_or_raise(self, record_id: str) -> GovernedRecord:
        """Return a record for read-only use (does not promote to managed store)."""
        record = self._repo.get_by_id(record_id)
        if record is None:
            raise RecordNotFoundError(record_id)
        return record

    def _get_mutable_or_raise(self, record_id: str) -> GovernedRecord:
        """Return a mutable record for governance mutation.

        If the record currently lives only in the seed store, it is first
        promoted into the managed store so the subsequent status mutation
        will be captured by ``repo.persist()``.

        Raises:
            RecordNotFoundError: if record_id does not exist.
        """
        record = self._repo.prepare_for_mutation(record_id)
        if record is None:
            raise RecordNotFoundError(record_id)
        return record

    @staticmethod
    def _validate_transition(
        record: GovernedRecord,
        record_id: str,
        from_status: GovernanceStatus,
        to_status: GovernanceStatus,
    ) -> None:
        if not is_valid_transition(from_status, to_status):
            raise GovernanceTransitionError(record_id, from_status, to_status)

    @staticmethod
    def _append_history(
        record: GovernedRecord,
        action: str,
        actor: str,
        previous_status: GovernanceStatus,
        new_status: GovernanceStatus,
        reason: str | None,
        notes: str | None,
        timestamp: datetime,
    ) -> None:
        """Append a governance audit entry to record.governance_history."""
        if not hasattr(record, "governance_history"):
            return  # should never happen for governed records
        entry: dict[str, Any] = {
            "action": action,
            "actor": actor,
            "timestamp": timestamp.isoformat(),
            "previous_status": previous_status.value,
            "new_status": new_status.value,
            "reason": reason,
            "notes": notes,
        }
        record.governance_history.append(entry)  # type: ignore[union-attr]

    @staticmethod
    def _action_response(
        record: GovernedRecord,
        record_id: str,
        previous_status: GovernanceStatus,
        new_status: GovernanceStatus,
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "kr_version": KR4_VERSION,
            "record_id": record_id,
            "previous_status": previous_status.value,
            "new_status": new_status.value,
            "production_eligible": is_production_eligible(new_status),
            "record": _serialize_record(record),
        }
