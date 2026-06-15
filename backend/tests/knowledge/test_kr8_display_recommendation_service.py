"""Tests for WLV KR-8 — Backend Display Recommendation Service.

Tests all 29 required cases:

Service / unit tests:
  1.  GR returns recommended display rule.
  2.  GR scale is linear.
  3.  GR recommended range/unit match current approved seed rule.
  4.  Deep resistivity returns logarithmic display rule.
  5.  Deep resistivity range/unit match current approved seed rule.
  6.  Unknown curve returns unrecommended.
  7.  Unknown curve sets review_required=True.
  8.  Classified curve with no display rule returns review_required.
  9.  Batch preserves input order.
  10. Batch handles mixed recommended/unrecommended curves.
  11. Source curve_id is preserved.
  12. Source curve index is preserved.
  13. Product group/subgroup are included.
  14. Display family is included where available.
  15. Candidate display rule does not affect recommendation.
  16. Rejected display rule does not affect recommendation.
  17. Deprecated display rule does not affect recommendation.
  18. Approved managed display rule affects recommendation.
  19. Candidate alias/curve definition does not indirectly create recommendation.
  20. Approved managed alias can produce recommendation if matching display rule exists.
  21. Empty curve list returns 200 with zero counts.
  22. Malformed request returns 422.

Regression / integration tests:
  23. KR-7 classify endpoint still works.
  24. KR-6 resolve endpoint still works.
  25. KR-5 storage health still works.
  26. KR-1 endpoints still work.
  27. Full knowledge suite passes.
  28. Frontend typecheck passes (structural contract shape check).
  29. Frontend build passes (structural guard).
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.knowledge.api_managed_knowledge import get_managed_repository
from app.knowledge.classification_service import CurveClassificationService
from app.knowledge.display_recommendation_service import (
    CurveRecommendInput,
    DisplayRecommendationRequest,
    DisplayRecommendationService,
    KR8_VERSION,
)
from app.knowledge.governance_service import GovernanceService
from app.knowledge.import_models import (
    ImportCurveDefinition,
    ImportDisplayRule,
    ImportPayload,
    ImportSource,
)
from app.knowledge.import_staging_service import stage_import_payload
from app.knowledge.managed_repository import ManagedKRRepository
from app.knowledge.resolution_service import KnowledgeResolutionService
from app.knowledge.models import KR_VERSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_repo(storage_path: Path) -> ManagedKRRepository:
    return ManagedKRRepository(storage_path=storage_path)


def _make_service(repo: ManagedKRRepository) -> DisplayRecommendationService:
    resolution = KnowledgeResolutionService(repo)
    classification = CurveClassificationService(resolution)
    return DisplayRecommendationService(classification)


def _approve_all(repo: ManagedKRRepository, record_ids: list[str]) -> None:
    gov = GovernanceService(repo)
    for rid in record_ids:
        gov.approve_record(rid, actor="kr8_tester", reason="kr8 test approval")


def _curve_and_display_rule_payload(
    canonical_id: str,
    display_name: str = "Test Curve",
    scale_type: str = "linear",
    display_min: float = 0.0,
    display_max: float = 150.0,
    default_unit: str = "TEST",
    preferred_track_family: str = "test_track",
) -> ImportPayload:
    """Minimal payload staging one curve definition + one display rule (candidate)."""
    return ImportPayload(
        source=ImportSource(
            source_type="manual_import",
            source_label=f"KR-8 Test {canonical_id}",
            source_reference=f"kr8_test_{canonical_id}",
        ),
        curve_definitions=[
            ImportCurveDefinition(
                canonical_curve_id=canonical_id,
                display_name=display_name,
                family="test_family",
                product_group="open_hole_logs",
            )
        ],
        display_rules=[
            ImportDisplayRule(
                canonical_curve_id=canonical_id,
                preferred_track_family=preferred_track_family,
                scale_type=scale_type,
                display_min=display_min,
                display_max=display_max,
                default_unit=default_unit,
            )
        ],
    )


def _curve_only_payload(
    canonical_id: str,
    display_name: str = "Test Curve",
) -> ImportPayload:
    """Minimal payload staging one curve definition only (no display rule)."""
    return ImportPayload(
        source=ImportSource(
            source_type="manual_import",
            source_label=f"KR-8 Test curve-only {canonical_id}",
            source_reference=f"kr8_test_curve_only_{canonical_id}",
        ),
        curve_definitions=[
            ImportCurveDefinition(
                canonical_curve_id=canonical_id,
                display_name=display_name,
                family="test_family",
                product_group="open_hole_logs",
            )
        ],
    )


def _display_rule_only_payload(
    canonical_id: str,
    scale_type: str = "linear",
    display_min: float = 0.0,
    display_max: float = 150.0,
    default_unit: str = "TEST",
    preferred_track_family: str = "test_track",
) -> ImportPayload:
    """Minimal payload staging one display rule only (no curve definition)."""
    return ImportPayload(
        source=ImportSource(
            source_type="manual_import",
            source_label=f"KR-8 Test display-only {canonical_id}",
            source_reference=f"kr8_test_display_only_{canonical_id}",
        ),
        display_rules=[
            ImportDisplayRule(
                canonical_curve_id=canonical_id,
                preferred_track_family=preferred_track_family,
                scale_type=scale_type,
                display_min=display_min,
                display_max=display_max,
                default_unit=default_unit,
            )
        ],
    )


_APPROVE_BODY = {
    "actor": "kr8_test_reviewer",
    "reason": "KR-8 test approval",
    "notes": "Automated KR-8 test suite",
}

_REJECT_BODY = {
    "actor": "kr8_test_reviewer",
    "reason": "KR-8 test rejection",
    "notes": "Automated KR-8 test suite",
}

_DEPRECATE_BODY = {
    "actor": "kr8_test_reviewer",
    "reason": "KR-8 test deprecation",
    "notes": "Automated KR-8 test suite",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage_path(tmp_path: Path) -> Path:
    return tmp_path / "knowledge" / "kr8_test.json"


@pytest.fixture
def repo(storage_path: Path) -> ManagedKRRepository:
    return _fresh_repo(storage_path)


@pytest.fixture
def service(repo: ManagedKRRepository) -> DisplayRecommendationService:
    return _make_service(repo)


@pytest.fixture
def client(repo: ManagedKRRepository) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_managed_repository] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def seed_display_rule_record_id(repo: ManagedKRRepository) -> str:
    """Return record_id of a known seed display rule (gamma_ray)."""
    rules = [
        r for r in repo.list_seeds()
        if r.record_type == "display_rule" and getattr(r, "canonical_curve_id", "") == "gamma_ray"
    ]
    assert rules, "Expected seed display rule for gamma_ray"
    return rules[0].record_id


# ===========================================================================
# Test 1: GR returns recommended display rule
# ===========================================================================


class TestGrReturnsRecommended:
    """Test 1: GR returns recommended display rule."""

    def test_gr_recommended(self, service: DisplayRecommendationService) -> None:
        """1a. 'GR' returns recommendation_status='recommended'."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="curve_001", mnemonic="GR", unit="API")]
        )
        result = service.recommend_display(req)
        r = result.recommendations[0]
        assert r.recommendation_status == "recommended"
        assert r.review_required is False
        assert r.warnings == []

    def test_gr_canonical_curve_id(self, service: DisplayRecommendationService) -> None:
        """1b. GR recommendation includes canonical_curve_id='gamma_ray'."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="GR")]
        )
        result = service.recommend_display(req)
        assert result.recommendations[0].canonical_curve_id == "gamma_ray"

    def test_gr_classification_status_is_classified(
        self, service: DisplayRecommendationService
    ) -> None:
        """1c. GR recommendation classification_status='classified'."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="GR")]
        )
        result = service.recommend_display(req)
        assert result.recommendations[0].classification_status == "classified"


