from app.identity import is_uuid7, new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalTrack
from app.wdv_session.canonical_service import CanonicalWdvSessionService


def test_unified_session_shared_and_uuid7(tmp_path, monkeypatch):
    monkeypatch.setenv("WLV_UNIFIED_MULTIWELL_SESSION", "1")
    well_a, well_b = new_uuid7_str(), new_uuid7_str()
    service = CanonicalWdvSessionService(storage_path=tmp_path / "sessions.json")
    first = service.get_session(well_a)
    second = service.get_session(well_b)
    assert first.session_uid == second.session_uid
    assert second.managed_well_uid == well_b
    assert all(is_uuid7(value) for value in (first.session_uid, well_a, well_b))


def test_legacy_fallback_uses_uuid7_per_well(tmp_path, monkeypatch):
    monkeypatch.setenv("WLV_UNIFIED_MULTIWELL_SESSION", "0")
    well_a, well_b = new_uuid7_str(), new_uuid7_str()
    service = CanonicalWdvSessionService(storage_path=tmp_path / "sessions.json")
    first = service.get_session(well_a)
    second = service.get_session(well_b)
    assert first.session_uid != second.session_uid
    assert is_uuid7(first.session_uid) and is_uuid7(second.session_uid)


def test_track_requires_uuid7_well_owner():
    track = WdvCanonicalTrack(track_uid=new_uuid7_str(), managed_well_uid=new_uuid7_str(), track_name="Owned")
    assert is_uuid7(track.track_uid) and is_uuid7(track.managed_well_uid)
