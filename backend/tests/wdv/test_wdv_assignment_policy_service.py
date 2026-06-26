from types import SimpleNamespace

from app.identity import new_uuid7_str
from app.wdv_session.assignment_policy_service import (
    CanonicalWdvAssignmentPolicyService,
    SYSTEM_DEFAULT_MAX,
    SYSTEM_DEFAULT_MIN,
    SYSTEM_DEFAULT_WARNING_CODE,
)


class FakeResolver:
    def __init__(self) -> None:
        self.well_uid = new_uuid7_str()
        self.curve_uid = new_uuid7_str()
        self.product_uid = new_uuid7_str()
        self.source_uid = new_uuid7_str()

    def resolve_curve(self, managed_well_uid: str, managed_curve_uid: str):
        assert managed_well_uid == self.well_uid
        assert managed_curve_uid == self.curve_uid
        return SimpleNamespace(
            managed_well_uid=self.well_uid,
            managed_curve_uid=self.curve_uid,
            managed_product_uid=self.product_uid,
            managed_source_uid=self.source_uid,
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


def build(policy: dict):
    resolver = FakeResolver()
    service = CanonicalWdvAssignmentPolicyService(
        resolver=resolver,
        display_policy_resolver=lambda _product: policy,
    )
    return resolver, service


def test_curve_policy_materializes_complete_assignment() -> None:
    resolver, service = build({
        "min": 1.95,
        "max": 2.95,
        "type": "linear",
        "direction": "normal",
        "source": "managed_knowledge_curve_rule",
    })

    assignment = service.create_assignment(
        managed_well_uid=resolver.well_uid,
        managed_curve_uid=resolver.curve_uid,
        track_uid=new_uuid7_str(),
        stack_index=0,
        assignment_source="manual_backend_command",
    )

    assert assignment.source == "manual_backend_command"
    assert assignment.scale_min == 1.95
    assert assignment.scale_max == 2.95
    assert assignment.display_policy_source == "curve"
    assert assignment.display_review_required is False
    assert assignment.display_warning_code is None


def test_family_policy_materializes_complete_assignment() -> None:
    resolver, service = build({
        "min": 0.2,
        "max": 2000.0,
        "type": "log",
        "direction": "normal",
        "source": "managed_knowledge_family_default",
    })

    assignment = service.create_assignment(
        managed_well_uid=resolver.well_uid,
        managed_curve_uid=resolver.curve_uid,
        track_uid=new_uuid7_str(),
        stack_index=1,
        assignment_source="configured_track_backend_command",
    )

    assert assignment.source == "configured_track_backend_command"
    assert assignment.scale_type == "logarithmic"
    assert assignment.display_policy_source == "family"
    assert assignment.display_review_required is False


def test_missing_governed_policy_uses_backend_system_default_with_warning() -> None:
    resolver, service = build({
        "min": None,
        "max": None,
        "type": "linear",
        "direction": "normal",
        "source": "unit_resolution_tier3_no_bounds",
    })

    assignment = service.create_assignment(
        managed_well_uid=resolver.well_uid,
        managed_curve_uid=resolver.curve_uid,
        track_uid=new_uuid7_str(),
        stack_index=0,
        assignment_source="manual_backend_command",
    )

    assert assignment.scale_min == SYSTEM_DEFAULT_MIN
    assert assignment.scale_max == SYSTEM_DEFAULT_MAX
    assert assignment.display_policy_source == "system_default"
    assert assignment.display_review_required is True
    assert assignment.display_warning_code == SYSTEM_DEFAULT_WARNING_CODE
    assert "system-default" in assignment.display_warning_message


def test_non_governed_usable_policy_is_marked_system_default() -> None:
    resolver, service = build({
        "min": 6.0,
        "max": 16.0,
        "type": "linear",
        "direction": "normal",
        "source": "internal_fallback",
    })

    assignment = service.create_assignment(
        managed_well_uid=resolver.well_uid,
        managed_curve_uid=resolver.curve_uid,
        track_uid=new_uuid7_str(),
        stack_index=0,
        assignment_source="manual_backend_command",
    )

    assert assignment.scale_min == 6.0
    assert assignment.scale_max == 16.0
    assert assignment.display_policy_source == "system_default"
    assert assignment.display_review_required is True


def test_invalid_log_policy_falls_back_to_safe_system_default() -> None:
    resolver, service = build({
        "min": 0.0,
        "max": 2000.0,
        "type": "logarithmic",
        "direction": "normal",
        "source": "managed_knowledge_family_default",
    })

    assignment = service.create_assignment(
        managed_well_uid=resolver.well_uid,
        managed_curve_uid=resolver.curve_uid,
        track_uid=new_uuid7_str(),
        stack_index=0,
        assignment_source="manual_backend_command",
    )

    assert assignment.scale_min == SYSTEM_DEFAULT_MIN
    assert assignment.scale_max == SYSTEM_DEFAULT_MAX
    assert assignment.scale_type == "linear"
    assert assignment.display_policy_source == "system_default"


def test_refresh_preserves_assignment_identity_source_and_style() -> None:
    resolver, service = build({
        "min": 1.95,
        "max": 2.95,
        "type": "linear",
        "direction": "normal",
        "source": "managed_knowledge_family_default",
    })
    original = service.create_assignment(
        managed_well_uid=resolver.well_uid,
        managed_curve_uid=resolver.curve_uid,
        track_uid=new_uuid7_str(),
        stack_index=0,
        assignment_source="canonical_governed_template_apply",
        color="#ffffff",
        line_width=1.8,
    )

    refreshed = service.refresh_assignment(original)

    assert refreshed.assignment_uid == original.assignment_uid
    assert refreshed.track_uid == original.track_uid
    assert refreshed.source == "canonical_governed_template_apply"
    assert refreshed.color == "#ffffff"
    assert refreshed.line_width == 1.8
    assert refreshed.display_policy_source == "family"


def test_refresh_does_not_replace_explicit_user_override() -> None:
    resolver, service = build({
        "min": 1.95,
        "max": 2.95,
        "type": "linear",
        "direction": "normal",
        "source": "managed_knowledge_family_default",
    })
    original = service.create_assignment(
        managed_well_uid=resolver.well_uid,
        managed_curve_uid=resolver.curve_uid,
        track_uid=new_uuid7_str(),
        stack_index=0,
        assignment_source="manual_backend_command",
    ).model_copy(
        update={
            "scale_min": 2.1,
            "scale_max": 2.8,
            "display_policy_source": "user_override",
        }
    )

    assert service.refresh_assignment(original) == original
