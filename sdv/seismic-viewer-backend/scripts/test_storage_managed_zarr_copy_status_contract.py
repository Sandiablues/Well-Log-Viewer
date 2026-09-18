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


def request_json(path: str) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"GET {path} failed: HTTP {exc.code}: {body}") from exc
    return json.loads(raw)


def main() -> int:
    print("---- storage managed Zarr copy status contract ----")

    payload = request_json("/api/storage/migration/managed-zarr-copy-status")
    summary = {
        "ok": payload.get("ok"),
        "service": payload.get("service"),
        "status_mode": payload.get("status_mode"),
        "operation": payload.get("operation"),
        "summary": payload.get("summary"),
        "policy": payload.get("policy"),
        "resolved_by": payload.get("resolved_by"),
    }
    print(json.dumps(summary, indent=2))

    require(payload.get("ok") is True, "status ok != true")
    require(payload.get("service") == "storage", "service marker mismatch")
    require(payload.get("status_mode") == "read_only_verification", "status mode must be read_only_verification")
    require(payload.get("operation") == "managed_zarr_copy_status", "operation marker mismatch")
    require(payload.get("resolved_by") == "end_seismic_repository_storage_service", "wrong resolver marker")

    rows = payload.get("rows")
    require(isinstance(rows, list), "rows must be list")
    require(len(rows) >= 1, "expected at least one managed Zarr status row")

    summary_payload = payload.get("summary") or {}
    require(summary_payload.get("managed_zarr_candidate_count") == len(rows), "candidate count mismatch")
    require(summary_payload.get("copy_or_move_performed") is False, "status endpoint must not copy or move")
    require(summary_payload.get("msi_rewrite_performed") is False, "status endpoint must not rewrite MSI")

    policy = payload.get("policy") or {}
    require(policy.get("status") == "verification_only", "policy status mismatch")
    require(policy.get("copy_or_move_performed") is False, "policy must not copy or move")
    require(policy.get("msi_rewrite_performed") is False, "policy must not rewrite MSI")

    required_keys = {
        "artifact_kind",
        "name",
        "inferred_dimension",
        "source_path",
        "source_exists",
        "source_is_dir",
        "target_uri",
        "target_path",
        "target_exists",
        "target_is_dir",
        "target_likely_valid",
        "validation_markers",
        "review_required",
        "issues",
        "ready_for_msi_storage_uri_rewrite",
    }

    ready_count = 0
    for row in rows:
        require(isinstance(row, dict), "status row must be dict")
        missing = required_keys - set(row.keys())
        require(not missing, f"status row missing keys: {sorted(missing)}")
        require(row.get("artifact_kind") == "legacy_zarr", "status row must be legacy_zarr")
        require(row.get("inferred_dimension") in {"2d", "3d"}, "legacy_zarr status row must have inferred dimension")
        require(isinstance(row.get("validation_markers"), list), "validation_markers must be list")
        require(isinstance(row.get("issues"), list), "issues must be list")
        require(row.get("source_exists") is True, "source legacy Zarr must exist")
        require(row.get("source_is_dir") is True, "source legacy Zarr must be directory")
        if row.get("ready_for_msi_storage_uri_rewrite") is True:
            ready_count += 1
            require(row.get("target_exists") is True, "ready row target must exist")
            require(row.get("target_is_dir") is True, "ready row target must be directory")
            require(row.get("target_likely_valid") is True, "ready row target must be likely valid Zarr")

    require(ready_count == summary_payload.get("ready_for_msi_storage_uri_rewrite_count"), "ready count mismatch")

    print("\nPASS storage managed Zarr copy status contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
