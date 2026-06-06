#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any


BASE_URL = "http://127.0.0.1:8000"


def request_json(path: str) -> Any:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"GET {path} failed: HTTP {exc.code}: {body}") from exc

    return json.loads(raw)


def main() -> int:
    data = request_json("/api/msi/audit/ownership")

    print(json.dumps({
        "ok": data.get("ok"),
        "converted_source_count": data.get("converted_source_count"),
        "audited_count": data.get("audited_count"),
        "issue_count": data.get("issue_count"),
    }, indent=2))

    for row in data.get("rows", []):
        print(json.dumps({
            "status": row.get("status"),
            "issues": row.get("issues"),
            "filename": row.get("filename"),
            "dataset_type": row.get("dataset_type"),
            "source_volume_id": row.get("source_volume_id"),
            "legacy_volume_exists": row.get("legacy_volume_exists"),
            "msi_dataset_exists": row.get("msi_dataset_exists"),
            "msi_representation_exists": row.get("msi_representation_exists"),
            "msi_registration_state": row.get("msi_registration_state"),
            "msi_lifecycle_state": row.get("msi_lifecycle_state"),
            "msi_viewer_ready": row.get("msi_viewer_ready"),
            "legacy_msi_identity_match": row.get("legacy_msi_identity_match"),
        }, indent=2))

    if not data.get("ok"):
        print("\nFAIL MSI ownership audit", file=sys.stderr)
        print(json.dumps(data.get("issues"), indent=2), file=sys.stderr)
        return 1

    print("\nPASS MSI ownership audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
