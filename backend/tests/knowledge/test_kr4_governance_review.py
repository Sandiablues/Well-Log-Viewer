"""Tests for WLV KR-4 — Managed Knowledge Review / Approval / Promotion Contract.

Covers all 28 required tests across 11 test groups:

TestManagedRecordListing
  1.  GET /managed/records returns seed records.
  2.  GET /managed/records?status=candidate returns staged candidates.
  3.  GET /managed/records?record_type=curve_definition filters correctly.

TestManagedRecordLookup
  4.  GET /managed/records/{record_id} returns the expected record.
  5.  Unknown record ID returns 404.

TestApproveCandidate
  6.  Candidate approve returns HTTP 200.
  7.  Approved candidate status becomes approved.
  8.  Approved candidate appears in production-eligible listing.

TestRejectCandidate
  9.  Candidate reject returns HTTP 200.
  10. Rejected candidate status becomes rejected.
  11. Rejected candidate does not appear in production-eligible listing.

TestDeprecateRecord
  12. Approved record deprecate returns HTTP 200.
  13. Deprecated record does not appear in production-eligible listing.
  14. Seed record deprecate is allowed (seed → deprecated is a valid transition).

TestInvalidTransitions
  15. candidate → deprecated is blocked (HTTP 400).
  16. approved → rejected is blocked (HTTP 400).
  17. rejected → approved is blocked (HTTP 400).
  18. deprecated → approved is blocked (HTTP 400).
  19. Unknown record transition returns 404.
  20. Malformed action body returns 422.

TestProductionEligibleListing
  21. Production-eligible listing returns seed + approved records only.
  22. Candidate does NOT appear in production-eligible before approval.
  23. Candidate DOES appear after approval.
  24. Deprecated record disappears from production-eligible.

TestGovernanceAuditFields
  25. Governance action records actor.
  26. Governance action records timestamp.
  27. Governance action records reason.

TestKR1Compatibility
  24. (test 24 in suite) KR-1 endpoints still pass after KR-4.
  27. (test 27 in suite) Candidate records do not affect KR-1 curve definitions.
  28. Production-eligible count changes correctly after approval/deprecation.

TestKR2Compatibility
  KR-2 managed health/schema/status-summary still HTTP 200.

TestKR3Compatibility
  KR-3 preview/stage still work; semantic-invalid preview still HTTP 200
  with valid=false; malformed payload still HTTP 422.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.knowledge.api_managed_knowledge import (
    get_managed_repository,
    get_governance_service,
)
from app.knowledge.governance import GovernanceStatus
from app.knowledge.governance_service import (
    GovernanceService,
    GovernanceTransitionError,
    RecordNotFoundError,
)
from app.knowledge.import_models import (
    ImportCurveDefinition,
    ImportPayload,
    ImportSource,
)
from app.knowledge.import_staging_service import stage_import_payload
from app.knowledge.managed_models import KR4_VERSION
from app.knowledge.managed_repository import ManagedKRRepository
from app.knowledge.models import KR_VERSION


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo() -> ManagedKRRepository:
    """Fresh isolated ManagedKRRepository with seed records only."""
    return ManagedKRRepository()


@pytest.fixture
def service(repo: ManagedKRRepository) -> GovernanceService:
    """GovernanceService wrapping the fresh repo."""
    return GovernanceService(repo)


@pytest.fixture
def client_with_repo(repo: ManagedKRRepository) -> TestClient:
    """TestClient wired to an isolated fresh repository via DI override."""
    app.dependency_overrides[get_managed_repository] = lambda: repo
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def staged_candidate_id(repo: ManagedKRRepository) -> str:
    """Stage one candidate curve definition record; return its record_id."""
    payload = _minimal_payload("test_kr4_candidate_curve")
    result = stage_import_payload(payload, repo)
    # Return the curve_definition record id (first in list)
    curve_ids = [rid for rid in result.record_ids if "curve_def" in rid]
    assert curve_ids, "No curve_def candidate was staged"
    return curve_ids[0]


@pytest.fixture
def seed_record_id(repo: ManagedKRRepository) -> str:
    """Return the record_id of a known seed curve_definition record."""
    seeds = repo.list_seeds()
    curve_seeds = [r for r in seeds if r.record_type == "curve_definition"]
    assert curve_seeds, "Expected at least one seed curve_definition"
    return curve_seeds[0].record_id


def _minimal_payload(canonical_id: str = "test_curve_kr4") -> ImportPayload:
    return ImportPayload(
        source=ImportSource(
            source_type="manual_import",
            source_label="KR-4 Test Batch",
            source_reference="test_kr4_ref",
        ),
        curve_definitions=[
            ImportCurveDefinition(
                canonical_curve_id=canonical_id,
                display_name="KR-4 Test Curve",
                family="test_family",
                product_group="open_hole_logs",
            )
        ],
    )


_ACTION_BODY = {
    "actor": "test_reviewer",
    "reason": "Reviewed and accepted for KR-4 test",
    "notes": "Automated KR-4 test suite",
}


# ===========================================================================
# TestManagedRecordListing
# ===========================================================================


class TestManagedRecordListing:
    """Tests 1–3: list endpoint filtering."""

    def test_records_endpoint_returns_seed_records(
        self, client_with_repo: TestClient
    ) -> None:
        """Test 1: GET /managed/records returns seed records."""
        resp = client_with_repo.get("/api/wlv/knowledge/managed/records")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kr_version"] == KR4_VERSION
        assert data["count"] > 0
        statuses = {r["status"] for r in data["records"]}
        assert "seed" in statuses, "Expected seed records in /records response"

    def test_records_status_filter_candidate(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """Test 2: GET /managed/records?status=candidate returns staged candidates."""
        resp = client_with_repo.get(
            "/api/wlv/knowledge/managed/records?status=candidate"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] > 0
        record_ids = {r["record_id"] for r in data["records"]}
        assert staged_candidate_id in record_ids
        # All returned records must be candidate
        for r in data["records"]:
            assert r["status"] == "candidate"

    def test_records_record_type_filter(
        self, client_with_repo: TestClient
    ) -> None:
        """Test 3: GET /managed/records?record_type=curve_definition filters correctly."""
        resp = client_with_repo.get(
            "/api/wlv/knowledge/managed/records?record_type=curve_definition"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] > 0
        for r in data["records"]:
            assert r["record_type"] == "curve_definition"

    def test_records_combined_filter(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """Combined status + record_type filter returns correct subset."""
        resp = client_with_repo.get(
            "/api/wlv/knowledge/managed/records?status=candidate&record_type=curve_definition"
        )
        assert resp.status_code == 200
        data = resp.json()
        for r in data["records"]:
            assert r["status"] == "candidate"
            assert r["record_type"] == "curve_definition"


# ===========================================================================
# TestManagedRecordLookup
# ===========================================================================


class TestManagedRecordLookup:
    """Tests 4–5: single record lookup."""

    def test_record_lookup_returns_expected_record(
        self, client_with_repo: TestClient, seed_record_id: str
    ) -> None:
        """Test 4: GET /managed/records/{record_id} returns the expected record."""
        resp = client_with_repo.get(
            f"/api/wlv/knowledge/managed/records/{seed_record_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "record" in data
        assert data["record"]["record_id"] == seed_record_id

    def test_unknown_record_id_returns_404(
        self, client_with_repo: TestClient
    ) -> None:
        """Test 5: Unknown record ID returns 404."""
        resp = client_with_repo.get(
            "/api/wlv/knowledge/managed/records/this_record_does_not_exist_kr4"
        )
        assert resp.status_code == 404

    def test_record_lookup_includes_kr_version(
        self, client_with_repo: TestClient, seed_record_id: str
    ) -> None:
        resp = client_with_repo.get(
            f"/api/wlv/knowledge/managed/records/{seed_record_id}"
        )
        data = resp.json()
        assert data["kr_version"] == KR4_VERSION

    def test_service_get_record_raises_on_unknown(
        self, service: GovernanceService
    ) -> None:
        with pytest.raises(RecordNotFoundError):
            service.get_record("nonexistent_record_id_kr4")


# ===========================================================================
# TestApproveCandidate
# ===========================================================================


class TestApproveCandidate:
    """Tests 6–8: approve workflow."""

    def test_approve_returns_200(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """Test 6: Candidate approve returns HTTP 200."""
        resp = client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/approve",
            json=_ACTION_BODY,
        )
        assert resp.status_code == 200

    def test_approve_response_shape(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        resp = client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/approve",
            json=_ACTION_BODY,
        )
        data = resp.json()
        assert data["ok"] is True
        assert data["kr_version"] == KR4_VERSION
        assert data["record_id"] == staged_candidate_id
        assert data["previous_status"] == "candidate"
        assert data["new_status"] == "approved"
        assert data["production_eligible"] is True

    def test_approved_candidate_status_is_approved(
        self, repo: ManagedKRRepository, staged_candidate_id: str
    ) -> None:
        """Test 7: Approved candidate status becomes approved."""
        svc = GovernanceService(repo)
        svc.approve_record(staged_candidate_id, actor="test_reviewer", reason="Approved")
        record = repo.get_by_id(staged_candidate_id)
        assert record is not None
        assert record.status == GovernanceStatus.APPROVED

    def test_approved_candidate_appears_in_production_eligible(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """Test 8: Approved candidate appears in production-eligible listing."""
        # Before approval: not in production-eligible
        pe_before = client_with_repo.get(
            "/api/wlv/knowledge/managed/production-eligible"
        ).json()
        pe_ids_before = {r["record_id"] for r in pe_before["records"]}
        assert staged_candidate_id not in pe_ids_before

        # Approve
        client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/approve",
            json=_ACTION_BODY,
        )

        # After approval: in production-eligible
        pe_after = client_with_repo.get(
            "/api/wlv/knowledge/managed/production-eligible"
        ).json()
        pe_ids_after = {r["record_id"] for r in pe_after["records"]}
        assert staged_candidate_id in pe_ids_after

    def test_approve_sets_approved_by_field(
        self, repo: ManagedKRRepository, staged_candidate_id: str
    ) -> None:
        svc = GovernanceService(repo)
        svc.approve_record(staged_candidate_id, actor="test_actor")
        record = repo.get_by_id(staged_candidate_id)
        assert getattr(record, "approved_by", None) == "test_actor"


# ===========================================================================
# TestRejectCandidate
# ===========================================================================


class TestRejectCandidate:
    """Tests 9–11: reject workflow."""

    def test_reject_returns_200(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """Test 9: Candidate reject returns HTTP 200."""
        resp = client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/reject",
            json=_ACTION_BODY,
        )
        assert resp.status_code == 200

    def test_rejected_candidate_status_is_rejected(
        self, repo: ManagedKRRepository, staged_candidate_id: str
    ) -> None:
        """Test 10: Rejected candidate status becomes rejected."""
        svc = GovernanceService(repo)
        svc.reject_record(staged_candidate_id, actor="test_reviewer", reason="Not needed")
        record = repo.get_by_id(staged_candidate_id)
        assert record is not None
        assert record.status == GovernanceStatus.REJECTED

    def test_rejected_candidate_not_in_production_eligible(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """Test 11: Rejected candidate does not appear in production-eligible listing."""
        client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/reject",
            json=_ACTION_BODY,
        )
        pe = client_with_repo.get(
            "/api/wlv/knowledge/managed/production-eligible"
        ).json()
        pe_ids = {r["record_id"] for r in pe["records"]}
        assert staged_candidate_id not in pe_ids

    def test_reject_response_shape(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        resp = client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/reject",
            json=_ACTION_BODY,
        )
        data = resp.json()
        assert data["ok"] is True
        assert data["new_status"] == "rejected"
        assert data["production_eligible"] is False


# ===========================================================================
# TestDeprecateRecord
# ===========================================================================


class TestDeprecateRecord:
    """Tests 12–14: deprecate workflow."""

    def test_deprecate_approved_returns_200(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """Test 12: Approved record deprecate returns HTTP 200."""
        # First approve the candidate
        client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/approve",
            json=_ACTION_BODY,
        )
        # Then deprecate the approved record
        resp = client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/deprecate",
            json=_ACTION_BODY,
        )
        assert resp.status_code == 200

    def test_deprecated_record_not_in_production_eligible(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """Test 13: Deprecated record does not appear in production-eligible."""
        # approve then deprecate
        client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/approve",
            json=_ACTION_BODY,
        )
        client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/deprecate",
            json=_ACTION_BODY,
        )
        pe = client_with_repo.get(
            "/api/wlv/knowledge/managed/production-eligible"
        ).json()
        pe_ids = {r["record_id"] for r in pe["records"]}
        assert staged_candidate_id not in pe_ids

    def test_seed_record_deprecate_allowed(
        self, client_with_repo: TestClient, seed_record_id: str
    ) -> None:
        """Test 14: Seed record deprecate is allowed (seed → deprecated is valid)."""
        resp = client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{seed_record_id}/deprecate",
            json=_ACTION_BODY,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["previous_status"] == "seed"
        assert data["new_status"] == "deprecated"

    def test_deprecate_seed_removes_from_production_eligible(
        self, client_with_repo: TestClient, seed_record_id: str
    ) -> None:
        pe_before = client_with_repo.get(
            "/api/wlv/knowledge/managed/production-eligible"
        ).json()
        pe_ids_before = {r["record_id"] for r in pe_before["records"]}
        assert seed_record_id in pe_ids_before, (
            "Seed record should be production-eligible before deprecation"
        )

        client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{seed_record_id}/deprecate",
            json=_ACTION_BODY,
        )

        pe_after = client_with_repo.get(
            "/api/wlv/knowledge/managed/production-eligible"
        ).json()
        pe_ids_after = {r["record_id"] for r in pe_after["records"]}
        assert seed_record_id not in pe_ids_after


# ===========================================================================
# TestInvalidTransitions
# ===========================================================================


class TestInvalidTransitions:
    """Tests 15–20: blocked / error transitions."""

    def test_candidate_to_deprecated_is_blocked(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """Test 15: candidate → deprecated is blocked (HTTP 400)."""
        resp = client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/deprecate",
            json=_ACTION_BODY,
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"] == "invalid_transition"
        assert detail["from_status"] == "candidate"
        assert detail["to_status"] == "deprecated"

    def test_approved_to_rejected_is_blocked(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """Test 16: approved → rejected is blocked (HTTP 400)."""
        client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/approve",
            json=_ACTION_BODY,
        )
        resp = client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/reject",
            json=_ACTION_BODY,
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["from_status"] == "approved"
        assert detail["to_status"] == "rejected"

    def test_rejected_to_approved_is_blocked(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """Test 17: rejected → approved is blocked (HTTP 400)."""
        client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/reject",
            json=_ACTION_BODY,
        )
        resp = client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/approve",
            json=_ACTION_BODY,
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["from_status"] == "rejected"
        assert detail["to_status"] == "approved"

    def test_deprecated_to_approved_is_blocked(
        self, client_with_repo: TestClient, seed_record_id: str
    ) -> None:
        """Test 18: deprecated → approved is blocked (HTTP 400)."""
        # Deprecate a seed record first
        client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{seed_record_id}/deprecate",
            json=_ACTION_BODY,
        )
        resp = client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{seed_record_id}/approve",
            json=_ACTION_BODY,
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["from_status"] == "deprecated"
        assert detail["to_status"] == "approved"

    def test_unknown_record_transition_returns_404(
        self, client_with_repo: TestClient
    ) -> None:
        """Test 19: Unknown record ID returns 404."""
        resp = client_with_repo.post(
            "/api/wlv/knowledge/managed/records/no_such_record_kr4/approve",
            json=_ACTION_BODY,
        )
        assert resp.status_code == 404

    def test_malformed_action_body_returns_422(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """Test 20: Malformed action body returns 422."""
        resp = client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/approve",
            json={"notes": "missing actor field"},  # actor is required
        )
        assert resp.status_code == 422

    def test_service_raises_governance_transition_error(
        self, service: GovernanceService, staged_candidate_id: str
    ) -> None:
        """GovernanceService raises GovernanceTransitionError on invalid transition."""
        with pytest.raises(GovernanceTransitionError) as exc_info:
            service.deprecate_record(staged_candidate_id, actor="test", reason="invalid")
        assert exc_info.value.from_status == GovernanceStatus.CANDIDATE
        assert exc_info.value.to_status == GovernanceStatus.DEPRECATED

    def test_double_approve_is_blocked(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """approved → approved is not a valid transition."""
        client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/approve",
            json=_ACTION_BODY,
        )
        resp = client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/approve",
            json=_ACTION_BODY,
        )
        assert resp.status_code == 400


# ===========================================================================
# TestProductionEligibleListing
# ===========================================================================


class TestProductionEligibleListing:
    """Tests 21–24: production-eligible semantics."""

    def test_production_eligible_returns_seed_records(
        self, client_with_repo: TestClient
    ) -> None:
        """Test 21: Production-eligible listing returns seed records."""
        resp = client_with_repo.get("/api/wlv/knowledge/managed/production-eligible")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kr_version"] == KR4_VERSION
        assert data["count"] > 0
        statuses = {r["status"] for r in data["records"]}
        assert "seed" in statuses
        # No candidates or rejected or deprecated
        assert "candidate" not in statuses
        assert "rejected" not in statuses
        assert "deprecated" not in statuses

    def test_candidate_not_in_production_eligible_before_approval(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """Test 22: Candidate does NOT appear before approval."""
        resp = client_with_repo.get("/api/wlv/knowledge/managed/production-eligible")
        ids = {r["record_id"] for r in resp.json()["records"]}
        assert staged_candidate_id not in ids

    def test_candidate_in_production_eligible_after_approval(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        """Test 23: Candidate DOES appear after approval."""
        client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/approve",
            json=_ACTION_BODY,
        )
        resp = client_with_repo.get("/api/wlv/knowledge/managed/production-eligible")
        ids = {r["record_id"] for r in resp.json()["records"]}
        assert staged_candidate_id in ids

    def test_deprecated_record_disappears_from_production_eligible(
        self, client_with_repo: TestClient, seed_record_id: str
    ) -> None:
        """Test 24: Deprecated record disappears from production-eligible."""
        # Confirm seed is eligible before
        pe_before = {
            r["record_id"]
            for r in client_with_repo.get(
                "/api/wlv/knowledge/managed/production-eligible"
            ).json()["records"]
        }
        assert seed_record_id in pe_before

        client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{seed_record_id}/deprecate",
            json=_ACTION_BODY,
        )

        pe_after = {
            r["record_id"]
            for r in client_with_repo.get(
                "/api/wlv/knowledge/managed/production-eligible"
            ).json()["records"]
        }
        assert seed_record_id not in pe_after

    def test_production_eligible_record_type_filter(
        self, client_with_repo: TestClient
    ) -> None:
        resp = client_with_repo.get(
            "/api/wlv/knowledge/managed/production-eligible?record_type=alias"
        )
        assert resp.status_code == 200
        data = resp.json()
        for r in data["records"]:
            assert r["record_type"] == "alias"


# ===========================================================================
# TestGovernanceAuditFields
# ===========================================================================


class TestGovernanceAuditFields:
    """Tests 25–27: audit metadata on governance actions."""

    def test_governance_history_records_actor(
        self, repo: ManagedKRRepository, staged_candidate_id: str
    ) -> None:
        """Test 25: Governance action records actor."""
        svc = GovernanceService(repo)
        svc.approve_record(staged_candidate_id, actor="audited_actor", reason="Test")
        record = repo.get_by_id(staged_candidate_id)
        assert record is not None
        history = record.governance_history  # type: ignore[union-attr]
        assert len(history) == 1
        assert history[0]["actor"] == "audited_actor"

    def test_governance_history_records_timestamp(
        self, repo: ManagedKRRepository, staged_candidate_id: str
    ) -> None:
        """Test 26: Governance action records timestamp."""
        svc = GovernanceService(repo)
        svc.approve_record(staged_candidate_id, actor="actor", reason="Test")
        record = repo.get_by_id(staged_candidate_id)
        history = record.governance_history  # type: ignore[union-attr]
        assert history[0]["timestamp"] is not None
        # Must be a valid ISO timestamp string
        from datetime import datetime
        dt = datetime.fromisoformat(history[0]["timestamp"])
        assert dt is not None

    def test_governance_history_records_reason(
        self, repo: ManagedKRRepository, staged_candidate_id: str
    ) -> None:
        """Test 27: Governance action records reason."""
        svc = GovernanceService(repo)
        svc.approve_record(
            staged_candidate_id,
            actor="actor",
            reason="My specific approval reason",
        )
        record = repo.get_by_id(staged_candidate_id)
        history = record.governance_history  # type: ignore[union-attr]
        assert history[0]["reason"] == "My specific approval reason"

    def test_governance_history_records_transition(
        self, repo: ManagedKRRepository, staged_candidate_id: str
    ) -> None:
        svc = GovernanceService(repo)
        svc.approve_record(staged_candidate_id, actor="actor", reason="Test")
        record = repo.get_by_id(staged_candidate_id)
        history = record.governance_history  # type: ignore[union-attr]
        assert history[0]["action"] == "approved"
        assert history[0]["previous_status"] == "candidate"
        assert history[0]["new_status"] == "approved"

    def test_governance_history_records_notes(
        self, repo: ManagedKRRepository, staged_candidate_id: str
    ) -> None:
        svc = GovernanceService(repo)
        svc.approve_record(
            staged_candidate_id,
            actor="actor",
            reason="Reason",
            notes="Specific reviewer notes here",
        )
        record = repo.get_by_id(staged_candidate_id)
        history = record.governance_history  # type: ignore[union-attr]
        assert history[0]["notes"] == "Specific reviewer notes here"

    def test_approve_response_record_includes_governance_history(
        self, client_with_repo: TestClient, staged_candidate_id: str
    ) -> None:
        resp = client_with_repo.post(
            f"/api/wlv/knowledge/managed/records/{staged_candidate_id}/approve",
            json=_ACTION_BODY,
        )
        record_data = resp.json()["record"]
        assert "governance_history" in record_data
        assert len(record_data["governance_history"]) == 1

    def test_multiple_actions_append_history(
        self, repo: ManagedKRRepository
    ) -> None:
        """Two governance actions → two history entries on same record."""
        payload = _minimal_payload("multi_action_curve")
        result = stage_import_payload(payload, repo)
        curve_id = [r for r in result.record_ids if "curve_def" in r][0]
        svc = GovernanceService(repo)
        svc.approve_record(curve_id, actor="actor1", reason="Approved")
        svc.deprecate_record(curve_id, actor="actor2", reason="Deprecated")
        record = repo.get_by_id(curve_id)
        history = record.governance_history  # type: ignore[union-attr]
        assert len(history) == 2
        assert history[0]["action"] == "approved"
        assert history[1]["action"] == "deprecated"

    def test_reject_records_actor_in_history(
        self, repo: ManagedKRRepository, staged_candidate_id: str
    ) -> None:
        svc = GovernanceService(repo)
        svc.reject_record(staged_candidate_id, actor="reject_actor", reason="Not needed")
        record = repo.get_by_id(staged_candidate_id)
        history = record.governance_history  # type: ignore[union-attr]
        assert history[0]["actor"] == "reject_actor"
        assert history[0]["action"] == "rejected"


# ===========================================================================
# TestKR1Compatibility
# ===========================================================================

_global_client = TestClient(app)


class TestKR1Compatibility:
    """Tests 24/27/28: KR-1 endpoints unaffected by KR-4."""

    def test_kr1_health_still_200(self) -> None:
        """KR-1 health endpoint returns 200."""
        resp = _global_client.get("/api/wlv/knowledge/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == KR_VERSION

    def test_kr1_product_groups_still_200(self) -> None:
        resp = _global_client.get("/api/wlv/knowledge/product-groups")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["groups"]) == 8

    def test_kr1_curve_definitions_still_200(self) -> None:
        resp = _global_client.get("/api/wlv/knowledge/curve-definitions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["curve_definitions"]) >= 10

    def test_kr1_display_rules_still_200(self) -> None:
        resp = _global_client.get("/api/wlv/knowledge/display-rules")
        assert resp.status_code == 200

    def test_kr1_templates_still_200_and_empty(self) -> None:
        resp = _global_client.get("/api/wlv/knowledge/templates")
        assert resp.status_code == 200
        assert resp.json()["templates"] == []

    def test_candidate_records_do_not_affect_kr1_curve_definitions(
        self, repo: ManagedKRRepository
    ) -> None:
        """Test 27: Candidate records do not affect KR-1 curve definitions."""
        from app.knowledge.repository import KnowledgeRepository
        kr1_repo = KnowledgeRepository()
        count_before = len(kr1_repo.get_curve_definitions().curve_definitions)

        # Stage a candidate
        payload = _minimal_payload("kr4_compat_test_curve")
        stage_import_payload(payload, repo)

        count_after = len(kr1_repo.get_curve_definitions().curve_definitions)
        assert count_before == count_after, (
            "KR-1 curve definition count must not change when candidates are staged"
        )

    def test_production_eligible_count_changes_after_approval_and_deprecation(
        self, repo: ManagedKRRepository
    ) -> None:
        """Test 28: Production-eligible count changes correctly."""
        svc = GovernanceService(repo)

        count_before = len(svc.list_production_eligible_records())

        # Stage and approve → count goes up by 1
        payload = _minimal_payload("pe_count_test_curve")
        result = stage_import_payload(payload, repo)
        curve_id = [r for r in result.record_ids if "curve_def" in r][0]
        svc.approve_record(curve_id, actor="actor", reason="Approved")
        count_after_approve = len(svc.list_production_eligible_records())
        assert count_after_approve == count_before + 1

        # Deprecate → count goes back down by 1
        svc.deprecate_record(curve_id, actor="actor", reason="Deprecated")
        count_after_deprecate = len(svc.list_production_eligible_records())
        assert count_after_deprecate == count_before


# ===========================================================================
# TestKR2Compatibility
# ===========================================================================


class TestKR2Compatibility:
    """KR-2 managed endpoints remain unchanged after KR-4."""

    def test_managed_health_still_200(self) -> None:
        resp = _global_client.get("/api/wlv/knowledge/managed/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "wlv_managed_knowledge_repository"
        assert data["status"] == "ok"

    def test_managed_schema_still_200(self) -> None:
        resp = _global_client.get("/api/wlv/knowledge/managed/schema")
        assert resp.status_code == 200
        data = resp.json()
        rt_keys = {rt["record_type"] for rt in data["record_types"]}
        expected = {
            "curve_definition", "alias", "alias_enrichment", "display_rule",
            "classification_rule", "template_rule", "evidence",
        }
        assert expected == rt_keys

    def test_managed_status_summary_still_200(self) -> None:
        resp = _global_client.get("/api/wlv/knowledge/managed/status-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kr_version"] == "kr-2"
        assert data["total_governed_records"] > 0
        assert data["production_eligible_count"] > 0
        assert data["seed_count"] > 0


# ===========================================================================
# TestKR3Compatibility
# ===========================================================================


class TestKR3Compatibility:
    """KR-3 import/staging remains functional after KR-4."""

    def test_import_preview_still_works(self, client_with_repo: TestClient) -> None:
        resp = client_with_repo.post(
            "/api/wlv/knowledge/managed/import/preview",
            json=_minimal_payload("compat_test").model_dump(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["staged"] is False
        assert data["kr_version"] == "kr-3"

    def test_import_stage_still_works(self, client_with_repo: TestClient) -> None:
        resp = client_with_repo.post(
            "/api/wlv/knowledge/managed/import/stage",
            json=_minimal_payload("compat_stage_test").model_dump(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["staged"] is True

    def test_semantic_invalid_preview_returns_200_valid_false(
        self, client_with_repo: TestClient
    ) -> None:
        """KR-3 contract: semantic validation failure → HTTP 200 with valid=false."""
        payload = {
            "source": {"source_type": "manual_import", "source_label": ""},
            "curve_definitions": [],
        }
        resp = client_with_repo.post(
            "/api/wlv/knowledge/managed/import/preview",
            json=payload,
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    def test_malformed_payload_returns_422(self, client_with_repo: TestClient) -> None:
        """KR-3 contract: malformed JSON → HTTP 422."""
        resp = client_with_repo.post(
            "/api/wlv/knowledge/managed/import/preview",
            json={},  # missing required 'source'
        )
        assert resp.status_code == 422

    def test_staged_candidates_remain_non_production_before_approval(
        self, repo: ManagedKRRepository
    ) -> None:
        """Staged candidates must not appear in production-eligible until approved."""
        payload = _minimal_payload("kr3_compat_non_prod")
        result = stage_import_payload(payload, repo)
        staged_ids = set(result.record_ids)
        pe_ids = {r.record_id for r in repo.list_production_eligible()}
        assert staged_ids.isdisjoint(pe_ids), (
            "Staged candidate IDs must not be production-eligible before approval"
        )
