"""Prepare a guarded WDV policy-unit migration without changing live knowledge.

UNIT-2C combines deterministic UNIT-2 inventory candidates with approved UNIT-2B
policy decisions.  It emits a complete migration manifest, applies that manifest
only to an in-memory/copy document, and reruns the inventory against the copied
KR.  The live Managed Knowledge file is never written.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.knowledge.managed_storage import DEFAULT_STORAGE_PATH
from app.knowledge.policy_unit_decision_validator import PolicyUnitDecisionValidator
from app.knowledge.policy_unit_inventory import (
    PolicyUnitInventoryService,
    PolicyUnitInventoryStatus,
)
from app.wdv_display.policy_unit_contract import WdvPolicyUnitContract

MIGRATION_PREPARATION_SCHEMA_VERSION = "wlv-policy-unit-migration-preparation-v1"
MIGRATION_MANIFEST_SCHEMA_VERSION = "wlv-policy-unit-migration-manifest-v1"
SIMULATION_SCHEMA_VERSION = "wlv-policy-unit-migration-simulation-v1"


@dataclass(frozen=True)
class PreparedPolicyUnitUpdate:
    record_id: str
    record_type: str
    expected_record_version: int
    expected_current_policy_value_unit: str | None
    proposed_policy_value_unit: str
    evidence_source: str
    evidence_raw_value: str | None
    evidence_reason: str
    source_kind: str


class PolicyUnitMigrationPreparationService:
    """Build and simulate a guarded migration manifest from committed contracts."""

    def __init__(
        self,
        *,
        storage_path: Path,
        decision_path: Path,
    ) -> None:
        self.storage_path = Path(storage_path)
        self.decision_path = Path(decision_path)

    def prepare(self) -> dict[str, Any]:
        source_bytes = self.storage_path.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        source_document = json.loads(source_bytes.decode("utf-8"))
        records = source_document.get("records")
        if not isinstance(records, list):
            raise ValueError("Managed Knowledge document must contain a records list")
        by_id = {
            str(record.get("record_id")): record
            for record in records
            if isinstance(record, dict) and record.get("record_id")
        }

        inventory = PolicyUnitInventoryService(storage_path=self.storage_path).run()
        decision_validation = PolicyUnitDecisionValidator(
            storage_path=self.storage_path,
            decision_path=self.decision_path,
        ).validate()
        decision_manifest = json.loads(self.decision_path.read_text(encoding="utf-8"))

        if inventory.source_sha256 != source_sha256:
            raise ValueError("inventory source hash changed during preparation")
        if decision_validation["source_kr_sha256"] != source_sha256:
            raise ValueError("decision validation source hash does not match inventory")

        updates: list[PreparedPolicyUnitUpdate] = []
        seen: set[str] = set()

        for entry in inventory.entries:
            if entry.status != PolicyUnitInventoryStatus.INFERABLE_SUPPORTED.value:
                continue
            proposed = entry.proposed_policy_value_unit
            if proposed is None:
                raise ValueError(f"{entry.record_id}: inferred candidate lacks proposed unit")
            updates.append(
                self._build_update(
                    record=by_id.get(entry.record_id),
                    record_id=entry.record_id,
                    proposed_unit=proposed,
                    evidence_source=str(entry.evidence_source or ""),
                    evidence_raw_value=entry.evidence_raw_value,
                    evidence_reason=entry.reason,
                    source_kind="deterministic_inventory",
                    seen=seen,
                )
            )

        for decision in decision_manifest.get("decisions", []):
            record_id = str(decision.get("record_id") or "")
            proposed = str(decision.get("policy_value_unit") or "")
            updates.append(
                self._build_update(
                    record=by_id.get(record_id),
                    record_id=record_id,
                    proposed_unit=proposed,
                    evidence_source="policy_unit_decisions_v1.decision_basis",
                    evidence_raw_value=decision.get("decision_basis"),
                    evidence_reason=str(decision.get("decision_basis") or ""),
                    source_kind="governed_decision",
                    seen=seen,
                )
            )

        updates.sort(key=lambda item: item.record_id)
        unresolved_ids = sorted(
            str(item.get("record_id") or "")
            for item in decision_manifest.get("unresolved", [])
        )
        if any(record_id in seen for record_id in unresolved_ids):
            raise ValueError("unresolved records must not be included in migration updates")

        manifest = {
            "schema_version": MIGRATION_MANIFEST_SCHEMA_VERSION,
            "source_kr_sha256": source_sha256,
            "entry_count": len(updates),
            "unresolved_record_ids": unresolved_ids,
            "entries": [asdict(update) for update in updates],
        }
        simulated_document = self._simulate(source_document, manifest)
        simulation = self._validate_simulated_document(
            simulated_document=simulated_document,
            source_sha256=source_sha256,
            manifest=manifest,
            unresolved_ids=unresolved_ids,
        )

        return {
            "schema_version": MIGRATION_PREPARATION_SCHEMA_VERSION,
            "source_kr_sha256": source_sha256,
            "inventory_status_counts_before": dict(sorted(inventory.status_counts.items())),
            "manifest": manifest,
            "simulation": simulation,
            "simulated_document": simulated_document,
        }

    @staticmethod
    def _build_update(
        *,
        record: dict[str, Any] | None,
        record_id: str,
        proposed_unit: str,
        evidence_source: str,
        evidence_raw_value: Any,
        evidence_reason: str,
        source_kind: str,
        seen: set[str],
    ) -> PreparedPolicyUnitUpdate:
        if not record_id or record_id in seen:
            raise ValueError(f"duplicate or blank migration record_id: {record_id!r}")
        seen.add(record_id)
        if record is None:
            raise ValueError(f"migration record not found: {record_id}")
        if record.get("status") != "approved" or record.get("runtime_eligible") is not True:
            raise ValueError(f"{record_id}: record is not approved/runtime eligible")
        if record.get("policy_value_unit") is not None:
            raise ValueError(f"{record_id}: policy_value_unit is no longer absent")
        normalized = WdvPolicyUnitContract.normalize_unit(proposed_unit)
        if normalized is None or normalized != proposed_unit:
            raise ValueError(f"{record_id}: proposed unit is not canonical and supported")
        raw_version = record.get("version")
        if isinstance(raw_version, bool) or not isinstance(raw_version, int):
            raise ValueError(f"{record_id}: record version is not an integer")
        return PreparedPolicyUnitUpdate(
            record_id=record_id,
            record_type=str(record.get("record_type") or ""),
            expected_record_version=raw_version,
            expected_current_policy_value_unit=None,
            proposed_policy_value_unit=normalized,
            evidence_source=evidence_source,
            evidence_raw_value=(
                None if evidence_raw_value is None else str(evidence_raw_value)
            ),
            evidence_reason=evidence_reason,
            source_kind=source_kind,
        )

    @staticmethod
    def _simulate(
        source_document: dict[str, Any], manifest: dict[str, Any]
    ) -> dict[str, Any]:
        simulated = copy.deepcopy(source_document)
        records = simulated.get("records")
        if not isinstance(records, list):
            raise ValueError("simulated document lacks records list")
        by_id = {
            str(record.get("record_id")): record
            for record in records
            if isinstance(record, dict) and record.get("record_id")
        }
        for entry in manifest["entries"]:
            record_id = entry["record_id"]
            record = by_id.get(record_id)
            if record is None:
                raise ValueError(f"simulation record not found: {record_id}")
            if record.get("version") != entry["expected_record_version"]:
                raise ValueError(f"{record_id}: version changed before simulation")
            if record.get("policy_value_unit") != entry["expected_current_policy_value_unit"]:
                raise ValueError(f"{record_id}: current policy unit changed before simulation")
            record["policy_value_unit"] = entry["proposed_policy_value_unit"]
            record["version"] = entry["expected_record_version"] + 1
        return simulated

    @staticmethod
    def _validate_simulated_document(
        *,
        simulated_document: dict[str, Any],
        source_sha256: str,
        manifest: dict[str, Any],
        unresolved_ids: list[str],
    ) -> dict[str, Any]:
        encoded = (json.dumps(simulated_document, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        with tempfile.TemporaryDirectory(prefix="wlv_policy_unit_sim_") as temp_dir:
            simulated_path = Path(temp_dir) / "managed_knowledge_simulated.json"
            simulated_path.write_bytes(encoded)
            report = PolicyUnitInventoryService(storage_path=simulated_path).run()

        expected_counts = {
            PolicyUnitInventoryStatus.EXPLICIT_SUPPORTED.value: 28,
            PolicyUnitInventoryStatus.EXPLICIT_UNKNOWN_UNIT.value: 0,
            PolicyUnitInventoryStatus.INFERABLE_SUPPORTED.value: 0,
            PolicyUnitInventoryStatus.AMBIGUOUS_REVIEW_REQUIRED.value: 1,
            PolicyUnitInventoryStatus.NON_NUMERIC_OR_NON_LINE.value: 5,
        }
        if report.status_counts != expected_counts:
            raise ValueError(
                "simulated inventory counts do not match activation prerequisites: "
                f"expected {expected_counts}, got {report.status_counts}"
            )
        ambiguous_ids = sorted(
            entry.record_id
            for entry in report.entries
            if entry.status
            == PolicyUnitInventoryStatus.AMBIGUOUS_REVIEW_REQUIRED.value
        )
        if ambiguous_ids != unresolved_ids:
            raise ValueError(
                f"simulated unresolved IDs changed: expected {unresolved_ids}, got {ambiguous_ids}"
            )
        if manifest["entry_count"] != 28:
            raise ValueError(f"migration manifest must contain 28 updates, got {manifest['entry_count']}")
        return {
            "schema_version": SIMULATION_SCHEMA_VERSION,
            "source_kr_sha256": source_sha256,
            "simulated_kr_sha256": hashlib.sha256(encoded).hexdigest(),
            "manifest_entry_count": manifest["entry_count"],
            "inventory_status_counts_after": dict(sorted(report.status_counts.items())),
            "unresolved_record_ids": ambiguous_ids,
        }


def write_preparation_outputs(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    serializable = dict(result)
    simulated_document = serializable.pop("simulated_document")
    (output_dir / "policy_unit_migration_preparation.json").write_text(
        json.dumps(serializable, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "policy_unit_migration_manifest.json").write_text(
        json.dumps(serializable["manifest"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "managed_knowledge_simulated.json").write_text(
        json.dumps(simulated_document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-path", type=Path, default=DEFAULT_STORAGE_PATH)
    parser.add_argument("--decision-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    result = PolicyUnitMigrationPreparationService(
        storage_path=args.storage_path,
        decision_path=args.decision_path,
    ).prepare()
    write_preparation_outputs(result, args.output_dir)
    summary = dict(result)
    summary.pop("simulated_document", None)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