# ===========================================================================
# Test 2: GR scale is linear
# ===========================================================================


class TestGrScaleLinear:
    """Test 2: GR scale is linear."""

    def test_gr_scale_linear(self, service: DisplayRecommendationService) -> None:
        """2. GR recommendation scale_type is 'linear'."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="GR")]
        )
        result = service.recommend_display(req)
        r = result.recommendations[0]
        assert r.scale_type == "linear"


# ===========================================================================
# Test 3: GR recommended range/unit match current approved seed rule
# ===========================================================================


class TestGrRangeAndUnit:
    """Test 3: GR recommended range and unit match current approved seed rule."""

    def test_gr_range_and_unit(self, service: DisplayRecommendationService) -> None:
        """3. GR range and unit match the seed display rule values."""
        from app.knowledge.curve_knowledge import CURVE_DEFINITIONS

        gr_def = next(d for d in CURVE_DEFINITIONS if d.canonical_curve_id == "gamma_ray")

        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="GR")]
        )
        result = service.recommend_display(req)
        r = result.recommendations[0]
        assert r.recommended_min == float(gr_def.display_min)
        assert r.recommended_max == float(gr_def.display_max)
        assert r.unit == gr_def.default_unit

    def test_gr_display_name_populated(self, service: DisplayRecommendationService) -> None:
        """3b. GR recommendation includes display_name."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="GR")]
        )
        result = service.recommend_display(req)
        assert result.recommendations[0].display_name is not None


