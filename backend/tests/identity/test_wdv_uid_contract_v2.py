from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.identity.wdv_contract_v2 import (
    WDV_IDENTITY_CONTRACT_VERSION,
    WDV_SAMPLE_CONTRACT_VERSION,
    WDV_SESSION_CONTRACT_VERSION,
    WdvCanonicalAssignment,
    WdvCanonicalCurveReference,
    WdvCanonicalSession,
    WdvCanonicalTrack,
    WdvCurveSampleProvenance,
    WdvCurveSampleRequest,
    WdvCurveSampleResponse,
)

WELL = "019f0000-0000-7000-8000-000000000001"
WELL_2 = "019f0000-0000-7000-8000-000000000002"
WELLBORE = "019f0000-0000-7000-8000-000000000003"
CURVE = "019f0000-0000-7000-8000-000000000004"
PRODUCT = "019f0000-0000-7000-8000-000000000005"
SOURCE = "019f0000-0000-7000-8000-000000000006"
TRACK = "019f0000-0000-7000-8000-000000000007"
ASSIGNMENT = "019f0000-0000-7000-8000-000000000008"
SESSION = "019f0000-0000-7000-8000-000000000009"
PLAN = "019f0000-0000-7000-8000-000000000010"


def _assignment(**overrides):
    values = {
        "assignment_uid": ASSIGNMENT,
        "managed_curve_uid": CURVE,
        "managed_product_uid": PRODUCT,
        "managed_well_uid": WELL,
        "managed_wellbore_uid": WELLBORE,
        "managed_source_uid": SOURCE,
        "track_uid": TRACK,
        "kr_curve_type_id": "gamma_ray",
        "observed_mnemonic": "GR",
        "normalized_mnemonic": "GR",
        "display_name": "Gamma Ray",
        "curve_family": "gamma_ray",
        "unit": "API",
        "stack_index": 0,
        "visible": True,
        "scale_min": 0.0,
        "scale_max": 150.0,
        "scale_type": "linear",
        "scale_direction": "normal",
        "color": "#111111",
        "line_style": "solid",
        "line_width": 1.5,
        "fill_mode": "none",
        "source": "template_application",
    }
    values.update(overrides)
    return WdvCanonicalAssignment(**values)


def _track(**overrides):
    values = {
        "track_uid": TRACK,
        "track_key": "gamma-ray",
        "track_number": 1,
        "track_name": "Gamma Ray",
        "track_type": "curve",
        "renderer_type": "line_curve",
        "track_role": "primary",
        "width_px": 240,
        "lattice": "major_minor",
        "lattice_source": "template",
        "source_template_key": "triple_combo",
        "source_application_plan_uid": PLAN,
        "assignments": (_assignment(),),
    }
    values.update(overrides)
    return WdvCanonicalTrack(**values)


def test_contract_versions_are_explicit_v21() -> None:
    assert WDV_IDENTITY_CONTRACT_VERSION == "wdv_identity_v2_1"
    assert WDV_SESSION_CONTRACT_VERSION == "wdv_session_layout_state_v2_1"
    assert WDV_SAMPLE_CONTRACT_VERSION == "wdv_curve_samples_v2_1"


def test_curve_reference_requires_canonical_occurrence_identity() -> None:
    curve = WdvCanonicalCurveReference(
        managed_curve_uid=CURVE,
        managed_product_uid=PRODUCT,
        managed_well_uid=WELL,
        managed_wellbore_uid=WELLBORE,
        managed_source_uid=SOURCE,
        kr_curve_type_id="gamma_ray",
        observed_mnemonic="GR",
        normalized_mnemonic="GR",
        display_name="Gamma Ray",
        unit="API",
        curve_family="gamma_ray",
        description="Natural gamma ray",
    )
    assert curve.managed_curve_uid == CURVE
    assert curve.managed_product_uid == PRODUCT


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("curve_id", "GR"),
        ("curve_uid", CURVE),
        ("product_id", "product-gr"),
        ("display_curve_id", "GR"),
        ("mnemonic", "GR"),
    ],
)
def test_curve_reference_rejects_active_legacy_identity_fields(
    field: str, value: str
) -> None:
    payload = {
        "managed_curve_uid": CURVE,
        "managed_product_uid": PRODUCT,
        "managed_well_uid": WELL,
        "managed_source_uid": SOURCE,
        "observed_mnemonic": "GR",
        "display_name": "Gamma Ray",
        field: value,
    }
    with pytest.raises(ValidationError):
        WdvCanonicalCurveReference(**payload)


def test_session_round_trip_preserves_complete_layout_and_render_state() -> None:
    session = WdvCanonicalSession(
        session_uid=SESSION,
        managed_well_uid=WELL,
        revision=4,
        state_status="active",
        source="backend_template_application",
        selected_track_uid=TRACK,
        tracks=(_track(),),
        warnings=("curve scale reviewed",),
        updated_at="2026-06-18T20:00:00+00:00",
    )

    restored = WdvCanonicalSession.model_validate_json(session.model_dump_json())
    assignment = restored.tracks[0].assignments[0]

    assert restored == session
    assert restored.tracks[0].renderer_type == "line_curve"
    assert restored.tracks[0].width_px == 240
    assert restored.tracks[0].lattice == "major_minor"
    assert restored.tracks[0].source_template_key == "triple_combo"
    assert assignment.scale_min == 0.0
    assert assignment.scale_max == 150.0
    assert assignment.scale_type == "linear"
    assert assignment.scale_direction == "normal"
    assert assignment.color == "#111111"
    assert assignment.curve_family == "gamma_ray"


