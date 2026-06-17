from pathlib import Path

from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.source_intake.models import (
    SourceIntakeBulkResolutionRequest,
    SourceIntakeRegisterRequest,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionDecision,
    SourceIntakeWellAssignmentMode,
    SourceRepositoryCreateRequest,
)
from app.source_intake.service import WlvSourceIntakeService


LAS_TEMPLATE = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. {well_name} : Well name
{uwi_line}COMP. Test Operator : Company
FLD. Test Field : Field
~Curve
DEPT.FT : Depth
{curve}.UNIT : Test curve
~ASCII
100.0 1.0
101.0 2.0
102.0 3.0
"""


def _write_las(
    path: Path,
    *,
    well_name: str,
    curve: str,
    uwi: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        LAS_TEMPLATE.format(
            well_name=well_name,
            curve=curve,
            uwi_line=f"UWI. {uwi} : Unique well identifier\n" if uwi else "",
        )
    )


def _services(tmp_path: Path):
    source = WlvSourceIntakeService(
        storage_path=tmp_path / "source_intake.json"
    )
    inventory = ManagedWellInventoryService(
        repository=ManagedWellInventoryRepository(
            tmp_path / "managed_wells.json"
        )
    )
    return source, inventory


def _register(
    source: WlvSourceIntakeService,
    inventory: ManagedWellInventoryService,
    candidate_id: str,
):
    return source.register_candidates(
        SourceIntakeRegisterRequest(
            candidate_ids=[candidate_id],
            approval={
                "approved_by": "e2e-test",
                "approval_note": "E2E lifecycle validation",
            },
        ),
        inventory_service=inventory,
    )


def test_complete_human_decision_lifecycle(tmp_path: Path) -> None:
    root = tmp_path / "source"

    _write_las(
        root / "base.las",
        well_name="Base Well",
        curve="GR",
        uwi="BASE-001",
    )
    _write_las(
        root / "existing-target.las",
        well_name="Different Source Name",
        curve="CALI",
    )
    _write_las(
        root / "new-well.las",
        well_name="WELL",
        curve="RHOB",
    )
    _write_las(
        root / "clear.las",
        well_name="WELL",
        curve="NPHI",
    )
    _write_las(
        root / "exclude.las",
        well_name="Excluded Source",
        curve="DT",
    )

    source, inventory = _services(tmp_path)
    repository = source.create_repository(
        SourceRepositoryCreateRequest(
            root_path=str(root),
            include_subfolders=True,
        )
    )
    scanned = source.scan_repository(repository.repository_id)
    by_name = {item.file_name: item for item in scanned.candidates}

    base = by_name["base.las"]
    base_registration = _register(
        source,
        inventory,
        base.source_file_id,
    )
    assert base_registration.registered_count == 1
    target_managed_well_id = (
        base_registration.results[0].managed_well_id
    )
    assert target_managed_well_id

    existing = by_name["existing-target.las"]
    source.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=existing.occurrence_id,
                    action=SourceIntakeResolutionAction.WELL_ASSIGNED,
                    actor="reviewer",
                    reason="Assign to selected existing well.",
                    assignment_mode=(
                        SourceIntakeWellAssignmentMode.EXISTING_WELL
                    ),
                    target_managed_well_id=target_managed_well_id,
                )
            ]
        )
    )
    existing_registration = _register(
        source,
        inventory,
        existing.source_file_id,
    )
    assert existing_registration.registered_count == 1
    assert (
        existing_registration.results[0].managed_well_id
        == target_managed_well_id
    )

    new_candidate = by_name["new-well.las"]
    source.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=new_candidate.occurrence_id,
                    action=SourceIntakeResolutionAction.WELL_ASSIGNED,
                    actor="reviewer",
                    reason="Create confirmed new well.",
                    assignment_mode=(
                        SourceIntakeWellAssignmentMode.NEW_WELL
                    ),
                    new_well_values={
                        "well_name": "Confirmed New Well",
                        "uwi": "NEW-002",
                        "operator": "Confirmed Operator",
                        "field": "Confirmed Field",
                    },
                )
            ]
        )
    )
    new_registration = _register(
        source,
        inventory,
        new_candidate.source_file_id,
    )
    assert new_registration.registered_count == 1
    assert (
        new_registration.results[0].managed_well_id
        != target_managed_well_id
    )

    clear_candidate = by_name["clear.las"]
    source.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=clear_candidate.occurrence_id,
                    action=SourceIntakeResolutionAction.WELL_ASSIGNED,
                    actor="reviewer",
                    reason="Temporary new-well decision.",
                    assignment_mode=(
                        SourceIntakeWellAssignmentMode.NEW_WELL
                    ),
                    new_well_values={
                        "well_name": "Temporary Well",
                    },
                )
            ]
        )
    )
    source.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=clear_candidate.occurrence_id,
                    action=SourceIntakeResolutionAction.REOPENED,
                    actor="reviewer",
                    reason="Leave unresolved for later review.",
                )
            ]
        )
    )
    clear_persisted = next(
        item
        for item in source.get_workbench().candidates
        if item.source_file_id == clear_candidate.source_file_id
    )
    assert clear_persisted.current_decision is not None
    assert (
        clear_persisted.current_decision.decision.value
        == "clear_decision"
    )
    assert clear_persisted.readiness_state.value == "review_required"
    clear_registration = _register(
        source,
        inventory,
        clear_candidate.source_file_id,
    )
    assert clear_registration.registered_count == 0
    assert clear_registration.skipped_count == 1

    exclude_candidate = by_name["exclude.las"]
    source.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=exclude_candidate.occurrence_id,
                    action=SourceIntakeResolutionAction.EXCLUDED,
                    actor="reviewer",
                    reason="Not valid for this intake.",
                )
            ]
        )
    )
    exclude_persisted = next(
        item
        for item in source.get_workbench().candidates
        if item.source_file_id == exclude_candidate.source_file_id
    )
    assert exclude_persisted.current_decision is not None
    assert exclude_persisted.current_decision.decision.value == "exclude"
    exclude_registration = _register(
        source,
        inventory,
        exclude_candidate.source_file_id,
    )
    assert exclude_registration.registered_count == 0
    assert exclude_registration.skipped_count == 1

    records = inventory.list_wells()
    assert len(records) == 2

    base_record = next(
        record
        for record in records
        if record.managed_well_id == target_managed_well_id
    )
    assert len(base_record.source_references) == 2
    base_curves = {
        item.curve_name
        for group in base_record.product_groups
        for item in group.items
    }
    assert {"GR", "CALI"}.issubset(base_curves)

    new_record = next(
        record
        for record in records
        if record.managed_well_id != target_managed_well_id
    )
    assert new_record.well_name == "Confirmed New Well"
    assert new_record.metadata["uwi"] == "NEW-002"

    final_workbench = source.get_workbench()
    registered = {
        item.file_name
        for item in final_workbench.candidates
        if item.registration_status == "registered"
    }
    assert registered == {
        "base.las",
        "existing-target.las",
        "new-well.las",
    }

    unresolved = next(
        item
        for item in final_workbench.candidates
        if item.file_name == "clear.las"
    )
    excluded = next(
        item
        for item in final_workbench.candidates
        if item.file_name == "exclude.las"
    )
    assert unresolved.readiness_state.value == "review_required"
    assert excluded.readiness_state.value == "excluded"
