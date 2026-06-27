from pathlib import Path
from types import SimpleNamespace

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import (
    WdvCanonicalAssignment,
    WdvCanonicalSession,
    WdvCanonicalTrack,
)
from app.wdv_session.canonical_command_service import CanonicalWdvCommandService
from app.wdv_session.canonical_service import CanonicalWdvSessionService


class FakeResolver:
    def __init__(self, well_uid: str, curve_uid: str) -> None:
        self.well_uid = well_uid
        self.curve_uid = curve_uid

    def resolve_curve(self, managed_well_uid: str, managed_curve_uid: str):
        assert managed_well_uid == self.well_uid
        assert managed_curve_uid == self.curve_uid
        return SimpleNamespace(
            managed_well_uid=self.well_uid,
            managed_curve_uid=self.curve_uid,
            managed_product_uid=new_uuid7_str(),
            managed_source_uid=new_uuid7_str(),
            managed_wellbore_uid=None,
            product=SimpleNamespace(
                kr_curve_type_id="density",
                observed_mnemonic="RHOZ",
                curve_name="RHOZ",
                display_name="Bulk Density",
                normalized_mnemonic="RHOZ",
                curve_family="density",
                curve_type="density",
                curve_description="Bulk density",
                curve_unit="G/C3",
            ),
        )


def family_policy(_product):
    return {
        "min": 1.95,
        "max": 2.95,
        "type": "linear",
        "direction": "normal",
        "source": "managed_knowledge_family_default",
    }


def assignment(
    *,
    well_uid: str,
    curve_uid: str,
    track_uid: str,
    policy_source: str | None,
    scale_min: float | None,
    scale_max: float | None,
) -> WdvCanonicalAssignment:
    return WdvCanonicalAssignment(
        assignment_uid=new_uuid7_str(),
        managed_curve_uid=curve_uid,
        managed_product_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        managed_source_uid=new_uuid7_str(),
        track_uid=track_uid,
        observed_mnemonic="RHOZ",
        display_name="Bulk Density",
        scale_min=scale_min,
        scale_max=scale_max,
        scale_type="linear" if scale_min is not None else None,
        scale_direction="normal" if scale_min is not None else None,
        source="manual_backend_command",
        display_policy_source=policy_source,
    )


def session_with(
    assignment_value: WdvCanonicalAssignment,
    *,
    revision: str,
) -> WdvCanonicalSession:
    return WdvCanonicalSession(
        session_uid=new_uuid7_str(),
        managed_well_uid=assignment_value.managed_well_uid,
        state_status="active",
        tracks=(
            WdvCanonicalTrack(
                track_uid=assignment_value.track_uid,
                track_name="Density",
                track_type="curve",
                assignments=(assignment_value,),
            ),
        ),
        display_policy_revision=revision,
        updated_at="2026-06-26T10:40:00+00:00",
    )


def build_service(
    tmp_path: Path,
    *,
    well_uid: str,
    curve_uid: str,
) -> CanonicalWdvSessionService:
    session_service = CanonicalWdvSessionService(
        tmp_path / "sessions.json",
    )
    CanonicalWdvCommandService(
        session_service=session_service,
        resolver=FakeResolver(well_uid, curve_uid),
        policy_revision_fn=lambda: "new-policy",
        display_policy_resolver=family_policy,
    )
    return session_service


