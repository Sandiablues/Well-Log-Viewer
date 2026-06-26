from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalAssignment
from app.wdv_session.canonical_service import _assignment_has_scale_override


def assignment(
    *,
    display_policy_source: str | None,
    with_scale: bool = True,
) -> WdvCanonicalAssignment:
    is_system_default = display_policy_source == "system_default"
    return WdvCanonicalAssignment(
        assignment_uid=new_uuid7_str(),
        managed_curve_uid=new_uuid7_str(),
        managed_product_uid=new_uuid7_str(),
        managed_well_uid=new_uuid7_str(),
        managed_source_uid=new_uuid7_str(),
        track_uid=new_uuid7_str(),
        observed_mnemonic="TEST",
        display_name="Test",
        scale_min=0.0 if with_scale else None,
        scale_max=100.0 if with_scale else None,
        scale_type="linear" if with_scale else None,
        scale_direction="normal" if with_scale else None,
        source="manual_backend_command",
        display_policy_source=display_policy_source,
        display_review_required=is_system_default,
        display_warning_code=(
            "NO_GOVERNED_DISPLAY_POLICY" if is_system_default else None
        ),
        display_warning_message=(
            "Backend system-default display scale is in use."
            if is_system_default
            else None
        ),
    )


def test_explicit_user_override_is_an_override() -> None:
    assert _assignment_has_scale_override(
        assignment(display_policy_source="user_override")
    )


def test_explicit_backend_policy_is_not_an_override() -> None:
    for source in ("curve", "family", "system_default"):
        assert not _assignment_has_scale_override(
            assignment(display_policy_source=source)
        )


def test_legacy_assignment_with_scale_retains_previous_override_semantics() -> None:
    assert _assignment_has_scale_override(
        assignment(display_policy_source=None, with_scale=True)
    )


def test_legacy_assignment_without_scale_is_not_an_override() -> None:
    assert not _assignment_has_scale_override(
        assignment(display_policy_source=None, with_scale=False)
    )
