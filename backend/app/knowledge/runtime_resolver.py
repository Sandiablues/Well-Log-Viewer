"""KR-RUNTIME-1 — approved-only runtime knowledge resolver.

This module defines the hardened runtime boundary for WLV Knowledge Repository
consumers.  It exposes a deterministic, read-only snapshot containing only
runtime-eligible knowledge:

    seed + approved managed records

Candidate, rejected, and deprecated records are intentionally excluded.  They
remain available to governance/review APIs, but they cannot influence runtime
classification, display, or template logic through this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from .alias_enrichment_models import AliasEnrichmentRecord
from .governance import GovernanceStatus, is_production_eligible
from .managed_models import EvidenceRecord
from .managed_repository import GovernedRecord, ManagedKRRepository

KR_RUNTIME_1_VERSION = "kr-runtime-1"
RUNTIME_SCOPE_SEED_PLUS_APPROVED = "seed_plus_approved"


@dataclass(frozen=True)
class RuntimeKnowledgePolicy:
    """Proof object describing the runtime knowledge scope used."""

    runtime_knowledge_scope: str = RUNTIME_SCOPE_SEED_PLUS_APPROVED
    candidate_records_used: bool = False
    rejected_records_used: bool = False
    deprecated_records_used: bool = False
    seed_record_count: int = 0
    approved_record_count: int = 0
    excluded_candidate_count: int = 0
    excluded_rejected_count: int = 0
    excluded_deprecated_count: int = 0
    knowledge_version: str = KR_RUNTIME_1_VERSION

    @property
    def production_record_count(self) -> int:
        return self.seed_record_count + self.approved_record_count

    def as_dict(self) -> dict[str, int | str | bool]:
        return {
            "runtime_knowledge_scope": self.runtime_knowledge_scope,
            "candidate_records_used": self.candidate_records_used,
            "rejected_records_used": self.rejected_records_used,
            "deprecated_records_used": self.deprecated_records_used,
            "seed_record_count": self.seed_record_count,
            "approved_record_count": self.approved_record_count,
            "production_record_count": self.production_record_count,
            "excluded_candidate_count": self.excluded_candidate_count,
            "excluded_rejected_count": self.excluded_rejected_count,
            "excluded_deprecated_count": self.excluded_deprecated_count,
            "knowledge_version": self.knowledge_version,
        }


@dataclass(frozen=True)
class RuntimeKnowledgeSnapshot:
    """Immutable read model for runtime-eligible KR knowledge."""

    kr_version: str
    policy: RuntimeKnowledgePolicy
    records: tuple[GovernedRecord, ...] = field(default_factory=tuple)
    evidence: tuple[EvidenceRecord, ...] = field(default_factory=tuple)

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def evidence_count(self) -> int:
        return len(self.evidence)

    def list_records(self, record_type: Optional[str] = None) -> list[GovernedRecord]:
        if record_type is None:
            return list(self.records)
        return [r for r in self.records if getattr(r, "record_type", None) == record_type]

    def type_summary(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for record in self.records:
            key = getattr(record, "record_type", "unknown")
            summary[key] = summary.get(key, 0) + 1
        return summary

    def status_summary(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for record in self.records:
            status = getattr(record, "status", None)
            key = status.value if isinstance(status, GovernanceStatus) else str(status)
            summary[key] = summary.get(key, 0) + 1
        return summary

    def as_summary_dict(self) -> dict[str, object]:
        return {
            "kr_version": self.kr_version,
            "record_count": self.record_count,
            "evidence_count": self.evidence_count,
            "policy": self.policy.as_dict(),
            "status_summary": self.status_summary(),
            "type_summary": self.type_summary(),
        }


class ApprovedKnowledgeRuntimeResolver:
    """Read-only resolver for runtime-eligible KR knowledge.

    This is the KR-RUNTIME-1 service boundary.  Downstream runtime consumers
    should depend on this resolver, not on raw managed storage or unrestricted
    repository queries, whenever runtime behavior is being decided.
    """

    def __init__(self, repository: ManagedKRRepository) -> None:
        self._repository = repository

    def build_snapshot(self) -> RuntimeKnowledgeSnapshot:
        """Return a runtime snapshot containing seed + approved records only."""
        all_records = self._repository.list_records()
        production_records = tuple(
            record for record in all_records
            if self._is_runtime_eligible(record)
        )

        policy = RuntimeKnowledgePolicy(
            seed_record_count=self._count_status(production_records, GovernanceStatus.SEED),
            approved_record_count=self._count_status(production_records, GovernanceStatus.APPROVED),
            excluded_candidate_count=self._count_status(all_records, GovernanceStatus.CANDIDATE),
            excluded_rejected_count=self._count_status(all_records, GovernanceStatus.REJECTED),
            excluded_deprecated_count=self._count_status(all_records, GovernanceStatus.DEPRECATED),
        )

        evidence = tuple(self._evidence_for_records(production_records))
        return RuntimeKnowledgeSnapshot(
            kr_version=KR_RUNTIME_1_VERSION,
            policy=policy,
            records=production_records,
            evidence=evidence,
        )

    def list_runtime_records(self, record_type: Optional[str] = None) -> list[GovernedRecord]:
        """Return runtime-eligible records, optionally filtered by record_type."""
        return self.build_snapshot().list_records(record_type=record_type)

    def get_runtime_policy(self) -> RuntimeKnowledgePolicy:
        """Return the runtime policy proof for the current repository state."""
        return self.build_snapshot().policy

    def list_approved_alias_enrichments(self, normalized_alias: Optional[str] = None) -> list[AliasEnrichmentRecord]:
        """Return approved alias enrichment records only.

        Candidate enrichments are excluded.  Approved enrichments are metadata
        only; they do not remap display canonical curves.
        """
        records = self.list_runtime_records(record_type="alias_enrichment")
        enrichments = [r for r in records if isinstance(r, AliasEnrichmentRecord)]
        if normalized_alias is None:
            return enrichments
        key = normalized_alias.strip().upper()
        return [r for r in enrichments if r.normalized_alias == key]

    @staticmethod
    def _is_runtime_eligible(record: GovernedRecord) -> bool:
        status = getattr(record, "status", None)
        return isinstance(status, GovernanceStatus) and is_production_eligible(status)

    @staticmethod
    def _count_status(records: Iterable[GovernedRecord], status: GovernanceStatus) -> int:
        return sum(1 for record in records if getattr(record, "status", None) == status)

    def _evidence_for_records(self, records: Iterable[GovernedRecord]) -> list[EvidenceRecord]:
        evidence_ids: set[str] = set()
        for record in records:
            for evidence_id in getattr(record, "evidence_refs", []) or []:
                if evidence_id:
                    evidence_ids.add(evidence_id)
        evidence: list[EvidenceRecord] = []
        for evidence_id in sorted(evidence_ids):
            item = self._repository.get_evidence_by_id(evidence_id)
            if item is not None:
                evidence.append(item)
        return evidence
