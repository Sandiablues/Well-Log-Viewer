from pathlib import Path
from types import SimpleNamespace

from app.identity import new_uuid7_str
from app.wdv_session.canonical_command_service import CanonicalWdvCommandService
from app.wdv_session.canonical_commands import CreateTrackCommand
from app.wdv_session.canonical_service import CanonicalWdvSessionService


class FakeResolver:
    def resolve_curve(self, managed_well_uid: str, managed_curve_uid: str):
        raise AssertionError("not used by create-track test")


class RecordingTransactionService:
    def __init__(self, session):
        self.session = session
        self.calls = []

    def execute(self, managed_well_uid, **kwargs):
        self.calls.append((managed_well_uid, kwargs))
        return kwargs["mutation"](self.session).model_copy(
            update={"revision": self.session.revision + 1}
        )


def test_manual_commands_use_workspace_transaction_boundary(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    command_id = new_uuid7_str()
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    current = sessions.get_session(well_uid)
    transaction = RecordingTransactionService(current)
    service = CanonicalWdvCommandService(
        session_service=sessions,
        resolver=FakeResolver(),
        transaction_service=transaction,
    )

    result = service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=0,
            command_id=command_id,
            track_name="Gamma Ray",
        ),
    )

    assert len(transaction.calls) == 1
    called_well, kwargs = transaction.calls[0]
    assert called_well == well_uid
    assert kwargs["expected_revision"] == 0
    assert kwargs["command_id"] == command_id
    assert kwargs["command_name"] == "CreateTrackCommand"
    assert kwargs["command_payload"]["track_name"] == "Gamma Ray"
    assert "expected_revision" not in kwargs["command_payload"]
    assert "command_id" not in kwargs["command_payload"]
    assert result.tracks[0].track_name == "Gamma Ray"