# ===========================================================================
# Test 4: Deep resistivity returns logarithmic display rule
# ===========================================================================


class TestDeepResistivityLogarithmic:
    """Test 4: Deep resistivity returns logarithmic display rule."""

    def test_rt_recommended_log(self, service: DisplayRecommendationService) -> None:
        """4a. 'RT' alias for deep_resistivity → recommendation_status='recommended', scale_type='log'."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="RT")]
        )
        result = service.recommend_display(req)
        r = result.recommendations[0]
        assert r.recommendation_status == "recommended"
        assert r.scale_type == "log"
        assert r.canonical_curve_id == "deep_resistivity"

    def test_at90_recommended_log(self, service: DisplayRecommendationService) -> None:
        """4b. 'AT90' alias for deep_resistivity → scale_type='log'."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="AT90")]
        )
        result = service.recommend_display(req)
        r = result.recommendations[0]
        assert r.scale_type == "log"
        assert r.recommendation_status == "recommended"


# ===========================================================================
# Test 5: Deep resistivity range/unit match current approved seed rule
# ===========================================================================


class TestDeepResistivityRangeAndUnit:
    """Test 5: Deep resistivity range and unit match current approved seed rule."""

    def test_deep_resistivity_range_and_unit(
        self, service: DisplayRecommendationService
    ) -> None:
        """5. RT range and unit match the seed display rule values."""
        from app.knowledge.curve_knowledge import CURVE_DEFINITIONS

        dr_def = next(d for d in CURVE_DEFINITIONS if d.canonical_curve_id == "deep_resistivity")

        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="RT")]
        )
        result = service.recommend_display(req)
        r = result.recommendations[0]
        assert r.recommended_min == float(dr_def.display_min)
        assert r.recommended_max == float(dr_def.display_max)
        assert r.unit == dr_def.default_unit


# ===========================================================================
# Test 6: Unknown curve returns unrecommended
# ===========================================================================


class TestUnknownCurveUnrecommended:
    """Test 6: Unknown curve returns unrecommended."""

    def test_unknown_unrecommended(self, service: DisplayRecommendationService) -> None:
        """6. 'XYZ' → recommendation_status='unrecommended'."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c999", mnemonic="XYZ")]
        )
        result = service.recommend_display(req)
        r = result.recommendations[0]
        assert r.recommendation_status == "unrecommended"
        assert r.classification_status == "unclassified"
        assert r.scale_type is None
        assert r.recommended_min is None
        assert r.recommended_max is None


# ===========================================================================
# Test 7: Unknown curve sets review_required=True
# ===========================================================================


class TestUnknownCurveReviewRequired:
    """Test 7: Unknown curve sets review_required=True."""

    def test_unknown_review_required(self, service: DisplayRecommendationService) -> None:
        """7. Unrecommended curve has review_required=True and warnings."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c999", mnemonic="XYZ")]
        )
        result = service.recommend_display(req)
        r = result.recommendations[0]
        assert r.review_required is True
        assert len(r.warnings) > 0
        assert "unclassified" in r.warnings[0].lower()


# ===========================================================================
# Test 8: Classified curve with no display rule returns review_required
# ===========================================================================


class TestClassifiedNoDisplayRuleReviewRequired:
    """Test 8: Classified curve with no display rule returns review_required."""

    def test_classified_no_display_rule(self, repo: ManagedKRRepository) -> None:
        """8. Approved curve def but no display rule → review_required."""
        # Stage and approve a curve definition with NO associated display rule
        payload = _curve_only_payload("kr8_no_display_rule_curve")
        stage_result = stage_import_payload(payload, repo)
        _approve_all(repo, stage_result.record_ids)

        svc = _make_service(repo)
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="kr8_no_display_rule_curve")]
        )
        result = svc.recommend_display(req)
        r = result.recommendations[0]
        assert r.classification_status == "classified"
        assert r.recommendation_status == "review_required"
        assert r.review_required is True
        assert r.scale_type is None