def test_stale_backend_policy_is_reresolved_and_persisted(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    service = build_service(
        tmp_path,
        well_uid=well_uid,
        curve_uid=curve_uid,
    )
    service.put_session(
        session_with(
            assignment(
                well_uid=well_uid,
                curve_uid=curve_uid,
                track_uid=track_uid,
                policy_source="curve",
                scale_min=0.0,
                scale_max=1.0,
            ),
            revision="old-policy",
        )
    )

    refreshed = service.get_session(well_uid)
    value = refreshed.tracks[0].assignments[0]

    assert refreshed.display_policy_revision == "new-policy"
    assert value.scale_min == 1.95
    assert value.scale_max == 2.95
    assert value.display_policy_source == "family"

    reread = service.get_session(well_uid)
    assert reread.revision == refreshed.revision
    assert reread.tracks[0].assignments[0].scale_min == 1.95


def test_stale_explicit_manual_override_is_retained(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    service = build_service(
        tmp_path,
        well_uid=well_uid,
        curve_uid=curve_uid,
    )
    manual_assignment = assignment(
        well_uid=well_uid,
        curve_uid=curve_uid,
        track_uid=track_uid,
        policy_source="family",
        scale_min=2.1,
        scale_max=2.8,
    ).model_copy(
        update={
            "range_override_mode": "manual",
            "manual_scale_min": 2.1,
            "manual_scale_max": 2.8,
            "effective_range_source": "manual",
        }
    )
    service.put_session(
        session_with(
            manual_assignment,
            revision="old-policy",
        )
    )

    refreshed = service.get_session(well_uid)
    value = refreshed.tracks[0].assignments[0]

    assert value.range_override_mode == "manual"
    assert value.effective_range_source == "manual"
    assert value.manual_scale_min == 2.1
    assert value.manual_scale_max == 2.8
    assert value.scale_min == 2.1
    assert value.scale_max == 2.8
    assert value.display_policy_source == "family"

def test_legacy_non_null_scale_without_explicit_override_migrates_to_governed(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    service = build_service(
        tmp_path,
        well_uid=well_uid,
        curve_uid=curve_uid,
    )
    service.put_session(
        session_with(
            assignment(
                well_uid=well_uid,
                curve_uid=curve_uid,
                track_uid=track_uid,
                policy_source=None,
                scale_min=2.1,
                scale_max=2.8,
            ),
            revision="old-policy",
        )
    )

    refreshed = service.get_session(well_uid)
    value = refreshed.tracks[0].assignments[0]

    assert value.range_override_mode == "governed"
    assert value.effective_range_source == "governed"
    assert value.manual_scale_min is None
    assert value.manual_scale_max is None
    assert value.scale_min == 1.95
    assert value.scale_max == 2.95
    assert value.display_policy_source == "family"

def test_legacy_assignment_without_scale_is_migrated_to_backend_policy(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    service = build_service(
        tmp_path,
        well_uid=well_uid,
        curve_uid=curve_uid,
    )
    service.put_session(
        session_with(
            assignment(
                well_uid=well_uid,
                curve_uid=curve_uid,
                track_uid=track_uid,
                policy_source=None,
                scale_min=None,
                scale_max=None,
            ),
            revision="old-policy",
        )
    )

    refreshed = service.get_session(well_uid)
    value = refreshed.tracks[0].assignments[0]

    assert value.scale_min == 1.95
    assert value.scale_max == 2.95
    assert value.display_policy_source == "family"


def test_matching_revision_is_idempotent(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    service = build_service(
        tmp_path,
        well_uid=well_uid,
        curve_uid=curve_uid,
    )
    stored = service.put_session(
        session_with(
            assignment(
                well_uid=well_uid,
                curve_uid=curve_uid,
                track_uid=track_uid,
                policy_source="family",
                scale_min=1.95,
                scale_max=2.95,
            ),
            revision="new-policy",
        )
    )

    reread = service.get_session(well_uid)
    assert reread.revision == stored.revision


def test_command_mutation_stamps_policy_revision_without_read_side_revision_bump(
    tmp_path: Path,
) -> None:
    from app.wdv_session.canonical_commands import CreateConfiguredTrackCommand

    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    session_service = CanonicalWdvSessionService(
        tmp_path / "sessions.json",
    )
    command_service = CanonicalWdvCommandService(
        session_service=session_service,
        resolver=FakeResolver(well_uid, curve_uid),
        policy_revision_fn=lambda: "new-policy",
        display_policy_resolver=family_policy,
    )

    created = command_service.create_configured_track(
        well_uid,
        CreateConfiguredTrackCommand(
            expected_revision=0,
            track_name="Density",
            initial_managed_curve_uids=(curve_uid,),
        ),
    )

    assert created.revision == 1
    assert created.display_policy_revision == "new-policy"

    reread = session_service.get_session(well_uid)
    assert reread.revision == 1
    assert reread.display_policy_revision == "new-policy"