def test_session_rejects_cross_well_assignment() -> None:
    with pytest.raises(ValidationError, match="session managed_well_uid"):
        WdvCanonicalSession(
            session_uid=SESSION,
            managed_well_uid=WELL,
            state_status="active",
            tracks=(_track(assignments=(_assignment(managed_well_uid=WELL_2),)),),
            updated_at="2026-06-18T20:00:00+00:00",
        )


def test_session_rejects_legacy_session_identity_fields() -> None:
    with pytest.raises(ValidationError):
        WdvCanonicalSession(
            session_uid=SESSION,
            managed_well_uid=WELL,
            state_status="empty",
            tracks=(),
            updated_at="2026-06-18T20:00:00+00:00",
            layout_session_id="legacy-session",
        )


def test_assignment_rejects_partial_or_invalid_scale_state() -> None:
    with pytest.raises(ValidationError, match="supplied together"):
        _assignment(scale_max=None)

    with pytest.raises(ValidationError, match="positive limits"):
        _assignment(scale_min=0, scale_max=100, scale_type="logarithmic")


def test_depth_track_rejects_curve_assignments() -> None:
    with pytest.raises(ValidationError, match="Depth tracks"):
        _track(track_type="depth")


def test_sample_request_cannot_be_addressed_by_product_id() -> None:
    with pytest.raises(ValidationError):
        WdvCurveSampleRequest(
            managed_well_uid=WELL,
            managed_curve_uid=CURVE,
            product_id="product-gr",
        )


def test_sample_response_round_trip_preserves_renderer_metadata() -> None:
    response = WdvCurveSampleResponse(
        managed_well_uid=WELL,
        managed_curve_uid=CURVE,
        managed_product_uid=PRODUCT,
        managed_source_uid=SOURCE,
        sample_revision="sha256:abc",
        observed_mnemonic="GR",
        normalized_mnemonic="GR",
        display_name="Gamma Ray",
        curve_family="gamma_ray",
        depth_unit="ft",
        value_unit="API",
        depth_min=1000.0,
        depth_max=1004.0,
        value_min=35.0,
        value_max=80.0,
        robust_value_min=38.0,
        robust_value_max=76.0,
        value_p01=36.0,
        value_p05=38.0,
        value_p50=55.0,
        value_p95=76.0,
        value_p99=79.0,
        sample_count=5,
        returned_sample_count=3,
        raw_numeric_sample_count=7,
        rejected_sample_count=2,
        rejected_null_count=1,
        rejected_sentinel_count=1,
        rejected_nonfinite_count=0,
        rejected_plausibility_count=0,
        rejected_row_count=0,
        decimation_stride=2,
        provenance=WdvCurveSampleProvenance(
            sample_source="las_original_path",
            source_path="/data/well.las",
            source_intake_candidate_id="candidate-1",
            checksum="abc",
            generated_at="2026-06-18T20:00:00Z",
        ),
        samples=((1000.0, 35.0), (1002.0, 55.0), (1004.0, 80.0)),
    )

    restored = WdvCurveSampleResponse.model_validate_json(
        response.model_dump_json()
    )

    assert restored == response
    assert restored.returned_sample_count == len(restored.samples)
    assert restored.robust_value_min == 38.0
    assert restored.value_p95 == 76.0
    assert restored.decimation_stride == 2
    assert restored.provenance.sample_source == "las_original_path"


def test_sample_response_rejects_inconsistent_counts() -> None:
    base = {
        "managed_well_uid": WELL,
        "managed_curve_uid": CURVE,
        "managed_product_uid": PRODUCT,
        "managed_source_uid": SOURCE,
        "observed_mnemonic": "GR",
        "display_name": "Gamma Ray",
        "depth_unit": "ft",
        "depth_min": 1000.0,
        "depth_max": 1001.0,
        "value_min": 10.0,
        "value_max": 20.0,
        "sample_count": 2,
        "returned_sample_count": 1,
        "rejected_sample_count": 0,
        "provenance": {"sample_source": "las_original_path"},
        "samples": ((1000.0, 10.0), (1001.0, 20.0)),
    }
    with pytest.raises(ValidationError, match="returned_sample_count"):
        WdvCurveSampleResponse(**base)


def test_sample_response_rejects_legacy_identity_fields() -> None:
    with pytest.raises(ValidationError):
        WdvCurveSampleResponse(
            managed_well_uid=WELL,
            managed_curve_uid=CURVE,
            managed_product_uid=PRODUCT,
            managed_source_uid=SOURCE,
            observed_mnemonic="GR",
            display_name="Gamma Ray",
            depth_unit="ft",
            depth_min=1000.0,
            depth_max=1000.0,
            value_min=50.0,
            value_max=50.0,
            sample_count=1,
            returned_sample_count=1,
            rejected_sample_count=0,
            provenance={"sample_source": "las_original_path"},
            samples=((1000.0, 50.0),),
            product_id="legacy-product",
        )
