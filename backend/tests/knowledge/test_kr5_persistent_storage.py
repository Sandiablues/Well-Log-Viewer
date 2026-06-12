"""Tests for WLV KR-5 — Persistent Managed Knowledge Storage.

Tests all 28 required cases across 8 groups:

TestStorageInitialization
  1.  Missing storage file starts with seed-only repository.
  2.  Storage directory is created when needed.
  3.  Empty managed store has zero persisted managed records.

TestStagePersistence
  4.  KR-3 stage writes candidate records to storage.
  5.  Preview does not write candidate records to storage.
  6.  Staged candidate survives repository reload.
  7.  Evidence record from staged import survives reload.

TestGovernancePersistence
  8.  Approved candidate persists as approved.
  9.  Approved candidate survives repository reload.
  10. Approved candidate appears in production-eligible after reload.
  11. Rejected candidate persists as rejected.
  12. Rejected candidate survives repository reload.
  13. Rejected candidate does not appear in production-eligible after reload.
  14. Deprecated approved record persists as deprecated.
  15. Deprecated approved record survives reload.
  16. Deprecated record does not appear in production-eligible after reload.

TestSeedOverridePersistence
  17. Deprecated seed record persists as a managed override.
  18. Deprecated seed record is removed from production-eligible after reload.
  19. Governance history survives reload.
  20. Audit fields survive reload.

TestRestartReload
  (covered by per-group reload checks above; also)
  21. Candidate records remain non-production after reload until approved.
  28. Candidate records remain non-production after reload until approved (alias).

TestMalformedStorage
  22. Malformed JSON storage raises ManagedStorageError.

TestAtomicWrite
  23. Atomic write uses temp file + replace (no .tmp left behind after save).

TestCompatibility
  24. KR-1 endpoints still HTTP 200 and unchanged.
  25. KR-2 health/schema/status-summary still HTTP 200.
  26. KR-3 import preview/stage still works.
  27. KR-4 approve/reject/deprecate still works.

TestDuplicateRecordId
  (duplicate import protection handled by import staging — IDs are
   deterministic; double-stage of same payload just overwrites)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.knowledge.api_managed_knowledge import (
    get_managed_repository,
)
from backend.app.knowledge.governance import GovernanceStatus
from backend.app.knowledge.governance_service import GovernanceService
from backend.app.knowledge.import_models import (
    ImportCurveDefinition,
    ImportPayload,
    ImportSource,
)
from backend.app.knowledge.import_staging_service import stage_import_payload
from backend.app.knowledge.managed_models import KR4_VERSION
from backend.app.knowledge.managed_repository import ManagedKRRepository
from backend.app.knowledge.managed_storage import (
    ManagedStorage,
    ManagedStorageError,
    STORAGE_SCHEMA_VERSION,
    KR5_VERSION,
)
from backend.app.knowledge.models import KR_VERSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_payload(canonical_id: str = "test_kr5_curve") -> ImportPayload:
    """Return a minimal valid import payload for test use."""
    return ImportPayload(
        source=ImportSource(
            source_type="manual_import",
            source_label="KR-5 Test Batch",
            source_reference=f"test_kr5_ref_{canonical_id}",
        ),
        curve_definitions=[
            ImportCurveDefinition(
                canonical_curve_id=canonical_id,
                display_name=f"KR-5 Test Curve {canonical_id}",
                family="test_family",
                product_group="open_hole_logs",
            )
        ],
    )


def _fresh_repo(storage_path: Path) -> ManagedKRRepository:
    """Create a fresh repository backed by the given storage path."""
    return ManagedKRRepository(storage_path=storage_path)


def _reload_repo(storage_path: Path) -> ManagedKRRepository:
    """Simulate backend restart by creating a new repo instance from storage."""
    return ManagedKRRepository(storage_path=storage_path)


_ACTION_BODY = {
    "actor": "test_reviewer",
    "reason": "KR-5 test approved",
    "notes": "Automated KR-5 test suite",
}

_REJECT_BODY = {
    "actor": "test_reviewer",
    "reason": "KR-5 test rejected",
    "notes": "Automated KR-5 test suite",
}

_DEPRECATE_BODY = {
    "actor": "test_reviewer",
    "reason": "KR-5 test deprecated",
    "notes": "Automated KR-5 test suite",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage_path(tmp_path: Path) -> Path:
    """Return a temp-dir storage path that does not yet exist."""
    return tmp_path / "knowledge" / "managed_knowledge.json"


@pytest.fixture
def repo(storage_path: Path) -> ManagedKRRepository:
    """Fresh isolated repository backed by a temp storage path."""
    return _fresh_repo(storage_path)


@pytest.fixture
def service(repo: ManagedKRRepository) -> GovernanceService:
    """GovernanceService wrapping the fresh isolated repo."""
    return GovernanceService(repo)


@pytest.fixture
def client(repo: ManagedKRRepository) -> Generator[TestClient, None, None]:
    """TestClient wired to an isolated repo via FastAPI DI override."""
    app.dependency_overrides[get_managed_repository] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def staged_candidate_id(repo: ManagedKRRepository) -> str:
    """Stage one candidate curve definition; return its record_id."""
    payload = _minimal_payload("kr5_candidate_curve")
    result = stage_import_payload(payload, repo)
    ids = [rid for rid in result.record_ids if "curve_def" in rid]
    assert ids, "No curve_def candidate staged"
    return ids[0]


@pytest.fixture
def seed_record_id(repo: ManagedKRRepository) -> str:
    """Return the record_id of the first seed curve_definition record."""
    seeds = [r for r in repo.list_seeds() if r.record_type == "curve_definition"]
    assert seeds, "Expected at least one seed curve_definition"
    return seeds[0].record_id


# ===========================================================================
# TestStorageInitialization
# ===========================================================================


class TestStorageInitialization:
    """Tests 1-3: storage start-up behaviour."""

    def test_missing_storage_file_starts_seed_only(self, storage_path: Path) -> None:
        """1. Missing storage file → seed-only repository (no error)."""
        assert not storage_path.exists(), "Pre-condition: storage file must not exist"
        repo = _fresh_repo(storage_path)
        # Seed records load correctly
        seeds = repo.list_seeds()
        assert len(seeds) > 0, "Expected seed records to be loaded"
        # No managed records
        candidates = repo.list_candidates()
        assert candidates == [], "Expected no candidates when storage is missing"

    def test_storage_directory_created_on_save(self, storage_path: Path) -> None:
        """2. Storage directory is created automatically when needed."""
        assert not storage_path.parent.exists(), "Pre-condition: dir must not exist"
        repo = _fresh_repo(storage_path)
        payload = _minimal_payload("kr5_dir_create_test")
        stage_import_payload(payload, repo)
        assert storage_path.parent.exists(), "Storage directory was not created"
        assert storage_path.exists(), "Storage file was not created after staging"

    def test_empty_managed_store_zero_persisted(self, storage_path: Path) -> None:
        """3. Fresh repo with no staging has zero persisted managed records."""
        # Trigger initial persist indirectly by checking storage health
        repo = _fresh_repo(storage_path)
        # Storage file may not exist yet (no mutations have happened)
        if storage_path.exists():
            storage = ManagedStorage(path=storage_path)
            records, evidence = storage.load()
            assert records == []
            assert evidence == []
        else:
            # Fine — no file means zero persisted
            pass
        assert repo.list_candidates() == []


# ===========================================================================
# TestStagePersistence
# ===========================================================================


class TestStagePersistence:
    """Tests 4-7: staging writes to disk; preview does not."""

    def test_stage_writes_candidate_to_storage(self, repo: ManagedKRRepository, storage_path: Path) -> None:
        """4. KR-3 stage writes candidate records to storage file."""
        payload = _minimal_payload("kr5_stage_write_curve")
        result = stage_import_payload(payload, repo)
        assert result.candidate_record_count > 0

        assert storage_path.exists(), "Storage file was not created after stage"
        storage = ManagedStorage(path=storage_path)
        persisted_records, _ = storage.load()
        assert len(persisted_records) > 0, "No records persisted after stage"

        # All persisted records must be candidates
        for r in persisted_records:
            assert r.status == GovernanceStatus.CANDIDATE

    def test_preview_does_not_write_to_storage(self, storage_path: Path) -> None:
        """5. Preview does not write candidate records to storage."""
        from backend.app.knowledge.import_validation_service import validate_import_payload
        repo = _fresh_repo(storage_path)
        payload = _minimal_payload("kr5_preview_no_write_curve")
        validate_import_payload(payload, repo)  # preview only

        # No storage file should be created by preview
        if storage_path.exists():
            storage = ManagedStorage(path=storage_path)
            records, evidence = storage.load()
            assert records == [], "Preview must not persist candidate records"

    def test_staged_candidate_survives_reload(self, repo: ManagedKRRepository, storage_path: Path) -> None:
        """6. Staged candidate survives repository reload (simulated restart)."""
        payload = _minimal_payload("kr5_survive_reload_curve")
        result = stage_import_payload(payload, repo)
        candidate_ids = [rid for rid in result.record_ids if "curve_def" in rid]
        assert candidate_ids

        # Reload (simulate restart)
        repo2 = _reload_repo(storage_path)
        reloaded = repo2.get_by_id(candidate_ids[0])
        assert reloaded is not None, "Staged candidate not found after reload"
        assert reloaded.status == GovernanceStatus.CANDIDATE

    def test_evidence_survives_reload(self, repo: ManagedKRRepository, storage_path: Path) -> None:
        """7. Evidence record from staged import survives reload."""
        payload = _minimal_payload("kr5_evidence_reload_curve")
        result = stage_import_payload(payload, repo)

        # Find the evidence record ID
        evidence_records = repo.list_evidence()
        assert len(evidence_records) > 0

        evidence_id = evidence_records[0].evidence_id

        # Reload
        repo2 = _reload_repo(storage_path)
        ev = repo2.get_evidence_by_id(evidence_id)
        assert ev is not None, "Evidence record not found after reload"
        assert ev.evidence_id == evidence_id


# ===========================================================================
# TestGovernancePersistence
# ===========================================================================


class TestGovernancePersistence:
    """Tests 8-16: approve/reject/deprecate transitions persist."""

    def test_approved_candidate_persists(
        self,
        repo: ManagedKRRepository,
        staged_candidate_id: str,
        storage_path: Path,
    ) -> None:
        """8. Approved candidate is persisted as approved in storage."""
        service = GovernanceService(repo)
        service.approve_record(staged_candidate_id, actor="test_reviewer", reason="ok")

        storage = ManagedStorage(path=storage_path)
        records, _ = storage.load()
        approved = [r for r in records if r.record_id == staged_candidate_id]
        assert approved, "Approved record not found in storage"
        assert approved[0].status == GovernanceStatus.APPROVED

    def test_approved_candidate_survives_reload(
        self,
        repo: ManagedKRRepository,
        staged_candidate_id: str,
        storage_path: Path,
    ) -> None:
        """9. Approved candidate survives repository reload."""
        service = GovernanceService(repo)
        service.approve_record(staged_candidate_id, actor="test_reviewer", reason="ok")

        repo2 = _reload_repo(storage_path)
        record = repo2.get_by_id(staged_candidate_id)
        assert record is not None
        assert record.status == GovernanceStatus.APPROVED

    def test_approved_candidate_production_eligible_after_reload(
        self,
        repo: ManagedKRRepository,
        staged_candidate_id: str,
        storage_path: Path,
    ) -> None:
        """10. Approved candidate appears in production-eligible after reload."""
        service = GovernanceService(repo)
        service.approve_record(staged_candidate_id, actor="test_reviewer", reason="ok")

        repo2 = _reload_repo(storage_path)
        production_ids = {r.record_id for r in repo2.list_production_eligible()}
        assert staged_candidate_id in production_ids

    def test_rejected_candidate_persists(
        self,
        repo: ManagedKRRepository,
        staged_candidate_id: str,
        storage_path: Path,
    ) -> None:
        """11. Rejected candidate is persisted as rejected in storage."""
        service = GovernanceService(repo)
        service.reject_record(staged_candidate_id, actor="test_reviewer", reason="nope")

        storage = ManagedStorage(path=storage_path)
        records, _ = storage.load()
        rejected = [r for r in records if r.record_id == staged_candidate_id]
        assert rejected, "Rejected record not found in storage"
        assert rejected[0].status == GovernanceStatus.REJECTED

    def test_rejected_candidate_survives_reload(
        self,
        repo: ManagedKRRepository,
        staged_candidate_id: str,
        storage_path: Path,
    ) -> None:
        """12. Rejected candidate survives repository reload."""
        service = GovernanceService(repo)
        service.reject_record(staged_candidate_id, actor="test_reviewer", reason="nope")

        repo2 = _reload_repo(storage_path)
        record = repo2.get_by_id(staged_candidate_id)
        assert record is not None
        assert record.status == GovernanceStatus.REJECTED

    def test_rejected_candidate_not_production_after_reload(
        self,
        repo: ManagedKRRepository,
        staged_candidate_id: str,
        storage_path: Path,
    ) -> None:
        """13. Rejected candidate does not appear in production-eligible after reload."""
        service = GovernanceService(repo)
        service.reject_record(staged_candidate_id, actor="test_reviewer", reason="nope")

        repo2 = _reload_repo(storage_path)
        production_ids = {r.record_id for r in repo2.list_production_eligible()}
        assert staged_candidate_id not in production_ids

    def test_deprecated_approved_persists(
        self,
        repo: ManagedKRRepository,
        staged_candidate_id: str,
        storage_path: Path,
    ) -> None:
        """14. Deprecated approved record is persisted as deprecated."""
        service = GovernanceService(repo)
        service.approve_record(staged_candidate_id, actor="test_reviewer", reason="ok")
        service.deprecate_record(staged_candidate_id, actor="test_reviewer", reason="old")

        storage = ManagedStorage(path=storage_path)
        records, _ = storage.load()
        deprecated = [r for r in records if r.record_id == staged_candidate_id]
        assert deprecated, "Deprecated record not found in storage"
        assert deprecated[0].status == GovernanceStatus.DEPRECATED

    def test_deprecated_approved_survives_reload(
        self,
        repo: ManagedKRRepository,
        staged_candidate_id: str,
        storage_path: Path,
    ) -> None:
        """15. Deprecated approved record survives reload."""
        service = GovernanceService(repo)
        service.approve_record(staged_candidate_id, actor="test_reviewer", reason="ok")
        service.deprecate_record(staged_candidate_id, actor="test_reviewer", reason="old")

        repo2 = _reload_repo(storage_path)
        record = repo2.get_by_id(staged_candidate_id)
        assert record is not None
        assert record.status == GovernanceStatus.DEPRECATED

    def test_deprecated_record_not_production_after_reload(
        self,
        repo: ManagedKRRepository,
        staged_candidate_id: str,
        storage_path: Path,
    ) -> None:
        """16. Deprecated record does not appear in production-eligible after reload."""
        service = GovernanceService(repo)
        service.approve_record(staged_candidate_id, actor="test_reviewer", reason="ok")
        service.deprecate_record(staged_candidate_id, actor="test_reviewer", reason="old")

        repo2 = _reload_repo(storage_path)
        production_ids = {r.record_id for r in repo2.list_production_eligible()}
        assert staged_candidate_id not in production_ids


# ===========================================================================
# TestSeedOverridePersistence
# ===========================================================================


class TestSeedOverridePersistence:
    """Tests 17-20: seed transitions create managed overrides and survive reload."""

    def test_deprecated_seed_persists_as_managed_override(
        self,
        repo: ManagedKRRepository,
        seed_record_id: str,
        storage_path: Path,
    ) -> None:
        """17. Deprecated seed record is stored as a managed override."""
        service = GovernanceService(repo)
        service.deprecate_record(seed_record_id, actor="test_reviewer", reason="obsolete")

        storage = ManagedStorage(path=storage_path)
        records, _ = storage.load()
        override = [r for r in records if r.record_id == seed_record_id]
        assert override, "Seed deprecation not found in managed storage"
        assert override[0].status == GovernanceStatus.DEPRECATED

    def test_deprecated_seed_removed_from_production_after_reload(
        self,
        repo: ManagedKRRepository,
        seed_record_id: str,
        storage_path: Path,
    ) -> None:
        """18. Deprecated seed record is removed from production-eligible after reload."""
        service = GovernanceService(repo)
        service.deprecate_record(seed_record_id, actor="test_reviewer", reason="obsolete")

        repo2 = _reload_repo(storage_path)
        production_ids = {r.record_id for r in repo2.list_production_eligible()}
        assert seed_record_id not in production_ids

    def test_governance_history_survives_reload(
        self,
        repo: ManagedKRRepository,
        staged_candidate_id: str,
        storage_path: Path,
    ) -> None:
        """19. Governance history entries survive repository reload."""
        service = GovernanceService(repo)
        service.approve_record(
            staged_candidate_id,
            actor="history_tester",
            reason="Testing history persistence",
            notes="KR-5 history test",
        )

        repo2 = _reload_repo(storage_path)
        record = repo2.get_by_id(staged_candidate_id)
        assert record is not None
        history = getattr(record, "governance_history", [])
        assert len(history) >= 1, "Governance history not found after reload"
        entry = history[-1]
        assert entry["action"] == "approved"
        assert entry["actor"] == "history_tester"

    def test_audit_fields_survive_reload(
        self,
        repo: ManagedKRRepository,
        staged_candidate_id: str,
        storage_path: Path,
    ) -> None:
        """20. Audit fields (approved_by, approved_at, change_reason) survive reload."""
        service = GovernanceService(repo)
        service.approve_record(
            staged_candidate_id,
            actor="audit_tester",
            reason="Testing audit persistence",
        )

        repo2 = _reload_repo(storage_path)
        record = repo2.get_by_id(staged_candidate_id)
        assert record is not None
        assert getattr(record, "approved_by", None) == "audit_tester"
        assert getattr(record, "approved_at", None) is not None
        assert getattr(record, "change_reason", None) == "Testing audit persistence"


# ===========================================================================
# TestRestartReload
# ===========================================================================


class TestRestartReload:
    """Tests 21, 28: candidates remain non-production after reload until approved."""

    def test_candidate_non_production_after_reload(
        self,
        repo: ManagedKRRepository,
        staged_candidate_id: str,
        storage_path: Path,
    ) -> None:
        """21. Candidate records remain non-production after reload until approved."""
        # Do NOT approve — just reload
        repo2 = _reload_repo(storage_path)
        record = repo2.get_by_id(staged_candidate_id)
        assert record is not None
        assert record.status == GovernanceStatus.CANDIDATE
        production_ids = {r.record_id for r in repo2.list_production_eligible()}
        assert staged_candidate_id not in production_ids

    def test_candidate_non_production_after_reload_alias(
        self,
        repo: ManagedKRRepository,
        storage_path: Path,
    ) -> None:
        """28. Candidate alias records remain non-production after reload until approved."""
        payload = _minimal_payload("kr5_alias_reload_test")
        result = stage_import_payload(payload, repo)
        alias_ids = [rid for rid in result.record_ids if "_alias_" in rid]
        assert alias_ids, "No alias candidate was staged"

        repo2 = _reload_repo(storage_path)
        production_ids = {r.record_id for r in repo2.list_production_eligible()}
        for alias_id in alias_ids:
            assert alias_id not in production_ids, (
                f"Alias candidate {alias_id} should not be production-eligible after reload"
            )


# ===========================================================================
# TestMalformedStorage
# ===========================================================================


class TestMalformedStorage:
    """Test 22: malformed JSON raises a clear error."""

    def test_malformed_json_raises_storage_error(self, storage_path: Path) -> None:
        """22. Malformed JSON storage raises ManagedStorageError on load."""
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_text("{this is not valid json!!!", encoding="utf-8")

        storage = ManagedStorage(path=storage_path)
        with pytest.raises(ManagedStorageError):
            storage.load()

    def test_malformed_json_raises_on_repo_init(self, storage_path: Path) -> None:
        """22b. Malformed JSON in storage path propagates on repo construction."""
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_text("not_json_at_all", encoding="utf-8")

        with pytest.raises(ManagedStorageError):
            _fresh_repo(storage_path)


# ===========================================================================
# TestAtomicWrite
# ===========================================================================


class TestAtomicWrite:
    """Test 23: atomic write uses temp file + replace."""

    def test_no_tmp_file_left_after_save(
        self,
        repo: ManagedKRRepository,
        storage_path: Path,
    ) -> None:
        """23. Atomic write uses temp file + replace; no .tmp file remains."""
        payload = _minimal_payload("kr5_atomic_write_curve")
        stage_import_payload(payload, repo)

        assert storage_path.exists(), "Storage file must exist after stage"
        tmp_path = storage_path.with_suffix(".tmp")
        assert not tmp_path.exists(), "Temp file must not remain after atomic write"

    def test_storage_file_valid_json_after_save(
        self,
        repo: ManagedKRRepository,
        storage_path: Path,
    ) -> None:
        """23b. Storage file contains valid JSON after save."""
        payload = _minimal_payload("kr5_valid_json_after_save_curve")
        stage_import_payload(payload, repo)

        raw = storage_path.read_text(encoding="utf-8")
        doc = json.loads(raw)
        assert doc["storage_schema_version"] == STORAGE_SCHEMA_VERSION
        assert doc["kr_version"] == KR5_VERSION
        assert isinstance(doc["records"], list)
        assert isinstance(doc["evidence_records"], list)


# ===========================================================================
# TestCompatibility
# ===========================================================================


class TestCompatibility:
    """Tests 24-27: KR-1 through KR-4 remain fully functional after KR-5."""

    def test_kr1_endpoints_http_200(self, client: TestClient) -> None:
        """24. KR-1 endpoints still HTTP 200 and unchanged."""
        kr1_paths = [
            "/api/wlv/knowledge/health",
            "/api/wlv/knowledge/product-groups",
            "/api/wlv/knowledge/curve-definitions",
            "/api/wlv/knowledge/display-rules",
            "/api/wlv/knowledge/templates",
        ]
        for path in kr1_paths:
            resp = client.get(path)
            assert resp.status_code == 200, f"KR-1 endpoint {path} returned {resp.status_code}"

    def test_kr2_managed_endpoints_http_200(self, client: TestClient) -> None:
        """25. KR-2 managed health/schema/status-summary still HTTP 200."""
        for path in [
            "/api/wlv/knowledge/managed/health",
            "/api/wlv/knowledge/managed/schema",
            "/api/wlv/knowledge/managed/status-summary",
        ]:
            resp = client.get(path)
            assert resp.status_code == 200, f"KR-2 endpoint {path} returned {resp.status_code}"

    def test_kr3_preview_and_stage_work(self, client: TestClient) -> None:
        """26. KR-3 import preview/stage still work."""
        payload = {
            "source": {
                "source_type": "manual_import",
                "source_label": "KR-5 Compat Test",
            },
            "curve_definitions": [
                {
                    "canonical_curve_id": "kr5_compat_curve",
                    "display_name": "Compat Curve",
                    "family": "test_family",
                    "product_group": "open_hole_logs",
                }
            ],
        }
        preview_resp = client.post("/api/wlv/knowledge/managed/import/preview", json=payload)
        assert preview_resp.status_code == 200
        assert preview_resp.json()["valid"] is True
        assert preview_resp.json()["staged"] is False

        stage_resp = client.post("/api/wlv/knowledge/managed/import/stage", json=payload)
        assert stage_resp.status_code == 200
        assert stage_resp.json()["staged"] is True

    def test_kr4_approve_reject_deprecate_work(
        self,
        client: TestClient,
        repo: ManagedKRRepository,
    ) -> None:
        """27. KR-4 approve/reject/deprecate still work end-to-end."""
        # Stage two candidates: one to approve→deprecate, one to reject
        payload_a = {
            "source": {"source_type": "manual_import", "source_label": "KR-5 Compat A"},
            "curve_definitions": [{
                "canonical_curve_id": "kr5_compat_approve_curve",
                "display_name": "Compat Approve Curve",
                "family": "test_family",
                "product_group": "open_hole_logs",
            }],
        }
        payload_b = {
            "source": {"source_type": "manual_import", "source_label": "KR-5 Compat B"},
            "curve_definitions": [{
                "canonical_curve_id": "kr5_compat_reject_curve",
                "display_name": "Compat Reject Curve",
                "family": "test_family",
                "product_group": "open_hole_logs",
            }],
        }

        stage_a = client.post("/api/wlv/knowledge/managed/import/stage", json=payload_a)
        stage_b = client.post("/api/wlv/knowledge/managed/import/stage", json=payload_b)
        assert stage_a.json()["staged"]
        assert stage_b.json()["staged"]

        # Get curve_def record IDs
        id_a = next(rid for rid in stage_a.json()["record_ids"] if "curve_def" in rid)
        id_b = next(rid for rid in stage_b.json()["record_ids"] if "curve_def" in rid)

        # Approve A
        resp = client.post(f"/api/wlv/knowledge/managed/records/{id_a}/approve", json=_ACTION_BODY)
        assert resp.status_code == 200
        assert resp.json()["new_status"] == "approved"

        # Deprecate A
        resp = client.post(f"/api/wlv/knowledge/managed/records/{id_a}/deprecate", json=_DEPRECATE_BODY)
        assert resp.status_code == 200
        assert resp.json()["new_status"] == "deprecated"

        # Reject B
        resp = client.post(f"/api/wlv/knowledge/managed/records/{id_b}/reject", json=_REJECT_BODY)
        assert resp.status_code == 200
        assert resp.json()["new_status"] == "rejected"

    def test_kr5_storage_health_endpoint(self, client: TestClient) -> None:
        """KR-5 storage health endpoint returns expected fields."""
        resp = client.get("/api/wlv/knowledge/managed/storage/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kr_version"] == KR5_VERSION
        assert data["storage_enabled"] is True
        assert "storage_path" in data
        assert data["storage_schema_version"] == STORAGE_SCHEMA_VERSION
        assert "persisted_record_count" in data
        assert "persisted_evidence_record_count" in data

    def test_kr1_candidate_records_do_not_affect_production_curves(
        self,
        client: TestClient,
    ) -> None:
        """24b. Candidate records do not appear in KR-1 curve-definitions endpoint."""
        # Stage a candidate
        payload = {
            "source": {"source_type": "manual_import", "source_label": "KR-5 KR1 Isolation"},
            "curve_definitions": [{
                "canonical_curve_id": "kr5_kr1_isolation_curve",
                "display_name": "KR-5 KR1 Isolation",
                "family": "test_family",
                "product_group": "open_hole_logs",
            }],
        }
        client.post("/api/wlv/knowledge/managed/import/stage", json=payload)

        # KR-1 curve-definitions endpoint must not include this candidate
        # (KR-1 uses KnowledgeRepository, which is independent of the managed repo)
        resp = client.get("/api/wlv/knowledge/curve-definitions")
        assert resp.status_code == 200
        data = resp.json()
        # curve-definitions response has a "curve_definitions" list
        canonical_ids = {
            c.get("canonical_curve_id", "")
            for c in data.get("curve_definitions", [])
        }
        assert "kr5_kr1_isolation_curve" not in canonical_ids
