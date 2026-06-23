from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.knowledge.policy_unit_decision_validator import PolicyUnitDecisionValidator


def _record(record_id: str, family: str, lo: float, hi: float) -> dict:
    return {
        "record_id": record_id,
        "record_type": "template_scale_default",
        "status": "approved",
        "runtime_eligible": True,
        "curve_family": family,
        "scale_type": "linear",
        "scale_min": lo,
        "scale_max": hi,
    }


def _write_source(path: Path) -> str:
    doc = {"records": [_record("r1", "porosity", 0.0, 0.45), _record("r2", "spinner_flow", -100.0, 100.0)]}
    raw = json.dumps(doc, sort_keys=True).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _write_manifest(path: Path, source_hash: str) -> None:
    path.write_text(json.dumps({
        "schema_version": "wlv-policy-unit-decisions-v1",
        "source_kr_sha256": source_hash,
        "decisions": [{
            "record_id": "r1", "expected_record_type": "template_scale_default",
            "expected_curve_family": "porosity", "expected_scale_type": "linear",
            "expected_scale_min": 0.0, "expected_scale_max": 0.45,
            "expected_policy_value_unit": None, "policy_value_unit": "v/v",
            "decision_basis": "fractional bounds", "decision_status": "approved_for_migration"
        }],
        "unresolved": [{
            "record_id": "r2", "expected_record_type": "template_scale_default",
            "expected_curve_family": "spinner_flow", "expected_scale_type": "linear",
            "expected_scale_min": -100.0, "expected_scale_max": 100.0,
            "expected_policy_value_unit": None, "reason": "quantity unknown",
            "decision_status": "requires_domain_review"
        }]
    }))


def test_validator_is_read_only_and_simulates_decisions(tmp_path: Path) -> None:
    source = tmp_path / "kr.json"
    manifest = tmp_path / "decisions.json"
    source_hash = _write_source(source)
    _write_manifest(manifest, source_hash)
    before = source.read_bytes()
    result = PolicyUnitDecisionValidator(storage_path=source, decision_path=manifest).validate()
    assert source.read_bytes() == before
    assert result["decision_count"] == 1
    assert result["unresolved_count"] == 1
    records = {r["record_id"]: r for r in result["simulated_document"]["records"]}
    assert records["r1"]["policy_value_unit"] == "v/v"
    assert "policy_value_unit" not in records["r2"]


def test_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "kr.json"; manifest = tmp_path / "decisions.json"
    _write_source(source); _write_manifest(manifest, "0" * 64)
    with pytest.raises(ValueError, match="source KR hash"):
        PolicyUnitDecisionValidator(storage_path=source, decision_path=manifest).validate()


def test_changed_record_contract_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "kr.json"; manifest = tmp_path / "decisions.json"
    source_hash = _write_source(source); _write_manifest(manifest, source_hash)
    doc = json.loads(source.read_text()); doc["records"][0]["scale_max"] = 0.5
    raw = json.dumps(doc, sort_keys=True).encode(); source.write_bytes(raw)
    m = json.loads(manifest.read_text()); m["source_kr_sha256"] = hashlib.sha256(raw).hexdigest(); manifest.write_text(json.dumps(m))
    with pytest.raises(ValueError, match="scale_max changed"):
        PolicyUnitDecisionValidator(storage_path=source, decision_path=manifest).validate()


def test_noncanonical_or_unknown_unit_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "kr.json"; manifest = tmp_path / "decisions.json"
    source_hash = _write_source(source); _write_manifest(manifest, source_hash)
    m = json.loads(manifest.read_text()); m["decisions"][0]["policy_value_unit"] = "fraction"
    manifest.write_text(json.dumps(m))
    with pytest.raises(ValueError, match="canonical supported unit"):
        PolicyUnitDecisionValidator(storage_path=source, decision_path=manifest).validate()


def test_unresolved_record_is_not_assigned_a_unit(tmp_path: Path) -> None:
    source = tmp_path / "kr.json"; manifest = tmp_path / "decisions.json"
    source_hash = _write_source(source); _write_manifest(manifest, source_hash)
    result = PolicyUnitDecisionValidator(storage_path=source, decision_path=manifest).validate()
    unresolved = [r for r in result["results"] if r["status"] == "validated_unresolved"]
    assert unresolved == [{"record_id": "r2", "status": "validated_unresolved", "policy_value_unit": None, "reason": "quantity unknown"}]
