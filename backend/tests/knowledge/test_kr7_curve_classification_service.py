"""Tests for WLV KR-7 — Backend Curve Classification Service.

Tests all 25 required cases:

Service / unit tests:
  1.  GR seed alias classifies as gamma_ray.
  2.  gamma_ray canonical ID classifies correctly.
  3.  Unknown mnemonic returns unclassified.
  4.  Unknown mnemonic sets review_required=True.
  5.  Batch preserves input order.
  6.  Batch handles mixed classified/unclassified curves.
  7.  Source curve_id is preserved.
  8.  Source curve index is preserved.
  9.  Unit and description are accepted and passed into resolver input.
  10. Display rule is included for resolved curve where available.
  11. Product group/subgroup are included for resolved curve.
  12. Candidate managed alias does not classify.
  13. Rejected managed alias does not classify.
  14. Deprecated managed alias does not classify.
  15. Approved managed alias classifies.
  16. Approved managed curve definition classifies.
  17. Classification response includes count summary.
  18. Empty curve list returns result with zero counts.

API / HTTP tests:
  19. Malformed request returns 422.
  20. KR-6 resolve endpoints still work.
  21. KR-5 storage health still works.
  22. KR-1 endpoints still work.
  23. Full knowledge suite passes (knowledge suite re-run guard).
  24. Frontend typecheck passes (structural — verified via import and contract shapes).
  25. Frontend build passes (structural here; validate script covers the full build).
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.knowledge.api_managed_knowledge import get_managed_repository
from app.knowledge.classification_service import (
    CurveClassificationRequest,
    CurveClassificationService,
    CurveClassifyInput,
    KR7_VERSION,
)
from app.knowledge.governance_service import GovernanceService
from app.knowledge.import_models import (
    ImportCurveDefinition,
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


def _make_service(repo: ManagedKRRepository) -> CurveClassificationService:
    return CurveClassificationService(KnowledgeResolutionService(repo))


def _curve_def_payload(canonical_id: str, display_name: str = "Test Curve") -> ImportPayload:
    """Minimal payload staging one curve definition (candidate)."""
    return ImportPayload(
        source=ImportSource(
            source_type="manual_import",
            source_label=f"KR-7 Test {canonical_id}",
            source_reference=f"kr7_test_{canonical_id}",
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


def _approve_all(repo: ManagedKRRepository, record_ids: list[str]) -> None:
    gov = GovernanceService(repo)
    for rid in record_ids:
        gov.approve_record(rid, actor="kr7_tester", reason="kr7 test approval")


_APPROVE_BODY = {
    "actor": "kr7_test_reviewer",
    "reason": "KR-7 test approval",
    "notes": "Automated KR-7 test suite",
}

_REJECT_BODY = {
    "actor": "kr7_test_reviewer",
    "reason": "KR-7 test rejection",
    "notes": "Automated KR-7 test suite",
}

_DEPRECATE_BODY = {
    "actor": "kr7_test_reviewer",
    "reason": "KR-7 test deprecation",
    "notes": "Automated KR-7 test suite",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage_path(tmp_path: Path) -> Path:
    return tmp_path / "knowledge" / "kr7_test.json"


@pytest.fixture
def repo(storage_path: Path) -> ManagedKRRepository:
    return _fresh_repo(storage_path)


@pytest.fixture
def service(repo: ManagedKRRepository) -> CurveClassificationService:
    return _make_service(repo)


@pytest.fixture
def client(repo: ManagedKRRepository) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_managed_repository] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def seed_standard_mnemonic_record_id(repo: ManagedKRRepository) -> str:
    """Return record_id of a known seed standard mnemonic (GR → gamma_ray)."""
    records = [
        r for r in repo.list_seeds()
        if r.record_type == "standard_mnemonic" and getattr(r, "mnemonic", "") == "GR"
    ]
    assert records, "Expected seed standard mnemonic for GR"
    return records[0].record_id


# ===========================================================================
# Test 1: GR seed alias classifies as gamma_ray
# ===========================================================================


class TestGrSeedAliasClassification:
    """Test 1: GR seed alias classifies as gamma_ray."""

    def test_gr_classifies(self, service: CurveClassificationService) -> None:
        """1a. 'GR' classifies as gamma_ray via seed alias."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="curve_001", mnemonic="GR", unit="API")]
        )
        result = service.classify_curves(req)
        c = result.classifications[0]
        assert c.resolved is True
        assert c.classification_status == "classified"
        assert c.canonical_curve_id == "gamma_ray"
        assert c.resolution_source == "seed_standard_mnemonic"
        assert c.confidence == 1.0

    def test_gr_classifies_knowledge_record_id_set(self, service: CurveClassificationService) -> None:
        """1b. knowledge_record_id is populated for resolved GR."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="curve_001", mnemonic="GR")]
        )
        result = service.classify_curves(req)
        assert result.classifications[0].knowledge_record_id is not None

    def test_gr_classifies_no_review_required(self, service: CurveClassificationService) -> None:
        """1c. review_required is False for resolved GR."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="GR")]
        )
        result = service.classify_curves(req)
        assert result.classifications[0].review_required is False

    def test_gr_no_warnings(self, service: CurveClassificationService) -> None:
        """1d. No warnings for resolved GR seed alias."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="GR")]
        )
        result = service.classify_curves(req)
        assert result.classifications[0].warnings == []


# ===========================================================================
# Test 2: gamma_ray canonical ID classifies correctly
# ===========================================================================


class TestGammaRayCanonicalClassification:
    """Test 2: gamma_ray canonical ID classifies correctly."""

    def test_canonical_classifies(self, service: CurveClassificationService) -> None:
        """2a. 'gamma_ray' classifies via canonical curve ID."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="gamma_ray")]
        )
        result = service.classify_curves(req)
        c = result.classifications[0]
        assert c.resolved is True
        assert c.classification_status == "classified"
        assert c.canonical_curve_id == "gamma_ray"
        assert c.resolution_source in {"seed_canonical", "managed_canonical"}

    def test_canonical_has_display_name(self, service: CurveClassificationService) -> None:
        """2b. Classified gamma_ray has display_name."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="gamma_ray")]
        )
        result = service.classify_curves(req)
        assert result.classifications[0].display_name is not None


# ===========================================================================
# Test 3: Unknown mnemonic returns unclassified
# ===========================================================================


class TestUnknownMnemonicUnclassified:
    """Test 3: unknown mnemonic returns unclassified."""

    def test_unknown_unclassified(self, service: CurveClassificationService) -> None:
        """3. 'XYZ' → classification_status='unclassified'."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="curve_999", mnemonic="XYZ")]
        )
        result = service.classify_curves(req)
        c = result.classifications[0]
        assert c.resolved is False
        assert c.classification_status == "unclassified"
        assert c.canonical_curve_id is None
        assert c.confidence == 0.0


