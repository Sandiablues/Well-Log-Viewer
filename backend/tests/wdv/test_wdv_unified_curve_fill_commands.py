from pathlib import Path

from app.curve_fill_v2.canonical_service import CanonicalCurveFillService
from app.curve_fill_v2.commands import CreateCurveFillRuleCommand
from app.curve_fill_v2.models import Boundary, FillStyle, RuleType
from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import (
    WdvCanonicalAssignment,
    WdvCanonicalSession,
    WdvCanonicalTrack,
)
from app.wdv_session.canonical_command_service import CanonicalWdvCommandService
from app.wdv_session.canonical_commands import ClearCanvasCommand, RemoveTrackCommand
from app.wdv_session.canonical_service import CanonicalWdvSessionService
from app.wdv_workspace.transaction_service import CanonicalWdvWorkspaceTransactionService


def _assignment(track_uid: str, well_uid: str, mnemonic: str) -> WdvCanonicalAssignment:
    return WdvCanonicalAssignment(
        assignment_uid=new_uuid7_str(),
        managed_curve_uid=new_uuid7_str(),
        managed_product_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        managed_source_uid=new_uuid7_str(),
        track_uid=track_uid,
        observed_mnemonic=mnemonic,
        display_name=mnemonic,
        unit="gAPI",
        curve_family="gamma_ray",
        scale_min=0.0,
        scale_max=150.0,
        scale_type="linear",
        scale_direction="normal",
        display_policy_source="family",
    )


def _seed_with_fill(store: Path, owner_well_uid: str):
    track_uid = new_uuid7_str()
    curve = _assignment(track_uid, owner_well_uid, "GR")
    track = WdvCanonicalTrack(
        track_uid=track_uid,
        managed_well_uid=owner_well_uid,
        track_name="GR",
        assignments=(curve,),
    )
    session_service = CanonicalWdvSessionService(storage_path=store)
    seeded = session_service.put_session(
        WdvCanonicalSession(
            session_uid=new_uuid7_str(),
            managed_well_uid=owner_well_uid,
            state_status="active",
            tracks=(track,),
            selected_track_uid=track_uid,
            display_policy_revision="test-policy",
            updated_at="2026-07-04T15:00:00+00:00",
        )
    )
    filled = CanonicalCurveFillService(session_service=session_service).create_rule(
        owner_well_uid,
        CreateCurveFillRuleCommand(
            expected_revision=seeded.revision,
            track_uid=track_uid,
            curve_a_assignment_uid=curve.assignment_uid,
            rule_type=RuleType.TO_BOUNDARY,
            boundary=Boundary.RIGHT,
            style=FillStyle(color="#999999", opacity=0.45),
        ),
    )
    commands = CanonicalWdvCommandService(
        session_service=session_service,
        transaction_service=CanonicalWdvWorkspaceTransactionService(
            session_service=session_service,
            workspace_service=None,
        ),
        policy_revision_fn=lambda: "test-policy",
    )
    return session_service, commands, filled, track_uid


def test_clear_canvas_from_other_working_well_removes_foreign_owned_fill(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("WLV_UNIFIED_MULTIWELL_SESSION", "1")
    owner_well_uid = new_uuid7_str()
    working_well_uid = new_uuid7_str()
    _sessions, commands, filled, _track_uid = _seed_with_fill(
        tmp_path / "sessions.json", owner_well_uid
    )

    projected = commands.session_service.get_session(working_well_uid)
    assert projected.managed_well_uid == working_well_uid
    assert projected.curve_fills[0].managed_well_uid == owner_well_uid

    cleared = commands.clear_canvas(
        working_well_uid,
        ClearCanvasCommand(
            expected_revision=filled.revision,
            preserve_depth_tracks=False,
        ),
    )
    assert cleared.state_status == "empty"
    assert cleared.tracks == ()
    assert cleared.curve_fills == ()


def test_remove_track_from_other_working_well_removes_foreign_owned_fill(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("WLV_UNIFIED_MULTIWELL_SESSION", "1")
    owner_well_uid = new_uuid7_str()
    working_well_uid = new_uuid7_str()
    _sessions, commands, filled, track_uid = _seed_with_fill(
        tmp_path / "sessions.json", owner_well_uid
    )

    removed = commands.remove_track(
        working_well_uid,
        RemoveTrackCommand(
            expected_revision=filled.revision,
            track_uid=track_uid,
        ),
    )
    assert removed.state_status == "empty"
    assert removed.tracks == ()
    assert removed.curve_fills == ()
