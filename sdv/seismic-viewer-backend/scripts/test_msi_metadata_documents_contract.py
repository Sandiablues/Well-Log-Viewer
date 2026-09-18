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
        "expected_dataset_type": "3d_volume",
    },
    {
        "label": "MB772 2D",
        "representation_id": "msi_repr:source_segy_segy_552a66ec59692f6c:zarr_f56f4cca-cf0b-4de5-b85e-00b78a7ea491",
        "expected_dataset_type": "2d_line",
    },
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def request(method: str, path: str) -> tuple[int, str, str]:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method=method)

    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            body = response.read().decode("utf-8", errors="replace")
            content_type = response.headers.get("content-type", "")
            return response.status, content_type, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        content_type = exc.headers.get("content-type", "")
        return exc.code, content_type, body


def request_json(path: str) -> dict[str, Any]:
    status, content_type, body = request("GET", path)
    require(status == 200, f"GET {path} expected 200, got {status}: {body[:500]}")
    try:
        return json.loads(body)
    except Exception as exc:
        raise AssertionError(f"GET {path} did not return JSON. content_type={content_type}, body={body[:500]}") from exc


def encoded_representation_id(representation_id: str) -> str:
    return urllib.parse.quote(representation_id, safe="")


def test_representation(label: str, representation_id: str, expected_dataset_type: str) -> None:
    encoded = encoded_representation_id(representation_id)
    base = f"/api/msi/representations/{encoded}"

    print(f"\n---- {label}: documents ----")
    documents = request_json(f"{base}/documents")
    print(json.dumps({
        "msi_representation_id": documents.get("msi_representation_id"),
        "physical_volume_id": documents.get("physical_volume_id"),
        "document_count": documents.get("document_count", len(documents.get("documents") or [])),
        "resolved_by": documents.get("resolved_by"),
        "warning": documents.get("warning"),
    }, indent=2))

    require(documents.get("msi_representation_id") == representation_id, f"{label}: documents representation id mismatch")
    require(documents.get("physical_volume_id"), f"{label}: documents missing physical_volume_id")
    require(isinstance(documents.get("documents"), list), f"{label}: documents payload missing documents list")
    require(documents.get("resolved_by") == "msi_representation_documents_service", f"{label}: wrong documents resolver")

    print(f"\n---- {label}: metadata summary ----")
    summary = request_json(f"{base}/metadata-summary")
    print(json.dumps({
        "volume_id": summary.get("volume_id"),
        "dataset_type": summary.get("dataset_type"),
        "_msi": summary.get("_msi"),
    }, indent=2))

    msi_marker = summary.get("_msi", {})
    require(summary.get("volume_id"), f"{label}: metadata summary missing volume_id")
    require(summary.get("dataset_type") == expected_dataset_type, f"{label}: metadata summary dataset_type mismatch")
    require(msi_marker.get("representation_id") == representation_id, f"{label}: metadata summary missing MSI marker")
    require(msi_marker.get("dataset_id"), f"{label}: metadata summary missing MSI dataset_id")
    require(msi_marker.get("managed_display_name"), f"{label}: metadata summary missing MSI managed display name")
    require(msi_marker.get("original_source_name"), f"{label}: metadata summary missing original/source name")
    require(msi_marker.get("resolved_by") == "msi_representation_metadata_service", f"{label}: wrong metadata summary resolver")

    print(f"\n---- {label}: normalized metadata ----")
    normalized = request_json(f"{base}/metadata/normalized")
    print(json.dumps({
        "volume_id": normalized.get("volume_id"),
        "msi_representation_id": normalized.get("msi_representation_id"),
        "physical_volume_id": normalized.get("physical_volume_id"),
        "resolved_by": normalized.get("resolved_by"),
        "has_normalized_metadata": bool(normalized.get("normalized_metadata")),
    }, indent=2))

    require(normalized.get("msi_representation_id") == representation_id, f"{label}: normalized metadata representation id mismatch")
    require(normalized.get("physical_volume_id"), f"{label}: normalized metadata missing physical_volume_id")
    require(normalized.get("normalized_metadata"), f"{label}: missing normalized_metadata")
    require(normalized.get("resolved_by") == "msi_representation_metadata_service", f"{label}: wrong normalized metadata resolver")

    print(f"\n---- {label}: metadata score report ----")
    status, content_type, body = request("GET", f"{base}/metadata-score-report")
    print(json.dumps({
        "status": status,
        "content_type": content_type,
        "body_prefix": body[:80],
    }, indent=2))

    require(status == 200, f"{label}: metadata score report expected 200, got {status}")
    require("<html" in body.lower() or "<!doctype html" in body.lower(), f"{label}: score report did not look like HTML")


def main() -> int:
    print("---- MSI metadata/documents contract ----")

    for item in REPRESENTATIONS:
        test_representation(
            label=item["label"],
            representation_id=item["representation_id"],
            expected_dataset_type=item["expected_dataset_type"],
        )

    print("\nPASS MSI metadata/documents contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