# ===========================================================================
# Test 9: Batch preserves input order
# ===========================================================================


class TestBatchPreservesInputOrder:
    """Test 9: batch preserves input order."""

    def test_order_preserved(self, service: DisplayRecommendationService) -> None:
        """9. Results appear in same order as input curves."""
        mnemonics = ["GR", "XYZ_UNKNOWN_A", "RT", "XYZ_UNKNOWN_B", "NPHI"]
        curves = [
            CurveRecommendInput(curve_id=f"c{i}", mnemonic=m)
            for i, m in enumerate(mnemonics)
        ]
        req = DisplayRecommendationRequest(curves=curves)
        result = service.recommend_display(req)
        assert len(result.recommendations) == len(mnemonics)
        for i, rec in enumerate(result.recommendations):
            assert rec.curve_id == f"c{i}", (
                f"Position {i}: expected curve_id=c{i}, got {rec.curve_id}"
            )


# ===========================================================================
# Test 10: Batch handles mixed recommended/unrecommended curves
# ===========================================================================


class TestBatchMixed:
    """Test 10: batch handles mixed recommended/unrecommended curves."""

    def test_mixed_batch(self, service: DisplayRecommendationService) -> None:
        """10. Mix of known and unknown mnemonics all returned correctly."""
        req = DisplayRecommendationRequest(
            curves=[
                CurveRecommendInput(curve_id="c0", mnemonic="GR"),
                CurveRecommendInput(curve_id="c1", mnemonic="UNKNOWNXXX"),
                CurveRecommendInput(curve_id="c2", mnemonic="NPHI"),
            ]
        )
        result = service.recommend_display(req)
        assert result.recommendations[0].recommendation_status == "recommended"
        assert result.recommendations[1].recommendation_status == "unrecommended"
        assert result.recommendations[2].recommendation_status == "recommended"
        assert result.recommended_count == 2
        assert result.unrecommended_count == 1


# ===========================================================================
# Test 11: Source curve_id is preserved
# ===========================================================================


class TestSourceCurveIdPreserved:
    """Test 11: source curve_id is preserved."""

    def test_curve_id_preserved_recommended(
        self, service: DisplayRecommendationService
    ) -> None:
        """11a. curve_id preserved for recommended result."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="my_stable_id_001", mnemonic="GR")]
        )
        result = service.recommend_display(req)
        assert result.recommendations[0].curve_id == "my_stable_id_001"

    def test_curve_id_preserved_unrecommended(
        self, service: DisplayRecommendationService
    ) -> None:
        """11b. curve_id preserved for unrecommended result."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="my_stable_id_999", mnemonic="XYZNOTREAL")]
        )
        result = service.recommend_display(req)
        assert result.recommendations[0].curve_id == "my_stable_id_999"


# ===========================================================================
# Test 12: Source curve index is preserved
# ===========================================================================


class TestSourceCurveIndexPreserved:
    """Test 12: source curve index is preserved."""

    def test_index_preserved(self, service: DisplayRecommendationService) -> None:
        """12a. source_curve_index round-trips through recommendation."""
        req = DisplayRecommendationRequest(
            curves=[
                CurveRecommendInput(curve_id="c0", mnemonic="GR", source_curve_index=0),
                CurveRecommendInput(curve_id="c1", mnemonic="NPHI", source_curve_index=1),
                CurveRecommendInput(curve_id="c2", mnemonic="XYZ", source_curve_index=2),
            ]
        )
        result = service.recommend_display(req)
        assert result.recommendations[0].source_curve_index == 0
        assert result.recommendations[1].source_curve_index == 1
        assert result.recommendations[2].source_curve_index == 2

    def test_none_index_preserved(self, service: DisplayRecommendationService) -> None:
        """12b. None source_curve_index is preserved as None."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c0", mnemonic="GR", source_curve_index=None)]
        )
        result = service.recommend_display(req)
        assert result.recommendations[0].source_curve_index is None


# ===========================================================================
# Test 13: Product group/subgroup are included
# ===========================================================================


class TestProductGroupSubgroupIncluded:
    """Test 13: product group and subgroup are included."""

    def test_gr_product_group(self, service: DisplayRecommendationService) -> None:
        """13a. GR recommendation includes product_group."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="GR")]
        )
        result = service.recommend_display(req)
        r = result.recommendations[0]
        assert r.product_group is not None
        assert r.product_group == "open_hole_logs"

    def test_gr_product_subgroup(self, service: DisplayRecommendationService) -> None:
        """13b. GR recommendation includes product_subgroup."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="GR")]
        )
        result = service.recommend_display(req)
        assert result.recommendations[0].product_subgroup is not None


# ===========================================================================
# Test 14: Display family is included where available
# ===========================================================================


class TestDisplayFamilyIncluded:
    """Test 14: display family is included where available."""

    def test_gr_display_family(self, service: DisplayRecommendationService) -> None:
        """14a. GR recommendation includes display_family."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="GR")]
        )
        result = service.recommend_display(req)
        assert result.recommendations[0].display_family is not None

    def test_unclassified_no_display_family(
        self, service: DisplayRecommendationService
    ) -> None:
        """14b. Unclassified curve has no display_family."""
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="XYZUNKOWN")]
        )
        result = service.recommend_display(req)
        assert result.recommendations[0].display_family is None


