from __future__ import annotations

from types import SimpleNamespace

from app.curve_display.contract_service import (
    BackendCurveDisplayContractService,
    BackendCurveDisplayIntent,
)
from app.inventory.models import ManagedProductGroupItem, ManagedWellRecord


def _record_and_item():
    item = ManagedProductGroupItem(
        product_id="curve-af10",
        display_name="AF10",
        curve_name="AF10",
        curve_type="resistivity",
        managed_curve_uid="019ee477-40ae-781d-86f6-05d2465bcb82",
    )
    record = ManagedWellRecord(
        managed_well_id="managed-well:forge",
        managed_well_uid="019ee477-40ae-781d-86f6-05d2465bcb7d",
        well_id="forge",
        well_name="Forge",
    )
    return record, item


def test_backend_assignment_p5_p95_contract_precedes_governed_policy(monkeypatch):
    record, item = _record_and_item()
    assignment = SimpleNamespace(
        managed_well_uid=record.managed_well_uid,
        managed_curve_uid=item.managed_curve_uid,
        scale_min=0.08076925406939689,
        scale_max=24307.021559381603,
        scale_type="logarithmic",
        scale_direction="normal",
        effective_range_source="fit_to_curve_p05_p95",
        clip_to_track=True,
        assignment_uid="019f1e8f-c4e6-77bb-885a-1570efab5802",
        track_uid="019f1e8f-c4d0-7e8c-8245-a1b3dfea5d7a",
        source="configured_track_backend_command",
        display_policy_source="family",
        display_review_required=False,
    )
    session = SimpleNamespace(
        tracks=(SimpleNamespace(assignments=(assignment,)),),
        display_policy_revision="policy-revision-9",
    )
    service = BackendCurveDisplayContractService(
        session_service=SimpleNamespace(get_session=lambda _: session)
    )
    monkeypatch.setattr(
        "app.curve_display.contract_service.WdvCurveDisplayPolicyService.resolve",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("governed fallback must not run")),
    )
    resolved = service.resolve(record=record, item=item, statistics={})
    assert resolved.minimum == 0.08076925406939689
    assert resolved.maximum == 24307.021559381603
    assert resolved.scale_type == "logarithmic"
    assert resolved.range_source == "fit_to_curve_p05_p95"
    assert resolved.policy_revision == "policy-revision-9"
    assert resolved.provenance["authority"] == "backend_curve_display_contract"


def test_missing_assignment_uses_shared_governed_backend_policy(monkeypatch):
    record, item = _record_and_item()
    session = SimpleNamespace(tracks=(), display_policy_revision="policy-revision-9")
    service = BackendCurveDisplayContractService(
        session_service=SimpleNamespace(get_session=lambda _: session)
    )
    monkeypatch.setattr(
        "app.curve_display.contract_service.WdvCurveDisplayPolicyService.resolve",
        lambda *_args, **_kwargs: {
            "min": 0.2,
            "max": 2000.0,
            "type": "log",
            "direction": "normal",
            "source": "managed_knowledge_family_default",
        },
    )
    resolved = service.resolve(record=record, item=item, statistics={})
    assert resolved.minimum == 0.2
    assert resolved.maximum == 2000.0
    assert resolved.range_source == "managed_knowledge_family_default"


def test_conflicting_backend_assignments_fail_visibly():
    record, item = _record_and_item()
    base = dict(
        managed_well_uid=record.managed_well_uid,
        managed_curve_uid=item.managed_curve_uid,
        scale_type="logarithmic",
        scale_direction="normal",
        effective_range_source="fit_to_curve_p05_p95",
        clip_to_track=True,
        assignment_uid="019f1e8f-c4e6-77bb-885a-1570efab5802",
        track_uid="019f1e8f-c4d0-7e8c-8245-a1b3dfea5d7a",
        source="configured_track_backend_command",
        display_policy_source="family",
        display_review_required=False,
    )
    a=SimpleNamespace(scale_min=1.0,scale_max=100.0,**base)
    b=SimpleNamespace(scale_min=2.0,scale_max=200.0,**base)
    session=SimpleNamespace(tracks=(SimpleNamespace(assignments=(a,b)),),display_policy_revision="r")
    service=BackendCurveDisplayContractService(session_service=SimpleNamespace(get_session=lambda _:session))
    try:
        service.resolve(record=record,item=item,statistics={})
    except ValueError as exc:
        assert "Conflicting backend display assignments" in str(exc)
    else:
        raise AssertionError("conflicting backend contracts must fail")


