"""C1 focused tests — WDV display-policy cache identity.

Tests verify:
  1. Missing policy version/revision makes a cached contract stale.
  2. Older/wrong revision makes it stale.
  3. Current revision permits reuse.
  4. Semantic KR policy change changes the revision.
  5. Timestamp-only change with identical governed content does NOT change revision.
  6. Resolver-version change changes the revision.
  7. AT30 rebuild resolves to 0.2–2000, logarithmic.
  8. Second unchanged request reuses the rebuilt contract.
  9. Existing identity and sample-access freshness checks still pass.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest import mock
from uuid import UUID

import pytest

import app.knowledge.managed_storage as _ms_module
from app.inventory.models import ManagedProductGroupItem, ManagedWellRecord
from app.inventory.service import ManagedWellInventoryService
from app.knowledge.managed_storage import ManagedStorage
from app.wdv_display.kr_family_policy_resolver import ManagedKrFamilyDisplayPolicyResolver
from app.wdv_display.policy_service import (
    WDV_DISPLAY_POLICY_CONTRACT_VERSION,
    WDV_DISPLAY_POLICY_RESOLVER_VERSION,
    _clear_display_policy_revision_cache_for_tests,
    compute_display_policy_revision,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid7(value: str) -> str:
    parsed = UUID(value)
    assert parsed.version == 7
    return value


def _write_kr(path: Path, records: list[dict]) -> Path:
    """Write a minimal valid managed_knowledge.json to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"storage_schema_version": "wlv-managed-kr-1", "records": records},
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return path


def _resistivity_tsd(
    *,
    scale_min: str = "0.2",
    scale_max: str = "2000",
    policy_value_unit: str | None = None,
) -> dict:
    """Approved template_scale_default for resistivity — minimal valid shape."""
    record: dict = {
        "record_id": "tsd-resistivity-c1-test",
        "record_type": "template_scale_default",
        "status": "approved",
        "runtime_eligible": True,
        "curve_family": "resistivity",
        "scale_type": "log",
        "scale_min": scale_min,
        "scale_max": scale_max,
        "display_direction": "normal",
        # Volatile fields absent intentionally — proves they don't affect revision.
    }
    if policy_value_unit is not None:
        record["policy_value_unit"] = policy_value_unit
    return record


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# A stable set of UUIDs for the shared identity fixture.
_WELL_UID   = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773101")
_WB_UID     = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773102")
_PROD_UID   = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773103")
_CURVE_UID  = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773104")
_SOURCE_UID = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773105")
_VPK_UID    = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773106")
_REPR_UID   = _uuid7("01976c6d-4aa7-7e43-b118-d7d30e773107")
_SAMPLES_URL = (
    f"/api/wlv/v2/inventory/wells/{_WELL_UID}/curves/{_CURVE_UID}/samples"
)


@pytest.fixture()
def record() -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id="c1-test-well",
        well_id="c1-test-well-id",
        well_name="C1 Test Well",
        managed_well_uid=_WELL_UID,
        managed_wellbore_uid=_WB_UID,
    )


@pytest.fixture()
def item() -> ManagedProductGroupItem:
    return ManagedProductGroupItem(
        product_id="AT30",
        display_name="Array Resistivity 30in",
        curve_name="AT30",
        curve_type="curve",
        curve_unit="ohmm",
        curve_family="resistivity",
        managed_product_uid=_PROD_UID,
        managed_curve_uid=_CURVE_UID,
        managed_source_uid=_SOURCE_UID,
        selectable=True,
    )


@pytest.fixture()
def complete_session(tmp_path: Path) -> dict:
    """A fully valid identity+policy session dict (passes all checks).

    The policy stamps use an absent KR path so the revision is the
    deterministic empty-store hash.  Individual tests override these fields
    as needed.
    """
    absent_kr = ManagedStorage(path=tmp_path / "absent_kr.json")
    revision = compute_display_policy_revision(storage=absent_kr)
    return {
        # Identity fields
        "managed_well_uid": _WELL_UID,
        "managed_wellbore_uid": _WB_UID,
        "viewer_package_uid": _VPK_UID,
        "representation_uid": _REPR_UID,
        # Curve items — one item matching `item` fixture
        "loaded_curve_items": [
            {
                "product_id": "AT30",
                "managed_product_uid": _PROD_UID,
                "managed_curve_uid": _CURVE_UID,
                "managed_source_uid": _SOURCE_UID,
                "samples_url": _SAMPLES_URL,
                "sample_revision": "c1-test-sample-rev-1",
                "sample_access": {
                    "contract_version": "wdv_curve_samples_v1",
                    "endpoint": _SAMPLES_URL,
                    "status": "available",
                    "revision": "c1-test-sample-rev-1",
                },
            }
        ],
        # Policy stamps — absent-KR revision (empty records → deterministic hash)
        "display_policy_contract_version": WDV_DISPLAY_POLICY_CONTRACT_VERSION,
        "display_policy_revision": revision,
    }


