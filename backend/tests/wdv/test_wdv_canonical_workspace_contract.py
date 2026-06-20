from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import (
    WdvCanonicalAssignment,
    WdvCanonicalSession,
    WdvCanonicalTrack,
)
from app.identity.wdv_viewer_package_v21 import (
    WdvCanonicalCurveDisplayPolicy,
    WdvCanonicalDepthRange,
    WdvCanonicalViewerCurve,
)
from app.wdv_workspace.models import WdvCanonicalWorkspace


def _policy() -> WdvCanonicalCurveDisplayPolicy:
    return WdvCanonicalCurveDisplayPolicy(
        curve_class="gamma",
        lattice="linear",
        scale_type="linear",
        display_min=0.0,
        display_max=200.0,
        scale_direction="normal",
        default_color="#000000",
        source="test",
    )


def _workspace(*, stack_index: int = 0, mismatched_product: bool = False):
    well_uid = new_uuid7_str()
    wellbore_uid = new_uuid7_str()
    source_uid = new_uuid7_str()
    product_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    track_uid = new_uuid7_str()

    curve = WdvCanonicalViewerCurve(
        managed_curve_uid=curve_uid,
        managed_product_uid=product_uid,
        managed_well_uid=well_uid,
        managed_wellbore_uid=wellbore_uid,
        managed_source_uid=source_uid,
        observed_mnemonic="GR",
        display_name="Gamma Ray",
        display_policy=_policy(),
    )
    assignment = WdvCanonicalAssignment(
        assignment_uid=new_uuid7_str(),
        managed_curve_uid=curve_uid,
        managed_product_uid=(new_uuid7_str() if mismatched_product else product_uid),
        managed_well_uid=well_uid,
        managed_wellbore_uid=wellbore_uid,
        managed_source_uid=source_uid,
        track_uid=track_uid,
        observed_mnemonic="GR",
        display_name="Gamma Ray",
        stack_index=stack_index,
    )
    track = WdvCanonicalTrack(
        track_uid=track_uid,
        track_name="Track 1",
        assignments=(assignment,),
    )
    session = WdvCanonicalSession(
        session_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        revision=1,
        state_status="active",
        tracks=(track,),
        selected_track_uid=track_uid,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    return dict(
        managed_well_uid=well_uid,
        managed_wellbore_uid=wellbore_uid,
        well_name="Test Well",
        depth_range=WdvCanonicalDepthRange(minimum=1000, maximum=2000, unit="ft"),
        curve_registry=(curve,),
        session=session,
    )


def test_workspace_accepts_fully_resolved_graph() -> None:
    workspace = WdvCanonicalWorkspace(**_workspace())
    assert workspace.contract_version == "wdv_workspace_v1"
    assert workspace.session.tracks[0].assignments[0].managed_curve_uid == (
        workspace.curve_registry[0].managed_curve_uid
    )


def test_workspace_rejects_assignment_product_mismatch() -> None:
    with pytest.raises(ValidationError, match="managed_product_uid"):
        WdvCanonicalWorkspace(**_workspace(mismatched_product=True))


def test_workspace_rejects_non_contiguous_stack_indices() -> None:
    with pytest.raises(ValidationError, match="stack_index"):
        WdvCanonicalWorkspace(**_workspace(stack_index=3))


def test_workspace_rejects_assignment_curve_absent_from_registry() -> None:
    payload = _workspace()
    payload["curve_registry"] = ()
    with pytest.raises(ValidationError, match="absent from the workspace registry"):
        WdvCanonicalWorkspace(**payload)
