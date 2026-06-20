from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from app.identity import new_uuid7_str
from app.inventory.managed_well_purge import (
    ManagedWellPurgeRequest,
    ManagedWellPurgeService,
)
from app.inventory.models import (
    ManagedInventorySnapshot,
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.source_intake.models import (
    SourceFileCandidate,
    SourceIntakeCandidateRole,
    SourceIntakeFileType,
    SourceIntakeParseStatus,
    SourceIntakeQaqcResult,
    SourceIntakeQaqcStatus,
    SourceIntakeResolutionState,
    SourceIntakeSnapshot,
)


def _record(*, managed_well_id: str, managed_well_uid: str, well_name: str) -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id=managed_well_id,
        managed_well_uid=managed_well_uid,
        well_id=f"well:{well_name.lower().replace(' ', '-')}",
        well_name=well_name,
        source_references=[
            ManagedSourceReference(
                source_id=f"source:{managed_well_id}",
                source_kind=ManagedSourceKind.LAS,
                display_name=f"{well_name}.las",
                file_name=f"{well_name}.las",
                file_format="LAS",
            )
        ],
        product_groups=[
            ManagedProductGroup(
                group_key=f"group:{managed_well_id}",
                group_label="Openhole",
                items=[
                    ManagedProductGroupItem(
                        product_id=f"product:{managed_well_id}",
                        display_name="GR",
                        curve_name="GR",
                        curve_type="Gamma Ray",
                    )
                ],
            )
        ],
    )


def _candidate(*, candidate_id: str, managed_well_id: str | None) -> SourceFileCandidate:
    return SourceFileCandidate(
        source_file_id=candidate_id,
        repository_id="repo-1",
        scan_id="scan-1",
        file_name=f"{candidate_id}.las",
        original_path=f"/tmp/{candidate_id}.las",
        relative_path=f"{candidate_id}.las",
        file_extension="las",
        detected_file_type=SourceIntakeFileType.LAS,
        candidate_role=SourceIntakeCandidateRole.WELL_LOG_CANDIDATE,
        size_bytes=10,
        modified_at="2026-01-01T00:00:00+00:00",
        checksum=candidate_id,
        parser_status=SourceIntakeParseStatus.PARSED,
        qaqc_status=SourceIntakeQaqcResult(status=SourceIntakeQaqcStatus.PASS),
        resolution_state=(
            SourceIntakeResolutionState.REGISTERED
            if managed_well_id
            else SourceIntakeResolutionState.RESOLVED
        ),
        registration_status="registered" if managed_well_id else "not_registered",
        managed_well_id=managed_well_id,
        managed_well_name="Forge 21-31" if managed_well_id else None,
        registered_product_count=1 if managed_well_id else 0,
        registered_curve_count=1 if managed_well_id else 0,
    )


