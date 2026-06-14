"""Managed KR repository and service layer — KR-2 through KR-5.

KR-5 adds durable, file-backed storage so that managed records survive
backend restart.  The design preserves the service-boundary model established
in KR-1 through KR-4:

  Seed knowledge
    - Loaded from the Python seed layer (managed_seed.py) on every startup.
    - Stored in ``_seed_records`` (in-memory only; never written to disk).
    - Record IDs are prefixed ``seed_`` and are deterministic.

  Managed knowledge
    - Candidates, approved, rejected, deprecated, and evidence records.
    - Loaded from persistent JSON storage on startup.
    - Written to disk after every mutating operation.
    - Stored in ``_managed_records`` (also held in memory for fast access).

  Merged view
    - ``list_*`` and ``get_by_id`` methods merge both stores.
    - Managed records take precedence over seed records on the same ID
      (enabling seed-override deprecations / approvals).

Seed transitions (approve / deprecate a seed record)
    When the governance layer transitions a seed record, the repository
    copies that record into ``_managed_records`` so the new status is
    persisted.  The seed constant layer is never mutated.

Persistence points
    - ``_add_record()``    — called by import staging
    - ``_add_evidence()``  — called by import staging
    - ``persist()``        — called by GovernanceService after approve/reject/deprecate
    - Read-only operations do NOT write.
    - Preview does NOT write.

Test isolation
    Pass ``storage_path=Path("/tmp/…")`` to the constructor.  Tests inject
    isolated repos via FastAPI dependency_overrides and never touch the
    real project storage file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .alias_enrichment_models import AliasEnrichmentRecord
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
    GenericManagedRecord,
    TemplateRuleRecord,
)
from .managed_seed import build_seed_managed_records
from .managed_storage import ManagedStorage, ManagedStorageError, serialize_record


# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

GovernedRecord = (
    CurveDefinitionRecord
    | AliasRecord
    | DisplayRuleRecord
    | ClassificationRuleRecord
    | TemplateRuleRecord
    | AliasEnrichmentRecord  # KR-DATA-MODEL-1
    | GenericManagedRecord  # WDV approved reference/template layer
)


# ---------------------------------------------------------------------------
# ManagedKRRepository
# ---------------------------------------------------------------------------


class ManagedKRRepository:
    """Managed Knowledge Repository with durable file-backed storage (KR-5).

    Lifecycle
    ---------
    Instantiated once by the API layer.  Seed records are loaded from the
    Python seed layer; managed records are loaded from JSON storage.  The
    two stores are merged for all read operations.

    Storage
    -------
    ``storage_path`` defaults to
    ``backend/data/knowledge/managed_knowledge.json`` relative to the
    project root.  Pass a custom path in tests for full isolation::

        repo = ManagedKRRepository(storage_path=tmp_path / "kr.json")
    """

    def __init__(self, storage_path: Path | None = None) -> None:
        # Seed records: record_id → GovernedRecord (never persisted)
        self._seed_records: dict[str, GovernedRecord] = {}
        # Set of seed record IDs for O(1) membership tests
        self._seed_ids: set[str] = set()

        # Managed records: record_id → GovernedRecord (persisted on mutation)
        self._managed_records: dict[str, GovernedRecord] = {}

        # Evidence records: evidence_id → EvidenceRecord (persisted)
        self._evidence: dict[str, EvidenceRecord] = {}

        # Storage layer (path-injectable for test isolation)
        self._storage: ManagedStorage = ManagedStorage(path=storage_path)

        self._load_seed_records()
        self._load_persisted_records()

    # ------------------------------------------------------------------
    # Internal loading
    # ------------------------------------------------------------------

    def _load_seed_records(self) -> None:
        """Load all seed records from the managed_seed module into _seed_records."""
        for record in build_seed_managed_records():
            rid = record.record_id  # type: ignore[union-attr]
            self._seed_records[rid] = record  # type: ignore[assignment]
            self._seed_ids.add(rid)

    def _load_persisted_records(self) -> None:
        """Load managed records and evidence from persistent storage.

        Missing file → start with seed-only state (no error).
        Empty file → same as missing.
        Malformed JSON → raises ManagedStorageError (hard startup failure).

        Managed records override seed records on the same record_id.
        """
        records, evidence = self._storage.load()
        for record in records:
            self._managed_records[record.record_id] = record  # type: ignore[union-attr]
        for ev in evidence:
            self._evidence[ev.evidence_id] = ev

    # ------------------------------------------------------------------
    # Merged view helpers
    # ------------------------------------------------------------------

    def _all_records(self) -> dict[str, GovernedRecord]:
        """Return merged seed + managed record dict.

        Managed records take precedence over seed records on the same ID.
        """
        merged: dict[str, GovernedRecord] = {**self._seed_records, **self._managed_records}
        return merged

    def _is_persisted_managed(self, record_id: str) -> bool:
        """Return True if this record_id lives in the managed (persisted) store."""
        return record_id in self._managed_records

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def persist(self) -> None:
        """Write current managed records and evidence to durable storage.

        Only ``_managed_records`` and ``_evidence`` are written.
        Seed records are never written.

        Called automatically by ``_add_record`` and ``_add_evidence``.
        Also called explicitly by GovernanceService after governance actions
        so that approve/reject/deprecate transitions survive restart.
        """
        records_to_persist = list(self._managed_records.values())
        evidence_to_persist = list(self._evidence.values())
        self._storage.save(records_to_persist, evidence_to_persist)

    def _ensure_managed(self, record_id: str) -> None:
        """If a seed record is being mutated, promote it to the managed store.

        This ensures seed transitions (approve/deprecate) are persisted.
        The seed constant layer is never mutated directly.

        If the record is already managed (candidate or previously promoted),
        this is a no-op.
        """
        if record_id in self._managed_records:
            return  # already in the managed store
        seed_record = self._seed_records.get(record_id)
        if seed_record is None:
            return  # record does not exist; caller will raise appropriately
        # Copy the seed record into the managed store so it can be persisted
        import copy
        self._managed_records[record_id] = copy.deepcopy(seed_record)

    # ------------------------------------------------------------------
    # Internal mutating helpers (called by staging and governance layers)
    # ------------------------------------------------------------------

    def _add_record(self, record: GovernedRecord) -> None:
        """Add or replace a governed record and persist immediately.

        Raises:
            ValueError: if the record_id already exists in the managed store
                with the same ID (duplicate import protection handled upstream).
        """
        self._managed_records[record.record_id] = record  # type: ignore[union-attr]
        self.persist()

    def _add_evidence(self, record: EvidenceRecord) -> None:
        """Add an evidence record and persist immediately."""
        self._evidence[record.evidence_id] = record
        self.persist()

    # ------------------------------------------------------------------
    # List / query methods (unchanged API from KR-2)
    # ------------------------------------------------------------------

    def list_records(
        self,
        record_type: str | None = None,
        status: GovernanceStatus | None = None,
    ) -> list[GovernedRecord]:
        """Return governed records (seed + managed merged), filtered optionally."""
        records: list[GovernedRecord] = list(self._all_records().values())
        if record_type is not None:
            records = [r for r in records if r.record_type == record_type]  # type: ignore[union-attr]
        if status is not None:
            records = [r for r in records if r.status == status]  # type: ignore[union-attr]
        return records

    def list_seeds(self) -> list[GovernedRecord]:
        """Return all seed-status governed records."""
        return self.list_records(status=GovernanceStatus.SEED)

    def list_candidates(self) -> list[GovernedRecord]:
        """Return all candidate-status governed records (NOT production-eligible)."""
        return self.list_records(status=GovernanceStatus.CANDIDATE)

    def list_approved(self) -> list[GovernedRecord]:
        """Return only explicitly approved governed records (NOT including seeds)."""
        return self.list_records(status=GovernanceStatus.APPROVED)

    def list_deprecated(self) -> list[GovernedRecord]:
        """Return deprecated governed records (retained for audit/history)."""
        return self.list_records(status=GovernanceStatus.DEPRECATED)

    def list_rejected(self) -> list[GovernedRecord]:
        """Return rejected governed records (retained for audit/history)."""
        return self.list_records(status=GovernanceStatus.REJECTED)

    def list_production_eligible(self) -> list[GovernedRecord]:
        """Return all records safe to serve to production (seed + approved)."""
        return [
            r
            for r in self._all_records().values()
            if is_production_eligible(r.status)  # type: ignore[union-attr]
        ]

    def list_evidence(self) -> list[EvidenceRecord]:
        """Return all evidence/provenance records."""
        return list(self._evidence.values())

    # ------------------------------------------------------------------
    # Get by ID
    # ------------------------------------------------------------------

    def get_by_id(self, record_id: str) -> GovernedRecord | None:
        """Return a governed record by its record_id, or None if not found.

        Managed records take precedence over seed records.
        """
        return self._all_records().get(record_id)

    def get_evidence_by_id(self, evidence_id: str) -> EvidenceRecord | None:
        """Return an evidence record by its evidence_id, or None."""
        return self._evidence.get(evidence_id)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_record(self, record: GovernedRecord) -> list[str]:
        """Validate a governed record and return a list of validation errors."""
        errors: list[str] = []
        if not getattr(record, "record_id", ""):
            errors.append("record_id must be non-empty")
        if not getattr(record, "record_type", ""):
            errors.append("record_type must be non-empty")
        status = getattr(record, "status", None)
        if status is not None and not isinstance(status, GovernanceStatus):
            errors.append(f"status {status!r} is not a valid GovernanceStatus")
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
        elif isinstance(record, AliasEnrichmentRecord):
            # KR-DATA-MODEL-1: validate alias enrichment required fields
            if not record.alias:
                errors.append("alias must be non-empty")
            if not record.normalized_alias:
                errors.append("normalized_alias must be non-empty")
            if not record.display_canonical_curve_id:
                errors.append("display_canonical_curve_id must be non-empty")
            if not record.technical_curve_id:
                errors.append("technical_curve_id must be non-empty")
            if not record.technical_display_name:
                errors.append("technical_display_name must be non-empty")
            if not record.parent_canonical_curve_id:
                errors.append("parent_canonical_curve_id must be non-empty")
            if not (0.0 <= record.confidence <= 1.0):
                errors.append("confidence must be between 0.0 and 1.0")
        return errors

    # ------------------------------------------------------------------
    # Governance transition helpers (used by GovernanceService)
    # ------------------------------------------------------------------

    def prepare_for_mutation(self, record_id: str) -> GovernedRecord | None:
        """Return the mutable record for governance actions.

        If the record currently lives only in the seed store, it is first
        copied into the managed store so the subsequent mutation will be
        persisted by ``persist()``.

        Returns None if the record does not exist.
        """
        record = self.get_by_id(record_id)
        if record is None:
            return None
        self._ensure_managed(record_id)
        return self._managed_records[record_id]

    # ------------------------------------------------------------------
    # Legacy service methods (kept for backward compatibility; not used by
    # governance_service.py which owns transition logic directly)
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
        """
        record = self.prepare_for_mutation(record_id)
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
        self.persist()
        return True

    def deprecate_record(
        self,
        record_id: str,
        change_reason: str | None = None,
    ) -> bool:
        """Deprecate an approved or seed record.

        Returns True on success, False if not found or transition disallowed.
        """
        record = self.prepare_for_mutation(record_id)
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
        self.persist()
        return True

    def reject_record(
        self,
        record_id: str,
        change_reason: str | None = None,
    ) -> bool:
        """Reject a candidate record.

        Returns True on success, False if not found or transition disallowed.
        """
        record = self.prepare_for_mutation(record_id)
        if record is None:
            return False
        current = getattr(record, "status", None)
        if current is None or not is_valid_transition(current, GovernanceStatus.REJECTED):
            return False
        record.status = GovernanceStatus.REJECTED  # type: ignore[union-attr]
        if change_reason:
            record.change_reason = change_reason  # type: ignore[union-attr]
        self.persist()
        return True

    # ------------------------------------------------------------------
    # Introspection / read-only summary methods (unchanged from KR-2)
    # ------------------------------------------------------------------

    def get_status_summary(self) -> dict[str, int]:
        """Return record counts per governance status value."""
        counts: dict[str, int] = {s.value: 0 for s in GovernanceStatus}
        for record in self._all_records().values():
            status = getattr(record, "status", None)
            if status is not None:
                counts[status.value] = counts.get(status.value, 0) + 1
        return counts

    def get_type_summary(self) -> dict[str, int]:
        """Return record counts per record type."""
        counts: dict[str, int] = {}
        for record in self._all_records().values():
            rt = getattr(record, "record_type", "unknown")
            counts[rt] = counts.get(rt, 0) + 1
        if self._evidence:
            counts["evidence"] = len(self._evidence)
        return counts

    def get_health(self) -> dict[str, Any]:
        """Return health/status data for the managed repository."""
        status_summary = self.get_status_summary()
        type_summary = self.get_type_summary()
        all_records = self._all_records()
        total = len(all_records) + len(self._evidence)
        return {
            "service": "wlv_managed_knowledge_repository",
            "status": "ok",
            "mode": "read_only",
            "kr_version": KR2_VERSION,
            "total_record_count": total,
            "governed_record_count": len(all_records),
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
                "seed_count": 0,
            },
            {
                "record_type": "template_rule",
                "description": "Viewer template construction rule (empty in KR-2)",
                "governed": True,
                "seed_count": 0,
            },
            {
                "record_type": "alias_enrichment",
                "description": (
                    "Technical-subtype enrichment for an existing alias/canonical mapping "
                    "(KR-DATA-MODEL-1). Attaches a specific technical identity without "
                    "replacing the display canonical curve. Does not affect KR-6/7/8."
                ),
                "governed": True,
                "seed_count": 0,
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
                "alias_enrichment records (KR-DATA-MODEL-1) carry technical-subtype metadata "
                "for existing alias mappings; they do not affect KR-6/7/8 display resolution",
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
            "total_governed_records": len(self._all_records()),
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
                for rt in sorted(
                    {getattr(r, "record_type", "unknown") for r in self._all_records().values()}
                )
            },
        }

    # ------------------------------------------------------------------
    # Alias enrichment query (KR-DATA-MODEL-1)
    # ------------------------------------------------------------------

    def list_alias_enrichments(
        self,
        alias: str | None = None,
        status: GovernanceStatus | None = None,
    ) -> list[AliasEnrichmentRecord]:
        """Return alias enrichment records, optionally filtered.

        KR-DATA-MODEL-1 convenience method.  Candidate enrichments are
        returned unless ``status`` narrows the filter.  Approved enrichments
        are production-eligible as metadata only — they do not affect KR-6/7/8.

        Args:
            alias:  If given, filter to enrichments whose normalized_alias
                    matches the upper-case form of ``alias``.
            status: If given, filter to enrichments with this governance status.

        Returns:
            List of AliasEnrichmentRecord instances.
        """
        records: list[AliasEnrichmentRecord] = [
            r for r in self._all_records().values()
            if isinstance(r, AliasEnrichmentRecord)
        ]
        if alias is not None:
            normalized = alias.strip().upper()
            records = [r for r in records if r.normalized_alias == normalized]
        if status is not None:
            records = [r for r in records if r.status == status]
        return records

    # ------------------------------------------------------------------
    # Storage health (KR-5)
    # ------------------------------------------------------------------

    def get_storage_health(self) -> dict[str, Any]:
        """Return storage health data (KR-5)."""
        return self._storage.health()
