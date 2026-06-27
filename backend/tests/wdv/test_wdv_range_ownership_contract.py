"""Backend-owned WDV range resolution contract."""

from types import SimpleNamespace

import pytest

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalAssignment
from app.inventory.curve_sample_service import CurveSampleServiceError
from app.wdv_session.assignment_policy_service import CanonicalWdvAssignmentPolicyService
from app.wdv_session.canonical_commands import UpdateCurveAssignmentCommand


def assignment(**updates):
    base = dict(
        assignment_uid=new_uuid7_str(),
        managed_curve_uid=new_uuid7_str(),
        managed_product_uid=new_uuid7_str(),
        managed_well_uid=new_uuid7_str(),
        managed_wellbore_uid=new_uuid7_str(),
        managed_source_uid=new_uuid7_str(),
        track_uid=new_uuid7_str(),
        observed_mnemonic="NPHI",
        display_name="NPHI",
        scale_min=0.45,
        scale_max=-0.15,
        scale_type="linear",
        scale_direction="reversed",
        display_policy_source="family",
    )
    base.update(updates)
    return WdvCanonicalAssignment(**base)


def test_default_mode_is_governed():
    item = assignment()
    assert item.range_override_mode == "governed"
    assert item.effective_range_source == "governed"


def test_manual_mode_requires_explicit_bounds():
    with pytest.raises(ValueError, match="manual mode requires"):
        assignment(range_override_mode="manual", effective_range_source="manual")


def test_update_command_uses_explicit_mode_not_effective_scale_fields():
    command = UpdateCurveAssignmentCommand(
        expected_revision=0,
        assignment_uid=new_uuid7_str(),
        range_override_mode="fit_to_curve_p05_p95",
    )
    dumped = command.model_dump()
    assert dumped["range_override_mode"] == "fit_to_curve_p05_p95"
    assert "reset_scale_to_governed_default" not in dumped
    assert "scale_min" not in dumped


def test_fit_preserves_governed_direction_and_type():
    product = SimpleNamespace(robust_observed_min=-0.05, robust_observed_max=0.32)
    service = CanonicalWdvAssignmentPolicyService.__new__(CanonicalWdvAssignmentPolicyService)
    fitted = service._fit_bounds(
        product,
        {"scale_type": "linear", "scale_direction": "reversed"},
    )
    assert fitted == pytest.approx((0.44333333333333336, -0.17333333333333334))


def test_fit_rejects_non_positive_log_domain():
    product = SimpleNamespace(robust_observed_min=0.0, robust_observed_max=100.0)
    service = CanonicalWdvAssignmentPolicyService.__new__(CanonicalWdvAssignmentPolicyService)
    assert service._fit_bounds(
        product,
        {"scale_type": "logarithmic", "scale_direction": "normal"},
    ) is None


class FakeResolver:
    def __init__(self, product):
        self.product = product

    def resolve_curve(self, managed_well_uid, managed_curve_uid):
        return SimpleNamespace(product=self.product)


