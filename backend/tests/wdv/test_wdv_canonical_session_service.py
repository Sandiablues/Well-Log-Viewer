from pathlib import Path

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalSession
from app.wdv_session.canonical_service import CanonicalWdvSessionService


def test_canonical_session_stability_and_clear(tmp_path: Path) -> None:
    service = CanonicalWdvSessionService(tmp_path / "sessions.json")
    well_uid = new_uuid7_str()

    empty = service.get_session(well_uid)
    reread = service.get_session(well_uid)

    assert empty.session_uid == reread.session_uid
    assert empty.revision == 0
    assert reread.revision == 0

    stored = service.put_session(
        WdvCanonicalSession(
            session_uid=empty.session_uid,
            managed_well_uid=well_uid,
            state_status="empty",
            tracks=(),
            updated_at="2026-06-18T20:00:00+00:00",
        )
    )
    assert service.get_session(well_uid).session_uid == stored.session_uid

    cleared = service.clear_session(well_uid, "test")
    assert cleared.session_uid == stored.session_uid
    assert cleared.state_status == "cleared"
    assert cleared.revision == stored.revision + 1
