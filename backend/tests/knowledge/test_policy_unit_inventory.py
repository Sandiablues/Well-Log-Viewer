"""UNIT-2 tests for actual-schema, read-only policy-unit inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.knowledge.policy_unit_inventory import (
    PolicyUnitInventoryService,
    PolicyUnitInventoryStatus,
    migration_manifest_candidate,
    write_inventory_outputs,
)


def _record(record_id: str, record_type: str, **fields):
    return {
        "record_id": record_id,
        "record_type": record_type,
        "status": "approved",
        "runtime_eligible": True,
        **fields,
    }


def _write(path: Path, records: list[dict]) -> bytes:
    payload = (json.dumps({"records": records}, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(payload)
    return payload


def _entry(path: Path):
    return PolicyUnitInventoryService(storage_path=path).run().entries[0]


def test_inventory_is_byte_for_byte_read_only(tmp_path: Path) -> None:
    path = tmp_path / "managed.json"
    before = _write(path, [
        _record("gr", "template_scale_default", curve_family="gamma_ray", unit_family="api", scale_type="linear", scale_min=0, scale_max=150),
    ])
    report = PolicyUnitInventoryService(storage_path=path).run()
    assert path.read_bytes() == before
    assert report.source_sha256 == hashlib.sha256(before).hexdigest()


def test_explicit_policy_value_unit_has_precedence(tmp_path: Path) -> None:
    path = tmp_path / "managed.json"
    _write(path, [
        _record("x", "template_scale_default", unit_family="engineering", policy_value_unit="psi", scale_type="linear", scale_min=0, scale_max=10000),
    ])
    entry = _entry(path)
    assert entry.status == PolicyUnitInventoryStatus.EXPLICIT_SUPPORTED.value
    assert entry.proposed_policy_value_unit == "psi"
    assert entry.evidence_source == "record.policy_value_unit"


def test_unknown_explicit_unit_is_distinct(tmp_path: Path) -> None:
    path = tmp_path / "managed.json"
    _write(path, [
        _record("x", "template_scale_default", policy_value_unit="mystery", scale_type="linear", scale_min=0, scale_max=1),
    ])
    assert _entry(path).status == PolicyUnitInventoryStatus.EXPLICIT_UNKNOWN_UNIT.value


def test_exact_display_rule_uses_governed_default_unit(tmp_path: Path) -> None:
    path = tmp_path / "managed.json"
    _write(path, [
        _record("dr", "display_rule", canonical_curve_id="deep_induction_resistivity", default_unit="ohm.m", scale_type="log", display_min=0.2, display_max=2000),
    ])
    entry = _entry(path)
    assert entry.status == PolicyUnitInventoryStatus.INFERABLE_SUPPORTED.value
    assert entry.proposed_policy_value_unit == "ohmm"
    assert entry.evidence_source == "display_rule.default_unit"
    assert entry.evidence_raw_value == "ohm.m"


def test_display_rule_missing_or_unknown_default_unit_requires_review(tmp_path: Path) -> None:
    path = tmp_path / "managed.json"
    _write(path, [
        _record("missing", "display_rule", scale_type="linear", display_min=0, display_max=1),
        _record("unknown", "display_rule", default_unit="mystery", scale_type="linear", display_min=0, display_max=1),
    ])
    entries = {entry.record_id: entry for entry in PolicyUnitInventoryService(storage_path=path).run().entries}
    assert entries["missing"].status == PolicyUnitInventoryStatus.AMBIGUOUS_REVIEW_REQUIRED.value
    assert entries["missing"].reason == "exact_display_rule_default_unit_missing"
    assert entries["unknown"].reason == "exact_display_rule_default_unit_not_supported"


def test_unambiguous_unit_family_tokens_map_to_supported_units(tmp_path: Path) -> None:
    cases = {
        "api": "gapi",
        "mv": "mv",
        "ohm_m": "ohmm",
        "g_per_cc": "g/cc",
        "us_per_ft": "us/ft",
        "barns_per_electron": "b/e",
        "md": "md",
    }
    path = tmp_path / "managed.json"
    _write(path, [
        _record(key, "template_scale_default", unit_family=key, scale_type="linear", scale_min=0, scale_max=1)
        for key in cases
    ])
    entries = {entry.record_id: entry for entry in PolicyUnitInventoryService(storage_path=path).run().entries}
    assert {key: entries[key].proposed_policy_value_unit for key in cases} == cases
    assert all(entry.status == PolicyUnitInventoryStatus.INFERABLE_SUPPORTED.value for entry in entries.values())


def test_broad_unit_family_tokens_are_never_guessed_from_bounds(tmp_path: Path) -> None:
    broad = ["length", "porosity_unit", "fraction_or_percent", "engineering"]
    path = tmp_path / "managed.json"
    _write(path, [
        _record(token, "template_scale_default", unit_family=token, scale_type="linear", scale_min=0, scale_max=10000)
        for token in broad
    ])
    report = PolicyUnitInventoryService(storage_path=path).run()
    assert all(entry.status == PolicyUnitInventoryStatus.AMBIGUOUS_REVIEW_REQUIRED.value for entry in report.entries)
    assert all(entry.proposed_policy_value_unit is None for entry in report.entries)
    assert all(entry.reason == "unit_family_is_broad_or_multi_representation" for entry in report.entries)


def test_unknown_or_missing_unit_family_requires_review(tmp_path: Path) -> None:
    path = tmp_path / "managed.json"
    _write(path, [
        _record("missing", "template_scale_default", scale_type="linear", scale_min=0, scale_max=1),
        _record("unknown", "template_scale_default", unit_family="new_token", scale_type="linear", scale_min=0, scale_max=1),
    ])
    entries = {entry.record_id: entry for entry in PolicyUnitInventoryService(storage_path=path).run().entries}
    assert entries["missing"].reason == "unit_family_missing"
    assert entries["unknown"].reason == "unit_family_not_defined_in_evidence_contract"


def test_non_line_or_incomplete_records_are_not_candidates(tmp_path: Path) -> None:
    path = tmp_path / "managed.json"
    _write(path, [
        _record("event", "template_scale_default", unit_family="event_or_curve", scale_type="event_track"),
        _record("image", "template_scale_default", unit_family="image", scale_type="image_track", scale_min=0, scale_max=360),
        _record("missing", "display_rule", default_unit="API", scale_type="linear", display_min=0),
    ])
    report = PolicyUnitInventoryService(storage_path=path).run()
    assert all(entry.status == PolicyUnitInventoryStatus.NON_NUMERIC_OR_NON_LINE.value for entry in report.entries)


def test_non_approved_and_non_runtime_records_are_excluded(tmp_path: Path) -> None:
    path = tmp_path / "managed.json"
    _write(path, [
        {**_record("candidate", "template_scale_default", scale_type="linear", scale_min=0, scale_max=1), "status": "candidate"},
        {**_record("disabled", "display_rule", scale_type="linear", display_min=0, display_max=1), "runtime_eligible": False},
    ])
    assert PolicyUnitInventoryService(storage_path=path).run().entries == ()


def test_manifest_contains_only_supported_inferred_candidates(tmp_path: Path) -> None:
    path = tmp_path / "managed.json"
    _write(path, [
        _record("gr", "template_scale_default", unit_family="api", scale_type="linear", scale_min=0, scale_max=150),
        _record("caliper", "template_scale_default", unit_family="length", scale_type="linear", scale_min=6, scale_max=16),
        _record("explicit", "template_scale_default", policy_value_unit="mv", scale_type="linear", scale_min=-100, scale_max=100),
    ])
    report = PolicyUnitInventoryService(storage_path=path).run()
    manifest = migration_manifest_candidate(report)
    assert [entry["record_id"] for entry in manifest["entries"]] == ["gr"]


def test_outputs_are_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "managed.json"
    original = _write(path, [
        _record("dr", "display_rule", default_unit="API", scale_type="linear", display_min=0, display_max=300),
    ])
    report = PolicyUnitInventoryService(storage_path=path).run()
    out1, out2 = tmp_path / "out1", tmp_path / "out2"
    write_inventory_outputs(report, out1)
    write_inventory_outputs(report, out2)
    assert path.read_bytes() == original
    for name in ("policy_unit_inventory.json", "policy_unit_inventory.csv", "policy_unit_migration_manifest_candidate.json"):
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes()
