"""UNIT-3B tests — persistent stale-override lifecycle.

Tests the stale override invalidation path added to get_session in UNIT-3B.
The service is constructed with an injected policy_revision_fn so tests
are deterministic and do not depend on real KR file content.

  B1.  Stale revision + scale overrides → overrides cleared, revision stamped.
  B2.  Matching revision → no mutation (idempotent).
  B3.  Stale revision + no overrides → no mutation.
  B4.  Injected fn controls revision check — new fn value triggers stale clear.
  B5.  Clearing increments the session revision by exactly 1.
  B6.  Cleared state is persisted — a subsequent get_session sees it.
  B7.  Overrides across multiple tracks and assignments are all cleared.
  B8.  Non-scale assignment fields are preserved after override clearing.
  B9.  display_policy_revision is stamped to exactly the fn() return value.
  B10. Only scale_direction override (no bounds) is detected and cleared.
  B11. Empty session (no tracks) is not mutated regardless of revision.
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
from app.wdv_session.canonical_service import (
    CanonicalWdvSessionService,
    _assignment_has_scale_override,
    _session_has_scale_overrides,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_assignment(
    well_uid: str,
    track_uid: str,
    *,
    scale_min: float | None = None,
    scale_max: float | None = None,
    scale_type: str | None = None,
    scale_direction: str | None = None,
    color: str | None = None,
    stack_index: int = 0,
) -> WdvCanonicalAssignment:
    return WdvCanonicalAssignment(
        assignment_uid=new_uuid7_str(),
        managed_curve_uid=new_uuid7_str(),
        managed_product_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        managed_wellbore_uid=new_uuid7_str(),
        managed_source_uid=new_uuid7_str(),
        track_uid=track_uid,
        observed_mnemonic="GR",
        display_name="GR",
        stack_index=stack_index,
        scale_min=scale_min,
        scale_max=scale_max,
        scale_type=scale_type,
        scale_direction=scale_direction,
        color=color,
    )


def _make_track(
    well_uid: str,
    assignments: list[WdvCanonicalAssignment],
    *,
    track_name: str = "Track 1",
) -> WdvCanonicalTrack:
    """Build a track whose track_uid is consistent with the supplied assignments."""
    assert assignments, "at least one assignment required"
    track_uid = assignments[0].track_uid
    return WdvCanonicalTrack(
        track_uid=track_uid,
        track_name=track_name,
        assignments=tuple(assignments),
    )


def _make_assignments_for_new_track(
    well_uid: str,
    count: int = 1,
    *,
    scale_min: float | None = None,
    scale_max: float | None = None,
    scale_type: str | None = None,
    scale_direction: str | None = None,
    color: str | None = None,
) -> tuple[str, list[WdvCanonicalAssignment]]:
    """Return (track_uid, assignments) for a fresh track."""
    track_uid = new_uuid7_str()
    assignments = [
        _make_assignment(
            well_uid,
            track_uid,
            scale_min=scale_min,
            scale_max=scale_max,
            scale_type=scale_type,
            scale_direction=scale_direction,
            color=color,
            stack_index=i,
        )
        for i in range(count)
    ]
    return track_uid, assignments


def _active_session(
    well_uid: str,
    tracks: list[WdvCanonicalTrack],
    *,
    display_policy_revision: str | None = None,
) -> WdvCanonicalSession:
    return WdvCanonicalSession(
        session_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        revision=0,
        display_policy_revision=display_policy_revision,
        state_status="active",
        tracks=tuple(tracks),
        updated_at=_now_iso(),
    )


def _service(
    tmp_path: Path,
    revision: str = "rev-current",
) -> CanonicalWdvSessionService:
    """Build a session service with a deterministic injectable revision fn."""
    return CanonicalWdvSessionService(
        storage_path=tmp_path / "sessions.json",
        policy_revision_fn=lambda: revision,
    )


# ---------------------------------------------------------------------------
# Unit tests for module-level helpers
# ---------------------------------------------------------------------------

def test_assignment_has_scale_override_detects_bounds() -> None:
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    a_with = _make_assignment(well_uid, track_uid, scale_min=0.0, scale_max=150.0)
    a_without = _make_assignment(well_uid, track_uid)
    assert _assignment_has_scale_override(a_with) is True
    assert _assignment_has_scale_override(a_without) is False


def test_assignment_has_scale_override_detects_direction_only() -> None:
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    a = _make_assignment(well_uid, track_uid, scale_direction="reversed")
    assert _assignment_has_scale_override(a) is True


def test_assignment_has_scale_override_detects_type_only() -> None:
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    a = _make_assignment(well_uid, track_uid, scale_type="logarithmic")
    assert _assignment_has_scale_override(a) is True


def test_session_has_scale_overrides_empty_session() -> None:
    well_uid = new_uuid7_str()
    session = WdvCanonicalSession(
        session_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        revision=0,
        state_status="empty",
        tracks=(),
        updated_at=_now_iso(),
    )
    assert _session_has_scale_overrides(session) is False


# ---------------------------------------------------------------------------
# B1: stale revision + overrides → overrides cleared, revision stamped
# ---------------------------------------------------------------------------

def test_b1_stale_revision_and_overrides_clears_and_stamps(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    track_uid, assignments = _make_assignments_for_new_track(
        well_uid, scale_min=10.0, scale_max=100.0, scale_type="linear"
    )
    track = _make_track(well_uid, assignments)
    # Seed with no stored revision (None != "rev-new")
    session = _active_session(well_uid, [track], display_policy_revision=None)

    svc = _service(tmp_path, revision="rev-new")
    svc.put_session(session)

    result = svc.get_session(well_uid)

    cleared = result.tracks[0].assignments[0]
    assert cleared.scale_min is None
    assert cleared.scale_max is None
    assert cleared.scale_type is None
    assert cleared.scale_direction is None
    assert result.display_policy_revision == "rev-new"


# ---------------------------------------------------------------------------
# B2: matching revision → no mutation
# ---------------------------------------------------------------------------

def test_b2_matching_revision_no_mutation(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    track_uid, assignments = _make_assignments_for_new_track(
        well_uid, scale_min=10.0, scale_max=100.0
    )
    track = _make_track(well_uid, assignments)
    # Seed with revision matching the injectable fn
    session = _active_session(well_uid, [track], display_policy_revision="rev-current")

    svc = _service(tmp_path, revision="rev-current")
    seeded = svc.put_session(session)
    seeded_revision = seeded.revision

    result = svc.get_session(well_uid)

    # Overrides preserved — no mutation was applied.
    assert result.tracks[0].assignments[0].scale_min is not None
    assert result.revision == seeded_revision
    assert result.display_policy_revision == "rev-current"


# ---------------------------------------------------------------------------
# B3: stale revision + no overrides → no mutation
# ---------------------------------------------------------------------------

def test_b3_stale_revision_no_overrides_no_mutation(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    track_uid, assignments = _make_assignments_for_new_track(well_uid)
    track = _make_track(well_uid, assignments)
    # No overrides, stale stored revision
    session = _active_session(well_uid, [track], display_policy_revision=None)

    svc = _service(tmp_path, revision="rev-new")
    seeded = svc.put_session(session)
    seeded_revision = seeded.revision

    result = svc.get_session(well_uid)

    # No overrides to clear → session returned unchanged.
    assert result.revision == seeded_revision
    # display_policy_revision is NOT stamped when there is nothing to clear.
    assert result.display_policy_revision is None


# ---------------------------------------------------------------------------
# B4: injected fn controls revision check
# ---------------------------------------------------------------------------

def test_b4_injected_fn_controls_revision_check(tmp_path: Path) -> None:
    """Service A (fn="rev-A") sees no stale state; service B (fn="rev-B") does."""
    well_uid = new_uuid7_str()
    track_uid, assignments = _make_assignments_for_new_track(
        well_uid, scale_min=5.0, scale_max=200.0
    )
    track = _make_track(well_uid, assignments)
    # Seed stamped at "rev-A"
    session = _active_session(well_uid, [track], display_policy_revision="rev-A")

    storage = tmp_path / "sessions.json"

    svc_a = CanonicalWdvSessionService(
        storage_path=storage,
        policy_revision_fn=lambda: "rev-A",
    )
    seeded = svc_a.put_session(session)
    seeded_revision = seeded.revision

    # Service A: matching revision → no mutation
    result_a = svc_a.get_session(well_uid)
    assert result_a.revision == seeded_revision
    assert result_a.tracks[0].assignments[0].scale_min is not None

    # Service B: stale revision → overrides cleared
    svc_b = CanonicalWdvSessionService(
        storage_path=storage,
        policy_revision_fn=lambda: "rev-B",
    )
    result_b = svc_b.get_session(well_uid)
    assert result_b.revision == seeded_revision + 1
    assert result_b.tracks[0].assignments[0].scale_min is None
    assert result_b.display_policy_revision == "rev-B"


# ---------------------------------------------------------------------------
# B5: clearing increments revision by exactly 1
# ---------------------------------------------------------------------------

def test_b5_clearing_increments_revision(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    track_uid, assignments = _make_assignments_for_new_track(
        well_uid, scale_min=0.0, scale_max=150.0
    )
    track = _make_track(well_uid, assignments)
    session = _active_session(well_uid, [track])

    svc = _service(tmp_path, revision="rev-bump")
    seeded = svc.put_session(session)

    result = svc.get_session(well_uid)

    assert result.revision == seeded.revision + 1


# ---------------------------------------------------------------------------
# B6: cleared state is persisted
# ---------------------------------------------------------------------------

def test_b6_cleared_state_is_persisted(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    track_uid, assignments = _make_assignments_for_new_track(
        well_uid, scale_min=0.0, scale_max=150.0
    )
    track = _make_track(well_uid, assignments)
    session = _active_session(well_uid, [track])

    svc = _service(tmp_path, revision="rev-persisted")
    svc.put_session(session)

    # First call: clears overrides and stamps revision.
    svc.get_session(well_uid)

    # Second call: returns whatever is in the store — must see cleared state.
    stored = svc.get_session(well_uid)

    assert stored.tracks[0].assignments[0].scale_min is None
    assert stored.display_policy_revision == "rev-persisted"


# ---------------------------------------------------------------------------
# B7: overrides across multiple tracks/assignments all cleared
# ---------------------------------------------------------------------------

def test_b7_multi_track_overrides_all_cleared(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()

    track_uid_a, assignments_a = _make_assignments_for_new_track(
        well_uid, 2, scale_min=0.0, scale_max=150.0, scale_type="linear"
    )
    track_uid_b, assignments_b = _make_assignments_for_new_track(
        well_uid, 1, scale_min=1.0, scale_max=1000.0, scale_type="logarithmic"
    )

    track_a = WdvCanonicalTrack(
        track_uid=track_uid_a,
        track_name="Track A",
        assignments=tuple(assignments_a),
    )
    track_b = WdvCanonicalTrack(
        track_uid=track_uid_b,
        track_name="Track B",
        assignments=tuple(assignments_b),
    )
    session = _active_session(well_uid, [track_a, track_b])

    svc = _service(tmp_path, revision="rev-multi")
    svc.put_session(session)

    result = svc.get_session(well_uid)

    for track in result.tracks:
        for a in track.assignments:
            assert a.scale_min is None, f"scale_min not cleared on {a.assignment_uid}"
            assert a.scale_max is None, f"scale_max not cleared on {a.assignment_uid}"
            assert a.scale_type is None, f"scale_type not cleared on {a.assignment_uid}"


# ---------------------------------------------------------------------------
# B8: non-scale assignment fields preserved after clearing
# ---------------------------------------------------------------------------

def test_b8_non_scale_fields_preserved(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    track_uid, assignments = _make_assignments_for_new_track(
        well_uid,
        scale_min=0.0,
        scale_max=150.0,
        scale_direction="reversed",
        color="#ff0000",
    )
    original_assignment = assignments[0]
    track = _make_track(well_uid, assignments)
    session = _active_session(well_uid, [track])

    svc = _service(tmp_path, revision="rev-preserve")
    svc.put_session(session)

    result = svc.get_session(well_uid)

    cleared = result.tracks[0].assignments[0]
    # Scale fields cleared.
    assert cleared.scale_min is None
    assert cleared.scale_max is None
    assert cleared.scale_direction is None
    # Non-scale fields preserved.
    assert cleared.color == "#ff0000"
    assert cleared.assignment_uid == original_assignment.assignment_uid
    assert cleared.managed_curve_uid == original_assignment.managed_curve_uid
    assert cleared.observed_mnemonic == original_assignment.observed_mnemonic


# ---------------------------------------------------------------------------
# B9: display_policy_revision stamped to exactly the fn() return value
# ---------------------------------------------------------------------------

def test_b9_revision_stamped_to_fn_return_value(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    track_uid, assignments = _make_assignments_for_new_track(
        well_uid, scale_min=0.0, scale_max=150.0
    )
    track = _make_track(well_uid, assignments)
    session = _active_session(well_uid, [track], display_policy_revision="old-rev")

    sentinel = "sha256:abc123deadbeef"
    svc = _service(tmp_path, revision=sentinel)
    svc.put_session(session)

    result = svc.get_session(well_uid)

    assert result.display_policy_revision == sentinel


# ---------------------------------------------------------------------------
# B10: scale_direction-only override is detected and cleared
# ---------------------------------------------------------------------------

def test_b10_scale_direction_only_override_cleared(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    track_uid, assignments = _make_assignments_for_new_track(
        well_uid, scale_direction="reversed"
    )
    track = _make_track(well_uid, assignments)
    session = _active_session(well_uid, [track])

    svc = _service(tmp_path, revision="rev-direction")
    svc.put_session(session)

    result = svc.get_session(well_uid)

    cleared = result.tracks[0].assignments[0]
    assert cleared.scale_direction is None
    assert result.display_policy_revision == "rev-direction"


# ---------------------------------------------------------------------------
# B11: empty session (no tracks) not mutated
# ---------------------------------------------------------------------------

def test_b11_empty_session_not_mutated(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    svc = _service(tmp_path, revision="rev-empty")

    # get_session with no prior store creates an empty session.
    empty = svc.get_session(well_uid)

    assert empty.state_status == "empty"
    assert empty.tracks == ()
    # No mutation was applied — revision is 0 from creation.
    assert empty.revision == 0
    # display_policy_revision is NOT stamped on empty sessions (no overrides to clear).
    assert empty.display_policy_revision is None
