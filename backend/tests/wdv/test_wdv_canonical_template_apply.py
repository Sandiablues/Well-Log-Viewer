from pathlib import Path
from types import SimpleNamespace

import pytest

from app.identity import new_uuid7_str
from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
)
from app.wdv_session.canonical_service import CanonicalWdvSessionService
from app.wdv_templates.canonical_apply_service import (
    ApplyGovernedTemplateCommand,
    CanonicalTemplateApplyBlockedError,
    CanonicalWdvTemplateApplyService,
)
from app.wdv_templates.models import (
    WdvRecommendedCurveResponse,
    WdvTemplateApplicationPlanEnvelope,
    WdvTemplateApplicationPlanResponse,
    WdvTemplateApplicationTrackPlanResponse,
)


class FakeResolver:
    def __init__(self, well, resolved) -> None:
        self.well = well
        self.resolved = resolved

    def resolve_well(self, managed_well_uid: str):
        assert managed_well_uid == str(self.well.managed_well_uid)
        return self.well

    def resolve_curve(self, managed_well_uid: str, managed_curve_uid: str):
        assert managed_well_uid == str(self.well.managed_well_uid)
        assert managed_curve_uid == self.resolved.managed_curve_uid
        return self.resolved


class FakePlanService:
    def __init__(self, envelope) -> None:
        self.envelope = envelope
        self.requests = []

    def build_from_request(self, request):
        self.requests.append(request)
        return self.envelope


def fixture():
    well_uid = new_uuid7_str()
    wellbore_uid = new_uuid7_str()
    source_uid = new_uuid7_str()
    product_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()

    source = ManagedSourceReference(
        source_id="legacy-source",
        managed_source_uid=source_uid,
        source_kind=ManagedSourceKind.LAS,
        display_name="LAS",
    )
    product = ManagedProductGroupItem(
        product_id="legacy-product",
        managed_product_uid=product_uid,
        managed_curve_uid=curve_uid,
        managed_wellbore_uid=wellbore_uid,
        managed_source_uid=source_uid,
        display_name="Gamma Ray",
        curve_name="GR",
        observed_mnemonic="GR",
        normalized_mnemonic="GR",
        curve_type="curve",
        curve_unit="API",
        curve_family="gamma_ray",
        kr_curve_type_id="gamma_ray",
        selectable=True,
    )
    well = ManagedWellRecord(
        managed_well_id="legacy-well",
        managed_well_uid=well_uid,
        managed_wellbore_uid=wellbore_uid,
        well_id="legacy-well",
        well_name="Test Well",
        depth_unit="ft",
        source_references=[source],
        product_groups=[
            ManagedProductGroup(
                group_key="logs",
                group_label="Logs",
                items=[product],
            )
        ],
    )
    resolved = SimpleNamespace(
        managed_well_uid=well_uid,
        managed_curve_uid=curve_uid,
        managed_product_uid=product_uid,
        managed_source_uid=source_uid,
        managed_wellbore_uid=wellbore_uid,
        product=product,
    )
    curve = WdvRecommendedCurveResponse(
        product_id=product_uid,
        curve_uid=curve_uid,
        well_uid=well_uid,
        source_uid=source_uid,
        kr_curve_type_id="gamma_ray",
        observed_mnemonic="GR",
        normalized_mnemonic="GR",
        curve_id=curve_uid,
        mnemonic="GR",
        display_name="Gamma Ray",
        unit="API",
        curve_family="gamma_ray",
        selection_reason="selected_for_track",
    )
    track = WdvTemplateApplicationTrackPlanResponse(
        track_id="track_gamma",
        track_key="gamma",
        track_number=1,
        track_name="Gamma Ray",
        track_role="open_hole",
        renderer_type="line_curve",
        selected_curves=[curve],
        scale_defaults=[
            {
                "curve_family": "gamma_ray",
                "scale_min": 0,
                "scale_max": 150,
                "scale_type": "linear",
                "display_direction": "normal",
            }
        ],
    )
    plan = WdvTemplateApplicationPlanResponse(
        application_plan_id="legacy-plan-id",
        plan_status="ready_for_review",
        template_key="triple_combo",
        template_label="Triple Combo",
        source_recommendation_rank=1,
        source_recommendation_score=100.0,
        apply_eligible=True,
        tracks=[track],
    )
    envelope = WdvTemplateApplicationPlanEnvelope(
        plan=plan,
        knowledge_policy={"approved_only": True},
    )
    return well, resolved, envelope