@pytest.fixture(autouse=True)
def clear_revision_cache():
    """Clear the in-process revision cache before and after each test."""
    _clear_display_policy_revision_cache_for_tests()
    yield
    _clear_display_policy_revision_cache_for_tests()


# ---------------------------------------------------------------------------
# Test 1 — Missing policy version/revision makes contract stale
# ---------------------------------------------------------------------------

def test_missing_policy_stamps_make_contract_stale(
    complete_session: dict,
    record: ManagedWellRecord,
    item: ManagedProductGroupItem,
    tmp_path: Path,
) -> None:
    """A session dict without display_policy_contract_version or
    display_policy_revision must be treated as stale (pre-C1 contract)."""
    absent_storage = ManagedStorage(path=tmp_path / "absent.json")

    session_no_stamps = {
        k: v for k, v in complete_session.items()
        if k not in ("display_policy_contract_version", "display_policy_revision")
    }
    assert not ManagedWellInventoryService._wdv_session_identity_contract_is_current(
        session_no_stamps, record, [item], storage=absent_storage
    )

    session_no_contract_version = {
        **complete_session,
        "display_policy_revision": complete_session["display_policy_revision"],
    }
    del session_no_contract_version["display_policy_contract_version"]
    assert not ManagedWellInventoryService._wdv_session_identity_contract_is_current(
        session_no_contract_version, record, [item], storage=absent_storage
    )

    session_no_revision = {
        **complete_session,
        "display_policy_contract_version": WDV_DISPLAY_POLICY_CONTRACT_VERSION,
    }
    del session_no_revision["display_policy_revision"]
    assert not ManagedWellInventoryService._wdv_session_identity_contract_is_current(
        session_no_revision, record, [item], storage=absent_storage
    )


# ---------------------------------------------------------------------------
# Test 2 — Wrong/older revision makes contract stale
# ---------------------------------------------------------------------------

def test_wrong_revision_makes_contract_stale(
    complete_session: dict,
    record: ManagedWellRecord,
    item: ManagedProductGroupItem,
    tmp_path: Path,
) -> None:
    """A session stamped with a plausible-looking but incorrect revision is stale."""
    absent_storage = ManagedStorage(path=tmp_path / "absent.json")
    session = {
        **complete_session,
        "display_policy_contract_version": WDV_DISPLAY_POLICY_CONTRACT_VERSION,
        "display_policy_revision": "a" * 64,  # wrong hash
    }
    assert not ManagedWellInventoryService._wdv_session_identity_contract_is_current(
        session, record, [item], storage=absent_storage
    )


# ---------------------------------------------------------------------------
# Test 3 — Current revision permits reuse
# ---------------------------------------------------------------------------

def test_current_revision_permits_reuse(
    complete_session: dict,
    record: ManagedWellRecord,
    item: ManagedProductGroupItem,
    tmp_path: Path,
) -> None:
    """A session stamped with the revision derived from the current KR state passes."""
    kr_path = _write_kr(tmp_path / "kr.json", [_resistivity_tsd()])
    storage = ManagedStorage(path=kr_path)
    revision = compute_display_policy_revision(storage=storage)

    session = {
        **complete_session,
        "display_policy_contract_version": WDV_DISPLAY_POLICY_CONTRACT_VERSION,
        "display_policy_revision": revision,
    }
    assert ManagedWellInventoryService._wdv_session_identity_contract_is_current(
        session, record, [item], storage=storage
    )


# ---------------------------------------------------------------------------
# Test 4 — Semantic KR policy change changes the revision
# ---------------------------------------------------------------------------

