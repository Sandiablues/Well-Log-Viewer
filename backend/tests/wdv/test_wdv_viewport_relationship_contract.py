from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.wdv_workspace.models import WdvSavedViewState


T1 = "0198a9b5-36d4-7a90-ae9a-c11d523dfe01"
T2 = "0198a9b5-36d4-7a90-ae9a-c11d523dfe02"
T3 = "0198a9b5-36d4-7a90-ae9a-c11d523dfe03"


def state(**updates):
    base = {
        "depth_unit": "m",
        "global_viewport": {"min": 1000.0, "max": 1100.0},
        "track_viewports_by_track_uid": {T2: {"min": 3000.0, "max": 3010.0}},
        "viewport_tie_groups": [{
            "group_id": "viewport-tie:t1",
            "leader_track_uid": T1,
            "member_track_uids": [T1, T2],
            "viewport": {"min": 1000.0, "max": 1100.0},
        }],
        "viewport_tie_suspended_track_uids": [T2],
    }
    base.update(updates)
    return base


def test_explicit_viewport_relationship_contract_accepts_valid_state():
    parsed = WdvSavedViewState.model_validate(state())
    assert parsed.track_viewports_by_track_uid[T2].min == 3000.0
    assert parsed.viewport_tie_groups[0].leader_track_uid == T1
    assert parsed.viewport_tie_suspended_track_uids == (T2,)


def test_tie_requires_at_least_two_members():
    bad = state(viewport_tie_groups=[{
        "group_id": "viewport-tie:t1",
        "leader_track_uid": T1,
        "member_track_uids": [T1],
        "viewport": {"min": 1000.0, "max": 1100.0},
    }])
    with pytest.raises(ValidationError):
        WdvSavedViewState.model_validate(bad)


def test_tie_leader_must_be_member():
    bad = state(viewport_tie_groups=[{
        "group_id": "viewport-tie:t1",
        "leader_track_uid": T3,
        "member_track_uids": [T1, T2],
        "viewport": {"min": 1000.0, "max": 1100.0},
    }])
    with pytest.raises(ValidationError):
        WdvSavedViewState.model_validate(bad)


def test_old_snapshot_without_new_fields_remains_readable():
    parsed = WdvSavedViewState.model_validate({
        "depth_unit": "m",
        "global_viewport": {"min": 1000.0, "max": 1100.0},
        "locked_track_uids": [T1],
        "locked_viewports_by_track_uid": {T1: {"min": 1000.0, "max": 1100.0}},
        "presentation_state": {
            "viewport_tie_groups": [{
                "group_id": "legacy",
                "leader_track_uid": T1,
                "member_track_uids": [T1, T2],
                "viewport": {"min": 1000.0, "max": 1100.0},
            }]
        },
    })
    assert parsed.track_viewports_by_track_uid == {}
    assert parsed.viewport_tie_groups == ()
