"""KR-LAS-1 tests — classify LAS curve metadata through approved-only KR."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.knowledge.alias_enrichment_models import AliasEnrichmentRecord
from app.knowledge.governance import GovernanceStatus
from app.knowledge.managed_repository import ManagedKRRepository
from app.knowledge.runtime_classification_service import RuntimeCurveClassificationService
from app.knowledge.runtime_resolver import ApprovedKnowledgeRuntimeResolver
from app.wells.las_import_service import (
    LasCurveInventoryClassificationResult,
    LasImportError,
    LasImportService,
)
from app.wells.models import CurveMetadata, MsiSourceRef


def _repo(tmp_path: Path) -> ManagedKRRepository:
    return ManagedKRRepository(storage_path=tmp_path / "kr_las_1.json")


def _las_service(repo: ManagedKRRepository) -> LasImportService:
    classifier = RuntimeCurveClassificationService(ApprovedKnowledgeRuntimeResolver(repo))
    return LasImportService(classification_service=classifier)


class TestLasCurveInventoryClassification:
    def test_curve_metadata_classification_preserves_order_and_policy(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        service = _las_service(repo)

        result = service.classify_curve_metadata(
            [
                CurveMetadata(mnemonic="GR", unit="GAPI", description="Gamma Ray"),
                CurveMetadata(mnemonic="NO_SUCH", unit="unitless", description="Unknown curve"),
                CurveMetadata(mnemonic="RHOB", unit="G/C3", description="Bulk Density"),
            ]
        )

        assert isinstance(result, LasCurveInventoryClassificationResult)
        assert result.curve_count == 3
        assert result.resolved_count == 2
        assert result.unknown_count == 1
        assert result.review_required_count == 1
        assert result.knowledge_policy["runtime_knowledge_scope"] == "seed_plus_approved"
        assert result.knowledge_policy["candidate_records_used"] is False

        classifications = result.classification_batch.classifications
        assert [item.source_curve_index for item in classifications] == [0, 1, 2]
        assert [item.source_mnemonic for item in classifications] == ["GR", "NO_SUCH", "RHOB"]
        assert classifications[0].canonical_curve_id == "gamma_ray"
        assert classifications[1].status == "unknown"
        assert classifications[1].requires_review is True
        assert classifications[2].canonical_curve_id == "bulk_density"

    def test_candidate_alias_enrichment_is_not_used_for_las_curve_inventory(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo._add_record(
            AliasEnrichmentRecord(
                record_id="candidate_ild_las_enrichment",
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
        service = _las_service(repo)

        result = service.classify_curve_metadata(
            [CurveMetadata(mnemonic="ILD", unit="OHMM", description="Deep induction")]
        )
        classification = result.classification_batch.classifications[0]

        assert classification.status == "resolved"
        assert classification.canonical_curve_id == "deep_resistivity"
        assert classification.technical_curve_id is None
        assert classification.knowledge_policy["excluded_candidate_count"] >= 1
        assert classification.knowledge_policy["candidate_records_used"] is False

    def test_approved_alias_enrichment_is_attached_as_metadata_only(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo._add_record(
            AliasEnrichmentRecord(
                record_id="approved_ild_las_enrichment",
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
        service = _las_service(repo)

        result = service.classify_curve_metadata(
            [CurveMetadata(mnemonic="ILD", unit="OHMM", description="Deep induction")]
        )
        classification = result.classification_batch.classifications[0]

        assert classification.status == "resolved"
        assert classification.canonical_curve_id == "deep_resistivity"
        assert classification.technical_curve_id == "deep_induction_resistivity"
        assert classification.measurement_family == "induction"
        assert classification.measurement_depth == "deep"
        assert classification.tool_family == "induction_resistivity"
        assert classification.knowledge_policy["candidate_records_used"] is False

    def test_result_contract_is_serializable_and_pairs_metadata_with_classification(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        service = _las_service(repo)

        result = service.classify_curve_metadata(
            [CurveMetadata(mnemonic="GR", unit="GAPI", description="Gamma Ray", null_value=-999.25)]
        )
        payload = result.as_dict()

        assert payload["curve_count"] == 1
        assert payload["knowledge_policy"]["runtime_knowledge_scope"] == "seed_plus_approved"
        assert payload["curves"][0]["metadata"]["mnemonic"] == "GR"
        assert payload["curves"][0]["metadata"]["null_value"] == -999.25
        assert payload["curves"][0]["classification"]["canonical_curve_id"] == "gamma_ray"
        assert payload["curves"][0]["classification"]["knowledge_policy"]["candidate_records_used"] is False

    def test_none_curve_metadata_is_rejected(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        service = _las_service(repo)

        with pytest.raises(LasImportError):
            service.classify_curve_metadata(None)  # type: ignore[arg-type]

    def test_las_parsing_methods_remain_deferred(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        service = _las_service(repo)
        source_ref = MsiSourceRef(source_id="src-001", filename="test.las")

        with pytest.raises(NotImplementedError):
            service.import_from_path("/tmp/test.las", source_ref)
        with pytest.raises(NotImplementedError):
            service.import_from_bytes(b"", source_ref)
