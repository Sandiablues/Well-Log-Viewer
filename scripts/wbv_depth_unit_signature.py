#!/usr/bin/env python3
"""WBV depth-unit regression signature helper.

Foundation version: records and compares machine-readable invariant signatures.
It does NOT modify WBV and does not attempt to drive the browser.

The runtime capture object should be exported by a future browser harness with
the contract documented below. This utility verifies that a unit switch changes
only explicitly allowed presentation fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ALLOWED_UNIT_SWITCH_PATHS = {
    "display_unit",
    "presentation.depth_unit",
}

REQUIRED_TOP_LEVEL = {
    "displayed_well_ids",
    "active_well_id",
    "trajectory_point_counts",
    "trajectory_geometry_hashes",
    "canonical_md_hashes",
    "layer_counts",
    "camera",
    "rotation_center",
    "selection",
    "saved_interval",
    "display_unit",
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def validate_signature(sig: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_TOP_LEVEL - set(sig))
    if missing:
        errors.append("missing required fields: " + ", ".join(missing))
    if sig.get("display_unit") not in {"m", "ft"}:
        errors.append("display_unit must be 'm' or 'ft'")
    return errors


def without_allowed(sig: dict[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(sig))
    clone.pop("display_unit", None)
    if isinstance(clone.get("presentation"), dict):
        clone["presentation"].pop("depth_unit", None)
    return clone


def compare(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    before_errors = validate_signature(before)
    after_errors = validate_signature(after)
    if before_errors or after_errors:
        return False, {"before_errors": before_errors, "after_errors": after_errors}

    b = without_allowed(before)
    a = without_allowed(after)
    same = canonical_json(b) == canonical_json(a)
    return same, {
        "before_unit": before.get("display_unit"),
        "after_unit": after.get("display_unit"),
        "before_invariant_hash": stable_hash(b),
        "after_invariant_hash": stable_hash(a),
        "invariants_equal": same,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("signature")

    p_compare = sub.add_parser("compare")
    p_compare.add_argument("before")
    p_compare.add_argument("after")

    args = parser.parse_args()

    if args.cmd == "validate":
        sig = json.loads(Path(args.signature).read_text())
        errors = validate_signature(sig)
        if errors:
            print("FAIL")
            for item in errors:
                print("-", item)
            return 1
        print("PASS signature contract")
        print("Invariant hash:", stable_hash(without_allowed(sig)))
        return 0

    before = json.loads(Path(args.before).read_text())
    after = json.loads(Path(args.after).read_text())
    ok, report = compare(before, after)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
