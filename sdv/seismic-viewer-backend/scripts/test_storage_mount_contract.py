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


def request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None
    headers = {}

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{method} {path} failed: HTTP {exc.code}: {error_body}") from exc

    return json.loads(raw)


def request_status(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    body = None
    headers = {}

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, json.loads(raw)


def main() -> int:
    print("---- End seismic repository storage mount contract ----")

    health = request_json("GET", "/api/storage/health")
    print(json.dumps(health, indent=2))

    require(health.get("ok") is True, "Storage health did not return ok=true")
    require(health.get("bucket_name") == "End_Seismic_Data_Repository", "Unexpected bucket name")
    require(health.get("bucket_scheme") == "endrepo", "Unexpected bucket scheme")
    require(health.get("manifest_exists") is True, "Storage bucket manifest is missing")
    require(health.get("missing_directories") == [], f"Missing storage directories: {health.get('missing_directories')}")

    print("\n---- resolve known repository directory ----")
    resolved = request_json("POST", "/api/storage/resolve", {"uri": "endrepo://managed/zarr/3d/"})
    print(json.dumps(resolved, indent=2))

    require(resolved.get("ok") is True, "Resolve response ok != true")
    require(resolved.get("scheme") == "endrepo", "Resolve response scheme mismatch")
    require(resolved.get("relative_path") == "managed/zarr/3d", "Resolve response relative path mismatch")
    require(resolved.get("exists") is True, "Known storage directory should exist")
    require(resolved.get("is_dir") is True, "Known storage directory should resolve as directory")
    require(resolved.get("resolved_by") == "end_seismic_repository_storage_service", "Unexpected resolver marker")

    print("\n---- resolve future artifact path ----")
    future = request_json("POST", "/api/storage/resolve", {"uri": "endrepo://managed/zarr/3d/example-volume.zarr"})
    print(json.dumps(future, indent=2))

    require(future.get("ok") is True, "Future artifact resolve response ok != true")
    require(future.get("relative_path") == "managed/zarr/3d/example-volume.zarr", "Future artifact relative path mismatch")
    require(future.get("exists") is False, "Future artifact path should not exist yet")

    print("\n---- reject unsupported schemes and traversal ----")
    bad_scheme_status, bad_scheme_payload = request_status("POST", "/api/storage/resolve", {"uri": "file:///tmp/bad"})
    print(json.dumps({"status": bad_scheme_status, "response": bad_scheme_payload}, indent=2))
    require(bad_scheme_status == 400, "Unsupported scheme should return 400")

    traversal_status, traversal_payload = request_status("POST", "/api/storage/resolve", {"uri": "endrepo://managed/../outside"})
    print(json.dumps({"status": traversal_status, "response": traversal_payload}, indent=2))
    require(traversal_status == 400, "Traversal URI should return 400")

    print("\nPASS End seismic repository storage mount contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
