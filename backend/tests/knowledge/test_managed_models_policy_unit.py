"""UNIT-3A storage contract: DisplayRuleRecord.policy_value_unit field.

Verifies that after adding ``policy_value_unit`` as a declared field on
``DisplayRuleRecord``:

1.  KR JSON deserializes ``policy_value_unit`` into the declared field (not
    into ``_storage_extra_fields``).
2.  ``serialize_record()`` round-trip preserves the field value in the output
    dict.
3.  ``_storage_extra_fields`` does NOT contain ``policy_value_unit`` after
    deserialization (no duplication).
4.  No unrelated extra fields present in the KR JSON are lost during a
    round-trip through ``deserialize_record`` → ``serialize_record``.
5.  Loading records from the live KR file does NOT rewrite the file
    (mtime and SHA-256 hash are unchanged).
6.  Record ``version`` integers are identical before and after loading.
7.  All 12 runtime-eligible approved ``display_rule`` records in the live KR
    have a non-None ``policy_value_unit`` on their deserialized model.

These tests load the live KR JSON directly via ``json.load`` and call
``deserialize_record`` / ``serialize_record`` from ``managed_storage``.
They do not use ``ManagedStorage()`` with no arguments and do not write
to the KR file under any circumstances.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from app.knowledge.managed_models import DisplayRuleRecord
from app.knowledge.managed_storage import deserialize_record, serialize_record

# ---------------------------------------------------------------------------
# Locate the live KR file.
# The knowledge conftest autouse fixture patches DEFAULT_STORAGE_PATH but
# that only affects ManagedStorage() calls with no explicit path argument.
# We resolve the path relative to this file's location so tests are
# independent of the working directory.
# ---------------------------------------------------------------------------

_KR_PATH: Path = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "knowledge"
    / "managed_knowledge.json"
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_kr_raw() -> list[dict[str, Any]]:
    """Load and return the raw records list from the live KR JSON."""
    with _KR_PATH.open(encoding="utf-8") as f:
        return json.load(f)["records"]


def _display_rules_raw() -> list[dict[str, Any]]:
    return [r for r in _load_kr_raw() if r.get("record_type") == "display_rule"]


def _runtime_eligible_display_rules_raw() -> list[dict[str, Any]]:
    return [
        r
        for r in _display_rules_raw()
        if r.get("runtime_eligible") is True and r.get("status") == "approved"
    ]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Test 1 — policy_value_unit lands in the declared field, not extra fields
# ---------------------------------------------------------------------------


def test_display_rule_deserialization_captures_policy_value_unit_as_declared_field() -> None:
    """policy_value_unit must be a declared dataclass field, not an extra."""
    declared = {f.name for f in dataclasses.fields(DisplayRuleRecord)}
    assert "policy_value_unit" in declared, (
        "policy_value_unit is not a declared field on DisplayRuleRecord; "
        "UNIT-3A model patch was not applied"
    )

    raw_records = _runtime_eligible_display_rules_raw()
    assert raw_records, "No runtime-eligible display_rule records found in live KR"

    for raw in raw_records:
        record = deserialize_record(dict(raw))
        assert isinstance(record, DisplayRuleRecord)
        assert hasattr(record, "policy_value_unit"), (
            f"record {raw['record_id']!r} missing policy_value_unit attribute"
        )
        # Value must match the JSON source — no normalization at this layer.
        assert record.policy_value_unit == raw.get("policy_value_unit"), (
            f"record {raw['record_id']!r}: "
            f"expected policy_value_unit={raw.get('policy_value_unit')!r} "
            f"but got {record.policy_value_unit!r}"
        )


# ---------------------------------------------------------------------------
# Test 2 — policy_value_unit is NOT in _storage_extra_fields
# ---------------------------------------------------------------------------


def test_display_rule_policy_value_unit_not_in_storage_extra_fields() -> None:
    """After deserialization, _storage_extra_fields must not contain policy_value_unit."""
    raw_records = _runtime_eligible_display_rules_raw()
    for raw in raw_records:
        record = deserialize_record(dict(raw))
        extra = getattr(record, "_storage_extra_fields", {})
        assert "policy_value_unit" not in extra, (
            f"record {raw['record_id']!r}: policy_value_unit found in "
            f"_storage_extra_fields={extra!r}; it must be a declared field"
        )


# ---------------------------------------------------------------------------
# Test 3 — round-trip preserves policy_value_unit in serialized output
# ---------------------------------------------------------------------------


def test_display_rule_round_trip_preserves_policy_value_unit() -> None:
    """serialize_record(deserialize_record(raw)) must carry policy_value_unit."""
    raw_records = _runtime_eligible_display_rules_raw()
    for raw in raw_records:
        record = deserialize_record(dict(raw))
        serialized = serialize_record(record)
        assert "policy_value_unit" in serialized, (
            f"record {raw['record_id']!r}: policy_value_unit missing from "
            f"serialize_record output"
        )
        assert serialized["policy_value_unit"] == raw.get("policy_value_unit"), (
            f"record {raw['record_id']!r}: serialized policy_value_unit="
            f"{serialized['policy_value_unit']!r} "
            f"!= original {raw.get('policy_value_unit')!r}"
        )


# ---------------------------------------------------------------------------
# Test 4 — no unrelated extra fields lost in round-trip
# ---------------------------------------------------------------------------


def test_no_unrelated_extra_fields_lost_in_round_trip() -> None:
    """All keys present in the raw JSON must survive a deserialize → serialize round-trip.

    The only permitted difference is key ordering; no key may be dropped.
    """
    raw_records = _display_rules_raw()
    for raw in raw_records:
        record = deserialize_record(dict(raw))
        serialized = serialize_record(record)
        for key in raw:
            assert key in serialized, (
                f"record {raw['record_id']!r}: key {key!r} present in KR JSON "
                f"but missing from serialize_record output"
            )


# ---------------------------------------------------------------------------
# Test 5 — loading records does not rewrite the KR file
# ---------------------------------------------------------------------------


def test_kr_file_not_rewritten_by_load() -> None:
    """Deserializing display_rule records must leave the KR file byte-for-byte unchanged."""
    assert _KR_PATH.exists(), f"Live KR not found at {_KR_PATH}"

    sha_before = _sha256(_KR_PATH)
    mtime_before = _KR_PATH.stat().st_mtime_ns

    # Trigger deserialization of all display_rule records.
    raw_records = _display_rules_raw()
    for raw in raw_records:
        deserialize_record(dict(raw))

    sha_after = _sha256(_KR_PATH)
    mtime_after = _KR_PATH.stat().st_mtime_ns

    assert sha_after == sha_before, (
        f"KR file SHA-256 changed after load: {sha_before} → {sha_after}"
    )
    assert mtime_after == mtime_before, (
        f"KR file mtime changed after load: {mtime_before} → {mtime_after}"
    )


# ---------------------------------------------------------------------------
# Test 6 — record version integers are unchanged by load
# ---------------------------------------------------------------------------


def test_display_rule_record_version_unchanged_by_load() -> None:
    """Deserialized record.version must equal the version integer in the KR JSON."""
    raw_records = _display_rules_raw()
    for raw in raw_records:
        record = deserialize_record(dict(raw))
        expected_version = raw.get("version")
        assert record.version == expected_version, (
            f"record {raw['record_id']!r}: "
            f"expected version={expected_version!r} "
            f"but got {record.version!r}"
        )


# ---------------------------------------------------------------------------
# Test 7 — all runtime-eligible display_rule records have non-None policy_value_unit
# ---------------------------------------------------------------------------


def test_all_runtime_eligible_display_rules_have_policy_value_unit() -> None:
    """Every approved runtime-eligible display_rule must expose a non-None policy_value_unit.

    The KR migration (HEAD 02ab9e4) guarantees that all 12 records were
    updated.  This test holds the deserialized model to the same guarantee.
    """
    raw_records = _runtime_eligible_display_rules_raw()
    assert len(raw_records) == 12, (
        f"Expected 12 runtime-eligible approved display_rule records "
        f"but found {len(raw_records)}"
    )

    missing = []
    for raw in raw_records:
        record = deserialize_record(dict(raw))
        if record.policy_value_unit is None:
            missing.append(raw["record_id"])

    assert not missing, (
        f"policy_value_unit is None after deserialization for: {missing}"
    )
