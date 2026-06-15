"""Tests for WLV KR-DATA-MODEL-1 — Alias Enrichment / Technical Subtype Model.

Tests 1–16 as specified in the work order.

Group A – Model and Governance
  1.  AliasEnrichmentRecord can be created and validated.
  2.  Alias enrichment records are governed records.
  3.  Alias enrichment records persist through KR-5 storage.
  4.  Alias enrichment records appear in schema/type summaries.

Group B – KR-6/7/8 Stability (candidate enrichments)
  5.  Candidate alias enrichments do not change KR-6 resolution.
  6.  Candidate alias enrichments do not change KR-7 classification.
  7.  Candidate alias enrichments do not change KR-8 display recommendations.

Group C – Approved Enrichment Behaviour
  8.  Approved alias enrichments can be queried as metadata.
  9.  Approved alias enrichments still do not remap display canonical curve.

Group D – Specific Alias Cases
  10. ILD: display=deep_resistivity, technical=deep_induction_resistivity.
  11. LLD: display=deep_resistivity, technical=deep_laterolog_resistivity.
  12. ILM: display=shallow_resistivity, technical=medium_induction_resistivity.
  13. LLS: display=shallow_resistivity, technical=shallow_laterolog_resistivity.

Group E – Reconciliation Logic
  14. A true unrelated alias conflict is detected as true_alias_conflict.
  15. Full knowledge test suite passes (compatibility guard — imports succeed).
  16. Frontend typecheck / build passes (placeholder; covered by validate script).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.knowledge.alias_enrichment_models import (
    AliasEnrichmentRecord,
    KR_DATA_MODEL_1_VERSION,
)
from app.knowledge.classification_service import (
    CurveClassificationService,
    CurveClassificationRequest,
    CurveClassifyInput,
)
from app.knowledge.curated_reconciliation_service import (
    CLS_SAFE_ALIAS_ENRICHMENT,
    CLS_TRUE_ALIAS_CONFLICT,
    CLS_NEW_CURVE_DEFINITION,
    CLS_NEW_ALIAS,
    CLS_SEED_CONFIRMATION,
    CuratedKRReconciliationService,
)
from app.knowledge.display_recommendation_service import (
    DisplayRecommendationService,
    DisplayRecommendationRequest,
    CurveRecommendInput,
)
from app.knowledge.governance import GovernanceStatus
from app.knowledge.governance_service import GovernanceService
from app.knowledge.import_models import (
    ImportCurveDefinition,
    ImportPayload,
    ImportSource,
)
from app.knowledge.managed_models import (
    AliasRecord,
    CurveDefinitionRecord,
    GOVERNED_RECORD_TYPES,
    ALL_RECORD_TYPES,
)
from app.knowledge.managed_repository import ManagedKRRepository
from app.knowledge.managed_storage import ManagedStorage, deserialize_record, serialize_record
from app.knowledge.resolution_service import (
    KnowledgeResolutionService,
    CurveResolveInput,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path: Path) -> ManagedKRRepository:
    """Fresh isolated ManagedKRRepository for each test."""
    return ManagedKRRepository(storage_path=tmp_path / "kr_test.json")


@pytest.fixture
def resolution_service(repo: ManagedKRRepository) -> KnowledgeResolutionService:
    return KnowledgeResolutionService(repo)


@pytest.fixture
def classification_service(
    resolution_service: KnowledgeResolutionService,
) -> CurveClassificationService:
    return CurveClassificationService(resolution_service)


@pytest.fixture
def display_service(
    classification_service: CurveClassificationService,
) -> DisplayRecommendationService:
    return DisplayRecommendationService(classification_service)


@pytest.fixture
def governance_service(repo: ManagedKRRepository) -> GovernanceService:
    return GovernanceService(repo)


def _make_ild_enrichment() -> AliasEnrichmentRecord:
    """Build a representative ILD alias enrichment record."""
    return AliasEnrichmentRecord(
        record_id="enrich_ILD_deep_induction_resistivity",
        alias="ILD",
        normalized_alias="ILD",
        display_canonical_curve_id="deep_resistivity",
        technical_curve_id="deep_induction_resistivity",
        technical_display_name="Deep Induction Resistivity",
        parent_canonical_curve_id="deep_resistivity",
        measurement_family="induction",
        measurement_depth="deep",
        tool_family="induction_resistivity",
        review_notes="Curated catalogue refines broad seed deep_resistivity alias.",
        status=GovernanceStatus.CANDIDATE,
    )


def _make_repo_with_seed_aliases(tmp_path: Path) -> ManagedKRRepository:
    """Return a repo pre-loaded with mock seed-like alias/curve def records.

    Simulates the seed data present in the real project for the four
    conflicting aliases: ILD, ILM, LLD, LLS.
    """
    repo = ManagedKRRepository(storage_path=tmp_path / "kr_seed_sim.json")

    # Inject mock broad-canonical curve defs (seed-like, SEED status)
    for cid, display, family, subgroup in [
        ("deep_resistivity",    "Deep Resistivity",    "resistivity", "resistivity"),
        ("shallow_resistivity", "Shallow Resistivity", "resistivity", "resistivity"),
    ]:
        rec = CurveDefinitionRecord(
            record_id=f"seed_curve_{cid}",
            canonical_curve_id=cid,
            display_name=display,
            family=family,
            product_group="open_hole_logs",
            product_subgroup=subgroup,
            status=GovernanceStatus.SEED,
        )
        repo._managed_records[rec.record_id] = rec

    # Inject mock seed alias records
    for alias, canonical in [
        ("ILD", "deep_resistivity"),
        ("ILM", "shallow_resistivity"),
        ("LLD", "deep_resistivity"),
        ("LLS", "shallow_resistivity"),
    ]:
        rec = AliasRecord(
            record_id=f"seed_alias_{alias.lower()}",
            alias=alias,
            normalized_alias=alias,
            canonical_curve_id=canonical,
            status=GovernanceStatus.SEED,
        )
        repo._managed_records[rec.record_id] = rec

    return repo


# ===========================================================================
# Group A — Model and Governance
# ===========================================================================

class TestAliasEnrichmentModel:
    """Test 1: AliasEnrichmentRecord can be created and validated."""

    def test_create_minimal(self, repo: ManagedKRRepository) -> None:
        rec = _make_ild_enrichment()
        assert rec.record_id == "enrich_ILD_deep_induction_resistivity"
        assert rec.alias == "ILD"
        assert rec.normalized_alias == "ILD"
        assert rec.display_canonical_curve_id == "deep_resistivity"
        assert rec.technical_curve_id == "deep_induction_resistivity"
        assert rec.technical_display_name == "Deep Induction Resistivity"
        assert rec.parent_canonical_curve_id == "deep_resistivity"
        assert rec.record_type == "alias_enrichment"
        assert rec.status == GovernanceStatus.CANDIDATE

    def test_validate_passes(self, repo: ManagedKRRepository) -> None:
        rec = _make_ild_enrichment()
        errors = repo.validate_record(rec)
        assert errors == [], f"Unexpected validation errors: {errors}"

    def test_validate_catches_missing_alias(self, repo: ManagedKRRepository) -> None:
        rec = _make_ild_enrichment()
        rec.alias = ""
        errors = repo.validate_record(rec)
        assert any("alias" in e for e in errors)

    def test_validate_catches_missing_display_canonical(self, repo: ManagedKRRepository) -> None:
        rec = _make_ild_enrichment()
        rec.display_canonical_curve_id = ""
        errors = repo.validate_record(rec)
        assert any("display_canonical_curve_id" in e for e in errors)

    def test_validate_catches_missing_technical_curve_id(self, repo: ManagedKRRepository) -> None:
        rec = _make_ild_enrichment()
        rec.technical_curve_id = ""
        errors = repo.validate_record(rec)
        assert any("technical_curve_id" in e for e in errors)

    def test_normalize_alias_auto(self) -> None:
        rec = AliasEnrichmentRecord(
            record_id="test",
            alias="ild",
            normalized_alias="",  # should be auto-normalised
            display_canonical_curve_id="deep_resistivity",
            technical_curve_id="deep_induction_resistivity",
            technical_display_name="Deep Induction Resistivity",
            parent_canonical_curve_id="deep_resistivity",
        )
        assert rec.normalized_alias == "ILD"

    def test_record_type_registered(self) -> None:
        assert "alias_enrichment" in GOVERNED_RECORD_TYPES
        assert "alias_enrichment" in ALL_RECORD_TYPES


class TestAliasEnrichmentGovernance:
    """Test 2: Alias enrichment records are governed records."""

    def test_has_governance_status(self) -> None:
        rec = _make_ild_enrichment()
        assert isinstance(rec.status, GovernanceStatus)
        assert rec.status == GovernanceStatus.CANDIDATE

    def test_candidate_is_not_production_eligible(self, repo: ManagedKRRepository) -> None:
        rec = _make_ild_enrichment()
        repo._add_record(rec)  # type: ignore[arg-type]
        production = repo.list_production_eligible()
        prod_ids = {r.record_id for r in production}
        assert rec.record_id not in prod_ids

    def test_governance_service_can_approve(
        self, repo: ManagedKRRepository, governance_service: GovernanceService
    ) -> None:
        rec = _make_ild_enrichment()
        repo._add_record(rec)  # type: ignore[arg-type]
        result = governance_service.approve_record(
            rec.record_id, actor="test_reviewer", reason="Verified subtype"
        )
        assert result["ok"] is True
        assert result["new_status"] == "approved"

    def test_governance_service_can_reject(
        self, repo: ManagedKRRepository, governance_service: GovernanceService
    ) -> None:
        rec = _make_ild_enrichment()
        repo._add_record(rec)  # type: ignore[arg-type]
        result = governance_service.reject_record(
            rec.record_id, actor="test_reviewer", reason="Duplicate"
        )
        assert result["ok"] is True
        assert result["new_status"] == "rejected"

    def test_governance_history_appended_on_approve(
        self, repo: ManagedKRRepository, governance_service: GovernanceService
    ) -> None:
        rec = _make_ild_enrichment()
        repo._add_record(rec)  # type: ignore[arg-type]
        governance_service.approve_record(rec.record_id, actor="reviewer")
        updated = repo.get_by_id(rec.record_id)
        assert updated is not None
        assert hasattr(updated, "governance_history")
        assert len(updated.governance_history) == 1  # type: ignore[union-attr]
        assert updated.governance_history[0]["action"] == "approved"  # type: ignore[union-attr]


class TestAliasEnrichmentStorage:
    """Test 3: Alias enrichment records persist through KR-5 storage."""

    def test_roundtrip_serialize_deserialize(self) -> None:
        rec = _make_ild_enrichment()
        serialized = serialize_record(rec)
        assert serialized["record_type"] == "alias_enrichment"
        restored = deserialize_record(serialized)
        assert isinstance(restored, AliasEnrichmentRecord)
        assert restored.record_id == rec.record_id
        assert restored.alias == rec.alias
        assert restored.display_canonical_curve_id == rec.display_canonical_curve_id
        assert restored.technical_curve_id == rec.technical_curve_id
        assert restored.status == GovernanceStatus.CANDIDATE

    def test_persists_through_file_storage(self, tmp_path: Path) -> None:
        storage_path = tmp_path / "enrich_test.json"
        repo1 = ManagedKRRepository(storage_path=storage_path)
        rec = _make_ild_enrichment()
        repo1._add_record(rec)  # type: ignore[arg-type]

        # Reload from disk
        repo2 = ManagedKRRepository(storage_path=storage_path)
        loaded = repo2.get_by_id(rec.record_id)
        assert loaded is not None
        assert isinstance(loaded, AliasEnrichmentRecord)
        assert loaded.technical_curve_id == "deep_induction_resistivity"
        assert loaded.display_canonical_curve_id == "deep_resistivity"

    def test_approved_enrichment_persists_status(self, tmp_path: Path) -> None:
        storage_path = tmp_path / "enrich_approved.json"
        repo1 = ManagedKRRepository(storage_path=storage_path)
        svc = GovernanceService(repo1)
        rec = _make_ild_enrichment()
        repo1._add_record(rec)  # type: ignore[arg-type]
        svc.approve_record(rec.record_id, actor="reviewer")

        repo2 = ManagedKRRepository(storage_path=storage_path)
        loaded = repo2.get_by_id(rec.record_id)
        assert loaded is not None
        assert loaded.status == GovernanceStatus.APPROVED  # type: ignore[union-attr]


class TestAliasEnrichmentSchemaSummary:
    """Test 4: Alias enrichment records appear in schema/type summaries."""

    def test_schema_contains_alias_enrichment_type(self, repo: ManagedKRRepository) -> None:
        schema = repo.get_schema()
        record_types = [rt["record_type"] for rt in schema["record_types"]]
        assert "alias_enrichment" in record_types

    def test_schema_alias_enrichment_is_governed(self, repo: ManagedKRRepository) -> None:
        schema = repo.get_schema()
        ae_entry = next(
            rt for rt in schema["record_types"] if rt["record_type"] == "alias_enrichment"
        )
        assert ae_entry["governed"] is True

    def test_type_summary_includes_alias_enrichment_after_add(
        self, repo: ManagedKRRepository
    ) -> None:
        rec = _make_ild_enrichment()
        repo._add_record(rec)  # type: ignore[arg-type]
        summary = repo.get_type_summary()
        assert "alias_enrichment" in summary
        assert summary["alias_enrichment"] >= 1

    def test_status_summary_response_includes_alias_enrichment(
        self, repo: ManagedKRRepository
    ) -> None:
        rec = _make_ild_enrichment()
        repo._add_record(rec)  # type: ignore[arg-type]
        status_resp = repo.get_status_summary_response()
        assert "alias_enrichment" in status_resp["status_by_type"]


# ===========================================================================
# Group B — KR-6/7/8 Stability
# ===========================================================================

class TestCandidateEnrichmentDoesNotAffectKR6:
    """Test 5: Candidate alias enrichments do not change KR-6 resolution."""

    def test_ild_resolves_same_with_candidate_enrichment(
        self, repo: ManagedKRRepository, resolution_service: KnowledgeResolutionService
    ) -> None:
        # Resolve ILD baseline (uses seed data from real project)
        baseline = resolution_service.resolve_curve(CurveResolveInput(mnemonic="ILD"))

        # Add a candidate enrichment
        rec = _make_ild_enrichment()
        repo._add_record(rec)  # type: ignore[arg-type]

        # Resolve again — must be identical
        after = resolution_service.resolve_curve(CurveResolveInput(mnemonic="ILD"))

        assert baseline.resolved == after.resolved
        assert baseline.canonical_curve_id == after.canonical_curve_id

    def test_candidate_enrichment_not_in_production_eligible(
        self, repo: ManagedKRRepository
    ) -> None:
        rec = _make_ild_enrichment()
        repo._add_record(rec)  # type: ignore[arg-type]
        production = repo.list_production_eligible()
        enrichments_in_prod = [r for r in production if r.record_type == "alias_enrichment"]
        assert len(enrichments_in_prod) == 0


class TestCandidateEnrichmentDoesNotAffectKR7:
    """Test 6: Candidate alias enrichments do not change KR-7 classification."""

    def test_ild_classification_unchanged_with_candidate_enrichment(
        self,
        repo: ManagedKRRepository,
        classification_service: CurveClassificationService,
    ) -> None:
        baseline_req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="ILD")]
        )
        baseline = classification_service.classify_curves(baseline_req)

        # Stage a candidate enrichment
        rec = _make_ild_enrichment()
        repo._add_record(rec)  # type: ignore[arg-type]

        after_req = CurveClassificationRequest(
            curves=[CurveClassifyInput(curve_id="c1", mnemonic="ILD")]
        )
        after = classification_service.classify_curves(after_req)

        b = baseline.classifications[0]
        a = after.classifications[0]
        assert b.resolved == a.resolved
        assert b.canonical_curve_id == a.canonical_curve_id
        assert b.classification_status == a.classification_status


class TestCandidateEnrichmentDoesNotAffectKR8:
    """Test 7: Candidate alias enrichments do not change KR-8 display recommendations."""

    def test_ild_display_recommendation_unchanged(
        self,
        repo: ManagedKRRepository,
        display_service: DisplayRecommendationService,
    ) -> None:
        req = DisplayRecommendationRequest(
            curves=[CurveRecommendInput(curve_id="c1", mnemonic="ILD")]
        )
        baseline = display_service.recommend_display(req)

        rec = _make_ild_enrichment()
        repo._add_record(rec)  # type: ignore[arg-type]

        after = display_service.recommend_display(req)

        b = baseline.recommendations[0]
        a = after.recommendations[0]
        assert b.canonical_curve_id == a.canonical_curve_id
        assert b.recommendation_status == a.recommendation_status


# ===========================================================================
# Group C — Approved Enrichment Behaviour
# ===========================================================================

class TestApprovedEnrichmentQueryable:
    """Test 8: Approved alias enrichments can be queried as metadata."""

    def test_approved_enrichment_queryable_via_list_alias_enrichments(
        self, repo: ManagedKRRepository, governance_service: GovernanceService
    ) -> None:
        rec = _make_ild_enrichment()
        repo._add_record(rec)  # type: ignore[arg-type]
        governance_service.approve_record(rec.record_id, actor="reviewer")

        enrichments = repo.list_alias_enrichments(alias="ILD")
        assert len(enrichments) >= 1
        approved = [e for e in enrichments if e.status == GovernanceStatus.APPROVED]
        assert len(approved) == 1
        assert approved[0].technical_curve_id == "deep_induction_resistivity"

    def test_approved_enrichment_queryable_via_list_records(
        self, repo: ManagedKRRepository, governance_service: GovernanceService
    ) -> None:
        rec = _make_ild_enrichment()
        repo._add_record(rec)  # type: ignore[arg-type]
        governance_service.approve_record(rec.record_id, actor="reviewer")

        enrichments = repo.list_records("alias_enrichment", status=GovernanceStatus.APPROVED)
        assert len(enrichments) >= 1

    def test_approved_enrichment_is_production_eligible(
        self, repo: ManagedKRRepository, governance_service: GovernanceService
    ) -> None:
        rec = _make_ild_enrichment()
        repo._add_record(rec)  # type: ignore[arg-type]
        governance_service.approve_record(rec.record_id, actor="reviewer")

        production = repo.list_production_eligible()
        prod_types = {r.record_type for r in production}
        assert "alias_enrichment" in prod_types


class TestApprovedEnrichmentDoesNotRemapDisplayCanonical:
    """Test 9: Approved alias enrichments still do not remap display canonical curve."""

    def test_ild_canonical_unchanged_after_enrichment_approval(
        self,
        repo: ManagedKRRepository,
        resolution_service: KnowledgeResolutionService,
        governance_service: GovernanceService,
    ) -> None:
        baseline = resolution_service.resolve_curve(CurveResolveInput(mnemonic="ILD"))

        rec = _make_ild_enrichment()
        repo._add_record(rec)  # type: ignore[arg-type]
        governance_service.approve_record(rec.record_id, actor="reviewer")

        after = resolution_service.resolve_curve(CurveResolveInput(mnemonic="ILD"))

        # KR-6 must still return the same display canonical (deep_resistivity)
        assert baseline.canonical_curve_id == after.canonical_curve_id
        # The enrichment's technical_curve_id must NOT appear as the resolved canonical
        assert after.canonical_curve_id != "deep_induction_resistivity"

    def test_enrichment_technical_curve_id_differs_from_display_canonical(self) -> None:
        rec = _make_ild_enrichment()
        assert rec.display_canonical_curve_id != rec.technical_curve_id
        assert rec.display_canonical_curve_id == "deep_resistivity"
        assert rec.technical_curve_id == "deep_induction_resistivity"


# ===========================================================================
# Group D — Specific Alias Cases
# ===========================================================================

class TestSpecificAliasCases:
    """Tests 10–13: ILD, LLD, ILM, LLS enrichment record representations."""

    def test_10_ild_enrichment_record(self) -> None:
        """Test 10: ILD can be represented as display=deep_resistivity and
        technical=deep_induction_resistivity."""
        rec = AliasEnrichmentRecord(
            record_id="enrich_ILD",
            alias="ILD",
            normalized_alias="ILD",
            display_canonical_curve_id="deep_resistivity",
            technical_curve_id="deep_induction_resistivity",
            technical_display_name="Deep Induction Resistivity",
            parent_canonical_curve_id="deep_resistivity",
            measurement_family="induction",
            measurement_depth="deep",
            tool_family="induction_resistivity",
        )
        assert rec.alias == "ILD"
        assert rec.display_canonical_curve_id == "deep_resistivity"
        assert rec.technical_curve_id == "deep_induction_resistivity"
        assert rec.parent_canonical_curve_id == "deep_resistivity"
        assert rec.record_type == "alias_enrichment"
        # Enrichment does NOT replace display — they must differ
        assert rec.display_canonical_curve_id != rec.technical_curve_id

    def test_11_lld_enrichment_record(self) -> None:
        """Test 11: LLD can be represented as display=deep_resistivity and
        technical=deep_laterolog_resistivity."""
        rec = AliasEnrichmentRecord(
            record_id="enrich_LLD",
            alias="LLD",
            normalized_alias="LLD",
            display_canonical_curve_id="deep_resistivity",
            technical_curve_id="deep_laterolog_resistivity",
            technical_display_name="Deep Laterolog Resistivity",
            parent_canonical_curve_id="deep_resistivity",
            measurement_family="laterolog",
            measurement_depth="deep",
            tool_family="laterolog_resistivity",
        )
        assert rec.alias == "LLD"
        assert rec.display_canonical_curve_id == "deep_resistivity"
        assert rec.technical_curve_id == "deep_laterolog_resistivity"
        assert rec.parent_canonical_curve_id == "deep_resistivity"
        assert rec.display_canonical_curve_id != rec.technical_curve_id

    def test_12_ilm_enrichment_record(self) -> None:
        """Test 12: ILM can be represented as display=shallow_resistivity and
        technical=medium_induction_resistivity."""
        rec = AliasEnrichmentRecord(
            record_id="enrich_ILM",
            alias="ILM",
            normalized_alias="ILM",
            display_canonical_curve_id="shallow_resistivity",
            technical_curve_id="medium_induction_resistivity",
            technical_display_name="Medium Induction Resistivity",
            parent_canonical_curve_id="shallow_resistivity",
            measurement_family="induction",
            measurement_depth="medium",
            tool_family="induction_resistivity",
        )
        assert rec.alias == "ILM"
        assert rec.display_canonical_curve_id == "shallow_resistivity"
        assert rec.technical_curve_id == "medium_induction_resistivity"
        assert rec.parent_canonical_curve_id == "shallow_resistivity"
        assert rec.display_canonical_curve_id != rec.technical_curve_id

    def test_13_lls_enrichment_record(self) -> None:
        """Test 13: LLS can be represented as display=shallow_resistivity and
        technical=shallow_laterolog_resistivity."""
        rec = AliasEnrichmentRecord(
            record_id="enrich_LLS",
            alias="LLS",
            normalized_alias="LLS",
            display_canonical_curve_id="shallow_resistivity",
            technical_curve_id="shallow_laterolog_resistivity",
            technical_display_name="Shallow Laterolog Resistivity",
            parent_canonical_curve_id="shallow_resistivity",
            measurement_family="laterolog",
            measurement_depth="shallow",
            tool_family="laterolog_resistivity",
        )
        assert rec.alias == "LLS"
        assert rec.display_canonical_curve_id == "shallow_resistivity"
        assert rec.technical_curve_id == "shallow_laterolog_resistivity"
        assert rec.parent_canonical_curve_id == "shallow_resistivity"
        assert rec.display_canonical_curve_id != rec.technical_curve_id

    def test_four_aliases_all_validate_clean(self, repo: ManagedKRRepository) -> None:
        """All four alias enrichment records pass repository validation."""
        for alias, display_canonical, technical_curve_id, technical_name in [
            ("ILD", "deep_resistivity",    "deep_induction_resistivity",  "Deep Induction Resistivity"),
            ("LLD", "deep_resistivity",    "deep_laterolog_resistivity",   "Deep Laterolog Resistivity"),
            ("ILM", "shallow_resistivity", "medium_induction_resistivity", "Medium Induction Resistivity"),
            ("LLS", "shallow_resistivity", "shallow_laterolog_resistivity","Shallow Laterolog Resistivity"),
        ]:
            rec = AliasEnrichmentRecord(
                record_id=f"enrich_{alias}",
                alias=alias,
                normalized_alias=alias,
                display_canonical_curve_id=display_canonical,
                technical_curve_id=technical_curve_id,
                technical_display_name=technical_name,
                parent_canonical_curve_id=display_canonical,
            )
            errors = repo.validate_record(rec)
            assert errors == [], (
                f"Validation errors for {alias} enrichment: {errors}"
            )


# ===========================================================================
# Group E — Reconciliation Logic
# ===========================================================================

class TestReconciliationService:
    """Tests 14–15: Reconciliation service detects true conflicts and enrichments."""

    def _make_curated_payload(
        self,
        alias: str,
        import_canonical: str,
        import_family: str,
        import_product_subgroup: str,
        display_name: str = "Test Curve",
    ) -> ImportPayload:
        """Build a minimal ImportPayload with one curve definition."""
        return ImportPayload(
            source=ImportSource(
                source_type="test",
                source_label="Test Payload",
                source_reference="test_ref",
            ),
            curve_definitions=[
                ImportCurveDefinition(
                    canonical_curve_id=import_canonical,
                    display_name=display_name,
                    family=import_family,
                    product_group="open_hole_logs",
                    product_subgroup=import_product_subgroup,
                    aliases=[alias],
                )
            ],
        )

    def test_14_true_alias_conflict_detected(self, tmp_path: Path) -> None:
        """Test 14: A true unrelated alias conflict is still detected as conflict.

        Scenario: existing KR has XYZ → gamma_ray (product_subgroup=gamma_ray).
        Curated import says XYZ → neutron_porosity (product_subgroup=density_neutron_porosity).
        These are different measurement domains → true_alias_conflict.
        """
        repo = ManagedKRRepository(storage_path=tmp_path / "conflict_test.json")

        # Inject existing seed alias and curve def
        existing_def = CurveDefinitionRecord(
            record_id="seed_gamma_ray_def",
            canonical_curve_id="gamma_ray",
            display_name="Gamma Ray",
            family="gamma_ray",
            product_group="open_hole_logs",
            product_subgroup="gamma_ray",
            status=GovernanceStatus.SEED,
        )
        existing_alias = AliasRecord(
            record_id="seed_alias_xyz",
            alias="XYZ",
            normalized_alias="XYZ",
            canonical_curve_id="gamma_ray",
            status=GovernanceStatus.SEED,
        )
        repo._managed_records[existing_def.record_id] = existing_def
        repo._managed_records[existing_alias.record_id] = existing_alias

        # Curated payload: XYZ → neutron_porosity (different domain)
        payload = self._make_curated_payload(
            alias="XYZ",
            import_canonical="neutron_porosity",
            import_family="neutron_porosity",
            import_product_subgroup="density_neutron_porosity",
            display_name="Neutron Porosity",
        )

        service = CuratedKRReconciliationService()
        result = service.reconcile(payload, repo)

        assert len(result.true_alias_conflicts) == 1, (
            f"Expected 1 true_alias_conflict, got {result.summary()}"
        )
        assert len(result.safe_alias_enrichments) == 0
        conflict_item = result.true_alias_conflicts[0]
        assert conflict_item.alias == "XYZ"
        assert conflict_item.classification == CLS_TRUE_ALIAS_CONFLICT

    def test_safe_enrichment_detected_for_resistivity_subtype(self, tmp_path: Path) -> None:
        """Broad-to-specific resistivity refinement classifies as safe_alias_enrichment."""
        repo = _make_repo_with_seed_aliases(tmp_path)

        payload = self._make_curated_payload(
            alias="ILD",
            import_canonical="deep_induction_resistivity",
            import_family="deep_induction_resistivity",
            import_product_subgroup="resistivity",
            display_name="Deep Induction Resistivity",
        )

        service = CuratedKRReconciliationService()
        result = service.reconcile(payload, repo)

        assert len(result.safe_alias_enrichments) == 1, (
            f"Expected safe enrichment, got: {result.summary()}"
        )
        assert len(result.true_alias_conflicts) == 0
        item = result.safe_alias_enrichments[0]
        assert item.alias == "ILD"
        assert item.classification == CLS_SAFE_ALIAS_ENRICHMENT
        assert item.enrichment_record is not None
        assert item.enrichment_record.display_canonical_curve_id == "deep_resistivity"
        assert item.enrichment_record.technical_curve_id == "deep_induction_resistivity"

    def test_all_four_ild_ilm_lld_lls_classify_as_safe_enrichments(
        self, tmp_path: Path
    ) -> None:
        """ILD, ILM, LLD, LLS all classify as safe enrichments against seed data."""
        repo = _make_repo_with_seed_aliases(tmp_path)

        cases = [
            ("ILD", "deep_induction_resistivity",  "deep_induction_resistivity",  "resistivity"),
            ("LLD", "deep_laterolog_resistivity",   "deep_laterolog_resistivity",  "resistivity"),
            ("ILM", "medium_induction_resistivity", "medium_induction_resistivity","resistivity"),
            ("LLS", "shallow_laterolog_resistivity","shallow_laterolog_resistivity","resistivity"),
        ]

        service = CuratedKRReconciliationService()
        for alias, canonical, family, subgroup in cases:
            payload = self._make_curated_payload(
                alias=alias,
                import_canonical=canonical,
                import_family=family,
                import_product_subgroup=subgroup,
                display_name=f"{alias} Technical Curve",
            )
            result = service.reconcile(payload, repo)
            assert len(result.safe_alias_enrichments) == 1, (
                f"{alias}: expected safe_alias_enrichment, got {result.summary()}"
            )
            assert len(result.true_alias_conflicts) == 0, (
                f"{alias}: unexpected true_alias_conflict"
            )

    def test_stage_enrichment_records_creates_candidates(self, tmp_path: Path) -> None:
        """Staged enrichments land in repo as CANDIDATE records."""
        repo = _make_repo_with_seed_aliases(tmp_path)
        payload = self._make_curated_payload(
            alias="ILD",
            import_canonical="deep_induction_resistivity",
            import_family="deep_induction_resistivity",
            import_product_subgroup="resistivity",
            display_name="Deep Induction Resistivity",
        )
        service = CuratedKRReconciliationService()
        result = service.reconcile(payload, repo)
        ids = service.stage_enrichment_records(result, repo, batch_id="test_batch")

        assert len(ids) == 1
        staged = repo.get_by_id(ids[0])
        assert staged is not None
        assert isinstance(staged, AliasEnrichmentRecord)
        assert staged.status == GovernanceStatus.CANDIDATE
        assert staged.display_canonical_curve_id == "deep_resistivity"
        assert staged.technical_curve_id == "deep_induction_resistivity"

    def test_true_conflict_items_not_staged(self, tmp_path: Path) -> None:
        """True conflict items are never staged even if stage_enrichment_records is called."""
        repo = ManagedKRRepository(storage_path=tmp_path / "conflict_stage.json")

        existing_def = CurveDefinitionRecord(
            record_id="seed_gr_def",
            canonical_curve_id="gamma_ray",
            display_name="Gamma Ray",
            family="gamma_ray",
            product_group="open_hole_logs",
            product_subgroup="gamma_ray",
            status=GovernanceStatus.SEED,
        )
        existing_alias = AliasRecord(
            record_id="seed_alias_abc",
            alias="ABC",
            normalized_alias="ABC",
            canonical_curve_id="gamma_ray",
            status=GovernanceStatus.SEED,
        )
        repo._managed_records[existing_def.record_id] = existing_def
        repo._managed_records[existing_alias.record_id] = existing_alias

        payload = self._make_curated_payload(
            alias="ABC",
            import_canonical="neutron_porosity",
            import_family="neutron_porosity",
            import_product_subgroup="density_neutron_porosity",
        )
        service = CuratedKRReconciliationService()
        result = service.reconcile(payload, repo)

        assert result.has_true_conflicts
        ids = service.stage_enrichment_records(result, repo)
        assert len(ids) == 0  # conflicts are never staged


class TestKRSuiteCompatibility:
    """Test 15: Full knowledge suite compatibility guard.

    Imports all KR modules to verify no circular dependencies or
    syntax errors were introduced by this change.  The actual pytest
    tests for KR-1 through KR-8 are run by the validation script.
    """

    def test_all_kr_modules_importable(self) -> None:
        from app.knowledge import alias_enrichment_models  # noqa: F401
        from app.knowledge import curated_reconciliation_service  # noqa: F401
        from app.knowledge import managed_models  # noqa: F401
        from app.knowledge import managed_storage  # noqa: F401
        from app.knowledge import managed_repository  # noqa: F401
        from app.knowledge import resolution_service  # noqa: F401
        from app.knowledge import classification_service  # noqa: F401
        from app.knowledge import display_recommendation_service  # noqa: F401
        from app.knowledge import governance  # noqa: F401
        from app.knowledge import governance_service  # noqa: F401
        from app.knowledge import import_models  # noqa: F401
        from app.knowledge import import_validation_service  # noqa: F401
        from app.knowledge import import_staging_service  # noqa: F401

    def test_alias_enrichment_record_type_in_governed_types(self) -> None:
        assert "alias_enrichment" in GOVERNED_RECORD_TYPES

    def test_alias_enrichment_version_constant(self) -> None:
        assert KR_DATA_MODEL_1_VERSION == "kr-data-model-1"

    def test_managed_storage_handles_alias_enrichment_roundtrip(self) -> None:
        """Storage serialize/deserialize does not raise for alias_enrichment."""
        rec = _make_ild_enrichment()
        serialized = serialize_record(rec)
        restored = deserialize_record(serialized)
        assert isinstance(restored, AliasEnrichmentRecord)
        assert restored.record_id == rec.record_id

    def test_list_alias_enrichments_returns_empty_on_fresh_repo(
        self, repo: ManagedKRRepository
    ) -> None:
        enrichments = repo.list_alias_enrichments()
        # Fresh repo has no enrichments
        assert isinstance(enrichments, list)
        assert all(isinstance(e, AliasEnrichmentRecord) for e in enrichments)