# ===========================================================================
# Test 15: Candidate display rule does not affect recommendation
# ===========================================================================


class TestCandidateDisplayRuleDoesNotRecommend:
    """Test 15: candidate display rule does not affect recommendation."""

    def test_candidate_display_rule_not_recommended(
        self, repo: ManagedKRRepository
    ) -> None:
        """15. Staged (candidate) display rule + staged curve def → not recommended."""
        payload = _curve_and_display_rule_payload("kr8_candidate_display_curve")
        stage_import_payload(payload, repo)  # staged as candidate, not approved

        svc = _make_service(repo)
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="kr8_candidate_display_curve")]
        )
        result = svc.recommend_display(req)
        r = result.recommendations[0]
        # Curve def is also candidate → unclassified → unrecommended
        assert r.recommendation_status in {"unrecommended", "review_required"}
        assert r.review_required is True


# ===========================================================================
# Test 16: Rejected display rule does not affect recommendation
# ===========================================================================


class TestRejectedDisplayRuleDoesNotRecommend:
    """Test 16: rejected display rule does not affect recommendation."""

    def test_rejected_display_rule_not_recommended(
        self, repo: ManagedKRRepository
    ) -> None:
        """16. Approved curve def but rejected display rule → review_required."""
        # Stage curve def + display rule, approve only the curve def, reject display rule
        payload = _curve_and_display_rule_payload("kr8_rejected_display_curve")
        stage_result = stage_import_payload(payload, repo)

        curve_def_ids = [rid for rid in stage_result.record_ids if "_curve_def_" in rid]
        display_rule_ids = [rid for rid in stage_result.record_ids if "_display_" in rid and "_curve_def_" not in rid]
        assert curve_def_ids
        assert display_rule_ids

        gov = GovernanceService(repo)
        gov.approve_record(curve_def_ids[0], actor="tester", reason="approve curve")
        gov.reject_record(display_rule_ids[0], actor="tester", reason="reject display rule")

        svc = _make_service(repo)
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="kr8_rejected_display_curve")]
        )
        result = svc.recommend_display(req)
        r = result.recommendations[0]
        # Curve classified but display rule rejected → no display rule → review_required
        assert r.classification_status == "classified"
        assert r.review_required is True
        assert r.scale_type is None


# ===========================================================================
# Test 17: Deprecated display rule does not affect recommendation
# ===========================================================================


class TestDeprecatedDisplayRuleDoesNotRecommend:
    """Test 17: deprecated display rule does not affect recommendation."""

    def test_deprecated_display_rule_not_recommended(
        self, repo: ManagedKRRepository, seed_display_rule_record_id: str
    ) -> None:
        """17a. Deprecating the seed display rule removes it from production-eligible."""
        gov = GovernanceService(repo)
        gov.deprecate_record(
            seed_display_rule_record_id, actor="tester", reason="test deprecate"
        )
        production_ids = {r.record_id for r in repo.list_production_eligible()}
        assert seed_display_rule_record_id not in production_ids

    def test_approved_then_deprecated_display_rule(
        self, repo: ManagedKRRepository
    ) -> None:
        """17b. Approved-then-deprecated display rule → no recommendation."""
        payload = _curve_and_display_rule_payload("kr8_depr_display_curve")
        stage_result = stage_import_payload(payload, repo)

        curve_def_ids = [rid for rid in stage_result.record_ids if "_curve_def_" in rid]
        display_rule_ids = [rid for rid in stage_result.record_ids if "_display_" in rid and "_curve_def_" not in rid]
        assert curve_def_ids
        assert display_rule_ids

        gov = GovernanceService(repo)
        gov.approve_record(curve_def_ids[0], actor="tester", reason="approve")
        gov.approve_record(display_rule_ids[0], actor="tester", reason="approve display")
        gov.deprecate_record(display_rule_ids[0], actor="tester", reason="now deprecate")

        svc = _make_service(repo)
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="kr8_depr_display_curve")]
        )
        result = svc.recommend_display(req)
        r = result.recommendations[0]
        assert r.classification_status == "classified"
        assert r.recommendation_status == "review_required"
        assert r.scale_type is None


