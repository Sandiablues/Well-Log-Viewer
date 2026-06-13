"""Tests for the WLV Managed Knowledge Repository — KR-2.

Covers:
1.  Managed KR health/status-summary endpoints work.
2.  Seed curve definitions convert to managed records with status="seed".
3.  Seed aliases convert to alias records with status="seed".
4.  Seed display rules convert to display rule records with status="seed".
5.  Record IDs are deterministic (non-empty, unique, stable).
6.  Governance status values validate correctly.
7.  Candidate records are not returned as approved production records
    unless explicitly requested.
8.  Approved records can be listed separately from seed/candidate records.
9.  Existing KR-1 endpoints still pass (compatibility guard).
10. Templates endpoint remains empty (no KR-2 template seeding).

Additional:
- Schema endpoint returns all record types and governance statuses.
- Validation helper catches invalid records.
- Valid governance transitions are enforced.
- promote/deprecate service methods work without HTTP exposure.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.knowledge.governance import (
    GovernanceStatus,
    PRODUCTION_STATUSES,
    TERMINAL_STATUSES,
    is_production_eligible,
    is_valid_transition,
    validate_status,
)
from backend.app.knowledge.managed_models import (
    AliasRecord,
    CurveDefinitionRecord,
    DisplayRuleRecord,
    ClassificationRuleRecord,
    TemplateRuleRecord,
    EvidenceRecord,
)
from backend.app.knowledge.managed_seed import (
    build_seed_curve_definition_records,
    build_seed_alias_records,
    build_seed_display_rule_records,
    build_seed_managed_records,
)
from backend.app.knowledge.managed_repository import ManagedKRRepository
from backend.app.knowledge.models import KR_VERSION

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo() -> ManagedKRRepository:
    """Fresh ManagedKRRepository for each test (isolates mutable state)."""
    return ManagedKRRepository()


# ===========================================================================
# 1. Managed KR health / status-summary endpoints work
# ===========================================================================

class TestManagedEndpoints:
    def test_managed_health_returns_200(self) -> None:
        resp = client.get("/api/wlv/knowledge/managed/health")
        assert resp.status_code == 200

    def test_managed_health_fields(self) -> None:
        data = client.get("/api/wlv/knowledge/managed/health").json()
        assert data["service"] == "wlv_managed_knowledge_repository"
        assert data["status"] == "ok"
        assert data["mode"] == "read_only"
        assert data["kr_version"] == "kr-2"
        assert data["total_record_count"] > 0
        assert data["governed_record_count"] > 0
        assert "status_summary" in data
        assert "type_summary" in data

    def test_managed_health_status_summary_has_all_statuses(self) -> None:
        data = client.get("/api/wlv/knowledge/managed/health").json()
        summary = data["status_summary"]
        for status in GovernanceStatus:
            assert status.value in summary, f"Missing status key: {status.value}"

    def test_managed_schema_returns_200(self) -> None:
        resp = client.get("/api/wlv/knowledge/managed/schema")
        assert resp.status_code == 200

    def test_managed_schema_has_all_record_types(self) -> None:
        data = client.get("/api/wlv/knowledge/managed/schema").json()
        rt_keys = {rt["record_type"] for rt in data["record_types"]}
        expected = {
            "curve_definition", "alias", "alias_enrichment", "display_rule",
            "classification_rule", "template_rule", "evidence",
        }
        assert expected == rt_keys

    def test_managed_schema_has_all_governance_statuses(self) -> None:
        data = client.get("/api/wlv/knowledge/managed/schema").json()
        gs_keys = set(data["governance_statuses"].keys())
        for status in GovernanceStatus:
            assert status.value in gs_keys

    def test_managed_status_summary_returns_200(self) -> None:
        resp = client.get("/api/wlv/knowledge/managed/status-summary")
        assert resp.status_code == 200

    def test_managed_status_summary_fields(self) -> None:
        data = client.get("/api/wlv/knowledge/managed/status-summary").json()
        assert data["kr_version"] == "kr-2"
        assert data["total_governed_records"] > 0
        assert data["production_eligible_count"] > 0
        assert data["seed_count"] > 0
        assert data["candidate_count"] == 0   # No candidates in seed layer
        assert data["approved_count"] == 0    # No approved records yet
        assert "status_by_type" in data


# ===========================================================================
# 2. Seed curve definitions convert to managed records with status="seed"
# ===========================================================================

class TestSeedCurveDefinitions:
    def test_seed_curve_definitions_non_empty(self) -> None:
        records = build_seed_curve_definition_records()
        assert len(records) >= 10

    def test_seed_curve_definitions_all_seed_status(self) -> None:
        for r in build_seed_curve_definition_records():
            assert r.status == GovernanceStatus.SEED, (
                f"Record {r.record_id} has unexpected status {r.status}"
            )

    def test_seed_curve_definitions_type(self) -> None:
        for r in build_seed_curve_definition_records():
            assert isinstance(r, CurveDefinitionRecord)
            assert r.record_type == "curve_definition"

    def test_seed_curve_definitions_required_fields(self) -> None:
        for r in build_seed_curve_definition_records():
            assert r.canonical_curve_id, f"Missing canonical_curve_id on {r.record_id}"
            assert r.display_name, f"Missing display_name on {r.record_id}"
            assert r.family, f"Missing family on {r.record_id}"
            assert r.product_group == "open_hole_logs"

    def test_seed_gamma_ray_curve_definition(self) -> None:
        records = build_seed_curve_definition_records()
        gr = next((r for r in records if r.canonical_curve_id == "gamma_ray"), None)
        assert gr is not None
        assert gr.display_name == "Gamma Ray"
        assert gr.product_subgroup == "gamma_ray"
        assert gr.source_type == "seed"

    def test_seed_resistivity_is_log_display_family(self) -> None:
        from backend.app.knowledge.managed_seed import build_seed_display_rule_records
        rules = build_seed_display_rule_records()
        dr = next((r for r in rules if r.canonical_curve_id == "deep_resistivity"), None)
        assert dr is not None
        assert dr.scale_type == "log"

    def test_repo_contains_seed_curve_definitions(self, repo: ManagedKRRepository) -> None:
        curve_defs = repo.list_records("curve_definition")
        assert len(curve_defs) >= 10
        for r in curve_defs:
            assert r.status == GovernanceStatus.SEED


# ===========================================================================
# 3. Seed aliases convert to alias records with status="seed"
# ===========================================================================

class TestSeedAliases:
    def test_seed_alias_records_non_empty(self) -> None:
        records = build_seed_alias_records()
        assert len(records) >= 10   # At least several aliases across curves

    def test_seed_alias_records_all_seed_status(self) -> None:
        for r in build_seed_alias_records():
            assert r.status == GovernanceStatus.SEED

    def test_seed_alias_records_type(self) -> None:
        for r in build_seed_alias_records():
            assert isinstance(r, AliasRecord)
            assert r.record_type == "alias"

    def test_seed_alias_records_have_required_fields(self) -> None:
        for r in build_seed_alias_records():
            assert r.alias, f"Missing alias on {r.record_id}"
            assert r.normalized_alias, f"Missing normalized_alias on {r.record_id}"
            assert r.canonical_curve_id, f"Missing canonical_curve_id on {r.record_id}"

    def test_seed_alias_gr_present(self) -> None:
        records = build_seed_alias_records()
        gr_aliases = [r for r in records if r.normalized_alias == "GR"]
        assert len(gr_aliases) >= 1
        assert gr_aliases[0].canonical_curve_id == "gamma_ray"

    def test_seed_alias_normalized_is_uppercase(self) -> None:
        for r in build_seed_alias_records():
            assert r.normalized_alias == r.normalized_alias.upper()

    def test_repo_contains_seed_aliases(self, repo: ManagedKRRepository) -> None:
        aliases = repo.list_records("alias")
        assert len(aliases) >= 10
        for r in aliases:
            assert r.status == GovernanceStatus.SEED


# ===========================================================================
# 4. Seed display rules convert to display rule records with status="seed"
# ===========================================================================

class TestSeedDisplayRules:
    def test_seed_display_rules_non_empty(self) -> None:
        records = build_seed_display_rule_records()
        assert len(records) >= 10

    def test_seed_display_rules_all_seed_status(self) -> None:
        for r in build_seed_display_rule_records():
            assert r.status == GovernanceStatus.SEED

    def test_seed_display_rules_type(self) -> None:
        for r in build_seed_display_rule_records():
            assert isinstance(r, DisplayRuleRecord)
            assert r.record_type == "display_rule"

    def test_seed_display_rules_required_fields(self) -> None:
        for r in build_seed_display_rule_records():
            assert r.canonical_curve_id
            assert r.preferred_track_family
            assert r.scale_type in {"linear", "log"}
            assert isinstance(r.display_min, float)
            assert isinstance(r.display_max, float)

    def test_seed_display_neutron_porosity_reverse_scale(self) -> None:
        records = build_seed_display_rule_records()
        np_rule = next(
            (r for r in records if r.canonical_curve_id == "neutron_porosity"), None
        )
        assert np_rule is not None
        assert np_rule.reverse_scale is True  # display_min > display_max

    def test_repo_contains_seed_display_rules(self, repo: ManagedKRRepository) -> None:
        rules = repo.list_records("display_rule")
        assert len(rules) >= 10
        for r in rules:
            assert r.status == GovernanceStatus.SEED


# ===========================================================================
# 5. Record IDs are deterministic, non-empty, and unique
# ===========================================================================

class TestRecordIds:
    def test_curve_def_ids_non_empty(self) -> None:
        for r in build_seed_curve_definition_records():
            assert r.record_id, "record_id must be non-empty"

    def test_alias_ids_non_empty(self) -> None:
        for r in build_seed_alias_records():
            assert r.record_id, "record_id must be non-empty"

    def test_display_ids_non_empty(self) -> None:
        for r in build_seed_display_rule_records():
            assert r.record_id, "record_id must be non-empty"

    def test_seed_record_ids_are_unique(self) -> None:
        all_records = build_seed_managed_records()
        ids = [r.record_id for r in all_records]
        assert len(ids) == len(set(ids)), "Duplicate record_ids found in seed records"

    def test_curve_def_ids_are_deterministic(self) -> None:
        """Build twice; IDs must be identical."""
        ids_a = [r.record_id for r in build_seed_curve_definition_records()]
        ids_b = [r.record_id for r in build_seed_curve_definition_records()]
        assert ids_a == ids_b

    def test_alias_ids_are_deterministic(self) -> None:
        ids_a = [r.record_id for r in build_seed_alias_records()]
        ids_b = [r.record_id for r in build_seed_alias_records()]
        assert ids_a == ids_b

    def test_gamma_ray_curve_def_id_format(self) -> None:
        records = build_seed_curve_definition_records()
        gr = next(r for r in records if r.canonical_curve_id == "gamma_ray")
        assert gr.record_id == "seed_curve_def_gamma_ray"

    def test_gamma_ray_display_id_format(self) -> None:
        records = build_seed_display_rule_records()
        gr = next(r for r in records if r.canonical_curve_id == "gamma_ray")
        assert gr.record_id == "seed_display_gamma_ray"

    def test_repo_record_ids_unique(self, repo: ManagedKRRepository) -> None:
        all_records = repo.list_records()
        ids = [r.record_id for r in all_records]
        assert len(ids) == len(set(ids))


# ===========================================================================
# 6. Governance status values validate correctly
# ===========================================================================

class TestGovernanceStatus:
    def test_all_status_values_exist(self) -> None:
        expected = {"seed", "candidate", "approved", "rejected", "deprecated"}
        actual = {s.value for s in GovernanceStatus}
        assert expected == actual

    def test_validate_status_valid(self) -> None:
        assert validate_status("seed") == GovernanceStatus.SEED
        assert validate_status("candidate") == GovernanceStatus.CANDIDATE
        assert validate_status("approved") == GovernanceStatus.APPROVED
        assert validate_status("rejected") == GovernanceStatus.REJECTED
        assert validate_status("deprecated") == GovernanceStatus.DEPRECATED

    def test_validate_status_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_status("unknown")
        with pytest.raises(ValueError):
            validate_status("")
        with pytest.raises(ValueError):
            validate_status("SEED")   # case-sensitive

    def test_production_statuses(self) -> None:
        assert GovernanceStatus.SEED in PRODUCTION_STATUSES
        assert GovernanceStatus.APPROVED in PRODUCTION_STATUSES
        assert GovernanceStatus.CANDIDATE not in PRODUCTION_STATUSES
        assert GovernanceStatus.REJECTED not in PRODUCTION_STATUSES
        assert GovernanceStatus.DEPRECATED not in PRODUCTION_STATUSES

    def test_terminal_statuses(self) -> None:
        assert GovernanceStatus.REJECTED in TERMINAL_STATUSES
        assert GovernanceStatus.DEPRECATED in TERMINAL_STATUSES
        assert GovernanceStatus.SEED not in TERMINAL_STATUSES
        assert GovernanceStatus.APPROVED not in TERMINAL_STATUSES

    def test_valid_transitions_seed(self) -> None:
        assert is_valid_transition(GovernanceStatus.SEED, GovernanceStatus.APPROVED)
        assert is_valid_transition(GovernanceStatus.SEED, GovernanceStatus.DEPRECATED)
        assert not is_valid_transition(GovernanceStatus.SEED, GovernanceStatus.CANDIDATE)
        assert not is_valid_transition(GovernanceStatus.SEED, GovernanceStatus.REJECTED)

    def test_valid_transitions_candidate(self) -> None:
        assert is_valid_transition(GovernanceStatus.CANDIDATE, GovernanceStatus.APPROVED)
        assert is_valid_transition(GovernanceStatus.CANDIDATE, GovernanceStatus.REJECTED)
        assert not is_valid_transition(GovernanceStatus.CANDIDATE, GovernanceStatus.DEPRECATED)
        assert not is_valid_transition(GovernanceStatus.CANDIDATE, GovernanceStatus.SEED)

    def test_valid_transitions_approved(self) -> None:
        assert is_valid_transition(GovernanceStatus.APPROVED, GovernanceStatus.DEPRECATED)
        assert not is_valid_transition(GovernanceStatus.APPROVED, GovernanceStatus.CANDIDATE)
        assert not is_valid_transition(GovernanceStatus.APPROVED, GovernanceStatus.SEED)

    def test_terminal_statuses_have_no_transitions(self) -> None:
        for status in TERMINAL_STATUSES:
            for target in GovernanceStatus:
                assert not is_valid_transition(status, target), (
                    f"Terminal status {status} should not transition to {target}"
                )

    def test_is_production_eligible(self) -> None:
        assert is_production_eligible(GovernanceStatus.SEED)
        assert is_production_eligible(GovernanceStatus.APPROVED)
        assert not is_production_eligible(GovernanceStatus.CANDIDATE)
        assert not is_production_eligible(GovernanceStatus.REJECTED)
        assert not is_production_eligible(GovernanceStatus.DEPRECATED)


# ===========================================================================
# 7. Candidate records are not returned as approved production records
# ===========================================================================

class TestCandidateIsolation:
    def _make_candidate_record(self) -> CurveDefinitionRecord:
        return CurveDefinitionRecord(
            record_id="cand_test_001",
            canonical_curve_id="test_candidate_curve",
            display_name="Test Candidate Curve",
            family="test_family",
            product_group="open_hole_logs",
            status=GovernanceStatus.CANDIDATE,
            source_type="import",
        )

    def test_candidate_not_in_list_approved(self, repo: ManagedKRRepository) -> None:
        candidate = self._make_candidate_record()
        repo._add_record(candidate)
        approved = repo.list_approved()
        assert all(r.record_id != "cand_test_001" for r in approved)

    def test_candidate_not_in_list_production_eligible(
        self, repo: ManagedKRRepository
    ) -> None:
        candidate = self._make_candidate_record()
        repo._add_record(candidate)
        production = repo.list_production_eligible()
        assert all(r.record_id != "cand_test_001" for r in production)

    def test_candidate_visible_in_list_candidates(
        self, repo: ManagedKRRepository
    ) -> None:
        candidate = self._make_candidate_record()
        repo._add_record(candidate)
        candidates = repo.list_candidates()
        assert any(r.record_id == "cand_test_001" for r in candidates)

    def test_candidate_visible_in_list_records_all(
        self, repo: ManagedKRRepository
    ) -> None:
        candidate = self._make_candidate_record()
        repo._add_record(candidate)
        all_records = repo.list_records()
        assert any(r.record_id == "cand_test_001" for r in all_records)

    def test_candidate_visible_by_status_filter(
        self, repo: ManagedKRRepository
    ) -> None:
        candidate = self._make_candidate_record()
        repo._add_record(candidate)
        filtered = repo.list_records(status=GovernanceStatus.CANDIDATE)
        assert any(r.record_id == "cand_test_001" for r in filtered)

    def test_seed_layer_has_no_candidates_by_default(
        self, repo: ManagedKRRepository
    ) -> None:
        """The seed bootstrap layer must not produce any candidate records."""
        assert len(repo.list_candidates()) == 0

    def test_status_summary_candidate_count_zero_for_seed_only(
        self, repo: ManagedKRRepository
    ) -> None:
        summary = repo.get_status_summary()
        assert summary["candidate"] == 0


# ===========================================================================
# 8. Approved records can be listed separately from seed/candidate records
# ===========================================================================

class TestApprovedListing:
    def test_list_approved_empty_before_promotion(
        self, repo: ManagedKRRepository
    ) -> None:
        """No approved records exist in the seed-only state."""
        assert len(repo.list_approved()) == 0

    def test_promote_seed_to_approved(self, repo: ManagedKRRepository) -> None:
        seed_records = repo.list_seeds()
        assert seed_records, "Need at least one seed record to promote"
        target_id = seed_records[0].record_id
        ok = repo.promote_to_approved(target_id, approved_by="test_user")
        assert ok is True

    def test_promoted_record_appears_in_list_approved(
        self, repo: ManagedKRRepository
    ) -> None:
        seed_records = repo.list_seeds()
        target_id = seed_records[0].record_id
        repo.promote_to_approved(target_id, approved_by="test_user")
        approved = repo.list_approved()
        assert any(r.record_id == target_id for r in approved)

    def test_promoted_record_not_in_list_seeds(
        self, repo: ManagedKRRepository
    ) -> None:
        seed_records = repo.list_seeds()
        target_id = seed_records[0].record_id
        repo.promote_to_approved(target_id, approved_by="test_user")
        seeds_after = repo.list_seeds()
        assert all(r.record_id != target_id for r in seeds_after)

    def test_approved_record_in_production_eligible(
        self, repo: ManagedKRRepository
    ) -> None:
        seed_records = repo.list_seeds()
        target_id = seed_records[0].record_id
        repo.promote_to_approved(target_id, approved_by="test_user")
        production = repo.list_production_eligible()
        assert any(r.record_id == target_id for r in production)

    def test_promote_sets_approved_by(self, repo: ManagedKRRepository) -> None:
        seed_records = repo.list_seeds()
        target_id = seed_records[0].record_id
        repo.promote_to_approved(target_id, approved_by="alice")
        record = repo.get_by_id(target_id)
        assert record is not None
        assert getattr(record, "approved_by", None) == "alice"

    def test_deprecate_service_method(self, repo: ManagedKRRepository) -> None:
        seed_records = repo.list_seeds()
        target_id = seed_records[0].record_id
        ok = repo.deprecate_record(target_id, change_reason="superseded")
        assert ok is True
        deprecated = repo.list_deprecated()
        assert any(r.record_id == target_id for r in deprecated)

    def test_deprecated_not_in_list_seeds(self, repo: ManagedKRRepository) -> None:
        seed_records = repo.list_seeds()
        target_id = seed_records[0].record_id
        repo.deprecate_record(target_id, change_reason="superseded")
        seeds_after = repo.list_seeds()
        assert all(r.record_id != target_id for r in seeds_after)

    def test_invalid_transition_blocked(self, repo: ManagedKRRepository) -> None:
        """Candidate → DEPRECATED is not a valid transition."""
        candidate = CurveDefinitionRecord(
            record_id="cand_transition_test",
            canonical_curve_id="test_curve",
            display_name="Test",
            family="test",
            product_group="open_hole_logs",
            status=GovernanceStatus.CANDIDATE,
        )
        repo._add_record(candidate)
        ok = repo.deprecate_record("cand_transition_test")
        assert ok is False  # Candidate → DEPRECATED is not permitted

    def test_reject_candidate(self, repo: ManagedKRRepository) -> None:
        candidate = CurveDefinitionRecord(
            record_id="cand_reject_test",
            canonical_curve_id="test_curve_2",
            display_name="Test 2",
            family="test",
            product_group="open_hole_logs",
            status=GovernanceStatus.CANDIDATE,
        )
        repo._add_record(candidate)
        ok = repo.reject_record("cand_reject_test", change_reason="low quality")
        assert ok is True
        rejected = repo.list_rejected()
        assert any(r.record_id == "cand_reject_test" for r in rejected)


# ===========================================================================
# 9. KR-1 endpoints still pass (compatibility guard)
# ===========================================================================

class TestKR1Compatibility:
    def test_kr1_health_still_works(self) -> None:
        resp = client.get("/api/wlv/knowledge/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "wlv_knowledge_repository"
        assert data["status"] == "ok"
        assert data["mode"] == "read_only"
        assert data["version"] == KR_VERSION
        assert data["product_group_count"] == 8
        assert data["template_count"] == 0

    def test_kr1_product_groups_still_works(self) -> None:
        resp = client.get("/api/wlv/knowledge/product-groups")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == KR_VERSION
        assert len(data["groups"]) == 8

    def test_kr1_curve_definitions_still_works(self) -> None:
        resp = client.get("/api/wlv/knowledge/curve-definitions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == KR_VERSION
        assert len(data["curve_definitions"]) >= 10

    def test_kr1_display_rules_still_works(self) -> None:
        resp = client.get("/api/wlv/knowledge/display-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == KR_VERSION
        assert len(data["display_rules"]) >= 10

    def test_kr1_templates_still_works(self) -> None:
        resp = client.get("/api/wlv/knowledge/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == KR_VERSION
        assert data["templates"] == []

    def test_kr1_open_hole_subgroup_labels_intact(self) -> None:
        resp = client.get("/api/wlv/knowledge/product-groups")
        data = resp.json()
        open_hole = next(g for g in data["groups"] if g["key"] == "open_hole_logs")
        gamma_ray_sg = next(
            s for s in open_hole["subgroups"] if s["key"] == "gamma_ray"
        )
        assert gamma_ray_sg["label"] == "Gamma Ray"

    def test_kr1_curve_definition_gamma_ray_aliases_intact(self) -> None:
        resp = client.get("/api/wlv/knowledge/curve-definitions")
        data = resp.json()
        gr = next(
            d for d in data["curve_definitions"]
            if d["canonical_curve_id"] == "gamma_ray"
        )
        assert "GR" in gr["aliases"]


# ===========================================================================
# 10. Templates endpoint remains empty — no KR-2 template seeding
# ===========================================================================

class TestTemplatesEmpty:
    def test_kr1_templates_endpoint_empty(self) -> None:
        resp = client.get("/api/wlv/knowledge/templates")
        assert resp.status_code == 200
        assert resp.json()["templates"] == []

    def test_no_template_rule_seeds_exist(self) -> None:
        from backend.app.knowledge.managed_seed import build_seed_managed_records
        from backend.app.knowledge.managed_models import TemplateRuleRecord
        all_records = build_seed_managed_records()
        template_records = [r for r in all_records if isinstance(r, TemplateRuleRecord)]
        assert template_records == [], (
            "No TemplateRuleRecords should be produced by the seed layer in KR-2"
        )

    def test_repo_has_no_template_rules(self, repo: ManagedKRRepository) -> None:
        template_rules = repo.list_records("template_rule")
        assert template_rules == []

    def test_schema_notes_templates_empty(self) -> None:
        data = client.get("/api/wlv/knowledge/managed/schema").json()
        template_rt = next(
            rt for rt in data["record_types"] if rt["record_type"] == "template_rule"
        )
        assert template_rt["seed_count"] == 0


# ===========================================================================
# Additional: schema, validation, and model-structure tests
# ===========================================================================

class TestSchemaAndValidation:
    def test_schema_governance_statuses_production_eligibility(self) -> None:
        data = client.get("/api/wlv/knowledge/managed/schema").json()
        gs = data["governance_statuses"]
        assert gs["seed"]["production_eligible"] is True
        assert gs["approved"]["production_eligible"] is True
        assert gs["candidate"]["production_eligible"] is False
        assert gs["rejected"]["production_eligible"] is False
        assert gs["deprecated"]["production_eligible"] is False

    def test_schema_terminal_statuses(self) -> None:
        data = client.get("/api/wlv/knowledge/managed/schema").json()
        gs = data["governance_statuses"]
        assert gs["rejected"]["terminal"] is True
        assert gs["deprecated"]["terminal"] is True
        assert gs["seed"]["terminal"] is False
        assert gs["approved"]["terminal"] is False

    def test_validate_record_valid(self, repo: ManagedKRRepository) -> None:
        record = CurveDefinitionRecord(
            record_id="test_valid_001",
            canonical_curve_id="test_curve",
            display_name="Test Curve",
            family="gamma_ray",
            product_group="open_hole_logs",
            status=GovernanceStatus.CANDIDATE,
        )
        errors = repo.validate_record(record)
        assert errors == []

    def test_validate_record_missing_canonical_id(
        self, repo: ManagedKRRepository
    ) -> None:
        record = CurveDefinitionRecord(
            record_id="test_invalid_001",
            canonical_curve_id="",  # invalid
            display_name="Test",
            family="test",
            product_group="open_hole_logs",
        )
        errors = repo.validate_record(record)
        assert any("canonical_curve_id" in e for e in errors)

    def test_alias_record_post_init_normalizes(self) -> None:
        r = AliasRecord(
            record_id="test_alias",
            alias="gr",
            canonical_curve_id="gamma_ray",
        )
        assert r.normalized_alias == "GR"

    def test_evidence_record_has_no_status(self) -> None:
        r = EvidenceRecord(
            evidence_id="ev_001",
            source_type="document",
            source_label="API RP 33 Gamma Ray Reference",
        )
        assert not hasattr(r, "status")

    def test_get_by_id_returns_correct_record(
        self, repo: ManagedKRRepository
    ) -> None:
        records = repo.list_records("curve_definition")
        target = records[0]
        fetched = repo.get_by_id(target.record_id)
        assert fetched is not None
        assert fetched.record_id == target.record_id

    def test_get_by_id_unknown_returns_none(
        self, repo: ManagedKRRepository
    ) -> None:
        assert repo.get_by_id("nonexistent_id_xyz") is None

    def test_type_summary_has_expected_keys(
        self, repo: ManagedKRRepository
    ) -> None:
        summary = repo.get_type_summary()
        assert "curve_definition" in summary
        assert "alias" in summary
        assert "display_rule" in summary

    def test_status_summary_all_zeros_except_seed(
        self, repo: ManagedKRRepository
    ) -> None:
        summary = repo.get_status_summary()
        assert summary["seed"] > 0
        assert summary["candidate"] == 0
        assert summary["approved"] == 0
        assert summary["rejected"] == 0
        assert summary["deprecated"] == 0
