"""C2 tests — WDV canonical curve scale override and reset.

Tests 5–9 of the C2 requirement:
  5. WDV override changes only that curve UID.
  6. Duplicate mnemonics with different curve UIDs remain independent.
  7. Reset clears the assignment override.
  8. After reset, effective display returns to the governed scale
     (assignment scale fields are None — governed values in contract are used).
  9. KR content and semantic revision do not change when a user edits/resets.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import (
    WdvCanonicalAssignment,
    WdvCanonicalSession,
    WdvCanonicalTrack,
)
from app.inventory.canonical_identity_resolver import CanonicalInventoryIdentityResolver
from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.wdv_session.canonical_commands import UpdateCurveAssignmentCommand
from app.wdv_session.canonical_command_service import CanonicalWdvCommandService
from app.wdv_session.canonical_service import CanonicalWdvSessionService
from app.wdv_display.policy_service import (
    compute_display_policy_revision,
    _clear_display_policy_revision_cache_for_tests,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_revision_cache():
    _clear_display_policy_revision_cache_for_tests()
    yield
    _clear_display_policy_revision_cache_for_tests()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assignment(
    *,
    well_uid: str,
    track_uid: str,
    curve_uid: str | None = None,
    mnemonic: str = "GR",
    stack_index: int = 0,
    scale_min: float | None = None,
    scale_max: float | None = None,
    scale_type: str | None = None,
    scale_direction: str | None = None,
) -> WdvCanonicalAssignment:
    return WdvCanonicalAssignment(
        assignment_uid=new_uuid7_str(),
        managed_curve_uid=curve_uid or new_uuid7_str(),
        managed_product_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        managed_wellbore_uid=new_uuid7_str(),
        managed_source_uid=new_uuid7_str(),
        track_uid=track_uid,
        observed_mnemonic=mnemonic,
        display_name=mnemonic,
        stack_index=stack_index,
        scale_min=scale_min,
        scale_max=scale_max,
        scale_type=scale_type,
        scale_direction=scale_direction,
    )


def _build_session(
    well_uid: str,
    assignments: list[WdvCanonicalAssignment],
    revision: int = 0,
) -> WdvCanonicalSession:
    """Build a session with all assignments on a single curve track."""
    track_uid = assignments[0].track_uid if assignments else new_uuid7_str()
    track = WdvCanonicalTrack(
        track_uid=track_uid,
        track_name="Track 1",
        assignments=tuple(assignments),
    )
    return WdvCanonicalSession(
        session_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        revision=revision,
        state_status="active",
        tracks=(track,),
        updated_at=_now_iso(),
    )


def _service(
    tmp_path: Path,
    well_uid: str,
    assignments: list[WdvCanonicalAssignment],
) -> tuple[CanonicalWdvCommandService, CanonicalWdvSessionService]:
    """Build a fully-wired command+session service pair backed by a temp inventory.

    The inventory is derived from *assignments* so that the workspace validator
    (WdvCanonicalWorkspace.validate_workspace_graph) finds a matching curve
    registry entry for every assignment.  The validator requires that each
    assignment's managed_curve_uid, managed_product_uid, managed_source_uid,
    and managed_wellbore_uid all match the corresponding inventory curve.

    The resolver is a real CanonicalInventoryIdentityResolver, so workspace
    validation runs in full — it is not bypassed.
    """
    # One source reference per unique managed_source_uid in the assignments.
    source_refs: dict[str, ManagedSourceReference] = {}
    for a in assignments:
        uid = a.managed_source_uid
        if uid not in source_refs:
            source_refs[uid] = ManagedSourceReference(
                source_id=uid,
                managed_source_uid=uid,
                source_kind=ManagedSourceKind.LAS,
                display_name="Test LAS",
            )

    # One inventory product item per assignment, using the assignment's UIDs
    # so that the workspace validator's cross-checks all pass.
    items = [
        ManagedProductGroupItem(
            product_id=a.managed_curve_uid,
            managed_product_uid=a.managed_product_uid,
            managed_curve_uid=a.managed_curve_uid,
            managed_wellbore_uid=a.managed_wellbore_uid,
            managed_source_uid=a.managed_source_uid,
            display_name=a.display_name,
            curve_name=a.observed_mnemonic,
            curve_type="curve",
            curve_family="gamma_ray",
        )
        for a in assignments
    ]

    repository = ManagedWellInventoryRepository(
        storage_path=tmp_path / "inventory.json"
    )
    repository.upsert_record(
        ManagedWellRecord(
            managed_well_id=well_uid,
            managed_well_uid=well_uid,
            well_id=well_uid,
            well_name="Test Well",
            source_references=list(source_refs.values()),
            product_groups=[
                ManagedProductGroup(
                    group_key="logs",
                    group_label="Logs",
                    items=items,
                )
            ],
        )
    )

    resolver = CanonicalInventoryIdentityResolver(repository=repository)
    session_service = CanonicalWdvSessionService(
        storage_path=tmp_path / "sessions.json"
    )
    command_service = CanonicalWdvCommandService(
        session_service=session_service,
        resolver=resolver,
    )
    return command_service, session_service


def _update_command(
    assignment_uid: str,
    revision: int = 0,
    *,
    scale_min: float | None = None,
    scale_max: float | None = None,
    scale_type: str | None = None,
    scale_direction: str | None = None,
    reset_scale_to_governed_default: bool = False,
) -> UpdateCurveAssignmentCommand:
    return UpdateCurveAssignmentCommand(
        expected_revision=revision,
        assignment_uid=assignment_uid,
        scale_min=scale_min,
        scale_max=scale_max,
        scale_type=scale_type,
        scale_direction=scale_direction,
        reset_scale_to_governed_default=reset_scale_to_governed_default,
    )


# ---------------------------------------------------------------------------
# Test 5 — WDV override changes only that curve UID
# ---------------------------------------------------------------------------

def test_override_changes_only_targeted_curve_uid(tmp_path: Path) -> None:
    """Applying a scale override to one assignment does not change another."""
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    curve_uid_a = new_uuid7_str()
    curve_uid_b = new_uuid7_str()

    # stack_index must be contiguous (0, 1) for workspace validation to pass.
    assignment_a = _assignment(
        well_uid=well_uid, track_uid=track_uid,
        curve_uid=curve_uid_a, mnemonic="GR", stack_index=0,
    )
    assignment_b = _assignment(
        well_uid=well_uid, track_uid=track_uid,
        curve_uid=curve_uid_b, mnemonic="GR", stack_index=1,
    )

    command_service, session_service = _service(
        tmp_path, well_uid, [assignment_a, assignment_b]
    )

    track = WdvCanonicalTrack(
        track_uid=track_uid,
        track_name="Track 1",
        assignments=(assignment_a, assignment_b),
    )
    session = WdvCanonicalSession(
        session_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        revision=0,
        state_status="active",
        tracks=(track,),
        updated_at=_now_iso(),
    )
    session_service.put_session(session)

    # Override assignment_a only
    cmd = _update_command(
        assignment_a.assignment_uid,
        revision=0,
        scale_min=10.0,
        scale_max=100.0,
        scale_type="linear",
    )
    result = command_service.update_assignment(well_uid, cmd)

    by_curve = {a.managed_curve_uid: a for a in result.tracks[0].assignments}
    # assignment_a changed
    assert by_curve[curve_uid_a].scale_min == pytest.approx(10.0)
    assert by_curve[curve_uid_a].scale_max == pytest.approx(100.0)
    # assignment_b unchanged
    assert by_curve[curve_uid_b].scale_min is None
    assert by_curve[curve_uid_b].scale_max is None


# ---------------------------------------------------------------------------
# Test 6 — duplicate mnemonics with different UIDs remain independent
# ---------------------------------------------------------------------------

def test_duplicate_mnemonic_overrides_are_uid_independent(tmp_path: Path) -> None:
    """Same mnemonic, different managed_curve_uids — overrides are independent."""
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    curve_uid_1 = new_uuid7_str()
    curve_uid_2 = new_uuid7_str()

    # stack_index must be contiguous (0, 1) for workspace validation to pass.
    a1 = _assignment(
        well_uid=well_uid, track_uid=track_uid,
        curve_uid=curve_uid_1, mnemonic="RT", stack_index=0,
    )
    a2 = _assignment(
        well_uid=well_uid, track_uid=track_uid,
        curve_uid=curve_uid_2, mnemonic="RT", stack_index=1,
    )

    command_service, session_service = _service(tmp_path, well_uid, [a1, a2])

    track = WdvCanonicalTrack(
        track_uid=track_uid,
        track_name="Track 1",
        assignments=(a1, a2),
    )
    session = WdvCanonicalSession(
        session_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        revision=0,
        state_status="active",
        tracks=(track,),
        updated_at=_now_iso(),
    )
    session_service.put_session(session)

    # Override a1 only
    cmd = _update_command(
        a1.assignment_uid, revision=0,
        scale_min=1.0, scale_max=500.0, scale_type="logarithmic",
    )
    result = command_service.update_assignment(well_uid, cmd)

    by_uid = {a.managed_curve_uid: a for a in result.tracks[0].assignments}
    assert by_uid[curve_uid_1].scale_min == pytest.approx(1.0)
    assert by_uid[curve_uid_1].scale_max == pytest.approx(500.0)
    assert by_uid[curve_uid_1].scale_type == "logarithmic"
    # Second RT curve with different UID is untouched
    assert by_uid[curve_uid_2].scale_min is None
    assert by_uid[curve_uid_2].scale_max is None
    assert by_uid[curve_uid_2].scale_type is None


# ---------------------------------------------------------------------------
# Test 7 — reset clears the assignment override
# ---------------------------------------------------------------------------

def test_reset_clears_all_scale_override_fields(tmp_path: Path) -> None:
    """reset_scale_to_governed_default=True clears all four scale fields."""
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()

    assignment = _assignment(
        well_uid=well_uid,
        track_uid=track_uid,
        scale_min=50.0,
        scale_max=500.0,
        scale_type="logarithmic",
        scale_direction="normal",
    )
    command_service, session_service = _service(tmp_path, well_uid, [assignment])
    session_service.put_session(_build_session(well_uid, [assignment]))

    cmd = _update_command(
        assignment.assignment_uid, revision=0,
        reset_scale_to_governed_default=True,
    )
    result = command_service.update_assignment(well_uid, cmd)

    cleared = result.tracks[0].assignments[0]
    assert cleared.scale_min is None
    assert cleared.scale_max is None
    assert cleared.scale_type is None
    assert cleared.scale_direction is None


# ---------------------------------------------------------------------------
# Test 8 — after reset, effective display returns to governed scale
# ---------------------------------------------------------------------------

def test_after_reset_assignment_carries_no_override(tmp_path: Path) -> None:
    """After reset, all four scale fields are None — governing contract values apply.

    The governed scale lives in the wdv_load_session_contract loaded_curve_items
    (display_left_value, display_right_value, scale_source etc.).  The canonical
    assignment with None scale fields signals 'no override — use governed values.'
    This test verifies the None state; the governed values themselves come from
    WdvCurveDisplayPolicyService and are covered by policy_precedence tests.
    """
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()

    # Start with a pre-set override so the reset has something to clear.
    assignment = _assignment(
        well_uid=well_uid,
        track_uid=track_uid,
        scale_min=0.5,
        scale_max=500.0,
        scale_type="logarithmic",
        scale_direction="normal",
    )
    command_service, session_service = _service(tmp_path, well_uid, [assignment])
    session_service.put_session(_build_session(well_uid, [assignment]))

    assert assignment.scale_min is not None  # confirm starting state

    cmd = _update_command(
        assignment.assignment_uid, revision=0,
        reset_scale_to_governed_default=True,
    )
    result = command_service.update_assignment(well_uid, cmd)

    final = result.tracks[0].assignments[0]
    assert final.scale_min is None, "scale_min must be None after reset"
    assert final.scale_max is None, "scale_max must be None after reset"
    assert final.scale_type is None, "scale_type must be None after reset"
    assert final.scale_direction is None, "scale_direction must be None after reset"
    # Non-scale identity fields must be preserved
    assert final.managed_curve_uid == assignment.managed_curve_uid
    assert final.assignment_uid == assignment.assignment_uid
    assert final.observed_mnemonic == assignment.observed_mnemonic


# ---------------------------------------------------------------------------
# Test 9 — KR content and semantic revision unchanged by user edits/resets
# ---------------------------------------------------------------------------

def test_user_scale_edit_and_reset_do_not_change_policy_revision(tmp_path: Path) -> None:
    """Editing and resetting a WDV assignment scale must not alter the KR or
    the semantic policy revision — the governed policy revision is KR-content-based
    and WDV session mutations are completely orthogonal."""
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()

    assignment = _assignment(well_uid=well_uid, track_uid=track_uid)
    command_service, session_service = _service(tmp_path, well_uid, [assignment])
    session_service.put_session(_build_session(well_uid, [assignment]))

    revision_before = compute_display_policy_revision()

    # Apply a user scale override
    cmd_edit = _update_command(
        assignment.assignment_uid, revision=0,
        scale_min=0.1, scale_max=1000.0, scale_type="logarithmic",
    )
    command_service.update_assignment(well_uid, cmd_edit)
    revision_after_edit = compute_display_policy_revision()

    # Apply reset — read current revision from stored session
    current_rev = session_service.get_session(well_uid).revision
    cmd_reset = _update_command(
        assignment.assignment_uid, revision=current_rev,
        reset_scale_to_governed_default=True,
    )
    command_service.update_assignment(well_uid, cmd_reset)
    revision_after_reset = compute_display_policy_revision()

    assert revision_after_edit == revision_before, (
        "User scale edit must not change the governed policy revision"
    )
    assert revision_after_reset == revision_before, (
        "Scale reset must not change the governed policy revision"
    )


# ---------------------------------------------------------------------------
# validate_patch — command-level guard tests (no inventory needed)
# ---------------------------------------------------------------------------

def test_reset_combined_with_explicit_scale_is_rejected() -> None:
    """reset_scale_to_governed_default may not be combined with explicit scale fields."""
    with pytest.raises(ValueError, match="reset_scale_to_governed_default"):
        UpdateCurveAssignmentCommand(
            expected_revision=0,
            assignment_uid=new_uuid7_str(),
            scale_min=1.0,
            scale_max=100.0,
            reset_scale_to_governed_default=True,
        )


def test_empty_command_is_rejected() -> None:
    """A command with no fields set at all must be rejected."""
    with pytest.raises(ValueError, match="requires at least one field"):
        UpdateCurveAssignmentCommand(
            expected_revision=0,
            assignment_uid=new_uuid7_str(),
        )


# ---------------------------------------------------------------------------
# UNIT-3B — revision-stamping lifecycle
# (additions only; all content above is the unmodified pre-existing baseline)
# ---------------------------------------------------------------------------


def _service_with_fn(
    tmp_path,
    well_uid,
    assignments,
    revision_fn,
):
    """Like _service() but injects policy_revision_fn into both services (UNIT-3B)."""
    source_refs = {}
    for a in assignments:
        uid = a.managed_source_uid
        if uid not in source_refs:
            source_refs[uid] = ManagedSourceReference(
                source_id=uid,
                managed_source_uid=uid,
                source_kind=ManagedSourceKind.LAS,
                display_name="Test LAS",
            )

    items = [
        ManagedProductGroupItem(
            product_id=a.managed_curve_uid,
            managed_product_uid=a.managed_product_uid,
            managed_curve_uid=a.managed_curve_uid,
            managed_wellbore_uid=a.managed_wellbore_uid,
            managed_source_uid=a.managed_source_uid,
            display_name=a.display_name,
            curve_name=a.observed_mnemonic,
            curve_type="curve",
            curve_family="gamma_ray",
        )
        for a in assignments
    ]

    repository = ManagedWellInventoryRepository(
        storage_path=tmp_path / "inventory.json"
    )
    repository.upsert_record(
        ManagedWellRecord(
            managed_well_id=well_uid,
            managed_well_uid=well_uid,
            well_id=well_uid,
            well_name="Test Well",
            source_references=list(source_refs.values()),
            product_groups=[
                ManagedProductGroup(
                    group_key="logs",
                    group_label="Logs",
                    items=items,
                )
            ],
        )
    )

    resolver = CanonicalInventoryIdentityResolver(repository=repository)
    session_service = CanonicalWdvSessionService(
        storage_path=tmp_path / "sessions.json",
        policy_revision_fn=revision_fn,
    )
    command_service = CanonicalWdvCommandService(
        session_service=session_service,
        resolver=resolver,
        policy_revision_fn=revision_fn,
    )
    return command_service, session_service


# ---------------------------------------------------------------------------
# Test C2-10 — new override stamps revision; survives next get_session
# ---------------------------------------------------------------------------

def test_update_assignment_stamps_revision_and_override_survives(tmp_path: Path) -> None:
    """update_assignment stamps display_policy_revision; get_session does not clear it."""
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    assignment = _assignment(well_uid=well_uid, track_uid=track_uid)

    revision_fn = lambda: "rev-stable"  # noqa: E731
    cmd_svc, session_svc = _service_with_fn(
        tmp_path, well_uid, [assignment], revision_fn
    )
    session_svc.put_session(_build_session(well_uid, [assignment]))

    # Apply scale override — must stamp display_policy_revision atomically.
    cmd = _update_command(
        assignment.assignment_uid,
        revision=0,
        scale_min=10.0,
        scale_max=100.0,
        scale_type="linear",
    )
    after_update = cmd_svc.update_assignment(well_uid, cmd)

    assert after_update.display_policy_revision == "rev-stable"

    # Reload via get_session — overrides must NOT be cleared (revision matches).
    reloaded = session_svc.get_session(well_uid)
    a = reloaded.tracks[0].assignments[0]
    assert a.scale_min == pytest.approx(10.0)
    assert a.scale_type == "linear"
    assert reloaded.display_policy_revision == "rev-stable"


# ---------------------------------------------------------------------------
# Test C2-11 — editing existing override re-stamps current revision
# ---------------------------------------------------------------------------

def test_edit_override_stamps_current_revision(tmp_path: Path) -> None:
    """Editing a scale override re-stamps display_policy_revision to the current value."""
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    assignment = _assignment(
        well_uid=well_uid,
        track_uid=track_uid,
        scale_min=1.0,
        scale_max=200.0,
    )

    revision_fn = lambda: "rev-new"  # noqa: E731
    cmd_svc, session_svc = _service_with_fn(
        tmp_path, well_uid, [assignment], revision_fn
    )
    # Seed with an old revision stamp
    old_session = _build_session(well_uid, [assignment])
    # Inject old stamp via put_session on a service with same storage
    from app.wdv_session.canonical_service import CanonicalWdvSessionService as _Svc
    seed_svc = _Svc(
        storage_path=tmp_path / "sessions.json",
        policy_revision_fn=lambda: "rev-old",
    )
    seed_svc.put_session(
        old_session.model_copy(update={"display_policy_revision": "rev-old"})
    )

    # Edit the override — must stamp "rev-new" atomically.
    current_rev = seed_svc.get_session(well_uid).revision
    cmd = _update_command(
        assignment.assignment_uid,
        revision=current_rev,
        scale_min=5.0,
        scale_max=500.0,
        scale_type="logarithmic",
    )
    after_edit = cmd_svc.update_assignment(well_uid, cmd)

    assert after_edit.display_policy_revision == "rev-new"

    # get_session must not clear the override (revision now matches "rev-new").
    reloaded = session_svc.get_session(well_uid)
    a = reloaded.tracks[0].assignments[0]
    assert a.scale_min == pytest.approx(5.0)
    assert reloaded.display_policy_revision == "rev-new"


# ---------------------------------------------------------------------------
# Test C2-12 — reset does not cause false stale clear on next get_session
# ---------------------------------------------------------------------------

def test_reset_does_not_cause_false_stale_clear(tmp_path: Path) -> None:
    """After reset_scale_to_governed_default, get_session must not stale-clear."""
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    assignment = _assignment(
        well_uid=well_uid,
        track_uid=track_uid,
        scale_min=10.0,
        scale_max=100.0,
        scale_type="linear",
    )

    fn_old = lambda: "rev-old"  # noqa: E731
    cmd_svc, session_svc = _service_with_fn(
        tmp_path, well_uid, [assignment], fn_old
    )
    session_svc.put_session(_build_session(well_uid, [assignment]))

    # Reset the override.
    cmd = _update_command(
        assignment.assignment_uid,
        revision=0,
        reset_scale_to_governed_default=True,
    )
    reset_result = cmd_svc.update_assignment(well_uid, cmd)
    assert reset_result.tracks[0].assignments[0].scale_min is None

    # Switch to a service with a "new" revision — but since no overrides remain,
    # get_session must NOT apply a stale-clear mutation (revision field irrelevant).
    from app.wdv_session.canonical_service import CanonicalWdvSessionService as _Svc
    svc_new = _Svc(
        storage_path=tmp_path / "sessions.json",
        policy_revision_fn=lambda: "rev-new",
    )
    revision_after_reset = reset_result.revision
    reloaded = svc_new.get_session(well_uid)

    # No stale-clear mutation: revision unchanged.
    assert reloaded.revision == revision_after_reset
    assert reloaded.tracks[0].assignments[0].scale_min is None


# ---------------------------------------------------------------------------
# Test C2-13 — genuinely stale pre-existing overrides cleared by get_session
# ---------------------------------------------------------------------------

def test_stale_legacy_overrides_cleared_by_get_session(tmp_path: Path) -> None:
    """A session seeded directly with overrides and a stale revision is cleared."""
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()

    assignment = _assignment(
        well_uid=well_uid,
        track_uid=track_uid,
        scale_min=0.5,
        scale_max=500.0,
        scale_type="logarithmic",
        scale_direction="normal",
    )

    # Seed directly via put_session (simulates a legacy or migrated session
    # that was written without revision-stamping support).
    from app.wdv_session.canonical_service import CanonicalWdvSessionService as _Svc
    from app.identity.wdv_contract_v2 import WdvCanonicalTrack as _Track, WdvCanonicalSession as _Session
    from app.identity import new_uuid7_str as _uid
    from datetime import datetime, timezone as _tz

    seed_svc = _Svc(
        storage_path=tmp_path / "sessions.json",
        policy_revision_fn=lambda: "rev-current",
    )
    track = _Track(
        track_uid=track_uid,
        track_name="Legacy Track",
        assignments=(assignment,),
    )
    legacy_session = _Session(
        session_uid=_uid(),
        managed_well_uid=well_uid,
        revision=0,
        display_policy_revision="rev-old",
        state_status="active",
        tracks=(track,),
        updated_at=datetime.now(_tz.utc).isoformat(),
    )
    seed_svc.put_session(legacy_session)

    # get_session detects stale override and clears.
    result = seed_svc.get_session(well_uid)

    assert result.tracks[0].assignments[0].scale_min is None
    assert result.tracks[0].assignments[0].scale_type is None
    assert result.display_policy_revision == "rev-current"
