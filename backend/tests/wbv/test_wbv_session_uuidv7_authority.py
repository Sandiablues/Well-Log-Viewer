from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.wbv.models import WbvSessionContract


CANONICAL_WELL_UID = "019ee477-40ae-781d-86f6-05d2465bcb7d"
LEGACY_WELL_ID = "managed-well:wlv-intake-name-forge-21-31-a23bc3f44656"


def test_wbv_session_exposes_legacy_id_and_canonical_uuid7_separately() -> None:
    session = WbvSessionContract(
        active_managed_well_id=LEGACY_WELL_ID,
        active_managed_well_uid=CANONICAL_WELL_UID,
    )

    assert session.active_managed_well_id == LEGACY_WELL_ID
    assert session.active_managed_well_uid == CANONICAL_WELL_UID


def test_wbv_session_rejects_legacy_id_in_uuid7_field() -> None:
    with pytest.raises(ValidationError):
        WbvSessionContract(
            active_managed_well_id=LEGACY_WELL_ID,
            active_managed_well_uid=LEGACY_WELL_ID,
        )
