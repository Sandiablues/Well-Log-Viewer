"""Idempotent Managed-KR migration for V1 curve-family display defaults."""

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

DEFAULT_POLICY_PATH = Path(__file__).with_name("family_scale_defaults_v1.json")


@dataclass(frozen=True)
class MigrationChange:
    record_id: str
    curve_family: str
    before: dict[str, Any]
    after: dict[str, Any]


@dataclass(frozen=True)
class MigrationResult:
    dry_run: bool
    expected_family_count: int
    found_family_count: int
    changed_count: int
    unchanged_count: int
    changes: list[MigrationChange]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "changes": [asdict(item) for item in self.changes],
        }


class FamilyScaleDefaultMigrationError(RuntimeError):
    pass


class FamilyScaleDefaultMigrationService:
    """Apply governed family defaults through the canonical ManagedStorage owner."""

    def __init__(
        self,
        *,
        storage: ManagedStorage | None = None,
        policy_path: Path | None = None,
    ) -> None:
        self.storage = storage or ManagedStorage()
        self.policy_path = policy_path or DEFAULT_POLICY_PATH

    def _load_policy(self) -> dict[str, Any]:
        payload = json.loads(self.policy_path.read_text(encoding="utf-8"))
        families = payload.get("families")
        expected = payload.get("expected_family_count")
        if not isinstance(families, dict) or not isinstance(expected, int):
            raise FamilyScaleDefaultMigrationError("Invalid family-default policy document")
        if len(families) != expected:
            raise FamilyScaleDefaultMigrationError(
                f"Policy family count mismatch: expected {expected}, found {len(families)}"
            )
        self._validate_policy(families)
        return payload

    @staticmethod
    def _validate_policy(families: dict[str, Any]) -> None:
        allowed_types = {
            "linear", "log", "event_track", "waveform_track",
            "image_track", "tadpole_track",
        }
        for family, rule in families.items():
            if not family or not isinstance(rule, dict):
                raise FamilyScaleDefaultMigrationError(f"Invalid family rule: {family!r}")
            scale_type = rule.get("scale_type")
            if scale_type not in allowed_types:
                raise FamilyScaleDefaultMigrationError(
                    f"{family}: unsupported scale_type {scale_type!r}"
                )
            mn, mx = rule.get("scale_min"), rule.get("scale_max")
            allow_null = bool(rule.get("allow_null_range"))
            if (mn is None or mx is None) and not allow_null:
                raise FamilyScaleDefaultMigrationError(
                    f"{family}: numeric bounds are required"
                )
            if scale_type == "log":
                if mn is None or mx is None or mn <= 0 or mx <= 0 or mn >= mx:
                    raise FamilyScaleDefaultMigrationError(
                        f"{family}: logarithmic bounds must satisfy 0 < min < max"
                    )
            if mn is not None and not isinstance(mn, (int, float)):
                raise FamilyScaleDefaultMigrationError(f"{family}: scale_min must be numeric")
            if mx is not None and not isinstance(mx, (int, float)):
                raise FamilyScaleDefaultMigrationError(f"{family}: scale_max must be numeric")

    def run(self, *, dry_run: bool) -> MigrationResult:
        policy = self._load_policy()
        records, evidence = self.storage.load()

        by_family: dict[str, GenericManagedRecord] = {}
        duplicates: list[str] = []
        for record in records:
            if getattr(record, "record_type", None) != "template_scale_default":
                continue
            family = getattr(record, "curve_family", None)
            if family in by_family:
                duplicates.append(str(family))
            if family:
                by_family[str(family)] = record

        if duplicates:
            raise FamilyScaleDefaultMigrationError(
                f"Duplicate template_scale_default families: {sorted(set(duplicates))}"
            )

        expected_families = set(policy["families"])
        missing = sorted(expected_families - set(by_family))
        unexpected = sorted(set(by_family) - expected_families)
        if missing or unexpected:
            raise FamilyScaleDefaultMigrationError(
                f"Family inventory mismatch: missing={missing}, unexpected={unexpected}"
            )

        now = datetime.now(tz=timezone.utc)
        changes: list[MigrationChange] = []
        unchanged = 0

        for family in sorted(expected_families):
            record = by_family[family]
            if record.status is not GovernanceStatus.APPROVED:
                raise FamilyScaleDefaultMigrationError(
                    f"{family}: record must be approved, found {record.status.value}"
                )

            target = policy["families"][family]
            before = {
                "scale_min": getattr(record, "scale_min", None),
                "scale_max": getattr(record, "scale_max", None),
                "scale_type": getattr(record, "scale_type", None),
                "display_direction": getattr(record, "display_direction", None),
            }
            after = {
                "scale_min": target.get("scale_min"),
                "scale_max": target.get("scale_max"),
                "scale_type": target.get("scale_type"),
                "display_direction": target.get("display_direction"),
            }
            if before == after:
                unchanged += 1
                continue

            changes.append(
                MigrationChange(
                    record_id=record.record_id,
                    curve_family=family,
                    before=before,
                    after=after,
                )
            )
            if not dry_run:
                record.extra_fields.update(after)
                record.version += 1
                record.updated_at = now
                record.change_reason = (
                    "Normalize V1 Managed-KR curve-family display defaults."
                )
                record.governance_history.append(
                    {
                        "at": now.isoformat(),
                        "by": "wlv_kr_family_defaults_v1_migration",
                        "action": "normalize_family_scale_default",
                        "reason": (
                            "Establish Managed KR as the governed fallback source "
                            "for WDV curve-family display policy."
                        ),
                    }
                )

        if not dry_run and changes:
            self.storage.save(records, evidence)

        return MigrationResult(
            dry_run=dry_run,
            expected_family_count=int(policy["expected_family_count"]),
            found_family_count=len(by_family),
            changed_count=len(changes),
            unchanged_count=unchanged,
            changes=changes,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--storage-path", type=Path)
    parser.add_argument("--policy-path", type=Path, default=DEFAULT_POLICY_PATH)
    args = parser.parse_args()

    service = FamilyScaleDefaultMigrationService(
        storage=ManagedStorage(path=args.storage_path) if args.storage_path else None,
        policy_path=args.policy_path,
    )
    result = service.run(dry_run=not args.apply)
    print(json.dumps(result.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
