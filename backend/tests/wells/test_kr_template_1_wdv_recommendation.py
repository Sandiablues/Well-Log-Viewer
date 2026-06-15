"""KR-TEMPLATE-1 tests — backend-owned WDV template recommendation contract."""

from __future__ import annotations

from pathlib import Path

from app.knowledge.alias_enrichment_models import AliasEnrichmentRecord
from app.knowledge.governance import GovernanceStatus
from app.knowledge.managed_repository import ManagedKRRepository
from app.knowledge.runtime_classification_service import RuntimeCurveClassificationService
from app.knowledge.runtime_resolver import ApprovedKnowledgeRuntimeResolver
from app.wells.las_import_service import (
    LasImportService,
    LasWdvTemplateRecommendation,
    LasWdvTemplateTrackRecommendation,
)
from app.wells.models import CurveMetadata


def _repo(tmp_path: Path) -> ManagedKRRepository:
    return ManagedKRRepository(storage_path=tmp_path / "kr_template_1.json")


def _las_service(repo: ManagedKRRepository) -> LasImportService:
    classifier = RuntimeCurveClassificationService(ApprovedKnowledgeRuntimeResolver(repo))
    return LasImportService(classification_service=classifier)


class TestLasWdvTemplateRecommendation:
    def test_auto_build_recommends_triple_combo_without_frontend_population(self, tmp_path: Path) -> None:
        service = _las_service(_repo(tmp_path))

        result = service.classify_curve_metadata(
            [
                CurveMetadata(mnemonic="GR", unit="GAPI", description="Gamma Ray"),
                CurveMetadata(mnemonic="ILD", unit="OHMM", description="Deep induction"),
                CurveMetadata(mnemonic="RHOB", unit="G/C3", description="Bulk Density"),
            ]
        )

        recommendation = result.wdv_template_recommendation()

        assert isinstance(recommendation, LasWdvTemplateRecommendation)
        assert recommendation.template_id == "triple_combo"
        assert recommendation.template_name == "Triple Combo"
        assert recommendation.recommendation_mode == "auto_build"
        assert recommendation.available_curve_count == 3
        assert recommendation.selected_curve_count == 3
        assert recommendation.has_recommendation is True
        assert recommendation.unresolved_mnemonics == []
        assert recommendation.knowledge_policy["candidate_records_used"] is False

        assert [track.track_id for track in recommendation.tracks] == [
            "gamma_ray",
            "resistivity",
            "porosity_density",
        ]
        assert all(isinstance(track, LasWdvTemplateTrackRecommendation) for track in recommendation.tracks)
        assert recommendation.tracks[0].curve_mnemonics == ["GR"]
        assert recommendation.tracks[1].curve_mnemonics == ["ILD"]
        assert recommendation.tracks[2].curve_mnemonics == ["RHOB"]

    def test_build_from_selected_filters_inventory_but_preserves_backend_contract(self, tmp_path: Path) -> None:
        service = _las_service(_repo(tmp_path))

        result = service.classify_curve_metadata(
            [
                CurveMetadata(mnemonic="GR", unit="GAPI", description="Gamma Ray"),
                CurveMetadata(mnemonic="ILD", unit="OHMM", description="Deep induction"),
                CurveMetadata(mnemonic="RHOB", unit="G/C3", description="Bulk Density"),
            ]
        )

        payload = result.wdv_template_recommendation_dict(selected_mnemonics=["GR", "RHOB"])

        assert payload["template_id"] == "curve_inventory"
        assert payload["recommendation_mode"] == "build_from_selected"
        assert payload["available_curve_count"] == 3
        assert payload["selected_curve_count"] == 2
        assert [track["track_id"] for track in payload["tracks"]] == ["gamma_ray", "porosity_density"]
        assert payload["tracks"][0]["curve_mnemonics"] == ["GR"]
        assert payload["tracks"][1]["curve_mnemonics"] == ["RHOB"]
        assert payload["knowledge_policy"]["candidate_records_used"] is False

    def test_unknown_curves_are_reported_without_generating_unknown_tracks(self, tmp_path: Path) -> None:
        service = _las_service(_repo(tmp_path))

        result = service.classify_curve_metadata(
            [
                CurveMetadata(mnemonic="GR", unit="GAPI", description="Gamma Ray"),
                CurveMetadata(mnemonic="NO_SUCH", unit="unitless", description="Unknown curve"),
            ]
        )

        payload = result.wdv_template_recommendation_dict()

        assert payload["template_id"] == "curve_inventory"
        assert payload["selected_curve_count"] == 2
        assert [track["track_id"] for track in payload["tracks"]] == ["gamma_ray"]
        assert payload["unresolved_mnemonics"] == ["NO_SUCH"]
        assert payload["warnings"] == ["Unresolved curves require review before template automation."]
        assert payload["knowledge_policy"]["candidate_records_used"] is False

    def test_candidate_alias_enrichment_does_not_influence_template_runtime_truth(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo._add_record(
            AliasEnrichmentRecord(
                record_id="candidate_ild_template_enrichment",
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

        payload = result.wdv_template_recommendation_dict()

        assert payload["template_id"] == "curve_inventory"
        assert payload["tracks"] == [
            {
                "track_id": "resistivity",
                "label": "Resistivity",
                "curve_mnemonics": ["ILD"],
                "canonical_curve_ids": ["deep_resistivity"],
                "reason": "Matched approved runtime curve classification.",
            }
        ]
        assert payload["knowledge_policy"]["candidate_records_used"] is False
        assert payload["knowledge_policy"]["excluded_candidate_count"] >= 1