class FakeCurveSampleService:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def get_curve_samples(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


def sample_response(
    *,
    robust_min=-0.0672,
    robust_max=0.0138,
    value_min=-0.0803,
    value_max=0.2525,
    value_p01=-0.0672,
    value_p05=-0.052045,
    value_p95=-0.0262,
    value_p99=0.0138,
):
    return SimpleNamespace(
        robust_value_min=robust_min,
        robust_value_max=robust_max,
        value_min=value_min,
        value_max=value_max,
        value_p01=value_p01,
        value_p05=value_p05,
        value_p95=value_p95,
        value_p99=value_p99,
    )


def policy(_product):
    return {
        "min": 0.45,
        "max": -0.15,
        "type": "linear",
        "direction": "reversed",
        "source": "managed_knowledge_family_default",
    }


def policy_service(product, curve_sample_service=None):
    return CanonicalWdvAssignmentPolicyService(
        resolver=FakeResolver(product),
        display_policy_resolver=policy,
        curve_sample_service=(
            curve_sample_service
            or FakeCurveSampleService(response=sample_response())
        ),
    )


def test_refresh_governed_keeps_governed_mode():
    product = SimpleNamespace(robust_observed_min=-0.05, robust_observed_max=0.32)
    refreshed = policy_service(product).refresh_assignment(assignment())
    assert refreshed.range_override_mode == "governed"
    assert refreshed.effective_range_source == "governed"
    assert refreshed.scale_min == 0.45
    assert refreshed.scale_max == -0.15


def test_refresh_manual_preserves_manual_intent_and_governed_direction():
    product = SimpleNamespace(robust_observed_min=-0.05, robust_observed_max=0.32)
    refreshed = policy_service(product).refresh_assignment(assignment(
        range_override_mode="manual",
        effective_range_source="manual",
        manual_scale_min=0.3,
        manual_scale_max=0.0,
    ))
    assert refreshed.range_override_mode == "manual"
    assert refreshed.effective_range_source == "manual"
    assert refreshed.manual_scale_min == 0.3
    assert refreshed.manual_scale_max == 0.0
    assert refreshed.scale_min == 0.3
    assert refreshed.scale_max == 0.0
    assert refreshed.scale_direction == "reversed"
    assert refreshed.scale_type == "linear"


def test_refresh_fit_p05_p95_uses_central_percentiles_with_padding():
    refreshed = policy_service(SimpleNamespace()).refresh_assignment(assignment(
        range_override_mode="fit_to_curve_p05_p95",
        effective_range_source="fit_to_curve_p05_p95",
    ))
    assert refreshed.scale_min == pytest.approx(-0.017585)
    assert refreshed.scale_max == pytest.approx(-0.06066)
    assert refreshed.range_edit_step == pytest.approx(0.001)
    assert refreshed.range_edit_precision == 3


def test_refresh_fit_p01_p99_uses_broad_percentiles_with_padding():
    refreshed = policy_service(SimpleNamespace()).refresh_assignment(assignment(
        range_override_mode="fit_to_curve_p01_p99",
        effective_range_source="fit_to_curve_p01_p99",
    ))
    assert refreshed.scale_min == pytest.approx(0.0408)
    assert refreshed.scale_max == pytest.approx(-0.0942)
    assert refreshed.range_edit_step == pytest.approx(0.01)
    assert refreshed.range_edit_precision == 2


def test_fit_uses_canonical_curve_sample_service_identity():
    samples = FakeCurveSampleService(response=sample_response())
    item = assignment(
        range_override_mode="fit_to_curve_p01_p99",
        effective_range_source="fit_to_curve_p01_p99",
    )

    refreshed = policy_service(
        SimpleNamespace(),
        curve_sample_service=samples,
    ).refresh_assignment(item)

    assert refreshed.scale_min == pytest.approx(0.0408)
    assert refreshed.scale_max == pytest.approx(-0.0942)
    assert len(samples.requests) == 1
    request = samples.requests[0]
    assert str(request.managed_well_uid) == str(item.managed_well_uid)
    assert str(request.managed_curve_uid) == str(item.managed_curve_uid)
    assert request.max_samples == 12000


def test_fit_falls_back_to_raw_sample_bounds_when_robust_bounds_are_absent():
    samples = FakeCurveSampleService(
        response=sample_response(
            robust_min=None,
            robust_max=None,
            value_min=-0.08,
            value_max=0.41,
            value_p01=None,
            value_p99=None,
        )
    )
    item = assignment(
        range_override_mode="fit_to_curve_p01_p99",
        effective_range_source="fit_to_curve_p01_p99",
    )

    refreshed = policy_service(
        SimpleNamespace(),
        curve_sample_service=samples,
    ).refresh_assignment(item)

    assert refreshed.scale_min == pytest.approx(0.5733333333333334)
    assert refreshed.scale_max == pytest.approx(-0.24333333333333335)


def test_fit_retains_governed_range_and_warning_when_sample_service_fails():
    samples = FakeCurveSampleService(
        error=CurveSampleServiceError("sample source unavailable")
    )
    item = assignment(
        range_override_mode="fit_to_curve_p01_p99",
        effective_range_source="fit_to_curve_p01_p99",
    )

    refreshed = policy_service(
        SimpleNamespace(),
        curve_sample_service=samples,
    ).refresh_assignment(item)

    assert refreshed.scale_min == 0.45
    assert refreshed.scale_max == -0.15
    assert refreshed.override_warning_code == "FIT_TO_CURVE_UNAVAILABLE"
    assert refreshed.override_warning_message
