"""KR-QAQC-1 tests — backend-owned curve inventory QAQC summary."""

from __future__ import annotations

from pathlib import Path

from backend.app.knowledge.alias_enrichment_models import AliasEnrichmentRecord
from backend.app.knowledge.governance import GovernanceStatus
from backend.app.knowledge.managed_repository import ManagedKRRepository
from backend.app.knowledge.runtime_classification_service import RuntimeCurveClassificationService
from backend.app.knowledge.runtime_resolver import ApprovedKnowledgeRuntimeResolver
from backend.app.wells.las_import_service import (
    LasCurveInventoryQaqcSummary,
    LasImportService,
)
from backend.app.wells.models import CurveMetadata


def _repo(tmp_path: Path) -> ManagedKRRepository:
    return ManagedKRRepository(storage_path=tmp_path / "kr_qaqc_1.json")


def _las_service(repo: ManagedKRRepository) -> LasImportService:
    classifier = RuntimeCurveClassificationService(ApprovedKnowledgeRuntimeResolver(repo))
    return LasImportService(classification_service=classifier)


class TestLasCurveInventoryQaqcSummary:
    def test_qaqc_summary_flags_unknown_review_unit_duplicate_and_template_gaps(self, tmp_path: Path) -> None:
        service = _las_service(_repo(tmp_path))

        result = service.classify_curve_metadata(
            [
                CurveMetadata(mnemonic="GR", unit="GAPI", description="Gamma Ray"),
                CurveMetadata(mnemonic="GR", unit="GAPI", description="Duplicate Gamma Ray"),
                CurveMetadata(mnemonic="RHOB", unit="", description="Bulk Density without unit"),
                CurveMetadata(mnemonic="NO_SUCH", unit="unitless", description="Unknown curve"),
            ]
        )

        summary = result.qaqc_summary()
        payload = result.qaqc_summary_dict()

        assert isinstance(summary, LasCurveInventoryQaqcSummary)
        assert payload["curve_count"] == 4
        assert payload["has_issues"] is True
        assert payload["has_review_blockers"] is True
        assert payload["unknown_mnemonics"] == ["NO_SUCH"]
        assert payload["review_required_mnemonics"] == ["NO_SUCH"]
        assert payload["duplicate_mnemonics"] == ["GR"]
        assert payload["unit_gap_mnemonics"] == ["RHOB"]
        assert payload["template_gap_groups"] == ["resistivity"]
        assert payload["knowledge_policy"]["candidate_records_used"] is False

        issue_types = {issue["issue_type"] for issue in payload["issues"]}
        assert "unknown_curve" in issue_types
        assert "classification_review_required" in issue_types
        assert "duplicate_mnemonic" in issue_types
        assert "duplicate_curve_category" in issue_types
        assert "unit_gap" in issue_types
        assert "template_coverage_gap" in issue_types

    def test_duplicate_curve_category_is_reported_without_blocking_review(self, tmp_path: Path) -> None:
        service = _las_service(_repo(tmp_path))

        result = service.classify_curve_metadata(
            [
                CurveMetadata(mnemonic="ILD", unit="OHMM", description="Deep induction"),
                CurveMetadata(mnemonic="LLD", unit="OHMM", description="Deep laterolog"),
                CurveMetadata(mnemonic="GR", unit="GAPI", description="Gamma Ray"),
                CurveMetadata(mnemonic="RHOB", unit="G/C3", description="Bulk Density"),
            ]
        )

        payload = result.qaqc_summary_dict()

        assert payload["has_review_blockers"] is False
        assert payload["duplicate_mnemonics"] == []
        assert payload["duplicate_canonical_curve_ids"] == ["deep_resistivity"]
        duplicate_issue = next(
            issue for issue in payload["issues"]
            if issue["issue_type"] == "duplicate_curve_category"
        )
        assert duplicate_issue["canonical_curve_id"] == "deep_resistivity"
        assert duplicate_issue["mnemonics"] == ["ILD", "LLD"]
        assert duplicate_issue["severity"] == "info"

    def test_clean_triple_combo_has_no_qaqc_issues(self, tmp_path: Path) -> None:
        service = _las_service(_repo(tmp_path))

        result = service.classify_curve_metadata(
            [
                CurveMetadata(mnemonic="GR", unit="GAPI", description="Gamma Ray"),
                CurveMetadata(mnemonic="ILD", unit="OHMM", description="Deep induction"),
                CurveMetadata(mnemonic="RHOB", unit="G/C3", description="Bulk Density"),
            ]
        )

        payload = result.qaqc_summary_dict()

        assert payload["issue_count"] == 0
        assert payload["has_issues"] is False
        assert payload["has_review_blockers"] is False
        assert payload["warnings"] == []
        assert payload["template_gap_groups"] == []
        assert payload["knowledge_policy"]["candidate_records_used"] is False

    def test_build_from_selected_template_gap_is_backend_owned_not_frontend_inferred(self, tmp_path: Path) -> None:
        service = _las_service(_repo(tmp_path))

        result = service.classify_curve_metadata(
            [
                CurveMetadata(mnemonic="GR", unit="GAPI", description="Gamma Ray"),
                CurveMetadata(mnemonic="ILD", unit="OHMM", description="Deep induction"),
            ]
        )

        payload = result.qaqc_summary_dict()

        assert payload["template_gap_groups"] == ["porosity_density"]
        assert any(
            issue["issue_type"] == "template_coverage_gap"
            and issue["template_group"] == "porosity_density"
            for issue in payload["issues"]
        )
        assert "Standard WDV template coverage is incomplete for this curve inventory." in payload["warnings"]

    def test_candidate_alias_enrichment_does_not_enter_qaqc_runtime_truth(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo._add_record(
            AliasEnrichmentRecord(
                record_id="candidate_ild_qaqc_enrichment",
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

        payload = result.qaqc_summary_dict()

        assert payload["knowledge_policy"]["candidate_records_used"] is False
        assert payload["knowledge_policy"]["excluded_candidate_count"] >= 1
        assert payload["duplicate_canonical_curve_ids"] == []
        assert payload["unknown_mnemonics"] == []