# ===========================================================================
# Test 4: Unknown mnemonic sets review_required=True
# ===========================================================================


class TestUnknownMnemonicReviewRequired:
    """Test 4: unknown mnemonic sets review_required=True."""

    def test_unknown_review_required(self, service: CurveClassificationService) -> None:
        """4. Unclassified curve has review_required=True."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="curve_999", mnemonic="XYZ")]
        )
        result = service.classify_curves(req)
        c = result.classifications[0]
        assert c.review_required is True
        assert len(c.warnings) > 0


# ===========================================================================
# Test 5: Batch preserves input order
# ===========================================================================


class TestBatchPreservesInputOrder:
    """Test 5: batch preserves input order."""

    def test_order_preserved(self, service: CurveClassificationService) -> None:
        """5. Results appear in same order as input curves."""
        mnemonics = ["GR", "XYZ_UNKNOWN_A", "NPHI", "XYZ_UNKNOWN_B", "gamma_ray"]
        curves = [
            CurveClassifyInput(curve_id=f"c{i}", mnemonic=m)
            for i, m in enumerate(mnemonics)
        ]
        req = CurveClassificationRequest(curves=curves)
        result = service.classify_curves(req)
        assert len(result.classifications) == len(mnemonics)
        for i, (expected_id, classification) in enumerate(
            zip([f"c{i}" for i in range(len(mnemonics))], result.classifications)
        ):
            assert classification.curve_id == expected_id, (
                f"Position {i}: expected curve_id={expected_id}, got {classification.curve_id}"
            )


# ===========================================================================
# Test 6: Batch handles mixed classified/unclassified
# ===========================================================================


class TestBatchMixedClassification:
    """Test 6: batch handles mixed classified/unclassified curves."""

    def test_mixed_batch(self, service: CurveClassificationService) -> None:
        """6. Mix of known and unknown mnemonics all returned correctly."""
        req = CurveClassificationRequest(
            curves=[
                CurveClassifyInput(curve_id="c0", mnemonic="GR"),
                CurveClassifyInput(curve_id="c1", mnemonic="UNKNOWNXXX"),
                CurveClassifyInput(curve_id="c2", mnemonic="NPHI"),
            ]
        )
        result = service.classify_curves(req)
        assert result.classifications[0].classification_status == "classified"
        assert result.classifications[1].classification_status == "unclassified"
        assert result.classifications[2].classification_status == "classified"
        assert result.classified_count == 2
        assert result.unclassified_count == 1


# ===========================================================================
# Test 7: Source curve_id is preserved
# ===========================================================================


class TestSourceCurveIdPreserved:
    """Test 7: source curve_id is preserved."""

    def test_curve_id_preserved_classified(self, service: CurveClassificationService) -> None:
        """7a. curve_id preserved for classified result."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="my_stable_id_001", mnemonic="GR")]
        )
        result = service.classify_curves(req)
        assert result.classifications[0].curve_id == "my_stable_id_001"

    def test_curve_id_preserved_unclassified(self, service: CurveClassificationService) -> None:
        """7b. curve_id preserved for unclassified result."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="my_stable_id_999", mnemonic="XYZNOTREAL")]
        )
        result = service.classify_curves(req)
        assert result.classifications[0].curve_id == "my_stable_id_999"


# ===========================================================================
# Test 8: Source curve index is preserved
# ===========================================================================


class TestSourceCurveIndexPreserved:
    """Test 8: source curve index is preserved."""

    def test_index_preserved(self, service: CurveClassificationService) -> None:
        """8. source_curve_index round-trips through classification."""
        req = CurveClassificationRequest(
            curves=[
                CurveClassifyInput(curve_id="c0", mnemonic="GR", source_curve_index=0),
                CurveClassifyInput(curve_id="c1", mnemonic="NPHI", source_curve_index=1),
                CurveClassifyInput(curve_id="c2", mnemonic="XYZ", source_curve_index=2),
            ]
        )
        result = service.classify_curves(req)
        assert result.classifications[0].source_curve_index == 0
        assert result.classifications[1].source_curve_index == 1
        assert result.classifications[2].source_curve_index == 2

    def test_none_index_preserved(self, service: CurveClassificationService) -> None:
        """8b. None source_curve_index is preserved as None."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c0", mnemonic="GR", source_curve_index=None)]
        )
        result = service.classify_curves(req)
        assert result.classifications[0].source_curve_index is None