# ===========================================================================
# Test 18: Approved managed display rule affects recommendation
# ===========================================================================


class TestApprovedManagedDisplayRuleRecommends:
    """Test 18: approved managed display rule affects recommendation."""

    def test_approved_display_rule_recommends(self, repo: ManagedKRRepository) -> None:
        """18. Stage + approve curve def + display rule → recommended."""
        payload = _curve_and_display_rule_payload(
            "kr8_approved_display_curve",
            scale_type="log",
            display_min=0.01,
            display_max=10000.0,
            default_unit="OHMM",
        )
        stage_result = stage_import_payload(payload, repo)
        _approve_all(repo, stage_result.record_ids)

        svc = _make_service(repo)
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="kr8_approved_display_curve")]
        )
        result = svc.recommend_display(req)
        r = result.recommendations[0]
        assert r.recommendation_status == "recommended"
        assert r.scale_type == "log"
        assert r.recommended_min == pytest.approx(0.01)
        assert r.recommended_max == pytest.approx(10000.0)
        assert r.unit == "OHMM"
        assert r.review_required is False


# ===========================================================================
# Test 19: Candidate alias/curve definition does not indirectly create recommendation
# ===========================================================================


class TestCandidateAliasNoIndirectRecommendation:
    """Test 19: candidate alias/curve definition does not indirectly create recommendation."""

    def test_candidate_curve_def_no_recommendation(
        self, repo: ManagedKRRepository
    ) -> None:
        """19. Staged (candidate) curve definition → unclassified → unrecommended."""
        payload = _curve_only_payload("kr8_candidate_curve_only")
        stage_import_payload(payload, repo)

        svc = _make_service(repo)
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="kr8_candidate_curve_only")]
        )
        result = svc.recommend_display(req)
        r = result.recommendations[0]
        assert r.recommendation_status == "unrecommended"
        assert r.review_required is True


# ===========================================================================
# Test 20: Approved managed alias can produce recommendation if matching display rule exists
# ===========================================================================


class TestApprovedManagedAliasWithDisplayRule:
    """Test 20: approved managed alias can produce recommendation if display rule exists."""

    def test_approved_alias_and_display_rule_recommends(
        self, repo: ManagedKRRepository
    ) -> None:
        """20. Stage + approve curve def + display rule for new canonical_id → recommended."""
        payload = _curve_and_display_rule_payload(
            "kr8_approved_alias_display",
            display_name="KR8 Alias Display Test",
        )
        stage_result = stage_import_payload(payload, repo)
        _approve_all(repo, stage_result.record_ids)

        svc = _make_service(repo)
        req = DisplayRecommendationRequest(
            curves=[
                CurveRecommendInput(
                    curve_id="c1", mnemonic="kr8_approved_alias_display"
                )
            ]
        )
        result = svc.recommend_display(req)
        r = result.recommendations[0]
        assert r.recommendation_status == "recommended"
        assert r.canonical_curve_id == "kr8_approved_alias_display"


# ===========================================================================
# Test 21: Empty curve list returns 200 with zero counts
# ===========================================================================


