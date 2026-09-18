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
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"GET {path} failed: HTTP {exc.code}: {body}") from exc

    return json.loads(raw)


def main() -> int:
    print("---- storage artifact inventory contract ----")

    payload = request_json("/api/storage/inventory")

    summary = {
        "ok": payload.get("ok"),
        "service": payload.get("service"),
        "inventory_mode": payload.get("inventory_mode"),
        "mutates_storage": payload.get("mutates_storage"),
        "summary": payload.get("summary"),
        "migration_policy": payload.get("migration_policy"),
        "resolved_by": payload.get("resolved_by"),
    }
    print(json.dumps(summary, indent=2))

    require(payload.get("ok") is True, "inventory ok != true")
    require(payload.get("service") == "storage", "inventory service marker mismatch")
    require(payload.get("inventory_mode") == "read_only", "inventory must be read_only")
    require(payload.get("mutates_storage") is False, "inventory must not mutate storage")
    require(payload.get("resolved_by") == "end_seismic_repository_storage_service", "wrong resolver marker")

    summary = payload.get("summary") or {}
    require(isinstance(summary, dict), "summary missing or not dict")
    for key in [
        "legacy_zarr_count",
        "legacy_zarr_tmp_count",
        "legacy_segy_index_count",
        "legacy_job_record_count",
        "target_bucket_item_count",
        "review_required_count",
    ]:
        require(key in summary, f"summary missing {key}")
        require(isinstance(summary[key], int), f"summary {key} is not int")

    legacy = payload.get("legacy_artifacts") or {}
    require(isinstance(legacy.get("zarr"), list), "legacy_artifacts.zarr must be list")
    require(isinstance(legacy.get("zarr_tmp"), list), "legacy_artifacts.zarr_tmp must be list")
    require(isinstance(legacy.get("segy_index"), list), "legacy_artifacts.segy_index must be list")
    require(isinstance(legacy.get("job_records"), list), "legacy_artifacts.job_records must be list")

    policy = payload.get("migration_policy") or {}
    require(policy.get("status") == "plan_only", "migration policy must be plan_only")
    require(policy.get("copy_or_move_performed") is False, "inventory must not copy or move")
    require(policy.get("msi_rewrite_performed") is False, "inventory must not rewrite MSI")

    print("\nPASS storage artifact inventory contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