def test_semantic_kr_change_changes_revision(tmp_path: Path) -> None:
    """Changing a policy-semantic field (scale_min) changes the content revision."""
    kr_v1 = _write_kr(tmp_path / "kr_v1.json", [_resistivity_tsd(scale_min="0.2")])
    kr_v2 = _write_kr(tmp_path / "kr_v2.json", [_resistivity_tsd(scale_min="0.1")])

    r1 = compute_display_policy_revision(storage=ManagedStorage(path=kr_v1))
    _clear_display_policy_revision_cache_for_tests()
    r2 = compute_display_policy_revision(storage=ManagedStorage(path=kr_v2))

    assert r1 != r2, "Different scale_min must produce different revisions"
    assert len(r1) == 64
    assert len(r2) == 64


# ---------------------------------------------------------------------------
# Test 5 — Timestamp-only change does NOT change revision (key invariant)
# ---------------------------------------------------------------------------

def test_timestamp_only_change_does_not_change_revision(tmp_path: Path) -> None:
    """Rewriting the KR file with identical governed content but a new file mtime
    must NOT change the content-based revision.

    This is the central invariant: the revision is content-based, not stat-based.
    The process-local fast-path cache will miss after the mtime changes, forcing
    a re-read and re-hash — which must produce the same result.
    """
    record_dict = _resistivity_tsd()
    kr_path = tmp_path / "kr.json"
    _write_kr(kr_path, [record_dict])
    storage = ManagedStorage(path=kr_path)

    r1 = compute_display_policy_revision(storage=storage)

    # Ensure the next write gets a different mtime on any filesystem.
    time.sleep(0.02)

    # Clear cache to force re-read on next call (simulates new process or eviction).
    _clear_display_policy_revision_cache_for_tests()

    # Overwrite with identical governed content — new mtime, same records.
    _write_kr(kr_path, [record_dict])

    r2 = compute_display_policy_revision(storage=storage)

    assert r1 == r2, (
        "Identical governed content must yield identical revision regardless of "
        "file mtime change. The revision is content-based, not stat-based."
    )


# ---------------------------------------------------------------------------
# Test 6 — Resolver-version change changes the revision
# ---------------------------------------------------------------------------

