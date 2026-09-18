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
MISSING_DATASET_ID = "source_segy:missing_display_name_contract_test"
MAX_DISPLAY_NAME_LENGTH = 240


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


METADATA_FIELDS = (
    "survey_name",
    "line_name",
    "volume_name",
    "processing_stage",
    "processing_version",
)

ADMIN_HEADER = {"X-MSI-Admin-Action": "true"}


def cleanup_leftover_contract_metadata() -> None:
    current = request_json("GET", f"/api/msi/datasets/{DATASET_ID}")
    values = {field_name: current.get(field_name) for field_name in METADATA_FIELDS}

    if not any(
        isinstance(value, str) and value.startswith("MSI Contract")
        for value in values.values()
    ):
        return

    print("\n---- cleanup leftover MSI contract metadata from prior failed validation ----")
    cleaned = request_json(
        "POST",
        f"/api/msi/datasets/{DATASET_ID}/metadata",
        {field_name: None for field_name in METADATA_FIELDS},
        ADMIN_HEADER,
    )
    print(json.dumps(cleaned, indent=2))


def request_status(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    url = f"{BASE_URL}{path}"
    body = None
    headers = {}

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


def encoded(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def assert_rejected_display_name(payload: dict[str, Any], expected_status: int = 400) -> None:
    status, data = request_status(
        "POST",
        f"/api/msi/datasets/{DATASET_ID}/display-name",
        payload,
    )
    require(
        status == expected_status,
        f"Expected display-name update to fail with HTTP {expected_status}, got {status}: {json.dumps(data, indent=2)}",
    )


def require_display_name_override_marker(dataset: dict[str, Any], context: str) -> None:
    source_reference = dataset.get("source_reference") or {}
    require(
        source_reference.get("display_name_override") is True,
        f"{context}: missing display_name_override=true marker",
    )
    require(
        source_reference.get("display_name_override_source") == "manual_msi_admin",
        f"{context}: unexpected display_name_override_source",
    )
    require(
        bool(source_reference.get("display_name_override_at")),
        f"{context}: missing display_name_override_at",
    )


def require_dataset_metadata_override_marker(
    dataset: dict[str, Any],
    expected_fields: set[str],
    context: str,
) -> None:
    source_reference = dataset.get("source_reference") or {}
    overrides = source_reference.get("dataset_metadata_overrides") or {}

    require(isinstance(overrides, dict), f"{context}: dataset_metadata_overrides is not a dict")

    for field_name in expected_fields:
        marker = overrides.get(field_name) or {}
        require(marker.get("source") == "manual_msi_admin", f"{context}: missing override source for {field_name}")
        require(bool(marker.get("at")), f"{context}: missing override timestamp for {field_name}")


def main() -> int:
    print("---- MSI dataset display-name contract ----")

    cleanup_leftover_contract_metadata()

    before = request_json("GET", f"/api/msi/datasets/{DATASET_ID}")
    original_name = before.get("display_name")
    original_metadata = {
        field_name: before.get(field_name)
        for field_name in METADATA_FIELDS
    }

    require(original_name, "Original display_name missing before test")

    test_name = f"{original_name} [MSI rename contract test]"
    if len(test_name) > MAX_DISPLAY_NAME_LENGTH:
        test_name = f"{original_name[:180]} [MSI rename contract test]"

    try:
        print("\n---- update display name ----")
        updated = request_json(
            "POST",
            f"/api/msi/datasets/{DATASET_ID}/display-name",
            {"display_name": test_name},
        )
        print(json.dumps(updated, indent=2))

        require(updated.get("ok") is True, "Update response ok != true")
        require(updated.get("dataset_id") == DATASET_ID, "Update response dataset_id mismatch")
        require(updated.get("display_name") == test_name, "Update response display_name mismatch")
        require(updated.get("resolved_by") == "msi_dataset_admin_service", "Unexpected resolver marker")

        after = request_json("GET", f"/api/msi/datasets/{DATASET_ID}")
        require(after.get("display_name") == test_name, "Dataset GET did not reflect updated display_name")
        require_display_name_override_marker(after, "dataset route update")

        managed = request_json("GET", "/api/msi/viewer/managed-volumes-compatible")
        matching = [
            row
            for row in managed
            if row.get("dataset_id") == DATASET_ID or row.get("id", "").find("segy_fb7e290e24111f66") >= 0
        ]
        require(matching, "Could not find updated dataset in managed compatible rows")
        require(
            any(row.get("display_name") == test_name for row in matching),
            "Managed compatible rows did not reflect updated display_name",
        )

        print("\n---- update display name through representation route ----")
        representation_test_name = f"{original_name} [MSI representation rename contract test]"
        if len(representation_test_name) > MAX_DISPLAY_NAME_LENGTH:
            representation_test_name = f"{original_name[:165]} [MSI representation rename test]"

        representation_updated = request_json(
            "POST",
            f"/api/msi/representations/{encoded(REPRESENTATION_ID)}/display-name",
            {"display_name": representation_test_name},
        )
        print(json.dumps(representation_updated, indent=2))

        require(representation_updated.get("ok") is True, "Representation update response ok != true")
        require(representation_updated.get("dataset_id") == DATASET_ID, "Representation update dataset_id mismatch")
        require(
            representation_updated.get("representation_id") == REPRESENTATION_ID,
            "Representation update representation_id mismatch",
        )
        require(
            representation_updated.get("display_name") == representation_test_name,
            "Representation update display_name mismatch",
        )
        require(
            representation_updated.get("resolved_by") == "msi_dataset_admin_service",
            "Unexpected representation update resolver marker",
        )

        represented_dataset = request_json("GET", f"/api/msi/datasets/{DATASET_ID}")
        require(
            represented_dataset.get("display_name") == representation_test_name,
            "Representation route did not update the dataset display_name",
        )
        require_display_name_override_marker(represented_dataset, "representation route update")

        print("\n---- production reconcile preserves manual display-name override ----")
        reconcile = request_json("POST", "/api/msi/registration/reconcile-converted?dry_run=false")
        print(json.dumps(
            {
                "ok": reconcile.get("ok"),
                "mode": reconcile.get("mode"),
                "registered_count": reconcile.get("registered_count"),
                "failed_count": reconcile.get("failed_count"),
            },
            indent=2,
        ))
        require(reconcile.get("ok") is True, "Production reconcile did not return ok=true")

        reconciled_dataset = request_json("GET", f"/api/msi/datasets/{DATASET_ID}")
        require(
            reconciled_dataset.get("display_name") == representation_test_name,
            "Production reconcile overwrote manual display_name override",
        )
        require_display_name_override_marker(reconciled_dataset, "post-reconcile override preservation")

        print("\n---- update dataset descriptive metadata ----")
        metadata_update = request_json(
            "POST",
            f"/api/msi/datasets/{DATASET_ID}/metadata",
            {
                "survey_name": "MSI Contract Survey",
                "line_name": "MSI Contract Line",
                "volume_name": "MSI Contract Volume",
            },
            ADMIN_HEADER,
        )
        print(json.dumps(metadata_update, indent=2))

        require(metadata_update.get("ok") is True, "Metadata update response ok != true")
        require(metadata_update.get("dataset_id") == DATASET_ID, "Metadata update dataset_id mismatch")
        require(metadata_update.get("survey_name") == "MSI Contract Survey", "Metadata update survey_name mismatch")
        require(metadata_update.get("line_name") == "MSI Contract Line", "Metadata update line_name mismatch")
        require(metadata_update.get("volume_name") == "MSI Contract Volume", "Metadata update volume_name mismatch")

        metadata_dataset = request_json("GET", f"/api/msi/datasets/{DATASET_ID}")
        require(metadata_dataset.get("survey_name") == "MSI Contract Survey", "Dataset GET survey_name mismatch")
        require(metadata_dataset.get("line_name") == "MSI Contract Line", "Dataset GET line_name mismatch")
        require(metadata_dataset.get("volume_name") == "MSI Contract Volume", "Dataset GET volume_name mismatch")
        require_dataset_metadata_override_marker(
            metadata_dataset,
            {"survey_name", "line_name", "volume_name"},
            "dataset metadata route update",
        )

        print("\n---- update descriptive metadata through representation route ----")
        representation_metadata_update = request_json(
            "POST",
            f"/api/msi/representations/{encoded(REPRESENTATION_ID)}/metadata",
            {
                "processing_stage": "MSI Contract Processing Stage",
                "processing_version": "MSI Contract Version",
            },
            ADMIN_HEADER,
        )
        print(json.dumps(representation_metadata_update, indent=2))

        require(representation_metadata_update.get("ok") is True, "Representation metadata update response ok != true")
        require(
            representation_metadata_update.get("representation_id") == REPRESENTATION_ID,
            "Representation metadata update representation_id mismatch",
        )
        require(
            representation_metadata_update.get("processing_stage") == "MSI Contract Processing Stage",
            "Representation metadata update processing_stage mismatch",
        )
        require(
            representation_metadata_update.get("processing_version") == "MSI Contract Version",
            "Representation metadata update processing_version mismatch",
        )

        represented_metadata_dataset = request_json("GET", f"/api/msi/datasets/{DATASET_ID}")
        require(
            represented_metadata_dataset.get("processing_stage") == "MSI Contract Processing Stage",
            "Representation route did not update processing_stage",
        )
        require(
            represented_metadata_dataset.get("processing_version") == "MSI Contract Version",
            "Representation route did not update processing_version",
        )
        require_dataset_metadata_override_marker(
            represented_metadata_dataset,
            {"survey_name", "line_name", "volume_name", "processing_stage", "processing_version"},
            "representation metadata route update",
        )

        print("\n---- production reconcile preserves manual descriptive metadata overrides ----")
        metadata_reconcile = request_json("POST", "/api/msi/registration/reconcile-converted?dry_run=false")
        print(json.dumps(
            {
                "ok": metadata_reconcile.get("ok"),
                "mode": metadata_reconcile.get("mode"),
                "registered_count": metadata_reconcile.get("registered_count"),
                "failed_count": metadata_reconcile.get("failed_count"),
            },
            indent=2,
        ))
        require(metadata_reconcile.get("ok") is True, "Production reconcile after metadata update did not return ok=true")

        reconciled_metadata_dataset = request_json("GET", f"/api/msi/datasets/{DATASET_ID}")
        require(
            reconciled_metadata_dataset.get("survey_name") == "MSI Contract Survey",
            "Production reconcile overwrote manual survey_name override",
        )
        require(
            reconciled_metadata_dataset.get("processing_stage") == "MSI Contract Processing Stage",
            "Production reconcile overwrote manual processing_stage override",
        )

        print("\n---- validation rejections ----")
        assert_rejected_display_name({"display_name": ""})
        assert_rejected_display_name({"display_name": "   "})
        assert_rejected_display_name({"display_name": "bad\nname"})
        assert_rejected_display_name({"display_name": "x" * (MAX_DISPLAY_NAME_LENGTH + 1)})

        representation_invalid_status, representation_invalid_data = request_status(
            "POST",
            f"/api/msi/representations/{encoded(REPRESENTATION_ID)}/display-name",
            {"display_name": "bad\nname"},
        )
        require(
            representation_invalid_status == 400,
            f"Missing representation display-name validation rejection. got HTTP {representation_invalid_status}: {json.dumps(representation_invalid_data, indent=2)}",
        )

        metadata_invalid_status, metadata_invalid_data = request_status(
            "POST",
            f"/api/msi/datasets/{DATASET_ID}/metadata",
            {"survey_name": "bad\nname"},
            ADMIN_HEADER,
        )
        require(
            metadata_invalid_status == 400,
            f"Missing dataset metadata validation rejection. got HTTP {metadata_invalid_status}: {json.dumps(metadata_invalid_data, indent=2)}",
        )

        representation_metadata_invalid_status, representation_metadata_invalid_data = request_status(
            "POST",
            f"/api/msi/representations/{encoded(REPRESENTATION_ID)}/metadata",
            {"processing_stage": "x" * 161},
            ADMIN_HEADER,
        )
        require(
            representation_metadata_invalid_status == 400,
            f"Missing representation metadata validation rejection. got HTTP {representation_metadata_invalid_status}: {json.dumps(representation_metadata_invalid_data, indent=2)}",
        )

        empty_metadata_status, empty_metadata_data = request_status(
            "POST",
            f"/api/msi/datasets/{DATASET_ID}/metadata",
            {},
            ADMIN_HEADER,
        )
        require(
            empty_metadata_status == 400,
            f"Missing empty metadata update validation rejection. got HTTP {empty_metadata_status}: {json.dumps(empty_metadata_data, indent=2)}",
        )

        missing_status, missing_data = request_status(
            "POST",
            f"/api/msi/datasets/{MISSING_DATASET_ID}/display-name",
            {"display_name": "Should Not Exist"},
        )
        require(
            missing_status == 404,
            f"Expected missing dataset update to fail with HTTP 404, got {missing_status}: {json.dumps(missing_data, indent=2)}",
        )

    finally:
        print("\n---- restore original display name ----")
        restored = request_json(
            "POST",
            f"/api/msi/datasets/{DATASET_ID}/display-name",
            {"display_name": original_name},
        )
        print(json.dumps(restored, indent=2))

        print("\n---- restore original descriptive metadata ----")
        restored_metadata = request_json(
            "POST",
            f"/api/msi/datasets/{DATASET_ID}/metadata",
            original_metadata,
            ADMIN_HEADER,
        )
        print(json.dumps(restored_metadata, indent=2))

    final = request_json("GET", f"/api/msi/datasets/{DATASET_ID}")
    require(final.get("display_name") == original_name, "Dataset display_name was not restored")
    for field_name, expected_value in original_metadata.items():
        require(
            final.get(field_name) == expected_value,
            f"Dataset {field_name} was not restored",
        )

    print("\nPASS MSI dataset display-name contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
