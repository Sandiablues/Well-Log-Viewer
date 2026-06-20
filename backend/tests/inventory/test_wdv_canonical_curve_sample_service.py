import pytest

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCurveSampleRequest
from app.inventory.canonical_curve_sample_service import CanonicalCurveSampleService


class FakeResolver:
    def resolve_curve(self, managed_well_uid: str, managed_curve_uid: str):
        raise RuntimeError("resolved through canonical boundary")


def test_sample_service_accepts_only_canonical_request_model() -> None:
    request = WdvCurveSampleRequest(
        managed_well_uid=new_uuid7_str(),
        managed_curve_uid=new_uuid7_str(),
        max_samples=100,
    )
    service = CanonicalCurveSampleService(resolver=FakeResolver())
    with pytest.raises(RuntimeError, match="canonical boundary"):
        service.get_curve_samples(request)


def test_sample_request_rejects_product_identity() -> None:
    with pytest.raises(Exception):
        WdvCurveSampleRequest(
            managed_well_uid=new_uuid7_str(),
            managed_curve_uid=new_uuid7_str(),
            product_id="legacy-product",
        )