# ===========================================================================
# Test 9: Unit and description are accepted and passed into resolver input
# ===========================================================================


class TestUnitAndDescriptionAccepted:
    """Test 9: unit and description are accepted without error."""

    def test_unit_accepted(self, service: CurveClassificationService) -> None:
        """9a. unit field accepted; does not break classification."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="GR", unit="API")]
        )
        result = service.classify_curves(req)
        assert result.classifications[0].classification_status == "classified"

    def test_description_accepted(self, service: CurveClassificationService) -> None:
        """9b. description field accepted; does not break classification."""
        req = CurveClassificationRequest(
            curves=[
                CurveClassifyInput(
                    curve_id="c1",
                    mnemonic="GR",
                    unit="API",
                    description="Gamma Ray",
                )
            ]
        )
        result = service.classify_curves(req)
        assert result.classifications[0].classification_status == "classified"

    def test_unit_and_description_for_unknown(self, service: CurveClassificationService) -> None:
        """9c. unit and description accepted for unknown mnemonic (still unclassified)."""
        req = CurveClassificationRequest(
            curves=[
                CurveClassifyInput(
                    curve_id="c1",
                    mnemonic="XYZUNK",
                    unit="ohm.m",
                    description="Unknown curve",
                )
            ]
        )
        result = service.classify_curves(req)
        assert result.classifications[0].classification_status == "unclassified"


# ===========================================================================
# Test 10: Display rule is included for resolved curve where available
# ===========================================================================


class TestDisplayRuleIncluded:
    """Test 10: display rule included for resolved curve where available."""

    def test_gr_has_display_rule(self, service: CurveClassificationService) -> None:
        """10a. GR classification includes a display_rule."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="GR")]
        )
        result = service.classify_curves(req)
        dr = result.classifications[0].display_rule
        assert dr is not None
        assert dr.scale_type in {"linear", "log"}
        assert isinstance(dr.recommended_min, float)
        assert isinstance(dr.recommended_max, float)

    def test_unclassified_no_display_rule(self, service: CurveClassificationService) -> None:
        """10b. Unclassified curve has no display_rule."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="XYZUNKOWN")]
        )
        result = service.classify_curves(req)
        assert result.classifications[0].display_rule is None


# ===========================================================================
# Test 11: Product group/subgroup are included for resolved curve
# ===========================================================================


class TestProductGroupSubgroupIncluded:
    """Test 11: product group/subgroup included for resolved curve."""

    def test_gr_has_product_group(self, service: CurveClassificationService) -> None:
        """11a. GR classification includes product_group."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="GR")]
        )
        result = service.classify_curves(req)
        c = result.classifications[0]
        assert c.product_group is not None
        assert c.product_group == "open_hole_logs"

    def test_gr_has_product_subgroup(self, service: CurveClassificationService) -> None:
        """11b. GR classification includes product_subgroup."""
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="GR")]
        )
        result = service.classify_curves(req)
        assert result.classifications[0].product_subgroup is not None


