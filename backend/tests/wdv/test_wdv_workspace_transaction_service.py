from pathlib import Path

import pytest

from app.identity import new_uuid7_str
from app.wdv_session.canonical_service import (
    CanonicalSessionCommandReplayConflict,
    CanonicalWdvSessionService,
)
from app.wdv_workspace.transaction_service import (
    CanonicalWdvWorkspaceTransactionService,
)


class RecordingWorkspaceValidator:
    def __init__(self) -> None:
        self.sessions = []
        self.reject = False

    def validate_session(self, managed_well_uid, session):
        assert session.managed_well_uid == managed_well_uid
        self.sessions.append(session)
        if self.reject:
            raise ValueError("workspace rejected candidate")
        return object()


def test_transaction_is_idempotent_and_revision_stable(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    command_id = new_uuid7_str()
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    validator = RecordingWorkspaceValidator()
    service = CanonicalWdvWorkspaceTransactionService(
        session_service=sessions,
        workspace_service=validator,
    )

    calls = 0

    def mutation(session):
        nonlocal calls
        calls += 1
        return session.model_copy(update={"warnings": ("activated",)})

    first = service.execute(
        well_uid,
        expected_revision=0,
        command_name="Activate",
        command_payload={"value": 1},
        command_id=command_id,
        mutation=mutation,
    )
    replay = service.execute(
        well_uid,
        expected_revision=0,
        command_name="Activate",
        command_payload={"value": 1},
        command_id=command_id,
        mutation=mutation,
    )

    assert calls == 1
    assert first == replay
    assert first.revision == 1
    assert sessions.get_session(well_uid).revision == 1
    assert len(validator.sessions) == 1


def test_command_id_reuse_with_different_payload_is_rejected(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    command_id = new_uuid7_str()
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    service = CanonicalWdvWorkspaceTransactionService(
        session_service=sessions,
    )

    service.execute(
        well_uid,
        expected_revision=0,
        command_name="Activate",
        command_payload={"value": 1},
        command_id=command_id,
        mutation=lambda session: session.model_copy(
            update={"warnings": ("activated",)}
        ),
    )

    with pytest.raises(CanonicalSessionCommandReplayConflict):
        service.execute(
            well_uid,
            expected_revision=1,
            command_name="Activate",
            command_payload={"value": 2},
            command_id=command_id,
            mutation=lambda session: session,
        )

    assert sessions.get_session(well_uid).revision == 1


def test_workspace_rejection_leaves_session_and_receipt_store_unchanged(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    command_id = new_uuid7_str()
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    validator = RecordingWorkspaceValidator()
    validator.reject = True
    service = CanonicalWdvWorkspaceTransactionService(
        session_service=sessions,
        workspace_service=validator,
    )

    with pytest.raises(ValueError, match="workspace rejected candidate"):
        service.execute(
            well_uid,
            expected_revision=0,
            command_name="Activate",
            command_payload={},
            command_id=command_id,
            mutation=lambda session: session.model_copy(
                update={"warnings": ("activated",)}
            ),
        )

    persisted = sessions.get_session(well_uid)
    assert persisted.revision == 0
    assert persisted.state_status == "empty"

    store_text = (tmp_path / "sessions.json").read_text()
    assert command_id not in store_text


def test_transaction_without_command_id_does_not_create_receipt(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    service = CanonicalWdvWorkspaceTransactionService(
        session_service=sessions,
    )

    result = service.execute(
        well_uid,
        expected_revision=0,
        command_name="Warn",
        command_payload={"value": 1},
        command_id=None,
        mutation=lambda session: session.model_copy(
            update={"warnings": ("one",)}
        ),
    )

    assert result.revision == 1
    store_text = (tmp_path / "sessions.json").read_text()
    assert '"command_receipts": {}' in store_text


def test_canonical_session_contract_is_enforced_without_workspace_service(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    service = CanonicalWdvWorkspaceTransactionService(
        session_service=sessions,
    )

    with pytest.raises(
        ValueError,
        match="Active WDV sessions must contain at least one track",
    ):
        service.execute(
            well_uid,
            expected_revision=0,
            command_name="InvalidActivate",
            command_payload={},
            command_id=None,
            mutation=lambda session: session.model_copy(
                update={"state_status": "active"}
            ),
        )

    persisted = sessions.get_session(well_uid)
    assert persisted.revision == 0
    assert persisted.state_status == "empty"