def test_resolver_version_change_changes_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bumping WDV_DISPLAY_POLICY_RESOLVER_VERSION changes the revision for an
    unchanged KR file, ensuring algorithm changes automatically invalidate cached
    contracts."""
    import app.wdv_display.policy_service as ps

    kr_path = _write_kr(tmp_path / "kr.json", [_resistivity_tsd()])
    storage = ManagedStorage(path=kr_path)

    r1 = compute_display_policy_revision(storage=storage)
    assert len(r1) == 64

    # Simulate bumping the resolver version constant.
    monkeypatch.setattr(ps, "WDV_DISPLAY_POLICY_RESOLVER_VERSION", "wdv_display_policy_resolver_v3")
    _clear_display_policy_revision_cache_for_tests()

    r2 = compute_display_policy_revision(storage=storage)

    assert r1 != r2, (
        "Bumping WDV_DISPLAY_POLICY_RESOLVER_VERSION must produce a different revision "
        "even with identical KR content."
    )
    assert len(r2) == 64


# ---------------------------------------------------------------------------
# Test 7 — AT30 rebuild resolves to 0.2–2000, logarithmic
# ---------------------------------------------------------------------------

def test_at30_resolves_to_governed_log_scale(tmp_path: Path) -> None:
    """After stale-contract detection forces a rebuild, AT30 must resolve to the
    governed resistivity family default: 0.2–2000, log, via the KR family resolver.

    Uses isolated temporary storage so the test is independent of live KR
    migration state.  The resistivity TSD is annotated with
    policy_value_unit='ohmm' (matches AT30's curve_unit; factor=1.0 passthrough).
    """
    from app.wdv_display.policy_service import WdvCurveDisplayPolicyService

    kr_path = _write_kr(
        tmp_path / "kr.json",
        [_resistivity_tsd(policy_value_unit="ohmm")],
    )
    ManagedKrFamilyDisplayPolicyResolver.clear_cache_for_tests()

    item = ManagedProductGroupItem(
        product_id="AT30",
        display_name="Array Resistivity 30in",
        curve_name="AT30",
        curve_type="curve",
        curve_unit="ohmm",
        curve_family="resistivity",
        selectable=True,
    )
    # No sample stats → pure governed range; no observed-stats override possible.
    with mock.patch.object(_ms_module, "DEFAULT_STORAGE_PATH", kr_path):
        result = WdvCurveDisplayPolicyService.resolve(item, {})

    ManagedKrFamilyDisplayPolicyResolver.clear_cache_for_tests()

    assert result["type"] == "log", f"Expected log, got {result['type']!r}"
    assert abs(result["min"] - 0.2) < 1e-9, f"Expected min 0.2, got {result['min']}"
    assert abs(result["max"] - 2000.0) < 1e-9, f"Expected max 2000, got {result['max']}"
    assert result["source"] == "managed_knowledge_family_default", result["source"]
    assert result["lattice"] == "logarithmic", result["lattice"]
    assert result["min"] > 0, "Log scale min must be positive"


# ---------------------------------------------------------------------------
# Test 8 — Second unchanged request reuses the rebuilt contract
# ---------------------------------------------------------------------------

def test_second_unchanged_request_reuses_contract(
    complete_session: dict,
    record: ManagedWellRecord,
    item: ManagedProductGroupItem,
    tmp_path: Path,
) -> None:
    """A session stamped with the current revision passes on both the first and
    second staleness check, proving no unnecessary rebuild on repeated requests."""
    kr_path = _write_kr(tmp_path / "kr.json", [_resistivity_tsd()])
    storage = ManagedStorage(path=kr_path)
    revision = compute_display_policy_revision(storage=storage)

    session = {
        **complete_session,
        "display_policy_contract_version": WDV_DISPLAY_POLICY_CONTRACT_VERSION,
        "display_policy_revision": revision,
    }

    # First check
    assert ManagedWellInventoryService._wdv_session_identity_contract_is_current(
        session, record, [item], storage=storage
    ), "First check must pass"

    # Second check — same session dict, same KR state
    assert ManagedWellInventoryService._wdv_session_identity_contract_is_current(
        session, record, [item], storage=storage
    ), "Second check must also pass — no rebuild triggered"

    # Revision must also be deterministic across two calls
    r1 = compute_display_policy_revision(storage=storage)
    r2 = compute_display_policy_revision(storage=storage)
    assert r1 == r2, "compute_display_policy_revision must be idempotent"


# ---------------------------------------------------------------------------
# Test 9 — Existing identity and sample-access checks still operate
# ---------------------------------------------------------------------------

def test_existing_identity_checks_not_bypassed_by_correct_revision(
    complete_session: dict,
    record: ManagedWellRecord,
    item: ManagedProductGroupItem,
    tmp_path: Path,
) -> None:
    """A session with the correct policy revision but a mismatched managed_curve_uid
    must still be rejected.  The pre-existing identity and sample-access checks
    are not bypassed by the policy revision being correct."""
    kr_path = _write_kr(tmp_path / "kr.json", [_resistivity_tsd()])
    storage = ManagedStorage(path=kr_path)
    revision = compute_display_policy_revision(storage=storage)

    # Corrupt the curve UID in loaded_curve_items.
    corrupted_items = [
        {
            **complete_session["loaded_curve_items"][0],
            "managed_curve_uid": "00000000-0000-7000-8000-000000000000",
        }
    ]
    session_bad_uid = {
        **complete_session,
        "display_policy_contract_version": WDV_DISPLAY_POLICY_CONTRACT_VERSION,
        "display_policy_revision": revision,
        "loaded_curve_items": corrupted_items,
    }
    assert not ManagedWellInventoryService._wdv_session_identity_contract_is_current(
        session_bad_uid, record, [item], storage=storage
    ), "Mismatched managed_curve_uid must still fail even with correct policy revision"

    # Sanity check: the un-corrupted session passes.
    session_good = {
        **complete_session,
        "display_policy_contract_version": WDV_DISPLAY_POLICY_CONTRACT_VERSION,
        "display_policy_revision": revision,
    }
    assert ManagedWellInventoryService._wdv_session_identity_contract_is_current(
        session_good, record, [item], storage=storage
    ), "Un-corrupted session must pass"