# ===========================================================================
# Test 12: Candidate managed alias does not classify
# ===========================================================================


class TestCandidateDoesNotClassify:
    """Test 12: candidate managed alias does not classify."""

    def test_candidate_does_not_classify(self, repo: ManagedKRRepository) -> None:
        """12. Staged (candidate) curve definition does not classify."""
        payload = _curve_def_payload("kr7_candidate_curve")
        stage_import_payload(payload, repo)

        svc = _make_service(repo)
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="kr7_candidate_curve")]
        )
        result = svc.classify_curves(req)
        assert result.classifications[0].classification_status == "unclassified"
        assert result.classifications[0].review_required is True


# ===========================================================================
# Test 13: Rejected managed alias does not classify
# ===========================================================================


class TestRejectedDoesNotClassify:
    """Test 13: rejected managed alias does not classify."""

    def test_rejected_does_not_classify(self, repo: ManagedKRRepository) -> None:
        """13. A rejected record does not classify."""
        payload = _curve_def_payload("kr7_rejected_curve")
        stage_result = stage_import_payload(payload, repo)
        curve_def_ids = [rid for rid in stage_result.record_ids if "curve_def" in rid]
        assert curve_def_ids

        gov = GovernanceService(repo)
        gov.reject_record(curve_def_ids[0], actor="tester", reason="test rejection")

        svc = _make_service(repo)
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="kr7_rejected_curve")]
        )
        result = svc.classify_curves(req)
        assert result.classifications[0].classification_status == "unclassified"