def test_targeted_purge_preserves_unrelated_records_and_resets_wsi(tmp_path: Path) -> None:
    inventory_path = tmp_path / "managed_wells.json"
    source_path = tmp_path / "source_intake.json"
    workspace_path = tmp_path / "wdv_workspace.json"
    canonical_path = tmp_path / "canonical_sessions.json"

    forge_uid = new_uuid7_str()
    other_uid = new_uuid7_str()
    forge = _record(
        managed_well_id="managed-well:forge",
        managed_well_uid=forge_uid,
        well_name="Forge 21-31",
    )
    other = _record(
        managed_well_id="managed-well:other",
        managed_well_uid=other_uid,
        well_name="Other Well",
    )
    repository = ManagedWellInventoryRepository(storage_path=inventory_path)
    repository.write_snapshot(ManagedInventorySnapshot(records=[forge, other]))

    forge_candidate = _candidate(
        candidate_id="forge-source",
        managed_well_id=forge.managed_well_id,
    )
    other_candidate = _candidate(
        candidate_id="other-source",
        managed_well_id=other.managed_well_id,
    )
    source_snapshot = SourceIntakeSnapshot(
        candidates=[forge_candidate, other_candidate]
    )
    source_path.write_text(source_snapshot.model_dump_json(indent=2))

    workspace_path.write_text(
        json.dumps(
            {
                "schema_version": "wlv_wdv_workspace_v2",
                "workspace_id": "default",
                "revision": 3,
                "active_managed_well_id": forge.managed_well_id,
                "active_managed_well_uid": forge_uid,
                "loaded_managed_well_ids": [
                    forge.managed_well_id,
                    other.managed_well_id,
                ],
                "loaded_managed_well_uids": [forge_uid, other_uid],
            }
        )
    )
    canonical_path.write_text(
        json.dumps(
            {
                "sessions": {forge_uid: {"managed_well_uid": forge_uid}},
                "command_receipts": {forge_uid: {"cmd": {}}},
            }
        )
    )

    other_before = other.model_dump(mode="json")
    other_candidate_before = other_candidate.model_dump(mode="json")

    service = ManagedWellPurgeService(
        repository=repository,
        source_intake_path=source_path,
        workspace_path=workspace_path,
        canonical_session_path=canonical_path,
    )
    response = service.purge_and_reset(
        well_reference=forge_uid,
        request=ManagedWellPurgeRequest(
            confirm="PURGE_AND_RESET",
            actor="test",
            reason="clean reload test",
        ),
    )

    assert response.removed_msi_record_count == 1
    assert response.reset_source_candidate_count == 1

    remaining = repository.list_records()
    assert [record.managed_well_id for record in remaining] == [other.managed_well_id]
    assert remaining[0].model_dump(mode="json") == other_before

    source_after = SourceIntakeSnapshot.model_validate(
        json.loads(source_path.read_text())
    )
    forge_after = next(
        item for item in source_after.candidates
        if item.source_file_id == forge_candidate.source_file_id
    )
    other_after = next(
        item for item in source_after.candidates
        if item.source_file_id == other_candidate.source_file_id
    )
    assert forge_after.managed_well_id is None
    assert forge_after.registration_status == "not_registered"
    assert forge_after.resolution_state == SourceIntakeResolutionState.RESOLVED
    assert forge_after.registered_product_count == 0
    assert forge_after.registered_curve_count == 0
    assert other_after.model_dump(mode="json") == other_candidate_before

    workspace_after = json.loads(workspace_path.read_text())
    assert forge.managed_well_id not in workspace_after["loaded_managed_well_ids"]
    assert forge_uid not in workspace_after["loaded_managed_well_uids"]
    assert workspace_after["active_managed_well_id"] == other.managed_well_id
    assert workspace_after["active_managed_well_uid"] == other_uid

    canonical_after = json.loads(canonical_path.read_text())
    assert forge_uid not in canonical_after["sessions"]
    assert forge_uid not in canonical_after["command_receipts"]


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    inventory_path = tmp_path / "managed_wells.json"
    source_path = tmp_path / "source_intake.json"
    workspace_path = tmp_path / "wdv_workspace.json"

    forge_uid = new_uuid7_str()
    forge = _record(
        managed_well_id="managed-well:forge",
        managed_well_uid=forge_uid,
        well_name="Forge 21-31",
    )
    repository = ManagedWellInventoryRepository(storage_path=inventory_path)
    repository.write_snapshot(ManagedInventorySnapshot(records=[forge]))
    source_path.write_text(
        SourceIntakeSnapshot(
            candidates=[
                _candidate(
                    candidate_id="forge-source",
                    managed_well_id=forge.managed_well_id,
                )
            ]
        ).model_dump_json(indent=2)
    )
    workspace_path.write_text(
        json.dumps(
            {
                "loaded_managed_well_ids": [forge.managed_well_id],
                "loaded_managed_well_uids": [forge_uid],
                "active_managed_well_id": forge.managed_well_id,
                "active_managed_well_uid": forge_uid,
            }
        )
    )

    before = {
        path: path.read_bytes()
        for path in (inventory_path, source_path, workspace_path)
    }
    service = ManagedWellPurgeService(
        repository=repository,
        source_intake_path=source_path,
        workspace_path=workspace_path,
        canonical_session_path=tmp_path / "missing.json",
    )
    response = service.purge_and_reset(
        well_reference=forge.managed_well_id,
        request=ManagedWellPurgeRequest(
            confirm="PURGE_AND_RESET",
            actor="test",
            reason="dry run",
            dry_run=True,
        ),
    )
    assert response.dry_run is True
    for path, payload in before.items():
        assert path.read_bytes() == payload
