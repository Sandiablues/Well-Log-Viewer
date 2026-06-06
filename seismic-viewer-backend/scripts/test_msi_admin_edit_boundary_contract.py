#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


BASE_URL = "http://127.0.0.1:8000"
DATASET_ID = "source_segy:segy_fb7e290e24111f66"
REPRESENTATION_ID = "msi_repr:source_segy_segy_fb7e290e24111f66:zarr_e7069f19-5f02-4d92-a24d-5cfa9e4ae97a"

METADATA_FIELDS = (
    "survey_name",
    "line_name",
    "volume_name",
    "processing_stage",
    "processing_version",
)

ADMIN_HEADER = {"X-MSI-Admin-Action": "true"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def encoded(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def request_status(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    url = f"{BASE_URL}{path}"
    body = None
    headers: dict[str, str] = {}

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    if extra_headers:
        headers.update(extra_headers)

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(error_body)
        except Exception:
            data = {"raw": error_body}
        return exc.code, data


def request_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    status, data = request_status(method, path, payload, extra_headers)
    if status != 200:
        raise AssertionError(f"{method} {path} failed: HTTP {status}: {json.dumps(data, indent=2)}")
    return data


def require_admin_override_marker(dataset: dict[str, Any], field_name: str, context: str) -> None:
    source_reference = dataset.get("source_reference") or {}
    admin_overrides = source_reference.get("admin_field_overrides") or {}

    require(isinstance(admin_overrides, dict), f"{context}: admin_field_overrides is not a dict")
    marker = admin_overrides.get(field_name) or {}

    require(marker.get("source") == "manual_msi_admin", f"{context}: admin marker source mismatch for {field_name}")
    require(marker.get("reason") == "MSI admin boundary contract test", f"{context}: reason missing for {field_name}")
    require(bool(marker.get("at")), f"{context}: timestamp missing for {field_name}")


def main() -> int:
    print("---- MSI admin editable-field boundary contract ----")

    before = request_json("GET", f"/api/msi/datasets/{DATASET_ID}")
    original_name = before.get("display_name")
    original_metadata = {field: before.get(field) for field in METADATA_FIELDS}

    require(original_name, "Original display_name missing before admin test")

    try:
        print("\n---- ordinary controlled metadata route requires admin signal ----")
        status, data = request_status(
            "POST",
            f"/api/msi/datasets/{DATASET_ID}/metadata",
            {"survey_name": "Should Not Apply"},
        )
        print(json.dumps({"status": status, "response": data}, indent=2))
        require(status == 403, f"Expected metadata route without admin signal to return 403, got {status}")

        print("\n---- admin dataset field update ----")
        updated = request_json(
            "POST",
            f"/api/msi/admin/datasets/{DATASET_ID}/fields",
            {
                "updates": {
                    "display_name": "MSI Admin Boundary Display Name",
                    "survey_name": "MSI Admin Boundary Survey",
                    "processing_version": "MSI Admin Boundary Version",
                },
                "reason": "MSI admin boundary contract test",
                "evidence_ref": "contract-test",
            },
        )
        print(json.dumps(updated, indent=2))

        require(updated.get("ok") is True, "Admin update ok != true")
        require(updated.get("admin_edit") is True, "Admin update missing admin_edit=true")
        require(updated.get("dataset_id") == DATASET_ID, "Admin update dataset_id mismatch")
        require(updated.get("rejected_fields") == [], "Admin update unexpectedly rejected fields")
        require(
            set(updated.get("updated_fields") or []) == {"display_name", "survey_name", "processing_version"},
            f"Admin updated_fields mismatch: {updated.get('updated_fields')}",
        )

        after_dataset_admin = request_json("GET", f"/api/msi/datasets/{DATASET_ID}")
        require(after_dataset_admin.get("display_name") == "MSI Admin Boundary Display Name", "Admin display_name did not persist")
        require(after_dataset_admin.get("survey_name") == "MSI Admin Boundary Survey", "Admin survey_name did not persist")
        require(after_dataset_admin.get("processing_version") == "MSI Admin Boundary Version", "Admin processing_version did not persist")
        require_admin_override_marker(after_dataset_admin, "display_name", "dataset admin update")
        require_admin_override_marker(after_dataset_admin, "survey_name", "dataset admin update")
        require_admin_override_marker(after_dataset_admin, "processing_version", "dataset admin update")

        print("\n---- admin representation route resolves to owning dataset ----")
        representation_update = request_json(
            "POST",
            f"/api/msi/admin/representations/{encoded(REPRESENTATION_ID)}/fields",
            {
                "updates": {
                    "line_name": "MSI Admin Boundary Line",
                    "volume_name": "MSI Admin Boundary Volume",
                },
                "reason": "MSI admin boundary contract test",
                "evidence_ref": "contract-test-representation",
            },
        )
        print(json.dumps(representation_update, indent=2))

        require(representation_update.get("ok") is True, "Representation admin update ok != true")
        require(representation_update.get("representation_id") == REPRESENTATION_ID, "Representation admin response id mismatch")
        require(
            set(representation_update.get("updated_fields") or []) == {"line_name", "volume_name"},
            f"Representation updated_fields mismatch: {representation_update.get('updated_fields')}",
        )

        after_representation_admin = request_json("GET", f"/api/msi/datasets/{DATASET_ID}")
        require(after_representation_admin.get("line_name") == "MSI Admin Boundary Line", "Representation admin line_name did not persist")
        require(after_representation_admin.get("volume_name") == "MSI Admin Boundary Volume", "Representation admin volume_name did not persist")
        require_admin_override_marker(after_representation_admin, "line_name", "representation admin update")
        require_admin_override_marker(after_representation_admin, "volume_name", "representation admin update")

        print("\n---- admin route rejects system/internal fields ----")
        rejected_status, rejected_data = request_status(
            "POST",
            f"/api/msi/admin/datasets/{DATASET_ID}/fields",
            {
                "updates": {
                    "dataset_id": "illegal",
                    "lifecycle_state": "viewer_ready",
                    "storage_uri": "/tmp/illegal",
                },
                "reason": "MSI admin boundary contract test",
            },
        )
        print(json.dumps({"status": rejected_status, "response": rejected_data}, indent=2))
        require(rejected_status == 400, f"Expected system/internal field rejection with 400, got {rejected_status}")

        detail = rejected_data.get("detail") or {}
        require("dataset_id" in detail.get("rejected_fields", []), "dataset_id was not listed as rejected")
        require("lifecycle_state" in detail.get("rejected_fields", []), "lifecycle_state was not listed as rejected")
        require("storage_uri" in detail.get("rejected_fields", []), "storage_uri was not listed as rejected")

        print("\n---- admin route requires reason ----")
        missing_reason_status, missing_reason_data = request_status(
            "POST",
            f"/api/msi/admin/datasets/{DATASET_ID}/fields",
            {"updates": {"survey_name": "No Reason"}},
        )
        print(json.dumps({"status": missing_reason_status, "response": missing_reason_data}, indent=2))
        require(missing_reason_status in {400, 422}, f"Expected missing reason rejection, got {missing_reason_status}")

    finally:
        print("\n---- restore display name and descriptive metadata ----")
        restored_name = request_json(
            "POST",
            f"/api/msi/datasets/{DATASET_ID}/display-name",
            {"display_name": original_name},
        )
        print(json.dumps(restored_name, indent=2))

        restored_metadata = request_json(
            "POST",
            f"/api/msi/datasets/{DATASET_ID}/metadata",
            original_metadata,
            ADMIN_HEADER,
        )
        print(json.dumps(restored_metadata, indent=2))

    final = request_json("GET", f"/api/msi/datasets/{DATASET_ID}")
    require(final.get("display_name") == original_name, "display_name was not restored")

    for field_name, expected_value in original_metadata.items():
        require(final.get(field_name) == expected_value, f"{field_name} was not restored")

    print("\nPASS MSI admin editable-field boundary contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