def test_canonical_template_apply_rebuilds_session_atomically(tmp_path: Path) -> None:
    well, resolved, envelope = fixture()
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    plans = FakePlanService(envelope)
    service = CanonicalWdvTemplateApplyService(
        plan_service=plans,
        resolver=FakeResolver(well, resolved),
        session_service=sessions,
    )

    initial = sessions.get_session(str(well.managed_well_uid))
    applied = service.apply(
        str(well.managed_well_uid),
        ApplyGovernedTemplateCommand(
            expected_revision=initial.revision,
            template_key="triple_combo",
            workflow_context="open_hole",
        ),
    )

    assert applied.revision == initial.revision + 1
    assert applied.session_uid == initial.session_uid
    assert applied.state_status == "active"
    assert applied.source == "canonical_template_apply:triple_combo"
    assert len(applied.tracks) == 1
    track = applied.tracks[0]
    assert track.track_uid
    assert track.source_template_key == "triple_combo"
    assert track.source_application_plan_uid
    assert track.lattice == "linear"
    assignment = track.assignments[0]
    assert assignment.assignment_uid
    assert assignment.managed_curve_uid == resolved.managed_curve_uid
    assert assignment.managed_product_uid == resolved.managed_product_uid
    assert assignment.track_uid == track.track_uid
    assert assignment.scale_min == 0
    assert assignment.scale_max == 150
    assert assignment.source == "canonical_governed_template_apply"

    request = plans.requests[0]
    assert request.loaded_curve_items[0].curve_uid == resolved.managed_curve_uid
    assert request.loaded_curve_items[0].product_id == resolved.managed_product_uid


def test_reapply_issues_new_track_and_assignment_uids(tmp_path: Path) -> None:
    well, resolved, envelope = fixture()
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    service = CanonicalWdvTemplateApplyService(
        plan_service=FakePlanService(envelope),
        resolver=FakeResolver(well, resolved),
        session_service=sessions,
    )

    first = service.apply(
        str(well.managed_well_uid),
        ApplyGovernedTemplateCommand(
            expected_revision=0,
            template_key="triple_combo",
        ),
    )
    second = service.apply(
        str(well.managed_well_uid),
        ApplyGovernedTemplateCommand(
            expected_revision=first.revision,
            template_key="triple_combo",
        ),
    )

    assert second.session_uid == first.session_uid
    assert second.tracks[0].track_uid != first.tracks[0].track_uid
    assert (
        second.tracks[0].assignments[0].assignment_uid
        != first.tracks[0].assignments[0].assignment_uid
    )


def test_blocked_plan_does_not_mutate_session(tmp_path: Path) -> None:
    well, resolved, envelope = fixture()
    blocked_plan = envelope.plan.model_copy(
        update={
            "apply_eligible": False,
            "blocking_issues": ["missing_required_families"],
        }
    )
    blocked_envelope = envelope.model_copy(update={"plan": blocked_plan})
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    initial = sessions.get_session(str(well.managed_well_uid))
    service = CanonicalWdvTemplateApplyService(
        plan_service=FakePlanService(blocked_envelope),
        resolver=FakeResolver(well, resolved),
        session_service=sessions,
    )

    with pytest.raises(CanonicalTemplateApplyBlockedError):
        service.apply(
            str(well.managed_well_uid),
            ApplyGovernedTemplateCommand(
                expected_revision=initial.revision,
                template_key="triple_combo",
            ),
        )

    reread = sessions.get_session(str(well.managed_well_uid))
    assert reread.revision == initial.revision
    assert reread.tracks == ()
