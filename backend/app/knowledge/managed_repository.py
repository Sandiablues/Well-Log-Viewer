"""Managed KR repository and service layer for KR-2.

ManagedKRRepository is the backend service that owns the in-memory managed
record store.  It is the single point of truth for:

  - listing governed records by status or record type
  - serving production-eligible (seed + approved) knowledge
  - promoting or deprecating records (service methods; not yet HTTP endpoints)
  - generating health, schema, and status-summary introspection data

Architecture
------------
KR-2 uses in-memory storage backed by the Python seed layer.  The repository
is designed so that a future KR block can swap in file-backed or database
storage without changing the service interface.

The ManagedKRRepository does NOT replace the KR-1 KnowledgeRepository.
KR-1 endpoints remain the stable external contract; the managed repository is
an additional internal service layer whose read-only introspection endpoints
are registered under /api/wlv/knowledge/managed/*.

Evidence records are stored separately from governed records because they have
no governance lifecycle status.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .governance import (
    GovernanceStatus,
    PRODUCTION_STATUSES,
    TERMINAL_STATUSES,
    is_production_eligible,
    is_valid_transition,
)
from .managed_models import (
    KR2_VERSION,
    AliasRecord,
    ClassificationRuleRecord,
    CurveDefinitionRecord,
    DisplayRuleRecord,
    EvidenceRecord,
    TemplateRuleRecord,
)
from .managed_seed import build_seed_managed_records


# ---------------------------------------------------------------------------
# Type alias for governed records (all types that carry GovernanceStatus)
# ---------------------------------------------------------------------------

GovernedRecord = (
    CurveDefinitionRecord
    | AliasRecord
    | DisplayRuleRecord
    | ClassificationRuleRecord
    | TemplateRuleRecord
)


# ---------------------------------------------------------------------------
# ManagedKRRepository
# ---------------------------------------------------------------------------

class ManagedKRRepository:
    """In-memory managed Knowledge Repository for KR-2.

    Lifecycle
    ---------
    Instantiated once by the API layer.  Seed records are loaded on __init__.
    The store is read-only from the HTTP perspective; promote/deprecate service
    methods exist but are not exposed as public write endpoints in KR-2.
    """

    def __init__(self) -> None:
        # Governed records: record_id → GovernedRecord
        self._records: dict[str, GovernedRecord] = {}
        # Evidence records: evidence_id → EvidenceRecord
        self._evidence: dict[str, EvidenceRecord] = {}
        self._load_seed_records()

    # ------------------------------------------------------------------
    # Internal loading
    # ------------------------------------------------------------------

    def _load_seed_records(self) -> None:
        """Load all seed records from the managed_seed module."""
        for record in build_seed_managed_records():
            self._records[record.record_id] = record  # type: ignore[union-attr]

    def _add_record(self, record: GovernedRecord) -> None:
        """Add or replace a governed record.

        Intended for internal use, testing, and future import pipelines.
        Not exposed as a public HTTP endpoint in KR-2.
        """
        self._records[record.record_id] = record  # type: ignore[union-attr]

    def _add_evidence(self, record: EvidenceRecord) -> None:
        """Add an evidence/provenance record."""
        self._evidence[record.evidence_id] = record

    # ------------------------------------------------------------------
    # List / query methods
    # ------------------------------------------------------------------

    def list_records(
        self,
        record_type: str | None = None,
        status: GovernanceStatus | None = None,
    ) -> list[GovernedRecord]:
        """Return governed records, optionally filtered by record_type and/or status."""
        records: list[GovernedRecord] = list(self._records.values())
        if record_type is not None:
            records = [r for r in records if r.record_type == record_type]
        if status is not None:
            records = [r for r in records if r.status == status]
        return records

    def list_seeds(self) -> list[GovernedRecord]:
        """Return all seed-status governed records."""
        return self.list_records(status=GovernanceStatus.SEED)

    def list_candidates(self) -> list[GovernedRecord]:
        """Return all candidate-status governed records.

        Candidate records are NOT production-eligible by default.
        """
        return self.list_records(status=GovernanceStatus.CANDIDATE)

    def list_approved(self) -> list[GovernedRecord]:
        """Return only explicitly approved governed records.

        Does NOT include seed records; use list_production_eligible() for
        the full set of records safe to serve to classifiers.
        """
        return self.list_records(status=GovernanceStatus.APPROVED)

    def list_deprecated(self) -> list[GovernedRecord]:
        """Return deprecated governed records (retained for audit/history)."""
        return self.list_records(status=GovernanceStatus.DEPRECATED)

    def list_rejected(self) -> list[GovernedRecord]:
        """Return rejected governed records (retained for audit/history)."""
        return self.list_records(status=GovernanceStatus.REJECTED)

    def list_production_eligible(self) -> list[GovernedRecord]:
        """Return all records safe to serve to production (seed + approved)."""
        return [r for r in self._records.values() if is_production_eligible(r.status)]  # type: ignore[union-attr]

    def list_evidence(self) -> list[EvidenceRecord]:
        """Return all evidence/provenance records."""
        return list(self._evidence.values())

    # ------------------------------------------------------------------
    # Get by ID
    # ------------------------------------------------------------------

    def get_by_id(self, record_id: str) -> GovernedRecord | None:
        """Return a governed record by its record_id, or None if not found."""
        return self._records.get(record_id)

    def get_evidence_by_id(self, evidence_id: str) -> EvidenceRecord | None:
        """Return an evidence record by its evidence_id, or None."""
        return self._evidence.get(evidence_id)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_record(self, record: GovernedRecord) -> list[str]:
        """Validate a governed record and return a list of validation errors.

        Returns an empty list if the record is valid.
        """
        errors: list[str] = []
        if not getattr(record, "record_id", ""):
            errors.append("record_id must be non-empty")
        if not getattr(record, "record_type", ""):
            errors.append("record_type must be non-empty")
        status = getattr(record, "status", None)
        if status is not None and not isinstance(status, GovernanceStatus):
            errors.append(f"status {status!r} is not a valid GovernanceStatus")
        # Record-type-specific validation
        if isinstance(record, CurveDefinitionRecord):
            if not record.canonical_curve_id:
                errors.append("canonical_curve_id must be non-empty")
            if not record.display_name:
                errors.append("display_name must be non-empty")
            if not record.family:
                errors.append("family must be non-empty")
            if not record.product_group:
                errors.append("product_group must be non-empty")
        elif isinstance(record, AliasRecord):
            if not record.alias:
                errors.append("alias must be non-empty")
            if not record.canonical_curve_id:
                errors.append("canonical_curve_id must be non-empty")
            if not (0.0 <= record.confidence <= 1.0):
                errors.append("confidence must be between 0.0 and 1.0")
        elif isinstance(record, DisplayRuleRecord):
            if not record.canonical_curve_id:
                errors.append("canonical_curve_id must be non-empty")
            if not record.preferred_track_family:
                errors.append("preferred_track_family must be non-empty")
            if record.scale_type not in {"linear", "log"}:
                errors.append(f"scale_type {record.scale_type!r} must be 'linear' or 'log'")
        return errors

    # ------------------------------------------------------------------
    # Service methods (not exposed as public HTTP endpoints in KR-2)
    # ------------------------------------------------------------------

    def promote_to_approved(
        self,
        record_id: str,
        approved_by: str,
        change_reason: str | None = None,
    ) -> bool:
        """Promote a candidate or seed record to approved status.

        Returns True on success, False if the record does not exist or the
        transition is not permitted.

        Not exposed as a public HTTP endpoint in KR-2.  Call from tests or
        future KR management service only.
        """
        record = self._records.get(record_id)
        if record is None:
            return False
        current = getattr(record, "status", None)
        if current is None or not is_valid_transition(current, GovernanceStatus.APPROVED):
            return False
        record.status = GovernanceStatus.APPROVED  # type: ignore[union-attr]
        record.approved_by = approved_by  # type: ignore[union-attr]
        if hasattr(record, "approved_at"):
            record.approved_at = datetime.now(tz=timezone.utc)  # type: ignore[union-attr]
        if change_reason:
            record.change_reason = change_reason  # type: ignore[union-attr]
        return True

    def deprecate_record(
        self,
        record_id: str,
        change_reason: str | None = None,
    ) -> bool:
        """Deprecate an approved or seed record.

        Returns True on success, False if the record does not exist or the
        transition is not permitted.

        Not exposed as a public HTTP endpoint in KR-2.
        """
        record = self._records.get(record_id)
        if record is None:
            return False
        current = getattr(record, "status", None)
        if current is None or not is_valid_transition(current, GovernanceStatus.DEPRECATED):
            return False
        record.status = GovernanceStatus.DEPRECATED  # type: ignore[union-attr]
        if hasattr(record, "deprecated_at"):
            record.deprecated_at = datetime.now(tz=timezone.utc)  # type: ignore[union-attr]
        if change_reason:
            record.change_reason = change_reason  # type: ignore[union-attr]
        return True

    def reject_record(
        self,
        record_id: str,
        change_reason: str | None = None,
    ) -> bool:
        """Reject a candidate record.

        Returns True on success, False if the record does not exist or the
        transition is not permitted.

        Not exposed as a public HTTP endpoint in KR-2.
        """
        record = self._records.get(record_id)
        if record is None:
            return False
        current = getattr(record, "status", None)
        if current is None or not is_valid_transition(current, GovernanceStatus.REJECTED):
            return False
        record.status = GovernanceStatus.REJECTED  # type: ignore[union-attr]
        if change_reason:
            record.change_reason = change_reason  # type: ignore[union-attr]
        return True

    # ------------------------------------------------------------------
    # Introspection / read-only summary methods
    # ------------------------------------------------------------------

    def get_status_summary(self) -> dict[str, int]:
        """Return record counts per governance status value."""
        counts: dict[str, int] = {s.value: 0 for s in GovernanceStatus}
        for record in self._records.values():
            status = getattr(record, "status", None)
            if status is not None:
                counts[status.value] = counts.get(status.value, 0) + 1
        return counts

    def get_type_summary(self) -> dict[str, int]:
        """Return record counts per record type."""
        counts: dict[str, int] = {}
        for record in self._records.values():
            rt = getattr(record, "record_type", "unknown")
            counts[rt] = counts.get(rt, 0) + 1
        if self._evidence:
            counts["evidence"] = len(self._evidence)
        return counts

    def get_health(self) -> dict[str, Any]:
        """Return health/status data for the managed repository."""
        status_summary = self.get_status_summary()
        type_summary = self.get_type_summary()
        total = len(self._records) + len(self._evidence)
        return {
            "service": "wlv_managed_knowledge_repository",
            "status": "ok",
            "mode": "read_only",
            "kr_version": KR2_VERSION,
            "total_record_count": total,
            "governed_record_count": len(self._records),
            "evidence_record_count": len(self._evidence),
            "status_summary": status_summary,
            "type_summary": type_summary,
        }

    def get_schema(self) -> dict[str, Any]:
        """Return schema metadata describing managed KR record types and statuses."""
        gov_statuses = {
            s.value: {
                "label": s.value.capitalize(),
                "production_eligible": is_production_eligible(s),
                "terminal": s in TERMINAL_STATUSES,
                "valid_transitions": [
                    t.value
                    for t in GovernanceStatus
                    if is_valid_transition(s, t)
                ],
            }
            for s in GovernanceStatus
        }
        record_types = [
            {
                "record_type": "curve_definition",
                "description": "Canonical curve knowledge record",
                "governed": True,
                "seed_count": sum(
                    1 for r in self.list_records("curve_definition")
                    if r.status == GovernanceStatus.SEED
                ),
            },
            {
                "record_type": "alias",
                "description": "Mnemonic alias record mapping to a canonical curve",
                "governed": True,
                "seed_count": sum(
                    1 for r in self.list_records("alias")
                    if r.status == GovernanceStatus.SEED
                ),
            },
            {
                "record_type": "display_rule",
                "description": "Curve display rendering rule",
                "governed": True,
                "seed_count": sum(
                    1 for r in self.list_records("display_rule")
                    if r.status == GovernanceStatus.SEED
                ),
            },
            {
                "record_type": "classification_rule",
                "description": "Deterministic classification hint rule",
                "governed": True,
                "seed_count": 0,  # No classification rule seeds in KR-2
            },
            {
                "record_type": "template_rule",
                "description": "Viewer template construction rule (empty in KR-2)",
                "governed": True,
                "seed_count": 0,  # Templates intentionally empty in KR-2
            },
            {
                "record_type": "evidence",
                "description": "Provenance/source record (no governance lifecycle)",
                "governed": False,
                "seed_count": 0,
            },
        ]
        return {
            "kr_version": KR2_VERSION,
            "record_types": record_types,
            "governance_statuses": gov_statuses,
            "notes": [
                "seed records are bootstrap/default knowledge from Python constants",
                "candidate records are not production-eligible unless explicitly requested",
                "approved records override seed records in future KR management blocks",
                "template_rule records are structurally defined but empty in KR-2",
                "mutating HTTP endpoints (promote/deprecate/import) are deferred to KR-3+",
            ],
        }

    def get_status_summary_response(self) -> dict[str, Any]:
        """Return a full status summary suitable for the /managed/status-summary endpoint."""
        status_summary = self.get_status_summary()
        type_summary = self.get_type_summary()
        production_count = len(self.list_production_eligible())
        candidate_count = len(self.list_candidates())
        approved_count = len(self.list_approved())
        seed_count = len(self.list_seeds())
        return {
            "kr_version": KR2_VERSION,
            "total_governed_records": len(self._records),
            "production_eligible_count": production_count,
            "seed_count": seed_count,
            "candidate_count": candidate_count,
            "approved_count": approved_count,
            "deprecated_count": status_summary.get("deprecated", 0),
            "rejected_count": status_summary.get("rejected", 0),
            "status_by_type": {
                rt: {
                    s.value: sum(
                        1 for r in self.list_records(rt)
                        if r.status == s
                    )
                    for s in GovernanceStatus
                }
                for rt in {
                    "curve_definition", "alias", "display_rule",
                    "classification_rule", "template_rule",
                }
            },
        }
