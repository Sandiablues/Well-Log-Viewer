#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


BASE_URL = "http://127.0.0.1:8000"

REPRESENTATIONS = [
    "msi_repr:source_segy_segy_fb7e290e24111f66:zarr_e7069f19-5f02-4d92-a24d-5cfa9e4ae97a",
    "msi_repr:source_segy_segy_552a66ec59692f6c:zarr_f56f4cca-cf0b-4de5-b85e-00b78a7ea491",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


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
    print("---- MSI representation resolver ----")

    for representation_id in REPRESENTATIONS:
        encoded = urllib.parse.quote(representation_id, safe="")
        payload = request_json(f"/api/msi/representations/{encoded}/resolved-volume")

        print(json.dumps({
            "representation_id": payload.get("representation_id"),
            "dataset_id": payload.get("dataset_id"),
            "physical_volume_id": payload.get("physical_volume_id"),
            "zarr_url": payload.get("zarr_url"),
            "zarr_exists": payload.get("zarr_exists"),
            "dataset_type": payload.get("dataset_type"),
            "viewer_mode": payload.get("viewer_mode"),
            "representation_type": payload.get("representation_type"),
            "lifecycle_state": payload.get("lifecycle_state"),
            "viewer_ready": payload.get("viewer_ready"),
            "legacy_volume_exists": payload.get("legacy_volume_exists"),
            "urls": payload.get("urls"),
        }, indent=2))

        require(payload.get("ok") is True, "Resolver did not return ok=true")
        require(payload.get("representation_id") == representation_id, "Representation id mismatch")
        require(payload.get("physical_volume_id"), "Missing physical_volume_id")
        require(payload.get("zarr_url"), "Missing zarr_url")
        require(payload.get("zarr_exists") is True, "Expected zarr_exists=true")
        require(payload.get("viewer_ready") is True, "Expected viewer_ready=true")
        require(payload.get("lifecycle_state") == "viewer_ready", "Expected lifecycle_state=viewer_ready")
        require(payload.get("legacy_volume_exists") is True, "Expected legacy_volume_exists=true during bridge phase")

        urls = payload.get("urls") or {}
        require(urls.get("volume_info", "").startswith("/api/msi/representations/"), "Missing MSI-native volume_info URL")

        legacy_urls_for_info = payload.get("legacy_bridge_urls") or {}
        require(legacy_urls_for_info.get("volume_info", "").startswith("/api/volumes/"), "Missing legacy volume_info bridge URL")
        require(urls.get("metadata_summary", "").startswith("/api/msi/representations/"), "Missing MSI-native metadata_summary URL")
        require(urls.get("normalized_metadata", "").startswith("/api/msi/representations/"), "Missing MSI-native normalized_metadata URL")
        require(urls.get("metadata_score_report", "").startswith("/api/msi/representations/"), "Missing MSI-native metadata_score_report URL")
        require(urls.get("documents", "").startswith("/api/msi/representations/"), "Missing MSI-native documents URL")

        legacy_urls = payload.get("legacy_bridge_urls") or {}
        require(legacy_urls.get("metadata_summary", "").startswith("/api/volumes/"), "Missing legacy metadata_summary bridge URL")
        require(legacy_urls.get("normalized_metadata", "").startswith("/api/volumes/"), "Missing legacy normalized_metadata bridge URL")
        require(legacy_urls.get("documents", "").startswith("/api/volumes/"), "Missing legacy documents bridge URL")

    print("\nPASS MSI representation resolver")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
