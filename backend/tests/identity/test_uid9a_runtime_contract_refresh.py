from __future__ import annotations

from uuid import UUID

import pytest

from app.inventory.models import ManagedProductGroupItem, ManagedWellRecord
from app.inventory.service import ManagedWellInventoryService
from app.wbv.models import WbvSetActiveTrajectoryRequest


def _uuid7(value: str) -> str:
    parsed = UUID(value)
    assert parsed.version == 7
    return value


def test_wdv_identity_contract_rejects_stale_legacy_only_session() -> None:
    well_uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e21")
    wellbore_uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e22")
    product_uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e23")
    curve_uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e24")
    source_uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e25")
    record = ManagedWellRecord(
        managed_well_id="legacy-well",
        well_id="legacy-well-id",
        well_name="Well A",
        managed_well_uid=well_uid,
        managed_wellbore_uid=wellbore_uid,
    )
    item = ManagedProductGroupItem(
        product_id="legacy-product",
        display_name="GR",
        curve_name="GR",
        curve_type="gamma_ray",
        managed_product_uid=product_uid,
        managed_curve_uid=curve_uid,
        managed_source_uid=source_uid,
    )
    stale = {
        "managed_well_id": "legacy-well",
        "loaded_curve_items": [{"product_id": "legacy-product", "curve_uid": "legacy-curve"}],
    }
    assert not ManagedWellInventoryService._wdv_session_identity_contract_is_current(stale, record, [item])


def test_wdv_identity_contract_accepts_complete_canonical_session() -> None:
    well_uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e31")
    wellbore_uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e32")
    product_uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e33")
    curve_uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e34")
    source_uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e35")
    record = ManagedWellRecord(
        managed_well_id="legacy-well",
        well_id="legacy-well-id",
        well_name="Well A",
        managed_well_uid=well_uid,
        managed_wellbore_uid=wellbore_uid,
    )
    item = ManagedProductGroupItem(
        product_id="legacy-product",
        display_name="GR",
        curve_name="GR",
        curve_type="gamma_ray",
        managed_product_uid=product_uid,
        managed_curve_uid=curve_uid,
        managed_source_uid=source_uid,
    )
    current = {
        "managed_well_uid": well_uid,
        "managed_wellbore_uid": wellbore_uid,
        "viewer_package_uid": _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e36"),
        "representation_uid": _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e37"),
        "loaded_curve_items": [{
            "product_id": "legacy-product",
            "managed_product_uid": product_uid,
            "managed_curve_uid": curve_uid,
            "managed_source_uid": source_uid,
            "samples_url": (
                "/api/wlv/v2/inventory/wells/"
                f"{well_uid}/curves/{curve_uid}/samples"
            ),
            "sample_revision": "sample-revision-1",
            "sample_access": {
                "contract_version": "wdv_curve_samples_v1",
                "endpoint": (
                    "/api/wlv/v2/inventory/wells/"
                    f"{well_uid}/curves/{curve_uid}/samples"
                ),
                "status": "available",
                "revision": "sample-revision-1",
            },
        }],
    }
    assert ManagedWellInventoryService._wdv_session_identity_contract_is_current(current, record, [item])


def test_wdv_identity_contract_rejects_missing_sample_access_contract() -> None:
    well_uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e51")
    product_uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e52")
    curve_uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e53")
    source_uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e54")
    record = ManagedWellRecord(
        managed_well_id="legacy-well",
        well_id="legacy-well-id",
        well_name="Well A",
        managed_well_uid=well_uid,
    )
    item = ManagedProductGroupItem(
        product_id="legacy-product",
        display_name="GR",
        curve_name="GR",
        curve_type="gamma_ray",
        managed_product_uid=product_uid,
        managed_curve_uid=curve_uid,
        managed_source_uid=source_uid,
    )
    incomplete = {
        "managed_well_uid": well_uid,
        "viewer_package_uid": _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e55"),
        "representation_uid": _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e56"),
        "loaded_curve_items": [{
            "product_id": "legacy-product",
            "managed_product_uid": product_uid,
            "managed_curve_uid": curve_uid,
            "managed_source_uid": source_uid,
            "samples_url": "/api/wlv/v2/samples",
            "sample_revision": "sample-revision-1",
        }],
    }
    assert not ManagedWellInventoryService._wdv_session_identity_contract_is_current(
        incomplete,
        record,
        [item],
    )


def test_wbv_request_accepts_canonical_or_legacy_reference() -> None:
    uid = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773e41")
    canonical = WbvSetActiveTrajectoryRequest(managed_trajectory_uid=uid)
    assert canonical.canonical_or_legacy_reference == uid
    previous_canonical_alias = WbvSetActiveTrajectoryRequest(trajectory_uid=uid)
    assert previous_canonical_alias.canonical_or_legacy_reference == uid
    legacy = WbvSetActiveTrajectoryRequest(trajectory_id="traj:legacy")
    assert legacy.canonical_or_legacy_reference == "traj:legacy"
    with pytest.raises(ValueError):
        WbvSetActiveTrajectoryRequest()
