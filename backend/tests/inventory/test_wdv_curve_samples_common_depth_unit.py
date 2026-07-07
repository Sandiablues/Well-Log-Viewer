from app.identity.wdv_contract_v2 import WdvCurveSampleRequest


def test_curve_sample_request_accepts_common_depth_target_unit() -> None:
    request = WdvCurveSampleRequest(
        managed_well_uid="01900000-0000-7000-8000-000000000001",
        managed_curve_uid="01900000-0000-7000-8000-000000000002",
        target_depth_unit="m",
        max_samples=100,
    )
    assert request.target_depth_unit == "m"
