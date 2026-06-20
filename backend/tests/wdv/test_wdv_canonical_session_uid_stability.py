from pathlib import Path

from app.identity import new_uuid7_str
from app.wdv_session.canonical_service import CanonicalWdvSessionService


def test_empty_session_uid_is_persisted_on_first_get(tmp_path: Path) -> None:
    service = CanonicalWdvSessionService(tmp_path / "sessions.json")
    well_uid = new_uuid7_str()

    first = service.get_session(well_uid)
    second = service.get_session(well_uid)

    assert first.session_uid == second.session_uid
    assert first.revision == 0
    assert second.revision == 0
    assert (tmp_path / "sessions.json").exists()
