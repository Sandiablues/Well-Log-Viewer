#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

BASE_URL = "http://127.0.0.1:8000"


def request_json(method: str, path: str, payload: Dict[str, Any] | None = None, expect_error: bool = False) -> tuple[int, Any]:
    body = None
    headers = {}

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            return response.status, data
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except Exception:
            data = raw
        if expect_error:
            return exc.code, data
        raise RuntimeError(f"{method} {path} failed: HTTP {exc.code}: {data}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def managed_rows() -> List[Dict[str, Any]]:
    status, payload = request_json("GET", "/api/managed-data")
    require(status == 200, "GET /api/managed-data did not return 200")
    require(isinstance(payload, list), "GET /api/managed-data did not return a list")
    return [row for row in payload if isinstance(row, dict)]


def main() -> int:
    status, error_payload = request_json(
        "POST",
        "/api/managed-data/bulk/delete-selected",
        {"representation_ids": [], "dry_run": True},
        expect_error=True,
    )
    require(status == 400, "empty bulk delete selection should return HTTP 400")

    rows_before = managed_rows()
    if not rows_before:
        print("SKIP dry-run target validation: no Managed Data rows currently exist.")
        print("PASS managed data bulk delete empty-selection contract")
        return 0

    target = rows_before[0]
    representation_id = str(target.get("msi_representation_id") or target.get("id") or "").strip()
    require(representation_id.startswith("msi_repr:"), "target row must expose MSI representation id")

    status, dry_run = request_json(
        "POST",
        "/api/managed-data/bulk/delete-selected",
        {"representation_ids": [representation_id, representation_id], "dry_run": True},
    )

    require(status == 200, "dry-run bulk delete should return HTTP 200")
    require(dry_run.get("ok") is True, "dry-run response ok should be true")
    require(dry_run.get("dry_run") is True, "dry-run response dry_run should be true")
    require(dry_run.get("requested_count") == 1, "duplicate IDs should be deduplicated")
    require(dry_run.get("valid_count") == 1, "dry-run valid_count should be 1")
    require(dry_run.get("delete_scope") == "managed_data_full_cascade", "unexpected delete scope")

    rows_after = managed_rows()
    still_present = any(
        str(row.get("msi_representation_id") or row.get("id") or "").strip() == representation_id
        for row in rows_after
    )
    require(still_present, "dry-run must not delete the selected representation")

    status, missing_payload = request_json(
        "POST",
        "/api/managed-data/bulk/delete-selected",
        {"representation_ids": ["msi_repr:missing_for_contract_test"], "dry_run": True},
        expect_error=True,
    )
    require(status == 404, "missing representation dry-run should return HTTP 404")

    print("PASS managed data bulk delete contract")
    print(json.dumps(
        {
            "tested_representation_id": representation_id,
            "managed_rows_before": len(rows_before),
            "managed_rows_after": len(rows_after),
            "dry_run_requested_count": dry_run.get("requested_count"),
            "dry_run_valid_count": dry_run.get("valid_count"),
        },
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
