from pathlib import Path
from types import SimpleNamespace

from app.identity import new_uuid7_str
from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceReference,
    ManagedWellRecord,
)
from app.inventory.mwd_selected_delete import SelectedManagedDataDeleteService
from app.inventory.repository import ManagedWellInventoryRepository
from app.source_intake.models import SourceFileCandidate, SourceIntakeSnapshot


def _item(product_id: str, candidate_id: str) -> ManagedProductGroupItem:
    return ManagedProductGroupItem(
        product_id=product_id,
        managed_product_uid=new_uuid7_str(),
        managed_curve_uid=new_uuid7_str(),
        managed_source_uid=new_uuid7_str(),
        display_name=product_id,
        curve_name=product_id,
        curve_type="curve",
        source_id=candidate_id,
        source_intake_candidate_id=candidate_id,
    )


def _record(well_id: str, candidate_id: str, products: list[str]) -> ManagedWellRecord:
    items = [_item(product, candidate_id) for product in products]
    return ManagedWellRecord(
        managed_well_id=well_id,
        managed_well_uid=new_uuid7_str(),
        well_id=well_id,
        well_name=well_id,
        source_intake_candidate_id=candidate_id,
        source_references=[
            ManagedSourceReference(
                source_id=candidate_id,
                source_kind="dlis",
                display_name=f"{candidate_id}.dlis",
                managed_source_uid=items[0].managed_source_uid,
            )
        ],
        product_groups=[
            ManagedProductGroup(
                group_key="curves",
                group_label="Curves",
                items=items,
            )
        ],
        viewer_curve_count=len(items),
        displayable_curve_count=len(items),
    )


def _candidate(candidate_id: str, well_id: str, count: int) -> SourceFileCandidate:
    file_name = f"{candidate_id}.dlis"
    return SourceFileCandidate(
        source_file_id=candidate_id,
        repository_id="repo:test",
        scan_id="scan:test",
        file_name=file_name,
        original_path=f"/immutable/source/{file_name}",
        relative_path=file_name,
        file_extension=".dlis",
        detected_file_type="DLIS",
        candidate_role="well_log_candidate",
        size_bytes=1,
        modified_at="2026-07-12T00:00:00+00:00",
        checksum=f"sha256:{candidate_id}",
        content_fingerprint=f"sha256:{candidate_id}",
        registration_status="registered",
        resolution_state="resolved",
        managed_well_id=well_id,
        managed_well_name=well_id,
        registered_product_count=count,
        registered_curve_count=count,
        registered_trajectory_count=0,
        wmdp_state="staged_in_wmdp",
    )


def _service(tmp_path: Path, records, candidates):
    repo = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    for record in records:
        repo.upsert_record(record)
    source_path = tmp_path / "source_intake.json"
    source_path.write_text(
        SourceIntakeSnapshot(candidates=candidates).model_dump_json(indent=2)
    )
    workspace_path = tmp_path / "wdv_workspace.json"
    workspace_path.write_text("{}")
    canonical_path = tmp_path / "canonical.json"
    canonical_path.write_text('{"sessions": {}, "command_receipts": {}}')
    return repo, SelectedManagedDataDeleteService(
        repository=repo,
        source_intake_path=source_path,
        workspace_path=workspace_path,
        canonical_session_path=canonical_path,
    ), source_path


def test_remove_selected_well_deletes_record_and_resets_only_linked_candidate(tmp_path: Path):
    f1 = _record("managed-well:f1", "occ:f1", ["GR", "RT"])
    other = _record("managed-well:other", "occ:other", ["CALI"])
    repo, service, source_path = _service(
        tmp_path,
        [f1, other],
        [_candidate("occ:f1", f1.managed_well_id, 2), _candidate("occ:other", other.managed_well_id, 1)],
    )

    response = service.delete_selected(managed_well_ids=[f1.managed_well_id])

    assert response.action == "deleted_from_mwd"
    assert response.result.retained_msi_records is False
    assert response.result.removed_managed_well_ids == [f1.managed_well_id]
    assert [record.managed_well_id for record in repo.list_records()] == [other.managed_well_id]

    snapshot = SourceIntakeSnapshot.model_validate_json(source_path.read_text())
    by_id = {candidate.source_file_id: candidate for candidate in snapshot.candidates}
    assert by_id["occ:f1"].managed_well_id is None
    assert by_id["occ:f1"].registered_curve_count == 0
    assert by_id["occ:f1"].registration_status == "not_registered"
    assert by_id["occ:other"].managed_well_id == other.managed_well_id
    assert by_id["occ:other"].registered_curve_count == 1


def test_remove_selected_product_deletes_only_product_and_updates_candidate_counts(tmp_path: Path):
    f1 = _record("managed-well:f1", "occ:f1", ["GR", "RT"])
    repo, service, source_path = _service(
        tmp_path,
        [f1],
        [_candidate("occ:f1", f1.managed_well_id, 2)],
    )

    response = service.delete_selected(product_ids=["GR"])

    saved = repo.get_record(f1.managed_well_id)
    remaining = [
        item.product_id
        for group in saved.product_groups
        for item in group.items
    ]
    assert remaining == ["RT"]
    assert response.result.removed_product_ids == ["GR"]
    snapshot = SourceIntakeSnapshot.model_validate_json(source_path.read_text())
    candidate = snapshot.candidates[0]
    assert candidate.managed_well_id == f1.managed_well_id
    assert candidate.registered_product_count == 1
    assert candidate.registered_curve_count == 1


def test_removing_last_selected_product_deletes_empty_well_and_resets_candidate(tmp_path: Path):
    f1 = _record("managed-well:f1", "occ:f1", ["GR"])
    repo, service, source_path = _service(
        tmp_path,
        [f1],
        [_candidate("occ:f1", f1.managed_well_id, 1)],
    )

    service.delete_selected(product_ids=["GR"])

    assert repo.list_records() == []
    snapshot = SourceIntakeSnapshot.model_validate_json(source_path.read_text())
    candidate = snapshot.candidates[0]
    assert candidate.managed_well_id is None
    assert candidate.registered_product_count == 0
    assert candidate.registered_curve_count == 0
