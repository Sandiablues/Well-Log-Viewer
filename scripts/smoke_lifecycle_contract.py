#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def fetch_json(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"Failed request for {url}: {exc}") from exc

    try:
        value = json.loads(body)
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON from {url}: {body[:500]}") from exc

    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object from {url}, got {type(value).__name__}")

    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def row_by_key(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload.get("representations")
    require(isinstance(rows, list), "payload.representations must be a list")

    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        require(isinstance(row, dict), f"representation row must be object, got {type(row).__name__}")
        key = row.get("key")
        require(isinstance(key, str) and key, f"representation row missing string key: {row}")
        mapped[key] = row

        for field in ("label", "state", "status_label"):
            require(field in row, f"{key} missing field: {field}")

        for field in ("can_create", "can_load", "can_delete", "can_archive"):
            require(isinstance(row.get(field), bool), f"{key}.{field} must be boolean")

        action_url = row.get("action_url")
        delete_url = row.get("delete_url")
        require(action_url is None or isinstance(action_url, str), f"{key}.action_url must be string or null")
        require(delete_url is None or isinstance(delete_url, str), f"{key}.delete_url must be string or null")

    return mapped


def check_common(payload: dict[str, Any], *, expected_mode: str, expected_source_id: str) -> None:
    require(payload.get("status") == "ok", f"status must be ok, got {payload.get('status')!r}")
    require(payload.get("mode") == expected_mode, f"mode must be {expected_mode}, got {payload.get('mode')!r}")
    require(payload.get("source_id") == expected_source_id, f"source_id mismatch: {payload.get('source_id')!r}")

    source = payload.get("source")
    require(isinstance(source, dict), "source must be object")
    require(source.get("segy_file_id") == expected_source_id, "source.segy_file_id mismatch")
    require(isinstance(source.get("source_path_exists"), bool), "source.source_path_exists must be boolean")

    monitor = payload.get("monitor")
    require(isinstance(monitor, dict), "monitor must be object")
    for field in ("state", "label", "message"):
        require(isinstance(monitor.get(field), str), f"monitor.{field} must be string")


def check_3d(base_url: str, segy_id: str) -> None:
    payload = fetch_json(f"{base_url}/api/segy-files/{segy_id}/lifecycle?mode=3d")
    check_common(payload, expected_mode="3d", expected_source_id=segy_id)

    rows = row_by_key(payload)
    expected = {"index_preview", "fast_zarr_cache", "managed_zarr"}
    require(set(rows) == expected, f"3D rows mismatch. expected={sorted(expected)}, got={sorted(rows)}")

    require(rows["index_preview"]["label"] == "Index / Preview", "3D index label mismatch")
    require(rows["fast_zarr_cache"]["label"] == "Fast Zarr Cache", "3D cache label mismatch")
    require(rows["managed_zarr"]["label"] == "Managed Zarr", "3D managed label mismatch")

    for key, slug in {
        "index_preview": "index-preview",
        "fast_zarr_cache": "fast-zarr-cache",
        "managed_zarr": "managed-zarr",
    }.items():
        row = rows[key]
        if row["can_delete"]:
            require(
                row["delete_url"] == f"/api/segy-files/{segy_id}/representations/{slug}",
                f"3D {key} delete_url mismatch: {row['delete_url']!r}",
            )
        if row["can_create"]:
            action_slug = {
                "index_preview": "create-index",
                "fast_zarr_cache": "build-fast-zarr-cache",
                "managed_zarr": "create-managed-zarr",
            }[key]
            require(
                row["action_url"] == f"/api/segy-files/{segy_id}/actions/{action_slug}",
                f"3D {key} action_url mismatch: {row['action_url']!r}",
            )

    print("PASS 3D lifecycle contract")


def check_2d(base_url: str, segy_id: str) -> None:
    payload = fetch_json(f"{base_url}/api/segy-files/{segy_id}/lifecycle?mode=2d")
    check_common(payload, expected_mode="2d", expected_source_id=segy_id)

    rows = row_by_key(payload)
    expected = {"managed_2d_line_zarr"}
    require(set(rows) == expected, f"2D rows mismatch. expected={sorted(expected)}, got={sorted(rows)}")

    row = rows["managed_2d_line_zarr"]
    require(row["label"] == "Managed 2D Line Zarr", "2D managed label mismatch")

    if row["can_delete"]:
        require(
            row["delete_url"] == f"/api/segy-files/{segy_id}/representations/managed-2d-line-zarr",
            f"2D delete_url mismatch: {row['delete_url']!r}",
        )

    if row["can_create"]:
        require(
            row["action_url"] == f"/api/segy-files/{segy_id}/actions/create-managed-2d-line-zarr",
            f"2D action_url mismatch: {row['action_url']!r}",
        )

    require("index_preview" not in rows, "2D must not expose 3D index_preview")
    require("fast_zarr_cache" not in rows, "2D must not expose 3D fast_zarr_cache")

    print("PASS 2D lifecycle contract")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test source SEG-Y lifecycle contract without destructive actions.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--id-3d", required=True)
    parser.add_argument("--id-2d", required=True)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    try:
        check_3d(base_url, args.id_3d)
        check_2d(base_url, args.id_2d)
    except Exception as exc:
        print(f"FAIL lifecycle smoke test: {exc}", file=sys.stderr)
        return 1

    print("PASS lifecycle smoke test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