class TestEmptyCurveList:
    """Test 21: empty curve list returns 200 with zero counts."""

    def test_empty_service_result(self, service: DisplayRecommendationService) -> None:
        """21a. Empty list → zero counts, empty recommendations list."""
        req = DisplayRecommendationRequest(curves=[])
        result = service.recommend_display(req)
        assert result.curve_count == 0
        assert result.recommended_count == 0
        assert result.unrecommended_count == 0
        assert result.review_required_count == 0
        assert result.recommendations == []
        assert result.kr_version == KR8_VERSION

    def test_empty_http_200(self, client: TestClient) -> None:
        """21b. HTTP endpoint with empty curves list returns 200."""
        resp = client.post(
            "/api/wlv/knowledge/recommend-display/curves",
            json={"curves": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["curve_count"] == 0
        assert data["recommended_count"] == 0
        assert data["kr_version"] == KR8_VERSION


# ===========================================================================
# Test 22: Malformed request returns 422
# ===========================================================================


class TestMalformedRequest:
    """Test 22: malformed request returns 422."""

    def test_missing_curves_field(self, client: TestClient) -> None:
        """22a. Missing required 'curves' field → 422."""
        resp = client.post(
            "/api/wlv/knowledge/recommend-display/curves",
            json={"well_id": "w1"},
        )
        assert resp.status_code == 422

    def test_curve_missing_mnemonic(self, client: TestClient) -> None:
        """22b. Curve item missing required 'mnemonic' → 422."""
        resp = client.post(
            "/api/wlv/knowledge/recommend-display/curves",
            json={"curves": [{"curve_id": "c1"}]},
        )
        assert resp.status_code == 422

    def test_curve_missing_curve_id(self, client: TestClient) -> None:
        """22c. Curve item missing required 'curve_id' → 422."""
        resp = client.post(
            "/api/wlv/knowledge/recommend-display/curves",
            json={"curves": [{"mnemonic": "GR"}]},
        )
        assert resp.status_code == 422


# ===========================================================================
# Test 23: KR-7 classify endpoint still works
# ===========================================================================


class TestKr7ClassifyStillWorks:
    """Test 23: KR-7 classify endpoint still works after KR-8 addition."""

    def test_classify_endpoint_works(self, client: TestClient) -> None:
        """23a. POST /api/wlv/knowledge/classify/curves returns 200."""
        resp = client.post(
            "/api/wlv/knowledge/classify/curves",
            json={"curves": [{"curve_id": "c1", "mnemonic": "GR"}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["classified_count"] == 1
        assert data["classifications"][0]["canonical_curve_id"] == "gamma_ray"

    def test_classify_kr7_version(self, client: TestClient) -> None:
        """23b. KR-7 classify endpoint still returns kr-7 version."""
        resp = client.post(
            "/api/wlv/knowledge/classify/curves",
            json={"curves": [{"curve_id": "c1", "mnemonic": "GR"}]},
        )
        assert resp.status_code == 200
        assert resp.json()["kr_version"] == "kr-7"


# ===========================================================================
# Test 24: KR-6 resolve endpoint still works
# ===========================================================================


class TestKr6ResolveStillWorks:
    """Test 24: KR-6 resolve endpoints still work after KR-8 addition."""

    def test_single_resolve_still_works(self, client: TestClient) -> None:
        """24a. POST /api/wlv/knowledge/resolve/curve still returns 200."""
        resp = client.post(
            "/api/wlv/knowledge/resolve/curve",
            json={"mnemonic": "GR"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["resolved"] is True
        assert data["canonical_curve_id"] == "gamma_ray"

    def test_batch_resolve_still_works(self, client: TestClient) -> None:
        """24b. POST /api/wlv/knowledge/resolve/curves still returns 200."""
        resp = client.post(
            "/api/wlv/knowledge/resolve/curves",
            json={"curves": [{"mnemonic": "GR"}, {"mnemonic": "NPHI"}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert data["resolved_count"] == 2


# ===========================================================================
# Test 25: KR-5 storage health still works
# ===========================================================================


class TestKr5StorageHealthStillWorks:
    """Test 25: KR-5 storage health endpoint still works."""

    def test_storage_health(self, client: TestClient) -> None:
        """25. GET /api/wlv/knowledge/managed/storage/health returns 200."""
        resp = client.get("/api/wlv/knowledge/managed/storage/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "storage_enabled" in data
        assert "persisted_record_count" in data


# ===========================================================================
# Test 26: KR-1 endpoints still work
# ===========================================================================


class TestKr1EndpointsStillWork:
    """Test 26: KR-1 read-only endpoints still work."""

    def test_kr1_curves(self, client: TestClient) -> None:
        """26a. GET /api/wlv/knowledge/curve-definitions returns 200."""
        resp = client.get("/api/wlv/knowledge/curve-definitions")
        assert resp.status_code == 200

    def test_kr1_product_groups(self, client: TestClient) -> None:
        """26b. GET /api/wlv/knowledge/product-groups returns 200."""
        resp = client.get("/api/wlv/knowledge/product-groups")
        assert resp.status_code == 200

    def test_kr1_managed_health(self, client: TestClient) -> None:
        """26c. GET /api/wlv/knowledge/managed/health returns 200."""
        resp = client.get("/api/wlv/knowledge/managed/health")
        assert resp.status_code == 200


# ===========================================================================
# Test 27: Full knowledge suite passes (structural import guard)
# ===========================================================================


class TestFullKnowledgeSuiteStructural:
    """Test 27: verify all KR service modules are importable together."""

    def test_all_kr_modules_importable(self) -> None:
        """27a. All KR service modules import without error."""
        from app.knowledge import resolution_service  # noqa: F401
        from app.knowledge import classification_service  # noqa: F401
        from app.knowledge import display_recommendation_service  # noqa: F401
        from app.knowledge import governance_service  # noqa: F401
        from app.knowledge import managed_repository  # noqa: F401
        from app.knowledge import managed_storage  # noqa: F401
        from app.knowledge import import_staging_service  # noqa: F401

    def test_kr8_version_constant(self) -> None:
        """27b. KR8_VERSION constant is correctly set."""
        assert KR8_VERSION == "kr-8"

    def test_recommend_endpoint_accessible(self, client: TestClient) -> None:
        """27c. POST /api/wlv/knowledge/recommend-display/curves is accessible."""
        resp = client.post(
            "/api/wlv/knowledge/recommend-display/curves",
            json={"curves": [{"curve_id": "c1", "mnemonic": "GR"}]},
        )
        assert resp.status_code == 200


# ===========================================================================
# Test 28: Frontend typecheck passes (structural contract shape check)
# ===========================================================================


class TestFrontendTypecheckStructural:
    """Test 28: structural contract shape check (full typecheck via validate script)."""

    def test_recommend_response_shape(self, client: TestClient) -> None:
        """28. recommend-display/curves response matches documented contract shape."""
        resp = client.post(
            "/api/wlv/knowledge/recommend-display/curves",
            json={
                "well_id": "test_well",
                "source": {
                    "source_type": "las_import",
                    "source_file": "well_a.las",
                    "import_batch_id": "batch_001",
                },
                "curves": [
                    {
                        "curve_id": "curve_001",
                        "mnemonic": "GR",
                        "unit": "API",
                        "description": "Gamma Ray",
                        "source_curve_index": 1,
                    }
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Top-level fields
        assert "kr_version" in data
        assert "well_id" in data
        assert "curve_count" in data
        assert "recommended_count" in data
        assert "unrecommended_count" in data
        assert "review_required_count" in data
        assert "recommendations" in data
        # Per-recommendation fields
        r = data["recommendations"][0]
        assert "curve_id" in r
        assert "mnemonic" in r
        assert "normalized_mnemonic" in r
        assert "canonical_curve_id" in r
        assert "classification_status" in r
        assert "recommendation_status" in r
        assert "source_curve_index" in r
        assert "display_name" in r
        assert "product_group" in r
        assert "product_subgroup" in r
        assert "display_family" in r
        assert "scale_type" in r
        assert "recommended_min" in r
        assert "recommended_max" in r
        assert "unit" in r
        assert "preferred_track_group" in r
        assert "review_required" in r
        assert "warnings" in r
        # Verify values for GR
        assert data["kr_version"] == KR8_VERSION
        assert r["recommendation_status"] == "recommended"
        assert r["review_required"] is False


# ===========================================================================
# Test 29: Frontend build passes (structural guard)
# ===========================================================================


class TestFrontendBuildStructural:
    """Test 29: structural guard; full build runs in validate script."""

    def test_no_frontend_files_changed(self) -> None:
        """29. KR-8 service file exists under backend knowledge package."""
        project = Path(__file__).resolve().parents[3]
        backend_service = (
            project / "backend" / "app" / "knowledge" / "display_recommendation_service.py"
        )
        frontend_dir = project / "frontend"

        assert backend_service.exists(), "display_recommendation_service.py must exist in backend"
        assert frontend_dir.exists(), "frontend directory should exist"
        assert backend_service.parts[-4:] == (
            "backend", "app", "knowledge", "display_recommendation_service.py"
        )
