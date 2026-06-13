"""KR-MDP-1-R3 tests — backend-owned MDP curve classification summary."""

from __future__ import annotations

from pathlib import Path

from backend.app.knowledge.alias_enrichment_models import AliasEnrichmentRecord
from backend.app.knowledge.governance import GovernanceStatus
from backend.app.knowledge.managed_repository import ManagedKRRepository
from backend.app.knowledge.runtime_classification_service import RuntimeCurveClassificationService
from backend.app.knowledge.runtime_resolver import ApprovedKnowledgeRuntimeResolver
from backend.app.wells.las_import_service import (
    LasImportService,
    LasMdpCurveClassificationSummary,
)
from backend.app.wells.models import CurveMetadata


def _repo(tmp_path: Path) -> ManagedKRRepository:
    return ManagedKRRepository(storage_path=tmp_path / "kr_mdp_1_r3.json")


def _las_service(repo: ManagedKRRepository) -> LasImportService:
    classifier = RuntimeCurveClassificationService(ApprovedKnowledgeRuntimeResolver(repo))
    return LasImportService(classification_service=classifier)


class TestLasMdpCurveClassificationSummary:
    def test_mdp_summary_contract_counts_and_groups_classified_curves(self, tmp_path: Path) -> None:
        service = _las_service(_repo(tmp_path))

        result = service.classify_curve_metadata(
            [
                CurveMetadata(mnemonic="GR", unit="GAPI", description="Gamma Ray"),
                CurveMetadata(mnemonic="NO_SUCH", unit="unitless", description="Unknown curve"),
                CurveMetadata(mnemonic="RHOB", unit="G/C3", description="Bulk Density"),
            ]
        )

        summary = result.mdp_summary()

        assert isinstance(summary, LasMdpCurveClassificationSummary)
        assert summary.curve_count == 3
        assert summary.resolved_count == 2
        assert summary.unknown_count == 1
        assert summary.review_required_count == 1
        assert summary.has_unknown_curves is True
        assert summary.has_review_required_curves is True
        assert summary.display_group_counts["gamma_ray"] == 1
        assert summary.display_group_counts["bulk_density"] == 1
        assert summary.display_group_counts["unknown"] == 1
        assert summary.unknown_mnemonics == ["NO_SUCH"]
        assert summary.review_required_mnemonics == ["NO_SUCH"]
        assert summary.knowledge_policy["runtime_knowledge_scope"] == "seed_plus_approved"
        assert summary.knowledge_policy["candidate_records_used"] is False

    def test_mdp_summary_dict_is_serializable_and_preserves_curve_order(self, tmp_path: Path) -> None:
        service = _las_service(_repo(tmp_path))

        result = service.classify_curve_metadata(
            [
                CurveMetadata(mnemonic="GR", unit="GAPI", description="Gamma Ray"),
                CurveMetadata(mnemonic="RHOB", unit="G/C3", description="Bulk Density"),
            ]
        )

        payload = result.mdp_summary_dict()

        assert payload["curve_count"] == 2
        assert payload["unknown_count"] == 0
        assert payload["has_unknown_curves"] is False
        assert payload["has_review_required_curves"] is False
        assert [curve["mnemonic"] for curve in payload["curves"]] == ["GR", "RHOB"]
        assert payload["curves"][0]["canonical_curve_id"] == "gamma_ray"
        assert payload["curves"][1]["canonical_curve_id"] == "bulk_density"
        assert payload["knowledge_policy"]["candidate_records_used"] is False

    def test_approved_alias_enrichment_appears_as_technical_metadata_only(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo._add_record(
            AliasEnrichmentRecord(
                record_id="approved_ild_mdp_enrichment",
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

        payload = result.mdp_summary_dict()

        assert payload["curve_count"] == 1
        assert payload["technical_curve_count"] == 1
        assert payload["display_group_counts"] == {"deep_resistivity": 1}
        assert payload["curves"][0]["canonical_curve_id"] == "deep_resistivity"
        assert payload["curves"][0]["technical_curve_id"] == "deep_induction_resistivity"
        assert payload["curves"][0]["measurement_family"] == "induction"
        assert payload["curves"][0]["measurement_depth"] == "deep"
        assert payload["curves"][0]["tool_family"] == "induction_resistivity"
        assert payload["knowledge_policy"]["candidate_records_used"] is False

    def test_candidate_alias_enrichment_does_not_enter_mdp_summary_runtime_truth(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo._add_record(
            AliasEnrichmentRecord(
                record_id="candidate_ild_mdp_enrichment",
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

        payload = result.mdp_summary_dict()

        assert payload["curve_count"] == 1
        assert payload["technical_curve_count"] == 0
        assert payload["display_group_counts"] == {"deep_resistivity": 1}
        assert payload["curves"][0]["canonical_curve_id"] == "deep_resistivity"
        assert payload["curves"][0]["technical_curve_id"] is None
        assert payload["knowledge_policy"]["candidate_records_used"] is False
        assert payload["knowledge_policy"]["excluded_candidate_count"] >= 1
