from pathlib import Path

from app.source_intake.models import (
    SourceIntakeBulkResolutionRequest,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionDecision,
    SourceIntakeResolutionState,
    SourceRepositoryCreateRequest,
)
from app.source_intake.service import WlvSourceIntakeService


LAS = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. WELL : Generic well name
~Curve
DEPT.FT : Depth
GR.API : Gamma Ray
~ASCII
100.0 50.0
101.0 51.0
102.0 52.0
"""


def _write(path: Path, text: str = LAS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _service(tmp_path: Path) -> WlvSourceIntakeService:
    return WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")


def test_rescan_preserves_resolution_history_and_canonical_metadata(tmp_path: Path) -> None:
    root = tmp_path / "repository-a"
    _write(root / "warning.las")
    service = _service(tmp_path)
    repository = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True)
    )
    candidate = service.scan_repository(repository.repository_id).candidates[0]

    service.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=candidate.occurrence_id,
                    action=SourceIntakeResolutionAction.METADATA_OVERRIDE,
                    actor="reviewer",
                    reason="Confirmed from package evidence.",
                    resolved_values={
                        "well_name": "Forge 21-31",
                        "uwi": "2700190539",
                    },
                )
            ]
        )
    )

    before = service.get_workbench().candidates[0]
    result = service.scan_repository(repository.repository_id)
    after = result.candidates[0]

    assert after.occurrence_id == before.occurrence_id
    assert after.resolution_state == SourceIntakeResolutionState.RESOLVED
    assert after.resolution_version == before.resolution_version
    assert after.resolution_history == before.resolution_history
    assert after.resolved_metadata == before.resolved_metadata
    assert after.resolved_metadata.well_name.value == "Forge 21-31"
    assert after.resolved_metadata.uwi.value == "2700190539"


def test_rescan_preserves_registration_and_managed_lifecycle_linkage(tmp_path: Path) -> None:
    root = tmp_path / "repository-a"
    _write(root / "registered.las")
    service = _service(tmp_path)
    repository = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True)
    )
    candidate = service.scan_repository(repository.repository_id).candidates[0]

    snapshot = service._load_snapshot()
    persisted = snapshot.candidates[0]
    persisted.resolution_state = SourceIntakeResolutionState.REGISTERED
    persisted.registration_status = "registered"
    persisted.managed_well_id = "managed-well:well-a"
    persisted.managed_well_name = "Well A"
    persisted.wmdp_state = "staged_in_wmdp"
    persisted.wdv_state = "not_loaded"
    persisted.registered_product_count = 3
    persisted.registered_curve_count = 3
    persisted.registered_trajectory_count = 0
    service._save_snapshot(snapshot)

    rescanned = service.scan_repository(repository.repository_id).candidates[0]

    assert rescanned.occurrence_id == candidate.occurrence_id
    assert rescanned.resolution_state == SourceIntakeResolutionState.REGISTERED
    assert rescanned.registration_status == "registered"
    assert rescanned.managed_well_id == "managed-well:well-a"
    assert rescanned.managed_well_name == "Well A"
    assert rescanned.wmdp_state == "staged_in_wmdp"
    assert rescanned.wdv_state == "not_loaded"
    assert rescanned.registered_product_count == 3
    assert rescanned.registered_curve_count == 3


def test_scanning_second_repository_preserves_first_repository_candidates(tmp_path: Path) -> None:
    root_a = tmp_path / "repository-a"
    root_b = tmp_path / "repository-b"
    _write(root_a / "a.las", LAS)
    _write(root_b / "b.las", LAS.replace("50.0", "60.0"))

    service = _service(tmp_path)
    repository_a = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root_a), include_subfolders=True)
    )
    repository_b = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root_b), include_subfolders=True)
    )

    first = service.scan_repository(repository_a.repository_id).candidates[0]
    service.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=first.occurrence_id,
                    action=SourceIntakeResolutionAction.METADATA_OVERRIDE,
                    actor="reviewer",
                    reason="Well A confirmed.",
                    resolved_values={"well_name": "Well A", "uwi": "A-001"},
                )
            ]
        )
    )

    service.scan_repository(repository_b.repository_id)
    rows = service.get_workbench().candidates
    by_repository = {row.repository_id: row for row in rows}

    assert set(by_repository) == {repository_a.repository_id, repository_b.repository_id}
    assert by_repository[repository_a.repository_id].occurrence_id == first.occurrence_id
    assert by_repository[repository_a.repository_id].resolution_state == SourceIntakeResolutionState.RESOLVED
    assert by_repository[repository_a.repository_id].resolved_metadata.well_name.value == "Well A"


def test_exact_duplicate_across_repositories_uses_fingerprint_only(tmp_path: Path) -> None:
    root_a = tmp_path / "repository-a"
    root_b = tmp_path / "repository-b"
    _write(root_a / "first-name.las", LAS)
    _write(root_b / "different-name.las", LAS)

    service = _service(tmp_path)
    repository_a = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root_a), include_subfolders=True)
    )
    repository_b = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root_b), include_subfolders=True)
    )

    service.scan_repository(repository_a.repository_id)
    service.scan_repository(repository_b.repository_id)
    rows = service.get_workbench().candidates

    assert len(rows) == 2
    assert rows[0].occurrence_id != rows[1].occurrence_id
    assert rows[0].content_fingerprint == rows[1].content_fingerprint
    assert rows[0].duplicate_group_id == rows[1].duplicate_group_id
    assert sum(row.resolution_state == SourceIntakeResolutionState.DUPLICATE for row in rows) == 1



def test_rescan_refreshes_stale_inference_and_keeps_manual_correction(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository-a"
    _write(root / "well.las")
    service = _service(tmp_path)
    repository = service.create_repository(
        SourceRepositoryCreateRequest(
            root_path=str(root),
            include_subfolders=True,
        )
    )
    candidate = service.scan_repository(
        repository.repository_id
    ).candidates[0]

    service.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=candidate.occurrence_id,
                    action=SourceIntakeResolutionAction.METADATA_OVERRIDE,
                    actor="reviewer",
                    reason="Correct operator only.",
                    resolved_values={
                        "operator": "Reviewed Operator",
                    },
                )
            ]
        )
    )

    snapshot = service._load_snapshot()
    persisted = snapshot.candidates[0]
    assert persisted.resolved_metadata is not None

    persisted.resolved_metadata.well_name.value = "STALE INFERRED NAME"
    persisted.resolved_metadata.well_name.source = "filename_inference"
    persisted.resolved_metadata.uwi.value = "STALE-INFERRED-UWI"
    persisted.resolved_metadata.uwi.source = "filename_inference"
    persisted.qaqc_status.messages = ["stale message"]
    persisted.readiness_issues = ["stale readiness issue"]

    service._save_snapshot(snapshot)

    rescanned = service.scan_repository(
        repository.repository_id
    ).candidates[0]

    assert rescanned.occurrence_id == candidate.occurrence_id
    assert rescanned.resolved_metadata is not None

    # The fixture contains the generic value "WELL", which the resolver
    # intentionally treats as weak/missing identity rather than a canonical
    # well name. The important contract is that the injected stale inference
    # is gone.
    assert rescanned.resolved_metadata.well_name.value is None
    assert rescanned.resolved_metadata.well_name.source == "missing"

    assert rescanned.resolved_metadata.uwi.value is None
    assert rescanned.resolved_metadata.uwi.source != "filename_inference"

    assert (
        rescanned.resolved_metadata.operator.value
        == "Reviewed Operator"
    )
    assert (
        rescanned.resolved_metadata.operator.source
        == "manual_resolution"
    )

    assert "stale message" not in rescanned.qaqc_status.messages
    assert "stale readiness issue" not in rescanned.readiness_issues


def test_changed_content_creates_new_occurrence_without_inheriting_decision(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository-a"
    path = root / "well.las"
    _write(path)

    service = _service(tmp_path)
    repository = service.create_repository(
        SourceRepositoryCreateRequest(
            root_path=str(root),
            include_subfolders=True,
        )
    )

    original = service.scan_repository(
        repository.repository_id
    ).candidates[0]

    service.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=original.occurrence_id,
                    action=SourceIntakeResolutionAction.METADATA_OVERRIDE,
                    actor="reviewer",
                    reason="Original occurrence correction.",
                    resolved_values={
                        "operator": "Reviewed Operator",
                    },
                )
            ]
        )
    )

    _write(path, LAS.replace("50.0", "60.0"))

    changed = service.scan_repository(
        repository.repository_id
    ).candidates[0]

    assert changed.occurrence_id != original.occurrence_id
    assert changed.current_decision is None
    assert changed.resolved_metadata is not None
    assert changed.resolved_metadata.operator.value is None
