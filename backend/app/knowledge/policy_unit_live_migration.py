"""Guarded live migration for WDV policy-value units.

UNIT-2D is the only block in the C2 sequence permitted to modify the live
Managed Knowledge document.  It regenerates the committed 28-entry manifest,
rechecks every optimistic-concurrency guard immediately before mutation,
creates an exact-byte backup, performs one atomic replacement, and validates
post-write inventory counts.  Strict runtime unit enforcement remains disabled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.knowledge.managed_storage import DEFAULT_STORAGE_PATH
from app.knowledge.policy_unit_inventory import (
    PolicyUnitInventoryService,
    PolicyUnitInventoryStatus,
)
from app.knowledge.policy_unit_migration_preparation import (
    PolicyUnitMigrationPreparationService,
)

LIVE_MIGRATION_SCHEMA_VERSION = "wlv-policy-unit-live-migration-v1"
MIGRATION_ACTOR = "wlv_policy_unit_live_migration_v1"
MIGRATION_ACTION = "add_policy_value_unit"
EXPECTED_ENTRY_COUNT = 28
EXPECTED_UNRESOLVED_ID = "wlv_approved_kr_refs_1_scale_default_spinner_flow"
EXPECTED_POST_COUNTS = {
    PolicyUnitInventoryStatus.EXPLICIT_SUPPORTED.value: 28,
    PolicyUnitInventoryStatus.EXPLICIT_UNKNOWN_UNIT.value: 0,
    PolicyUnitInventoryStatus.INFERABLE_SUPPORTED.value: 0,
    PolicyUnitInventoryStatus.AMBIGUOUS_REVIEW_REQUIRED.value: 1,
    PolicyUnitInventoryStatus.NON_NUMERIC_OR_NON_LINE.value: 5,
}


class PolicyUnitLiveMigrationError(RuntimeError):
    """Raised when any guarded migration precondition or validation fails."""


@dataclass(frozen=True)
class AppliedPolicyUnitChange:
    record_id: str
    before_version: int
    after_version: int
    before_policy_value_unit: str | None
    after_policy_value_unit: str
    source_kind: str
    evidence_source: str


class PolicyUnitLiveMigrationService:
    """Apply the committed guarded migration to one Managed Knowledge file."""

    def __init__(
        self,
        *,
        storage_path: Path,
        decision_path: Path,
        backup_path: Path,
    ) -> None:
        self.storage_path = Path(storage_path)
        self.decision_path = Path(decision_path)
        self.backup_path = Path(backup_path)

    @staticmethod
    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def apply(self) -> dict[str, Any]:
        if not self.storage_path.is_file():
            raise PolicyUnitLiveMigrationError(
                f"Managed Knowledge file not found: {self.storage_path}"
            )
        if self.backup_path.exists():
            raise PolicyUnitLiveMigrationError(
                f"Backup path already exists: {self.backup_path}"
            )

        source_bytes = self.storage_path.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()

        preparation = PolicyUnitMigrationPreparationService(
            storage_path=self.storage_path,
            decision_path=self.decision_path,
        ).prepare()
        manifest = preparation["manifest"]
        self._validate_manifest(manifest=manifest, source_sha256=source_sha256)

        document = json.loads(source_bytes.decode("utf-8"))
        records = document.get("records")
        if not isinstance(records, list):
            raise PolicyUnitLiveMigrationError(
                "Managed Knowledge document does not contain a records list"
            )
        by_id = {
            str(record.get("record_id")): record
            for record in records
            if isinstance(record, dict) and record.get("record_id")
        }

        now = datetime.now(tz=timezone.utc).isoformat()
        changes: list[AppliedPolicyUnitChange] = []

        for entry in manifest["entries"]:
            record_id = str(entry["record_id"])
            record = by_id.get(record_id)
            if record is None:
                raise PolicyUnitLiveMigrationError(
                    f"Manifest record missing immediately before write: {record_id}"
                )
            if record.get("record_type") != entry["record_type"]:
                raise PolicyUnitLiveMigrationError(
                    f"{record_id}: record_type changed immediately before write"
                )
            if record.get("version") != entry["expected_record_version"]:
                raise PolicyUnitLiveMigrationError(
                    f"{record_id}: version changed immediately before write"
                )
            if record.get("policy_value_unit") != entry[
                "expected_current_policy_value_unit"
            ]:
                raise PolicyUnitLiveMigrationError(
                    f"{record_id}: current policy_value_unit changed immediately before write"
                )
            if record.get("status") != "approved" or record.get("runtime_eligible") is not True:
                raise PolicyUnitLiveMigrationError(
                    f"{record_id}: governance eligibility changed immediately before write"
                )

            before_version = int(record["version"])
            record["policy_value_unit"] = entry["proposed_policy_value_unit"]
            record["version"] = before_version + 1
            record["updated_at"] = now
            record["change_reason"] = entry["evidence_reason"]
            history = record.get("governance_history")
            if history is None:
                history = []
                record["governance_history"] = history
            if not isinstance(history, list):
                raise PolicyUnitLiveMigrationError(
                    f"{record_id}: governance_history is not a list"
                )
            history.append(
                {
                    "at": now,
                    "by": MIGRATION_ACTOR,
                    "action": MIGRATION_ACTION,
                    "reason": entry["evidence_reason"],
                    "source_kind": entry["source_kind"],
                    "evidence_source": entry["evidence_source"],
                    "evidence_raw_value": entry["evidence_raw_value"],
                    "source_kr_sha256": source_sha256,
                }
            )
            changes.append(
                AppliedPolicyUnitChange(
                    record_id=record_id,
                    before_version=before_version,
                    after_version=before_version + 1,
                    before_policy_value_unit=None,
                    after_policy_value_unit=entry["proposed_policy_value_unit"],
                    source_kind=entry["source_kind"],
                    evidence_source=entry["evidence_source"],
                )
            )

        spinner = by_id.get(EXPECTED_UNRESOLVED_ID)
        if spinner is None or spinner.get("policy_value_unit") is not None:
            raise PolicyUnitLiveMigrationError(
                "Spinner-flow unresolved record was changed or is missing"
            )

        document["updated_at"] = now
        encoded = (json.dumps(document, indent=2) + "\n").encode("utf-8")

        self.backup_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_path.write_bytes(source_bytes)
        self._atomic_replace(encoded)

        try:
            post_report = PolicyUnitInventoryService(storage_path=self.storage_path).run()
            if post_report.status_counts != EXPECTED_POST_COUNTS:
                raise PolicyUnitLiveMigrationError(
                    "Post-migration inventory counts are invalid: "
                    f"expected {EXPECTED_POST_COUNTS}, got {post_report.status_counts}"
                )
            unresolved_ids = sorted(
                entry.record_id
                for entry in post_report.entries
                if entry.status
                == PolicyUnitInventoryStatus.AMBIGUOUS_REVIEW_REQUIRED.value
            )
            if unresolved_ids != [EXPECTED_UNRESOLVED_ID]:
                raise PolicyUnitLiveMigrationError(
                    f"Unexpected unresolved records after migration: {unresolved_ids}"
                )
        except Exception:
            self.restore_backup()
            raise

        return {
            "schema_version": LIVE_MIGRATION_SCHEMA_VERSION,
            "source_kr_sha256": source_sha256,
            "migrated_kr_sha256": self.sha256(self.storage_path),
            "backup_path": str(self.backup_path),
            "entry_count": len(changes),
            "unresolved_record_ids": [EXPECTED_UNRESOLVED_ID],
            "inventory_status_counts_after": dict(sorted(post_report.status_counts.items())),
            "changes": [asdict(change) for change in changes],
        }

    def restore_backup(self) -> None:
        if not self.backup_path.is_file():
            raise PolicyUnitLiveMigrationError(
                f"Migration backup not found: {self.backup_path}"
            )
        backup_bytes = self.backup_path.read_bytes()
        self._atomic_replace(backup_bytes)

    def _atomic_replace(self, payload: bytes) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.storage_path.name}.",
            suffix=".tmp",
            dir=str(self.storage_path.parent),
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.storage_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @staticmethod
    def _validate_manifest(*, manifest: dict[str, Any], source_sha256: str) -> None:
        if manifest.get("source_kr_sha256") != source_sha256:
            raise PolicyUnitLiveMigrationError(
                "Prepared manifest source hash does not match live KR"
            )
        entries = manifest.get("entries")
        if not isinstance(entries, list) or len(entries) != EXPECTED_ENTRY_COUNT:
            raise PolicyUnitLiveMigrationError(
                f"Expected exactly {EXPECTED_ENTRY_COUNT} migration entries"
            )
        if manifest.get("entry_count") != EXPECTED_ENTRY_COUNT:
            raise PolicyUnitLiveMigrationError("Manifest entry_count is invalid")
        if manifest.get("unresolved_record_ids") != [EXPECTED_UNRESOLVED_ID]:
            raise PolicyUnitLiveMigrationError(
                "Manifest unresolved record contract is invalid"
            )
        ids = [str(entry.get("record_id") or "") for entry in entries]
        if len(set(ids)) != EXPECTED_ENTRY_COUNT or any(not item for item in ids):
            raise PolicyUnitLiveMigrationError(
                "Manifest contains duplicate or blank record IDs"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-path", type=Path, default=DEFAULT_STORAGE_PATH)
    parser.add_argument("--decision-path", type=Path, required=True)
    parser.add_argument("--backup-path", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, required=True)
    args = parser.parse_args()

    service = PolicyUnitLiveMigrationService(
        storage_path=args.storage_path,
        decision_path=args.decision_path,
        backup_path=args.backup_path,
    )
    result = service.apply()
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