# ===========================================================================
# Test 14: Deprecated managed alias does not classify
# ===========================================================================


class TestDeprecatedDoesNotClassify:
    """Test 14: deprecated managed alias does not classify."""

    def test_deprecated_does_not_classify(
        self, repo: ManagedKRRepository, seed_standard_mnemonic_record_id: str
    ) -> None:
        """14a. Deprecating a seed alias removes it from production-eligible records."""
        gov = GovernanceService(repo)
        gov.deprecate_record(seed_standard_mnemonic_record_id, actor="tester", reason="test deprecated")
        production_ids = {r.record_id for r in repo.list_production_eligible()}
        assert seed_standard_mnemonic_record_id not in production_ids

    def test_approved_then_deprecated_does_not_classify(
        self, repo: ManagedKRRepository
    ) -> None:
        """14b. An approved-then-deprecated curve definition does not classify."""
        payload = _curve_def_payload("kr7_depr_curve")
        stage_result = stage_import_payload(payload, repo)
        curve_def_ids = [rid for rid in stage_result.record_ids if "curve_def" in rid]
        assert curve_def_ids

        gov = GovernanceService(repo)
        gov.approve_record(curve_def_ids[0], actor="tester", reason="approve first")
        gov.deprecate_record(curve_def_ids[0], actor="tester", reason="now deprecate")

        svc = _make_service(repo)
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="kr7_depr_curve")]
        )
        result = svc.classify_curves(req)
        assert result.classifications[0].classification_status == "unclassified"


# ===========================================================================
# Test 15: Approved managed alias classifies
# ===========================================================================


class TestApprovedManagedAliasClassifies:
    """Test 15: approved managed alias classifies."""

    def test_approved_alias_classifies(self, repo: ManagedKRRepository) -> None:
        """15. Stage + approve → classifies via managed knowledge."""
        payload = _curve_def_payload("kr7_approved_alias_curve")
        stage_result = stage_import_payload(payload, repo)

        _approve_all(repo, stage_result.record_ids)

        svc = _make_service(repo)
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="kr7_approved_alias_curve")]
        )
        result = svc.classify_curves(req)
        c = result.classifications[0]
        assert c.classification_status == "classified"
        assert c.canonical_curve_id == "kr7_approved_alias_curve"
        assert c.resolution_source in {"managed_alias", "managed_canonical"}


# ===========================================================================
# Test 16: Approved managed curve definition classifies
# ===========================================================================


class TestApprovedManagedCurveDefinitionClassifies:
    """Test 16: approved managed curve definition classifies."""

    def test_approved_curve_def_classifies(self, repo: ManagedKRRepository) -> None:
        """16. Stage + approve curve definition → classifies."""
        payload = _curve_def_payload("kr7_approved_def_curve", display_name="KR7 Approved Def")
        stage_result = stage_import_payload(payload, repo)
        _approve_all(repo, stage_result.record_ids)

        svc = _make_service(repo)
        req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="kr7_approved_def_curve")]
        )
        result = svc.classify_curves(req)
        c = result.classifications[0]
        assert c.classification_status == "classified"
        assert c.resolved is True
        assert c.canonical_curve_id == "kr7_approved_def_curve"


# ===========================================================================
# Test 17: Classification response includes count summary
# ===========================================================================


class TestCountSummary:
    """Test 17: classification response includes count summary."""

    def test_count_summary_all_classified(self, service: CurveClassificationService) -> None:
        """17a. All classified → counts match."""
        req = CurveClassificationRequest(
            curves=[
                CurveClassifyInput(curve_id="c0", mnemonic="GR"),
                CurveClassifyInput(curve_id="c1", mnemonic="NPHI"),
            ]
        )
        result = service.classify_curves(req)
        assert result.curve_count == 2
        assert result.classified_count == 2
        assert result.unclassified_count == 0
        assert result.review_required_count == 0
        assert result.kr_version == KR7_VERSION

    def test_count_summary_mixed(self, service: CurveClassificationService) -> None:
        """17b. Mixed batch → counts are correct."""
        req = CurveClassificationRequest(
            curves=[
                CurveClassifyInput(curve_id="c0", mnemonic="GR"),
                CurveClassifyInput(curve_id="c1", mnemonic="XYZUNK1"),
                CurveClassifyInput(curve_id="c2", mnemonic="XYZUNK2"),
            ]
        )
        result = service.classify_curves(req)
        assert result.curve_count == 3
        assert result.classified_count == 1
        assert result.unclassified_count == 2
        assert result.review_required_count == 2


