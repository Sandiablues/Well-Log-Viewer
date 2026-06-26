from __future__ import annotations

import json
from pathlib import Path

from app.knowledge.family_scale_default_migration import (
    FamilyScaleDefaultMigrationService,
)
from app.knowledge.managed_storage import ManagedStorage


def _copy_kr(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[2] / "data" / "knowledge" / "managed_knowledge.json"
    target = tmp_path / "managed_knowledge.json"
    payload = json.loads(source.read_text())

    # Build a deterministic pre-migration fixture. The production KR may
    # already have the migration applied, so this test must not depend on the
    # live repository's current migration state.
    before = {
        "bit_size": (None, None, "linear", "normal"),
        "caliper": (None, None, "linear", "normal"),
        "permeability": (None, None, "log", "normal"),
        "pressure": (None, None, "linear", "normal"),
        "resistivity": (0.2, 200, "log", "normal"),
        "sonic_slowness": (40, 140, "linear", "normal"),
        "spinner_flow": (None, None, "linear", "centered_optional"),
        "spontaneous_potential": (None, None, "linear", "reversible"),
        "temperature": (None, None, "linear", "normal"),
    }
    for record in payload["records"]:
        if record.get("record_type") != "template_scale_default":
            continue
        family = record.get("curve_family")
        if family not in before:
            continue
        mn, mx, scale_type, direction = before[family]
        record["scale_min"] = mn
        record["scale_max"] = mx
        record["scale_type"] = scale_type
        record["display_direction"] = direction

    target.write_text(json.dumps(payload, indent=2) + "\n")
    return target


def test_family_default_migration_is_idempotent(tmp_path: Path) -> None:
    target = _copy_kr(tmp_path)
    service = FamilyScaleDefaultMigrationService(storage=ManagedStorage(path=target))

    preview = service.run(dry_run=True)
    assert preview.expected_family_count == 22
    assert preview.found_family_count == 22
    assert preview.changed_count == 9

    applied = service.run(dry_run=False)
    assert applied.changed_count == 9

    second = service.run(dry_run=False)
    assert second.changed_count == 0
    assert second.unchanged_count == 22

    payload = json.loads(target.read_text())
    records = {
        record["curve_family"]: record
        for record in payload["records"]
        if record.get("record_type") == "template_scale_default"
    }
    assert records["resistivity"]["scale_min"] == 0.2
    assert records["resistivity"]["scale_max"] == 2000
    assert records["resistivity"]["scale_type"] == "log"
    assert records["sonic_slowness"]["display_direction"] == "reversed"
    assert records["spontaneous_potential"]["scale_min"] == -100
    assert records["spontaneous_potential"]["scale_max"] == 100
