#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.error
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
    status, payload = request_json("GET", "/api/managed-data/query?limit=10")
    require(status == 200, "GET /api/managed-data/query did not return 200")
    require(isinstance(payload, dict), "query payload must be an object")
    rows = payload.get("rows")
    require(isinstance(rows, list), "query payload rows must be a list")
    return [row for row in rows if isinstance(row, dict)]


def main() -> int:
    for endpoint in ["load-selected", "unload-selected"]:
        status, _ = request_json(
            "POST",
            f"/api/managed-data/bulk/{endpoint}",
            {"representation_ids": [], "dry_run": True},
            expect_error=True,
        )
        require(status == 400, f"empty {endpoint} selection should return HTTP 400")

    rows = managed_rows()
    if not rows:
        print("SKIP dry-run target validation: no Managed Data query rows currently exist.")
        print("PASS managed data bulk viewer action empty-selection contract")
        return 0

    representation_id = str(rows[0].get("msi_representation_id") or rows[0].get("id") or "").strip()
    require(representation_id.startswith("msi_repr:"), "target row must expose MSI representation id")

    for endpoint, expected_action in [
        ("load-selected", "load_selected"),
        ("unload-selected", "unload_selected"),
    ]:
        status, dry_run = request_json(
            "POST",
            f"/api/managed-data/bulk/{endpoint}",
            {"representation_ids": [representation_id, representation_id], "dry_run": True},
        )

        require(status == 200, f"dry-run {endpoint} should return HTTP 200")
        require(dry_run.get("ok") is True, "dry-run response ok should be true")
        require(dry_run.get("dry_run") is True, "dry-run response dry_run should be true")
        require(dry_run.get("action") == expected_action, f"unexpected dry-run action for {endpoint}")
        require(dry_run.get("requested_count") == 1, "duplicate IDs should be deduplicated")
        require(dry_run.get("valid_count") == 1, "dry-run valid_count should be 1")
        require(dry_run.get("action_scope") == "managed_data_viewer_catalog", "unexpected action scope")
        require(isinstance(dry_run.get("targets"), list), "targets must be a list")

        status, _ = request_json(
            "POST",
            f"/api/managed-data/bulk/{endpoint}",
            {"representation_ids": ["msi_repr:missing_for_viewer_contract_test"], "dry_run": True},
            expect_error=True,
        )
        require(status == 404, f"missing representation dry-run should return HTTP 404 for {endpoint}")

    print("PASS managed data bulk viewer action contract")
    print(json.dumps(
        {
            "tested_representation_id": representation_id,
            "managed_rows_available": len(rows),
        },
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