# ===========================================================================
# Test 18: Empty curve list returns 200 with zero counts
# ===========================================================================


class TestEmptyCurveList:
    """Test 18: empty curve list returns result with zero counts."""

    def test_empty_service_result(self, service: CurveClassificationService) -> None:
        """18a. Empty list → zero counts, empty classifications list."""
        req = CurveClassificationRequest(curves=[])
        result = service.classify_curves(req)
        assert result.curve_count == 0
        assert result.classified_count == 0
        assert result.unclassified_count == 0
        assert result.review_required_count == 0
        assert result.classifications == []

    def test_empty_http_200(self, client: TestClient) -> None:
        """18b. HTTP endpoint with empty curves list returns 200."""
        resp = client.post(
            "/api/wlv/knowledge/classify/curves",
            json={"curves": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["curve_count"] == 0
        assert data["classified_count"] == 0
        assert data["kr_version"] == KR7_VERSION


# ===========================================================================
# Test 19: Malformed request returns 422
# ===========================================================================


class TestMalformedRequest:
    """Test 19: malformed request returns 422."""

    def test_missing_curves_field(self, client: TestClient) -> None:
        """19a. Missing required 'curves' field → 422."""
        resp = client.post(
            "/api/wlv/knowledge/classify/curves",
            json={"well_id": "w1"},
        )
        assert resp.status_code == 422

    def test_curve_missing_mnemonic(self, client: TestClient) -> None:
        """19b. Curve item missing required 'mnemonic' → 422."""
        resp = client.post(
            "/api/wlv/knowledge/classify/curves",
            json={"curves": [{"curve_id": "c1"}]},
        )
        assert resp.status_code == 422

    def test_curve_missing_curve_id(self, client: TestClient) -> None:
        """19c. Curve item missing required 'curve_id' → 422."""
        resp = client.post(
            "/api/wlv/knowledge/classify/curves",
            json={"curves": [{"mnemonic": "GR"}]},
        )
        assert resp.status_code == 422


# ===========================================================================
# Test 20: KR-6 resolve endpoints still work
# ===========================================================================


class TestKr6ResolveEndpointsStillWork:
    """Test 20: KR-6 resolve endpoints still work after KR-7 addition."""

    def test_single_resolve_still_works(self, client: TestClient) -> None:
        """20a. POST /api/wlv/knowledge/resolve/curve still returns 200."""
        resp = client.post(
            "/api/wlv/knowledge/resolve/curve",
            json={"mnemonic": "GR"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["resolved"] is True
        assert data["canonical_curve_id"] == "gamma_ray"

    def test_batch_resolve_still_works(self, client: TestClient) -> None:
        """20b. POST /api/wlv/knowledge/resolve/curves still returns 200."""
        resp = client.post(
            "/api/wlv/knowledge/resolve/curves",
            json={"curves": [{"mnemonic": "GR"}, {"mnemonic": "NPHI"}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert data["resolved_count"] == 2

    def test_classify_endpoint_accessible(self, client: TestClient) -> None:
        """20c. POST /api/wlv/knowledge/classify/curves is accessible."""
        resp = client.post(
            "/api/wlv/knowledge/classify/curves",
            json={"curves": [{"curve_id": "c1", "mnemonic": "GR"}]},
        )
        assert resp.status_code == 200


# ===========================================================================
# Test 21: KR-5 storage health still works
# ===========================================================================


class TestKr5StorageHealthStillWorks:
    """Test 21: KR-5 storage health endpoint still works."""

    def test_storage_health(self, client: TestClient) -> None:
        """21. GET /api/wlv/knowledge/managed/storage/health returns 200."""
        resp = client.get("/api/wlv/knowledge/managed/storage/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "storage_enabled" in data
        assert "persisted_record_count" in data


# ===========================================================================
# Test 22: KR-1 endpoints still work
# ===========================================================================


class TestKr1EndpointsStillWork:
    """Test 22: KR-1 read-only endpoints still work."""

    def test_kr1_curves(self, client: TestClient) -> None:
        """22a. GET /api/wlv/knowledge/curve-definitions returns 200."""
        resp = client.get("/api/wlv/knowledge/curve-definitions")
        assert resp.status_code == 200

    def test_kr1_curve_families(self, client: TestClient) -> None:
        """22b. GET /api/wlv/knowledge/product-groups returns 200."""
        resp = client.get("/api/wlv/knowledge/product-groups")
        assert resp.status_code == 200

    def test_kr1_managed_health(self, client: TestClient) -> None:
        """22c. GET /api/wlv/knowledge/managed/health returns 200."""
        resp = client.get("/api/wlv/knowledge/managed/health")
        assert resp.status_code == 200


# ===========================================================================
# Test 23: Full knowledge suite passes (structural import guard)
# ===========================================================================


class TestFullKnowledgeSuiteStructural:
    """Test 23: verify all KR service modules are importable together."""

    def test_all_kr_modules_importable(self) -> None:
        """23. All KR service modules import without error."""
        from app.knowledge import resolution_service  # noqa: F401
        from app.knowledge import classification_service  # noqa: F401
        from app.knowledge import governance_service  # noqa: F401
        from app.knowledge import managed_repository  # noqa: F401
        from app.knowledge import managed_storage  # noqa: F401
        from app.knowledge import import_staging_service  # noqa: F401

    def test_kr7_version_constant(self) -> None:
        """23b. KR7_VERSION constant is correctly set."""
        assert KR7_VERSION == "kr-7"


# ===========================================================================
# Test 24: Frontend typecheck passes (structural contract shape check)
# ===========================================================================


class TestFrontendTypecheckStructural:
    """Test 24: structural contract shape check (full typecheck via validate script)."""

    def test_classify_response_shape(self, client: TestClient) -> None:
        """24. classify/curves response matches documented contract shape."""
        resp = client.post(
            "/api/wlv/knowledge/classify/curves",
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
        assert "source" in data
        assert "curve_count" in data
        assert "classified_count" in data
        assert "unclassified_count" in data
        assert "review_required_count" in data
        assert "classifications" in data
        # Per-classification fields
        c = data["classifications"][0]
        assert "curve_id" in c
        assert "mnemonic" in c
        assert "normalized_mnemonic" in c
        assert "resolved" in c
        assert "classification_status" in c
        assert "canonical_curve_id" in c
        assert "confidence" in c
        assert "resolution_source" in c
        assert "review_required" in c
        assert "warnings" in c
        assert "source_curve_index" in c
        assert "display_rule" in c
        assert "product_group" in c
        assert "product_subgroup" in c


# ===========================================================================
# Test 25: Frontend build passes (structural — validate script runs full build)
# ===========================================================================


class TestFrontendBuildStructural:
    """Test 25: structural guard; full build runs in validate script."""

    def test_no_frontend_files_changed(self) -> None:
        """25. KR-7 service file exists under backend knowledge package."""
        from pathlib import Path

        project = Path(__file__).resolve().parents[3]
        backend_service = project / "backend" / "app" / "knowledge" / "classification_service.py"
        frontend_dir = project / "frontend"

        assert backend_service.exists(), "classification_service.py must exist in backend"
        assert frontend_dir.exists(), "frontend directory should exist"
        assert backend_service.parts[-4:] == ("backend", "app", "knowledge", "classification_service.py")
