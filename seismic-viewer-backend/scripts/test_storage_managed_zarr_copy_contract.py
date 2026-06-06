#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

BASE_URL = "http://127.0.0.1:8000"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def request_json(path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{method} {path} failed: HTTP {exc.code}: {body}") from exc

    return json.loads(raw)


def print_summary(label: str, payload: dict[str, Any]) -> None:
    summary = {
        "ok": payload.get("ok"),
        "service": payload.get("service"),
        "operation": payload.get("operation"),
        "mode": payload.get("mode"),
        "eligible_count": payload.get("eligible_count"),
        "copied_count": payload.get("copied_count"),
        "skipped_count": payload.get("skipped_count"),
        "failed_count": payload.get("failed_count"),
        "ignored_count": payload.get("ignored_count"),
        "copy_or_move_performed": payload.get("copy_or_move_performed"),
        "move_performed": payload.get("move_performed"),
        "delete_performed": payload.get("delete_performed"),
        "msi_rewrite_performed": payload.get("msi_rewrite_performed"),
        "manifest_uri": payload.get("manifest_uri"),
        "resolved_by": payload.get("resolved_by"),
    }
    print(f"\n---- {label} ----")
    print(json.dumps(summary, indent=2))


def main() -> int:
    print("---- storage managed Zarr copy contract ----")

    dry_run = request_json("/api/storage/migration/execute-managed-zarr-copy", method="POST", payload={"execute": False})
    print_summary("dry run", dry_run)

    require(dry_run.get("ok") is True, "Dry run ok != true")
    require(dry_run.get("mode") == "dry_run", "Dry run mode mismatch")
    require(dry_run.get("eligible_count", 0) >= 1, "Expected at least one managed Zarr copy candidate")
    require(dry_run.get("copied_count") == 0, "Dry run copied artifacts unexpectedly")
    require(dry_run.get("copy_or_move_performed") is False, "Dry run mutated storage")
    require(dry_run.get("move_performed") is False, "Dry run moved artifacts")
    require(dry_run.get("delete_performed") is False, "Dry run deleted artifacts")
    require(dry_run.get("msi_rewrite_performed") is False, "Dry run rewrote MSI")

    execute = request_json("/api/storage/migration/execute-managed-zarr-copy", method="POST", payload={"execute": True})
    print_summary("execute", execute)

    require(execute.get("ok") is True, "Execute ok != true")
    require(execute.get("mode") == "execute", "Execute mode mismatch")
    require(execute.get("eligible_count") == dry_run.get("eligible_count"), "Eligible count changed between dry run and execute")
    require(execute.get("failed_count") == 0, "Managed Zarr copy reported failures")
    require(execute.get("move_performed") is False, "Managed Zarr copy moved artifacts")
    require(execute.get("delete_performed") is False, "Managed Zarr copy deleted artifacts")
    require(execute.get("msi_rewrite_performed") is False, "Managed Zarr copy rewrote MSI")
    require(execute.get("manifest_uri"), "Execute response missing manifest URI")

    copied_or_skipped = int(execute.get("copied_count") or 0) + int(execute.get("skipped_count") or 0)
    require(copied_or_skipped == execute.get("eligible_count"), "Not all eligible artifacts were copied or skipped")

    inventory = request_json("/api/storage/inventory")
    target_count = int((inventory.get("summary") or {}).get("target_bucket_item_count") or 0)
    require(target_count >= copied_or_skipped, "Target bucket inventory did not reflect copied/skipped Zarr artifacts")

    second_execute = request_json("/api/storage/migration/execute-managed-zarr-copy", method="POST", payload={"execute": True})
    print_summary("second execute idempotency check", second_execute)
    require(second_execute.get("failed_count") == 0, "Second execute reported failures")
    require(second_execute.get("copied_count") == 0, "Second execute should not copy already-existing targets")
    require(second_execute.get("skipped_count") == second_execute.get("eligible_count"), "Second execute should skip all existing targets")
    require(second_execute.get("move_performed") is False, "Second execute moved artifacts")
    require(second_execute.get("delete_performed") is False, "Second execute deleted artifacts")
    require(second_execute.get("msi_rewrite_performed") is False, "Second execute rewrote MSI")

    print("\nPASS storage managed Zarr copy contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