def test_explicit_backend_p5_p95_intent_precedes_canonical_assignment(monkeypatch):
    record, item = _record_and_item()
    assignment = SimpleNamespace(
        managed_well_uid=record.managed_well_uid, managed_curve_uid=item.managed_curve_uid,
        scale_min=0.08076925406939689, scale_max=24307.021559381603,
        scale_type="logarithmic", scale_direction="normal",
        effective_range_source="fit_to_curve_p05_p95", clip_to_track=True,
        assignment_uid="019f1e8f-c4e6-77bb-885a-1570efab5802",
        track_uid="019f1e8f-c4d0-7e8c-8245-a1b3dfea5d7a",
        source="configured_track_backend_command", display_policy_source="family",
        display_review_required=False,
    )
    session=SimpleNamespace(tracks=(SimpleNamespace(assignments=(assignment,)),),display_policy_revision="old")
    service=BackendCurveDisplayContractService(session_service=SimpleNamespace(get_session=lambda _:session))
    monkeypatch.setattr(
        "app.curve_display.contract_service.WdvCurveDisplayPolicyService.resolve",
        lambda *_args, **_kwargs: {
            "min": 0.2, "max": 2000.0, "type": "logarithmic",
            "direction": "normal", "source": "managed_knowledge_family_default",
        },
    )
    resolved=service.resolve(
        record=record, item=item,
        statistics={"observed_p05":1.0068,"observed_p95":1950.0},
        intent=BackendCurveDisplayIntent(range_mode="robust_p5_p95"),
    )
    assert resolved.minimum == 1.0068
    assert resolved.maximum == 1950.0
    assert resolved.scale_type == "logarithmic"
    assert resolved.range_source == "backend_observed_p05_p95"
    assert resolved.provenance["range_mode"] == "robust_p5_p95"


def test_backend_manual_intent_is_resolved_by_shared_service(monkeypatch):
    record, item = _record_and_item()
    session=SimpleNamespace(tracks=(),display_policy_revision="r")
    service=BackendCurveDisplayContractService(session_service=SimpleNamespace(get_session=lambda _:session))
    monkeypatch.setattr(
        "app.curve_display.contract_service.WdvCurveDisplayPolicyService.resolve",
        lambda *_args, **_kwargs: {
            "min":0.2,"max":2000.0,"type":"logarithmic",
            "direction":"normal","source":"managed_knowledge_family_default",
        },
    )
    resolved=service.resolve(
        record=record,item=item,statistics={},
        intent=BackendCurveDisplayIntent(
            range_mode="manual",minimum=1.0,maximum=100.0,
            scale_type="logarithmic",direction_override="reversed",clamp=False,
        ),
    )
    assert (resolved.minimum,resolved.maximum)==(1.0,100.0)
    assert resolved.direction == "reversed"
    assert resolved.clamp is False
    assert resolved.range_source == "backend_manual_range"


def test_backend_p5_p95_intent_fails_when_statistics_are_missing(monkeypatch):
    record, item = _record_and_item()
    service=BackendCurveDisplayContractService(session_service=SimpleNamespace(get_session=lambda _:SimpleNamespace(tracks=())))
    monkeypatch.setattr(
        "app.curve_display.contract_service.WdvCurveDisplayPolicyService.resolve",
        lambda *_args, **_kwargs: {
            "min":0.2,"max":2000.0,"type":"logarithmic",
            "direction":"normal","source":"managed_knowledge_family_default",
        },
    )
    try:
        service.resolve(
            record=record,item=item,statistics={},
            intent=BackendCurveDisplayIntent(range_mode="robust_p5_p95"),
        )
    except ValueError as exc:
        assert "P5/P95 intent has no usable percentile range" in str(exc)
    else:
        raise AssertionError("missing backend P5/P95 statistics must fail visibly")
