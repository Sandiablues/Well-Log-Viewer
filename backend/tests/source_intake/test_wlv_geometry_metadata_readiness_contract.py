from pathlib import Path

from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.source_intake.models import (
    SourceIntakeBulkResolutionRequest,
    SourceIntakeReadinessState,
    SourceIntakeRegisterRequest,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionDecision,
    SourceRepositoryCreateRequest,
)
from app.source_intake.service import WlvSourceIntakeService


GEOMETRY = """MD,INC,AZI
0,0,0
100,5,90
200,10,90
"""


def _scan(tmp_path: Path, file_name: str = "F21-31_FULL_WELLBORE_SYNTHETIC_DEVIATION_SURVEY.csv"):
    root = tmp_path / "source"
    root.mkdir()
    (root / file_name).write_text(GEOMETRY)

    source = WlvSourceIntakeService(
        storage_path=tmp_path / "source_intake.json"
    )
    repository = source.create_repository(
        SourceRepositoryCreateRequest(
            root_path=str(root),
            include_subfolders=True,
        )
    )
    candidate = source.scan_repository(repository.repository_id).candidates[0]
    return source, candidate


def _inventory(tmp_path: Path) -> ManagedWellInventoryService:
    return ManagedWellInventoryService(
        repository=ManagedWellInventoryRepository(
            tmp_path / "managed_wells.json"
        )
    )


def test_geometry_filename_does_not_become_authoritative_well_name(tmp_path: Path) -> None:
    _source, candidate = _scan(tmp_path)

    assert candidate.resolved_metadata is not None
    assert candidate.resolved_metadata.well_name.value is None
    assert candidate.resolved_metadata.well_name.source == "missing"
    assert candidate.resolved_metadata.well_name.review_required is True


def test_geometry_without_well_identity_is_review_required_not_ready(tmp_path: Path) -> None:
    _source, candidate = _scan(tmp_path)

    assert candidate.readiness_state == SourceIntakeReadinessState.REVIEW_REQUIRED
    assert any(
        "destination well" in issue.lower()
        for issue in candidate.readiness_issues
    )


def test_geometry_registration_is_blocked_before_inventory_write_when_identity_missing(tmp_path: Path) -> None:
    source, candidate = _scan(tmp_path)
    inventory = _inventory(tmp_path)

    response = source.register_candidates(
        SourceIntakeRegisterRequest(
            candidate_ids=[candidate.source_file_id],
        ),
        inventory_service=inventory,
    )

    assert response.registered_count == 0
    assert response.skipped_count == 1
    assert response.results[0].status == "blocked"
    assert "not MWD-ready: review_required" in response.results[0].reason
    assert inventory.list_wells() == []


def test_geometry_manual_metadata_correction_succeeds_and_recomputes_readiness(tmp_path: Path) -> None:
    source, candidate = _scan(tmp_path)

    response = source.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=candidate.occurrence_id,
                    action=SourceIntakeResolutionAction.MANUAL_CORRECTION,
                    actor="test",
                    reason="Confirm geometry destination well.",
                    resolved_values={
                        "well_name": "F 21-31",
                    },
                )
            ]
        )
    )

    assert response.resolved_count == 1
    updated = source.get_workbench().candidates[0]
    assert updated.resolved_metadata is not None
    assert updated.resolved_metadata.well_name.value == "F 21-31"
    assert updated.resolved_metadata.well_name.source == "manual_resolution"
    assert updated.readiness_state == SourceIntakeReadinessState.READY


def test_corrected_geometry_can_register_after_readiness_gate(tmp_path: Path) -> None:
    source, candidate = _scan(tmp_path)
    inventory = _inventory(tmp_path)

    source.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=candidate.occurrence_id,
                    action=SourceIntakeResolutionAction.MANUAL_CORRECTION,
                    actor="test",
                    reason="Confirm geometry destination well.",
                    resolved_values={
                        "well_name": "F 21-31",
                    },
                )
            ]
        )
    )

    response = source.register_candidates(
        SourceIntakeRegisterRequest(
            candidate_ids=[candidate.source_file_id],
        ),
        inventory_service=inventory,
    )

    assert response.registered_count == 1
    assert response.skipped_count == 0
    assert response.results[0].well_name == "F 21-31"
    assert len(inventory.list_wells()) == 1
