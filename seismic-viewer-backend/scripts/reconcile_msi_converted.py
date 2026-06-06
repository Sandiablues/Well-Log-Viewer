#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


BASE_URL = "http://127.0.0.1:8000"


def request_json(path: str, *, method: str = "POST") -> Any:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method=method)

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{method} {path} failed: HTTP {exc.code}: {body}") from exc

    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile converted source SEG-Y rows into production MSI.")
    parser.add_argument("--execute", action="store_true", help="Perform production MSI upserts. Default is dry-run.")
    args = parser.parse_args()

    dry_run = "false" if args.execute else "true"
    data = request_json(f"/api/msi/registration/reconcile-converted?dry_run={dry_run}")

    print(json.dumps({
        "ok": data.get("ok"),
        "mode": data.get("mode"),
        "writes_performed": data.get("writes_performed"),
        "test_seed": data.get("test_seed"),
        "candidate_count": data.get("candidate_count"),
        "skipped_count": data.get("skipped_count"),
        "registered_count": data.get("registered_count"),
        "failed_count": data.get("failed_count"),
    }, indent=2))

    if data.get("skipped"):
        print("\n---- skipped ----")
        print(json.dumps(data.get("skipped"), indent=2))

    if data.get("results"):
        print("\n---- results ----")
        for row in data.get("results", []):
            print(json.dumps({
                "registered": row.get("registered"),
                "dataset_id": row.get("dataset_id"),
                "representation_id": row.get("representation_id"),
                "dataset_type": row.get("dataset_type"),
                "representation_type": row.get("representation_type"),
                "viewer_mode": row.get("viewer_mode"),
                "volume_id": row.get("volume_id"),
                "test_seed": row.get("test_seed"),
                "reason": row.get("reason"),
            }, indent=2))

    if data.get("ok") is not True:
        print("\nFAIL MSI converted registration reconcile", file=sys.stderr)
        return 1

    print("\nPASS MSI converted registration reconcile")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
