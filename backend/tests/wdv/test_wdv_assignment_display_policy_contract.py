import pytest
from pydantic import ValidationError

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalAssignment


def make_assignment(**overrides) -> WdvCanonicalAssignment:
    payload = {
        "assignment_uid": new_uuid7_str(),
        "managed_curve_uid": new_uuid7_str(),
        "managed_product_uid": new_uuid7_str(),
        "managed_well_uid": new_uuid7_str(),
        "managed_source_uid": new_uuid7_str(),
        "track_uid": new_uuid7_str(),
        "observed_mnemonic": "RHOZ",
        "display_name": "Bulk Density",
        "source": "configured_track_backend_command",
    }
    payload.update(overrides)
    return WdvCanonicalAssignment(**payload)


def test_existing_assignment_contract_remains_backward_compatible() -> None:
    assignment = make_assignment()

    assert assignment.source == "configured_track_backend_command"
    assert assignment.display_policy_source is None
    assert assignment.display_review_required is False
    assert assignment.display_warning_code is None
    assert assignment.display_warning_message is None


@pytest.mark.parametrize("policy_source", ["curve", "family"])
def test_non_default_policy_sources_do_not_require_warning(
    policy_source: str,
) -> None:
    assignment = make_assignment(display_policy_source=policy_source)

    assert assignment.source == "configured_track_backend_command"
    assert assignment.display_policy_source == policy_source
    assert assignment.display_review_required is False


def test_system_default_policy_requires_review_and_warning_details() -> None:
    assignment = make_assignment(
        display_policy_source="system_default",
        display_review_required=True,
        display_warning_code="NO_GOVERNED_DISPLAY_POLICY",
        display_warning_message=(
            "No approved curve-level or family display policy was resolved."
        ),
    )

    assert assignment.source == "configured_track_backend_command"
    assert assignment.display_policy_source == "system_default"
    assert assignment.display_review_required is True
    assert assignment.display_warning_code == "NO_GOVERNED_DISPLAY_POLICY"


@pytest.mark.parametrize(
    "overrides",
    [
        {"display_policy_source": "system_default"},
        {
            "display_policy_source": "system_default",
            "display_review_required": True,
        },
        {
            "display_policy_source": "family",
            "display_review_required": True,
        },
        {
            "display_policy_source": "curve",
            "display_warning_code": "UNEXPECTED",
        },
    ],
)
def test_invalid_display_policy_metadata_is_rejected(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        make_assignment(**overrides)


def test_display_policy_metadata_survives_json_round_trip() -> None:
    original = make_assignment(
        scale_min=0.0,
        scale_max=100.0,
        scale_type="linear",
        scale_direction="normal",
        display_policy_source="system_default",
        display_review_required=True,
        display_warning_code="NO_GOVERNED_DISPLAY_POLICY",
        display_warning_message="Backend system-default display scale is in use.",
    )

    restored = WdvCanonicalAssignment.model_validate_json(
        original.model_dump_json()
    )

    assert restored == original
    assert restored.source == "configured_track_backend_command"
