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
    {
        "label": "F3 3D",
        "representation_id": "msi_repr:source_segy_segy_fb7e290e24111f66:zarr_e7069f19-5f02-4d92-a24d-5cfa9e4ae97a",
        "expected_physical_volume_id": "e7069f19-5f02-4d92-a24d-5cfa9e4ae97a",
    },
    {
        "label": "MB772 2D",
        "representation_id": "msi_repr:source_segy_segy_552a66ec59692f6c:zarr_f56f4cca-cf0b-4de5-b85e-00b78a7ea491",
        "expected_physical_volume_id": "f56f4cca-cf0b-4de5-b85e-00b78a7ea491",
    },
]


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


def encoded(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def test_representation(label: str, representation_id: str, expected_physical_volume_id: str) -> None:
    payload = request_json(f"/api/msi/representations/{encoded(representation_id)}/info")

    print(f"\n---- {label}: MSI info ----")
    print(json.dumps({
        "msi_representation_id": payload.get("msi_representation_id"),
        "msi_dataset_id": payload.get("msi_dataset_id"),
        "physical_volume_id": payload.get("physical_volume_id"),
        "resolved_by": payload.get("resolved_by"),
        "top_level_keys": sorted(payload.keys())[:20],
    }, indent=2))

    require(payload.get("msi_representation_id") == representation_id, f"{label}: msi_representation_id mismatch")
    require(payload.get("physical_volume_id") == expected_physical_volume_id, f"{label}: physical_volume_id mismatch")
    require(payload.get("resolved_by") == "msi_representation_info_service", f"{label}: wrong resolver marker")
    require(payload.get("msi_dataset_id"), f"{label}: missing msi_dataset_id")
    require(len(payload.keys()) > 4, f"{label}: info payload looks too small")


def main() -> int:
    print("---- MSI representation info contract ----")

    for item in REPRESENTATIONS:
        test_representation(
            label=item["label"],
            representation_id=item["representation_id"],
            expected_physical_volume_id=item["expected_physical_volume_id"],
        )

    print("\nPASS MSI representation info contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
