"""Idempotent Managed-KR migration: add policy_value_unit to template_scale_default records.

Adds a ``policy_value_unit`` extra-field to every governed
``template_scale_default`` record whose display-scale values are expressed in
a specific physical unit.  This field is required by the unit-aware display-
policy resolver so that KR-sourced scale bounds can be converted to whatever
unit the incoming curve carries.

The migration is idempotent: re-running when ``policy_value_unit`` is already
set leaves the record unchanged.

Usage::

    # Dry-run (no changes written)
    python -m app.knowledge.policy_value_unit_migration

    # Apply changes to the default managed_knowledge.json
    python -m app.knowledge.policy_value_unit_migration --apply

    # Apply against a custom storage path (for tests)
    python -m app.knowledge.policy_value_unit_migration --apply \\
        --storage-path /tmp/test_kr.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .governance import GovernanceStatus
from .managed_models import GenericManagedRecord
from .managed_storage import ManagedStorage


# ---------------------------------------------------------------------------
# Migration table
# ---------------------------------------------------------------------------

# Each entry declares the policy_value_unit that should be stored on the
# corresponding template_scale_default record.  Only records that are
# *approved* and whose extra_fields don't already carry the target value
# will be modified.

_POLICY_UNIT_MIGRATIONS: list[dict[str, str]] = [
    {
        "record_id": "wlv_approved_kr_refs_1_scale_default_neutron_porosity",
        "policy_value_unit": "%",
        "reason": (
            "Neutron porosity scale policy values (45 to -15) are expressed in "
            "percent (p.u.).  Adding policy_value_unit enables the WDV display-"
            "policy resolver to convert these bounds when curves arrive in v/v."
        ),
    },
]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyUnitMigrationChange:
    record_id: str
    curve_family: str
    before: dict[str, Any]
    after: dict[str, Any]


@dataclass(frozen=True)
class PolicyUnitMigrationResult:
    dry_run: bool
    changed_count: int
    unchanged_count: int
    not_found_count: int
    changes: list[PolicyUnitMigrationChange]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "changes": [asdict(c) for c in self.changes],
        }


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PolicyUnitMigrationError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PolicyValueUnitMigrationService:
    """Apply policy_value_unit fields through the canonical ManagedStorage owner.

    Follows the same mutation pattern as ``FamilyScaleDefaultMigrationService``:
    load → mutate extra_fields in-process → save atomically.  Never edits
    managed_knowledge.json directly.
    """

    def __init__(self, *, storage: ManagedStorage | None = None) -> None:
        self.storage = storage or ManagedStorage()

    def run(self, *, dry_run: bool) -> PolicyUnitMigrationResult:
        records, evidence = self.storage.load()

        # Index template_scale_default records by record_id.
        by_id: dict[str, GenericManagedRecord] = {}
        for record in records:
            if getattr(record, "record_type", None) != "template_scale_default":
                continue
            rid = getattr(record, "record_id", None)
            if rid:
                by_id[str(rid)] = record  # type: ignore[assignment]

        now = datetime.now(tz=timezone.utc)
        changes: list[PolicyUnitMigrationChange] = []
        unchanged = 0
        not_found = 0

        for migration in _POLICY_UNIT_MIGRATIONS:
            record_id = migration["record_id"]
            target_unit = migration["policy_value_unit"]
            reason = migration["reason"]

            record = by_id.get(record_id)
            if record is None:
                not_found += 1
                continue

            if record.status is not GovernanceStatus.APPROVED:
                raise PolicyUnitMigrationError(
                    f"Record {record_id!r} must be APPROVED before migration; "
                    f"found status={record.status.value!r}."
                )

            current_unit = getattr(record, "policy_value_unit", None)
            if current_unit == target_unit:
                unchanged += 1
                continue

            changes.append(
                PolicyUnitMigrationChange(
                    record_id=record_id,
                    curve_family=str(getattr(record, "curve_family", "") or ""),
                    before={"policy_value_unit": current_unit},
                    after={"policy_value_unit": target_unit},
                )
            )

            if not dry_run:
                record.extra_fields["policy_value_unit"] = target_unit
                record.version += 1
                record.updated_at = now
                record.change_reason = reason
                record.governance_history.append(
                    {
                        "at": now.isoformat(),
                        "by": "wlv_policy_value_unit_migration",
                        "action": "add_policy_value_unit",
                        "reason": reason,
                    }
                )

        if not dry_run and changes:
            self.storage.save(records, evidence)

        return PolicyUnitMigrationResult(
            dry_run=dry_run,
            changed_count=len(changes),
            unchanged_count=unchanged,
            not_found_count=not_found,
            changes=changes,
        )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add policy_value_unit to governed template_scale_default records.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to storage (default: dry-run only).",
    )
    parser.add_argument(
        "--storage-path",
        type=Path,
        default=None,
        metavar="PATH",
        help="Override the default managed_knowledge.json path.",
    )
    args = parser.parse_args()

    storage = ManagedStorage(path=args.storage_path) if args.storage_path else None
    service = PolicyValueUnitMigrationService(storage=storage)
    result = service.run(dry_run=not args.apply)
    print(json.dumps(result.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
