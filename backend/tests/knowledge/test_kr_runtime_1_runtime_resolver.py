"""Tests for KR-RUNTIME-1 approved-only runtime resolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.knowledge.alias_enrichment_models import AliasEnrichmentRecord
from backend.app.knowledge.governance import GovernanceStatus
from backend.app.knowledge.managed_models import AliasRecord, CurveDefinitionRecord, EvidenceRecord
from backend.app.knowledge.managed_repository import ManagedKRRepository
from backend.app.knowledge.runtime_resolver import (
    ApprovedKnowledgeRuntimeResolver,
    KR_RUNTIME_1_VERSION,
    RUNTIME_SCOPE_SEED_PLUS_APPROVED,
)


@pytest.fixture
def repo(tmp_path: Path) -> ManagedKRRepository:
    return ManagedKRRepository(storage_path=tmp_path / "runtime_kr.json")


@pytest.fixture
def resolver(repo: ManagedKRRepository) -> ApprovedKnowledgeRuntimeResolver:
    return ApprovedKnowledgeRuntimeResolver(repo)


def _candidate_alias(record_id: str, alias: str = "ZZZ") -> AliasRecord:
    return AliasRecord(
        record_id=record_id,
        alias=alias,
        normalized_alias=alias.strip().upper(),
        canonical_curve_id="candidate_curve",
        status=GovernanceStatus.CANDIDATE,
    )


def _approved_alias(record_id: str, alias: str = "APP") -> AliasRecord:
    return AliasRecord(
        record_id=record_id,
        alias=alias,
        normalized_alias=alias.strip().upper(),
        canonical_curve_id="approved_curve",
        status=GovernanceStatus.APPROVED,
        evidence_refs=["ev_runtime_approved"],
    )


def _curve_def(record_id: str, canonical: str, status: GovernanceStatus) -> CurveDefinitionRecord:
    return CurveDefinitionRecord(
        record_id=record_id,
        canonical_curve_id=canonical,
        display_name=canonical.replace("_", " ").title(),
        family="runtime_test",
        product_group="open_hole_logs",
        status=status,
    )


def _ild_enrichment(status: GovernanceStatus) -> AliasEnrichmentRecord:
    return AliasEnrichmentRecord(
        record_id=f"runtime_ild_{status.value}",
        alias="ILD",
        normalized_alias="ILD",
        display_canonical_curve_id="deep_resistivity",
        technical_curve_id="deep_induction_resistivity",
        technical_display_name="Deep Induction Resistivity",
        parent_canonical_curve_id="deep_resistivity",
        measurement_family="induction",
        measurement_depth="deep",
        tool_family="induction_resistivity",
        status=status,
    )


class TestRuntimePolicy:
    def test_snapshot_declares_approved_only_runtime_scope(
        self, resolver: ApprovedKnowledgeRuntimeResolver
    ) -> None:
        snapshot = resolver.build_snapshot()

        assert snapshot.kr_version == KR_RUNTIME_1_VERSION
        assert snapshot.policy.runtime_knowledge_scope == RUNTIME_SCOPE_SEED_PLUS_APPROVED
        assert snapshot.policy.candidate_records_used is False
        assert snapshot.policy.rejected_records_used is False
        assert snapshot.policy.deprecated_records_used is False
        assert snapshot.policy.seed_record_count > 0
        assert snapshot.policy.approved_record_count == 0
        assert snapshot.record_count == snapshot.policy.production_record_count

    def test_snapshot_summary_is_serializable(
        self, resolver: ApprovedKnowledgeRuntimeResolver
    ) -> None:
        summary = resolver.build_snapshot().as_summary_dict()

        assert summary["kr_version"] == KR_RUNTIME_1_VERSION
        assert summary["policy"]["runtime_knowledge_scope"] == RUNTIME_SCOPE_SEED_PLUS_APPROVED
        assert summary["policy"]["candidate_records_used"] is False
        assert "type_summary" in summary
        assert "status_summary" in summary


class TestRuntimeFiltering:
    def test_candidate_records_are_excluded(
        self, repo: ManagedKRRepository, resolver: ApprovedKnowledgeRuntimeResolver
    ) -> None:
        candidate = _candidate_alias("runtime_candidate_alias", "CAND")
        repo._add_record(candidate)

        snapshot = resolver.build_snapshot()
        runtime_ids = {r.record_id for r in snapshot.records}

        assert candidate.record_id not in runtime_ids
        assert snapshot.policy.excluded_candidate_count == 1
        assert snapshot.policy.candidate_records_used is False

    def test_approved_records_are_included(
        self, repo: ManagedKRRepository, resolver: ApprovedKnowledgeRuntimeResolver
    ) -> None:
        evidence = EvidenceRecord(
            evidence_id="ev_runtime_approved",
            source_type="unit_test",
            source_label="Runtime approved evidence",
        )
        approved = _approved_alias("runtime_approved_alias", "APP")
        repo._add_evidence(evidence)
        repo._add_record(approved)

        snapshot = resolver.build_snapshot()
        runtime_ids = {r.record_id for r in snapshot.records}
        evidence_ids = {e.evidence_id for e in snapshot.evidence}

        assert approved.record_id in runtime_ids
        assert "ev_runtime_approved" in evidence_ids
        assert snapshot.policy.approved_record_count == 1

    def test_rejected_and_deprecated_records_are_excluded(
        self, repo: ManagedKRRepository, resolver: ApprovedKnowledgeRuntimeResolver
    ) -> None:
        rejected = _curve_def("runtime_rejected_curve", "runtime_rejected", GovernanceStatus.REJECTED)
        deprecated = _curve_def("runtime_deprecated_curve", "runtime_deprecated", GovernanceStatus.DEPRECATED)
        repo._add_record(rejected)
        repo._add_record(deprecated)

        snapshot = resolver.build_snapshot()
        runtime_ids = {r.record_id for r in snapshot.records}

        assert rejected.record_id not in runtime_ids
        assert deprecated.record_id not in runtime_ids
        assert snapshot.policy.excluded_rejected_count == 1
        assert snapshot.policy.excluded_deprecated_count == 1
        assert snapshot.policy.rejected_records_used is False
        assert snapshot.policy.deprecated_records_used is False

    def test_record_type_filter_uses_runtime_eligible_records_only(
        self, repo: ManagedKRRepository, resolver: ApprovedKnowledgeRuntimeResolver
    ) -> None:
        repo._add_record(_candidate_alias("runtime_candidate_alias_filter", "CFILT"))
        repo._add_record(_approved_alias("runtime_approved_alias_filter", "AFILT"))

        aliases = resolver.list_runtime_records(record_type="alias")
        alias_ids = {r.record_id for r in aliases}

        assert "runtime_approved_alias_filter" in alias_ids
        assert "runtime_candidate_alias_filter" not in alias_ids


class TestRuntimeAliasEnrichment:
    def test_candidate_alias_enrichment_is_excluded(
        self, repo: ManagedKRRepository, resolver: ApprovedKnowledgeRuntimeResolver
    ) -> None:
        candidate = _ild_enrichment(GovernanceStatus.CANDIDATE)
        repo._add_record(candidate)

        enrichments = resolver.list_approved_alias_enrichments("ILD")

        assert enrichments == []
        assert resolver.build_snapshot().policy.excluded_candidate_count == 1

    def test_approved_alias_enrichment_is_runtime_metadata(
        self, repo: ManagedKRRepository, resolver: ApprovedKnowledgeRuntimeResolver
    ) -> None:
        approved = _ild_enrichment(GovernanceStatus.APPROVED)
        repo._add_record(approved)

        enrichments = resolver.list_approved_alias_enrichments("ILD")

        assert len(enrichments) == 1
        enrichment = enrichments[0]
        assert enrichment.display_canonical_curve_id == "deep_resistivity"
        assert enrichment.technical_curve_id == "deep_induction_resistivity"
        assert enrichment.status == GovernanceStatus.APPROVED

    def test_kr_data_1r_candidate_enrichments_do_not_enter_runtime(
        self, repo: ManagedKRRepository, resolver: ApprovedKnowledgeRuntimeResolver
    ) -> None:
        for alias, technical in [
            ("ILD", "deep_induction_resistivity"),
            ("ILM", "medium_induction_resistivity"),
            ("LLD", "deep_laterolog_resistivity"),
            ("LLS", "shallow_laterolog_resistivity"),
        ]:
            repo._add_record(
                AliasEnrichmentRecord(
                    record_id=f"kr_data_1r_{alias}_{technical}",
                    alias=alias,
                    normalized_alias=alias,
                    display_canonical_curve_id="deep_resistivity" if alias in {"ILD", "LLD"} else "shallow_resistivity",
                    technical_curve_id=technical,
                    technical_display_name=technical.replace("_", " ").title(),
                    parent_canonical_curve_id="deep_resistivity" if alias in {"ILD", "LLD"} else "shallow_resistivity",
                    status=GovernanceStatus.CANDIDATE,
                )
            )

        snapshot = resolver.build_snapshot()
        type_summary = snapshot.type_summary()

        assert type_summary.get("alias_enrichment", 0) == 0
        assert snapshot.policy.excluded_candidate_count == 4
        assert snapshot.policy.candidate_records_used is False
