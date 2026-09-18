#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from typing import Any


BASE_URL = "http://127.0.0.1:8000"


def request_json(path: str) -> Any:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    payload = request_json("/api/managed-data/query?limit=2&offset=0")
    require(isinstance(payload, dict), "query response must be an object")
    require(isinstance(payload.get("rows"), list), "query response rows must be a list")
    require(payload.get("limit") == 2, "limit must be echoed")
    require(payload.get("offset") == 0, "offset must be echoed")
    require("total_count" in payload, "total_count missing")
    require("has_more" in payload, "has_more missing")
    require(payload.get("source") == "msi_sql_query", "source marker mismatch")
    require(len(payload["rows"]) <= 2, "rows exceeded requested limit")

    for row in payload["rows"]:
        rep = row.get("msi_representation_id")
        require(bool(rep), "row missing msi_representation_id")
        require(row.get("id") == rep, "row id must equal msi_representation_id")
        require(row.get("volume_id") == rep, "row volume_id must equal msi_representation_id")
        require(row.get("source") == "msi", "row source must be msi")
        require(row.get("registry_source") == "msi", "row registry_source must be msi")

    q_payload = request_json("/api/managed-data/query?q=__definitely_no_match__&limit=5")
    require(q_payload.get("total_count") == 0, "no-match query should return total_count=0")
    require(q_payload.get("rows") == [], "no-match query should return no rows")

    loaded_payload = request_json("/api/managed-data/query?loaded=true&limit=50")
    for row in loaded_payload.get("rows", []):
        require(row.get("is_loaded") is True, "loaded=true query returned unloaded row")

    unloaded_payload = request_json("/api/managed-data/query?loaded=false&limit=50")
    for row in unloaded_payload.get("rows", []):
        require(row.get("is_loaded") is False, "loaded=false query returned loaded row")

    sort_payload = request_json("/api/managed-data/query?limit=3&sort_by=updated_at&sort_dir=desc")
    require(sort_payload.get("sort_by") == "updated_at", "sort_by not echoed")
    require(sort_payload.get("sort_dir") == "desc", "sort_dir not echoed")

    print("PASS managed data enterprise query contract")
    print(json.dumps(
        {
            "default_total_count": payload.get("total_count"),
            "default_returned_count": len(payload.get("rows", [])),
            "loaded_total_count": loaded_payload.get("total_count"),
            "unloaded_total_count": unloaded_payload.get("total_count"),
        },
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
