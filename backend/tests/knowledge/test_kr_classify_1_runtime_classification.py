from __future__ import annotations

from pathlib import Path

from app.knowledge.alias_enrichment_models import AliasEnrichmentRecord
from app.knowledge.governance import GovernanceStatus
from app.knowledge.managed_models import AliasRecord, CurveDefinitionRecord
from app.knowledge.managed_repository import ManagedKRRepository
from app.knowledge.runtime_classification_service import (
    KR_CLASSIFY_1_VERSION,
    CurveClassificationInput,
    RuntimeCurveClassificationService,
)
from app.knowledge.runtime_resolver import ApprovedKnowledgeRuntimeResolver


def _repo(tmp_path: Path) -> ManagedKRRepository:
    return ManagedKRRepository(storage_path=tmp_path / "kr_classify_1.json")


def _service(repo: ManagedKRRepository) -> RuntimeCurveClassificationService:
    return RuntimeCurveClassificationService(ApprovedKnowledgeRuntimeResolver(repo))


def test_seed_standard_mnemonic_resolves_with_runtime_policy(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    service = _service(repo)

    result = service.classify_curve(
        CurveClassificationInput(
            curve_id="c_gr",
            source_mnemonic="GR",
            unit="API",
            source_curve_index=0,
        )
    )

    assert result.status == "resolved"
    assert result.resolved is True
    assert result.requires_review is False
    assert result.canonical_curve_id == "gamma_ray"
    assert result.product_group is not None
    assert result.knowledge_policy["runtime_knowledge_scope"] == "seed_plus_approved"
    assert result.knowledge_policy["candidate_records_used"] is False
    assert result.knowledge_policy["rejected_records_used"] is False
    assert result.knowledge_policy["deprecated_records_used"] is False


def test_unknown_mnemonic_returns_review_required_unknown(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    service = _service(repo)

    result = service.classify_curve(CurveClassificationInput(source_mnemonic="NO_SUCH_CURVE"))

    assert result.status == "unknown"
    assert result.resolved is False
    assert result.requires_review is True
    assert result.canonical_curve_id is None
    assert result.technical_curve_id is None
    assert result.knowledge_policy["candidate_records_used"] is False
    assert result.warnings == ["No approved runtime knowledge match found"]


def test_candidate_alias_is_not_runtime_classification_knowledge(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo._add_record(
        CurveDefinitionRecord(
            record_id="candidate_def_special_curve",
            canonical_curve_id="special_candidate_curve",
            display_name="Special Candidate Curve",
            family="test",
            product_group="test",
            status=GovernanceStatus.CANDIDATE,
        )
    )
    repo._add_record(
        AliasRecord(
            record_id="candidate_alias_special_curve",
            alias="SPCAND",
            canonical_curve_id="special_candidate_curve",
            status=GovernanceStatus.CANDIDATE,
        )
    )

    service = _service(repo)
    result = service.classify_curve(CurveClassificationInput(source_mnemonic="SPCAND"))

    assert result.status == "unknown"
    assert result.resolved is False
    assert result.canonical_curve_id is None
    assert result.knowledge_policy["excluded_candidate_count"] >= 2
    assert result.knowledge_policy["candidate_records_used"] is False


def test_approved_alias_and_curve_definition_are_runtime_classification_knowledge(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo._add_record(
        CurveDefinitionRecord(
            record_id="approved_def_special_curve",
            canonical_curve_id="approved_special_curve",
            display_name="Approved Special Curve",
            family="approved_family",
            product_group="approved_group",
            product_subgroup="approved_subgroup",
            default_unit="unitless",
            status=GovernanceStatus.APPROVED,
        )
    )
    repo._add_record(
        AliasRecord(
            record_id="approved_alias_special_curve",
            alias="APPCURVE",
            canonical_curve_id="approved_special_curve",
            status=GovernanceStatus.APPROVED,
            confidence=0.87,
        )
    )

    service = _service(repo)
    result = service.classify_curve(CurveClassificationInput(source_mnemonic="APPCURVE"))

    assert result.status == "resolved"
    assert result.resolved is True
    assert result.canonical_curve_id == "approved_special_curve"
    assert result.display_name == "Approved Special Curve"
    assert result.product_group == "approved_group"
    assert result.product_subgroup == "approved_subgroup"
    assert result.default_unit == "unitless"
    assert result.confidence == 0.87
    assert result.knowledge_record_id == "approved_alias_special_curve"
    assert result.knowledge_policy["approved_record_count"] >= 2


def test_candidate_alias_enrichment_does_not_attach_technical_subtype(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo._add_record(
        AliasEnrichmentRecord(
            record_id="candidate_ild_enrichment",
            alias="ILD",
            normalized_alias="ILD",
            display_canonical_curve_id="deep_resistivity",
            technical_curve_id="deep_induction_resistivity",
            technical_display_name="Deep Induction Resistivity",
            parent_canonical_curve_id="deep_resistivity",
            measurement_family="induction",
            measurement_depth="deep",
            tool_family="induction_resistivity",
            status=GovernanceStatus.CANDIDATE,
        )
    )

    service = _service(repo)
    result = service.classify_curve(CurveClassificationInput(source_mnemonic="ILD"))

    assert result.status == "resolved"
    assert result.canonical_curve_id == "deep_resistivity"
    assert result.technical_curve_id is None
    assert result.technical_display_name is None
    assert result.knowledge_policy["excluded_candidate_count"] >= 1
    assert result.knowledge_policy["candidate_records_used"] is False


def test_approved_alias_enrichment_attaches_metadata_without_remapping_display_canonical(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo._add_record(
        AliasEnrichmentRecord(
            record_id="approved_ild_enrichment",
            alias="ILD",
            normalized_alias="ILD",
            display_canonical_curve_id="deep_resistivity",
            technical_curve_id="deep_induction_resistivity",
            technical_display_name="Deep Induction Resistivity",
            parent_canonical_curve_id="deep_resistivity",
            measurement_family="induction",
            measurement_depth="deep",
            tool_family="induction_resistivity",
            status=GovernanceStatus.APPROVED,
        )
    )

    service = _service(repo)
    result = service.classify_curve(CurveClassificationInput(source_mnemonic="ILD"))

    assert result.status == "resolved"
    assert result.canonical_curve_id == "deep_resistivity"
    assert result.technical_curve_id == "deep_induction_resistivity"
    assert result.technical_display_name == "Deep Induction Resistivity"
    assert result.measurement_family == "induction"
    assert result.measurement_depth == "deep"
    assert result.tool_family == "induction_resistivity"
    assert result.knowledge_policy["approved_record_count"] >= 1
    assert result.knowledge_policy["candidate_records_used"] is False


def test_batch_classification_preserves_order_and_counts(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    service = _service(repo)

    batch = service.classify_curves(
        [
            CurveClassificationInput(curve_id="c1", source_mnemonic="GR", source_curve_index=0),
            CurveClassificationInput(curve_id="c2", source_mnemonic="NO_SUCH", source_curve_index=1),
            CurveClassificationInput(curve_id="c3", source_mnemonic="RHOB", source_curve_index=2),
        ]
    )

    assert batch.classify_version == KR_CLASSIFY_1_VERSION
    assert batch.curve_count == 3
    assert batch.resolved_count == 2
    assert batch.unknown_count == 1
    assert batch.review_required_count == 1
    assert [item.curve_id for item in batch.classifications] == ["c1", "c2", "c3"]
    assert batch.knowledge_policy["runtime_knowledge_scope"] == "seed_plus_approved"
    assert batch.knowledge_policy["candidate_records_used"] is False


def test_result_and_batch_are_serializable_dict_contracts(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    service = _service(repo)

    batch = service.classify_curves([CurveClassificationInput(curve_id="c1", source_mnemonic="GR")])
    payload = batch.as_dict()

    assert payload["classify_version"] == KR_CLASSIFY_1_VERSION
    assert payload["curve_count"] == 1
    assert payload["knowledge_policy"]["runtime_knowledge_scope"] == "seed_plus_approved"
    assert payload["classifications"][0]["source_mnemonic"] == "GR"
    assert payload["classifications"][0]["canonical_curve_id"] == "gamma_ray"
    assert payload["classifications"][0]["knowledge_policy"]["candidate_records_used"] is False
