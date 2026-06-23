"""Validate governed policy-unit decisions without mutating live Managed Knowledge."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from app.knowledge.managed_storage import DEFAULT_STORAGE_PATH
from app.wdv_display.policy_unit_contract import WdvPolicyUnitContract

DECISION_SCHEMA_VERSION = "wlv-policy-unit-decisions-v1"
VALID_DECISION_STATUS = "approved_for_migration"
VALID_UNRESOLVED_STATUS = "requires_domain_review"


@dataclass(frozen=True)
class DecisionValidationResult:
    record_id: str
    status: str
    policy_value_unit: str | None
    reason: str


class PolicyUnitDecisionValidator:
    def __init__(self, *, storage_path: Path, decision_path: Path) -> None:
        self.storage_path = Path(storage_path)
        self.decision_path = Path(decision_path)

    def validate(self) -> dict[str, Any]:
        source_bytes = self.storage_path.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        source = json.loads(source_bytes.decode("utf-8"))
        manifest = json.loads(self.decision_path.read_text(encoding="utf-8"))

        if manifest.get("schema_version") != DECISION_SCHEMA_VERSION:
            raise ValueError("unsupported decision schema version")
        if manifest.get("source_kr_sha256") != source_sha256:
            raise ValueError("source KR hash does not match decision manifest")

        records = source.get("records")
        if not isinstance(records, list):
            raise ValueError("Managed Knowledge document must contain records")
        by_id = {str(r.get("record_id")): r for r in records if isinstance(r, dict)}

        results: list[DecisionValidationResult] = []
        seen: set[str] = set()
        for decision in manifest.get("decisions", []):
            result = self._validate_decision(decision, by_id, seen)
            results.append(result)
        for unresolved in manifest.get("unresolved", []):
            result = self._validate_unresolved(unresolved, by_id, seen)
            results.append(result)

        simulated = copy.deepcopy(source)
        simulated_by_id = {
            str(r.get("record_id")): r
            for r in simulated.get("records", [])
            if isinstance(r, dict)
        }
        for decision in manifest.get("decisions", []):
            simulated_by_id[decision["record_id"]]["policy_value_unit"] = decision[
                "policy_value_unit"
            ]

        simulated_bytes = (
            json.dumps(simulated, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        return {
            "schema_version": "wlv-policy-unit-decision-validation-v1",
            "source_kr_sha256": source_sha256,
            "decision_count": len(manifest.get("decisions", [])),
            "unresolved_count": len(manifest.get("unresolved", [])),
            "simulated_kr_sha256": hashlib.sha256(simulated_bytes).hexdigest(),
            "results": [asdict(item) for item in results],
            "simulated_document": simulated,
        }

    @staticmethod
    def _validate_common(entry: dict[str, Any], record: dict[str, Any]) -> None:
        checks = {
            "record_type": "expected_record_type",
            "curve_family": "expected_curve_family",
            "scale_type": "expected_scale_type",
            "scale_min": "expected_scale_min",
            "scale_max": "expected_scale_max",
            "policy_value_unit": "expected_policy_value_unit",
        }
        for actual_key, expected_key in checks.items():
            if record.get(actual_key) != entry.get(expected_key):
                raise ValueError(
                    f"{entry.get('record_id')}: {actual_key} changed; "
                    f"expected {entry.get(expected_key)!r}, got {record.get(actual_key)!r}"
                )
        if record.get("status") != "approved" or record.get("runtime_eligible") is not True:
            raise ValueError(f"{entry.get('record_id')}: record is not approved/runtime eligible")

    def _validate_decision(
        self, entry: dict[str, Any], by_id: dict[str, dict[str, Any]], seen: set[str]
    ) -> DecisionValidationResult:
        record_id = str(entry.get("record_id") or "")
        if not record_id or record_id in seen:
            raise ValueError(f"duplicate or blank decision record_id: {record_id!r}")
        seen.add(record_id)
        record = by_id.get(record_id)
        if record is None:
            raise ValueError(f"decision record not found: {record_id}")
        self._validate_common(entry, record)
        if entry.get("decision_status") != VALID_DECISION_STATUS:
            raise ValueError(f"{record_id}: decision status is not approved_for_migration")
        normalized = WdvPolicyUnitContract.normalize_unit(entry.get("policy_value_unit"))
        if normalized is None or normalized != entry.get("policy_value_unit"):
            raise ValueError(f"{record_id}: policy unit is not a canonical supported unit")
        return DecisionValidationResult(
            record_id=record_id,
            status="validated_decision",
            policy_value_unit=normalized,
            reason=str(entry.get("decision_basis") or ""),
        )

    def _validate_unresolved(
        self, entry: dict[str, Any], by_id: dict[str, dict[str, Any]], seen: set[str]
    ) -> DecisionValidationResult:
        record_id = str(entry.get("record_id") or "")
        if not record_id or record_id in seen:
            raise ValueError(f"duplicate or blank unresolved record_id: {record_id!r}")
        seen.add(record_id)
        record = by_id.get(record_id)
        if record is None:
            raise ValueError(f"unresolved record not found: {record_id}")
        self._validate_common(entry, record)
        if entry.get("decision_status") != VALID_UNRESOLVED_STATUS:
            raise ValueError(f"{record_id}: unresolved status is invalid")
        return DecisionValidationResult(
            record_id=record_id,
            status="validated_unresolved",
            policy_value_unit=None,
            reason=str(entry.get("reason") or ""),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-path", type=Path, default=DEFAULT_STORAGE_PATH)
    parser.add_argument("--decision-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    result = PolicyUnitDecisionValidator(
        storage_path=args.storage_path,
        decision_path=args.decision_path,
    ).validate()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    simulated = result.pop("simulated_document")
    (args.output_dir / "policy_unit_decision_validation.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "managed_knowledge_simulated.json").write_text(
        json.dumps(simulated, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
