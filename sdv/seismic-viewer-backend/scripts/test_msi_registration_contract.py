#!/usr/bin/env python3
"""
MSI production registration regression test.

Purpose:
- Verify already-converted source SEG-Y records can register into MSI without test seed.
- Verify registration result is test_seed=false.
- Verify MSI managed rows expose the production-registered row.
- Verify identity audit remains clean.
- Verify load/unload works on the production-registered representation.

This complements test_msi_contract.py, which validates the test-seed path.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = "http://127.0.0.1:8000"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ZARR_ROOT = BACKEND_DIR / "data" / "zarr"

# Current clean 3D and 2D test artifacts.
F3_SEGY_ID = "segy_fb7e290e24111f66"
F3_VOLUME_ID = "e7069f19-5f02-4d92-a24d-5cfa9e4ae97a"
F3_REPRESENTATION_ID = f"msi_repr:source_segy_{F3_SEGY_ID}:zarr_{F3_VOLUME_ID}"

MB772_SEGY_ID = "segy_552a66ec59692f6c"
MB772_VOLUME_ID = "f56f4cca-cf0b-4de5-b85e-00b78a7ea491"
MB772_REPRESENTATION_ID = f"msi_repr:source_segy_{MB772_SEGY_ID}:zarr_{MB772_VOLUME_ID}"


def request_json(method: str, path: str) -> Any:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{method} {path} failed: HTTP {exc.code}: {body}") from exc
    except Exception as exc:
        raise AssertionError(f"{method} {path} failed: {exc}") from exc

    try:
        return json.loads(raw)
    except Exception as exc:
        raise AssertionError(f"{method} {path} returned non-JSON: {raw[:500]}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def zarr_exists_from_url(zarr_url: str | None) -> bool:
    if not zarr_url or not zarr_url.startswith("/data/zarr/"):
        return False
    name = zarr_url.replace("/data/zarr/", "", 1)
    return (ZARR_ROOT / name).exists()


def assert_identity_row(row: dict[str, Any], context: str) -> None:
    rep = row.get("msi_representation_id")
    require(bool(rep), f"{context}: missing msi_representation_id")
    require(row.get("id") == rep, f"{context}: id must equal msi_representation_id")
    require(row.get("volume_id") == rep, f"{context}: volume_id must equal msi_representation_id")
    require(row.get("source") == "msi", f"{context}: source must be msi")
    require(row.get("registry_source") == "msi", f"{context}: registry_source must be msi")
    require(bool(row.get("physical_volume_id")), f"{context}: missing physical_volume_id")
    require(bool(row.get("zarr_url")), f"{context}: missing zarr_url")
    require(zarr_exists_from_url(row.get("zarr_url")), f"{context}: zarr artifact missing: {row.get('zarr_url')}")


def assert_audit_ok(label: str, expected_loaded_count: int | None = None) -> dict[str, Any]:
    audit = request_json("GET", "/api/msi/viewer/compatibility-identity-audit")
    require(audit.get("ok") is True, f"{label}: audit not ok: {json.dumps(audit, indent=2)}")
    require(not audit.get("issues"), f"{label}: audit issues present: {audit.get('issues')}")

    if expected_loaded_count is not None:
        require(
            audit.get("loaded_count") == expected_loaded_count,
            f"{label}: expected loaded_count={expected_loaded_count}, got {audit.get('loaded_count')}",
        )

    return audit



def register_already_converted_and_assert(
    *,
    label: str,
    segy_id: str,
    volume_id: str,
    representation_id: str,
    expected_dataset_type: str,
    expected_representation_type: str,
    expected_viewer_mode: str,
) -> dict[str, Any]:
    print(f"\n---- register already-converted {label} through convert endpoint ----")
    response = request_json("POST", f"/api/segy-files/{segy_id}/convert")
    print(json.dumps({
        "status": response.get("status"),
        "volume_id": response.get("volume_id"),
        "zarr_url": response.get("zarr_url"),
        "msi_registration": response.get("msi_registration"),
    }, indent=2))

    registration = response.get("msi_registration") or {}
    require(response.get("status") == "converted", f"{label}: expected already-converted response status")
    require(registration.get("registered") is True, f"{label}: MSI registration failed: {registration}")
    require(registration.get("test_seed") is False, f"{label}: production registration must return test_seed=false")
    require(registration.get("dataset_upserts") == 1, f"{label}: expected one dataset upsert")
    require(registration.get("representation_upserts") == 1, f"{label}: expected one representation upsert")
    require(registration.get("representation_id") == representation_id, f"{label}: unexpected representation id")
    require(registration.get("volume_id") == volume_id, f"{label}: unexpected physical volume id")
    require(registration.get("dataset_type") == expected_dataset_type, f"{label}: wrong dataset_type")
    require(registration.get("representation_type") == expected_representation_type, f"{label}: wrong representation_type")
    require(registration.get("viewer_mode") == expected_viewer_mode, f"{label}: wrong viewer_mode")

    return registration


def managed_row_for_representation(representation_id: str) -> dict[str, Any]:
    managed = request_json("GET", "/api/msi/viewer/managed-volumes-compatible")
    rows = [row for row in managed if row.get("msi_representation_id") == representation_id]
    require(len(rows) == 1, f"Expected exactly one managed row for {representation_id}, got {len(rows)}")
    return rows[0]


def assert_managed_row(
    *,
    label: str,
    row: dict[str, Any],
    volume_id: str,
    expected_dataset_type: str,
) -> None:
    assert_identity_row(row, f"managed:{label}")
    require(row.get("physical_volume_id") == volume_id, f"{label}: managed row has wrong physical_volume_id")
    require(row.get("dataset_type") == expected_dataset_type, f"{label}: managed row has wrong dataset_type")
    require(row.get("is_loaded") is False, f"{label}: row should start unloaded")
    require(row.get("hidden") is True, f"{label}: row should start hidden/unloaded")

    print(json.dumps({
        "display_name": row.get("display_name"),
        "dataset_type": row.get("dataset_type"),
        "id": row.get("id"),
        "volume_id": row.get("volume_id"),
        "physical_volume_id": row.get("physical_volume_id"),
        "msi_representation_id": row.get("msi_representation_id"),
        "hidden": row.get("hidden"),
        "is_loaded": row.get("is_loaded"),
        "zarr_url": row.get("zarr_url"),
    }, indent=2))


def main() -> int:
    print("---- MSI health ----")
    health = request_json("GET", "/api/msi/health")
    require(health.get("ok") is True, f"MSI health failed: {health}")
    print(json.dumps(health, indent=2))

    print("\n---- purge MSI test seed rows ----")
    purge = request_json("POST", "/api/msi/adapters/source-registry/purge-test-seed")
    print(json.dumps(purge, indent=2))

    register_already_converted_and_assert(
        label="F3 3D",
        segy_id=F3_SEGY_ID,
        volume_id=F3_VOLUME_ID,
        representation_id=F3_REPRESENTATION_ID,
        expected_dataset_type="3d_volume",
        expected_representation_type="zarr_3d",
        expected_viewer_mode="3d",
    )

    register_already_converted_and_assert(
        label="MB772 2D",
        segy_id=MB772_SEGY_ID,
        volume_id=MB772_VOLUME_ID,
        representation_id=MB772_REPRESENTATION_ID,
        expected_dataset_type="2d_line",
        expected_representation_type="zarr_2d",
        expected_viewer_mode="2d",
    )

    print("\n---- managed rows after production registration ----")
    f3_row = managed_row_for_representation(F3_REPRESENTATION_ID)
    mb772_row = managed_row_for_representation(MB772_REPRESENTATION_ID)

    assert_managed_row(
        label="F3 3D production registration",
        row=f3_row,
        volume_id=F3_VOLUME_ID,
        expected_dataset_type="3d_volume",
    )

    assert_managed_row(
        label="MB772 2D production registration",
        row=mb772_row,
        volume_id=MB772_VOLUME_ID,
        expected_dataset_type="2d_line",
    )

    print("\n---- identity audit after production registration ----")
    audit = assert_audit_ok("after production registration", expected_loaded_count=0)
    require(audit.get("managed_count") >= 2, f"Expected at least two managed rows, got {audit.get('managed_count')}")
    print(json.dumps(audit, indent=2))

    print("\n---- load production-registered F3 ----")
    loaded_response = request_json("POST", f"/api/msi/representations/{F3_REPRESENTATION_ID}/load")
    print(json.dumps(loaded_response, indent=2))
    require(loaded_response.get("loaded") is True, "Load response did not mark loaded=true")

    print("\n---- loaded rows after load ----")
    loaded_rows = request_json("GET", "/api/msi/viewer/loaded-volumes-compatible")
    f3_loaded_rows = [row for row in loaded_rows if row.get("msi_representation_id") == F3_REPRESENTATION_ID]

    require(len(f3_loaded_rows) == 1, f"Expected exactly one loaded F3 row, got {len(f3_loaded_rows)}")
    loaded_row = f3_loaded_rows[0]
    assert_identity_row(loaded_row, "loaded:F3 production registration")
    require(loaded_row.get("hidden") is False, "Loaded production row should not be hidden")
    require(loaded_row.get("is_loaded") is True, "Loaded production row should be is_loaded=true")

    print(json.dumps({
        "display_name": loaded_row.get("display_name"),
        "dataset_type": loaded_row.get("dataset_type"),
        "id": loaded_row.get("id"),
        "volume_id": loaded_row.get("volume_id"),
        "physical_volume_id": loaded_row.get("physical_volume_id"),
        "msi_representation_id": loaded_row.get("msi_representation_id"),
        "hidden": loaded_row.get("hidden"),
        "is_loaded": loaded_row.get("is_loaded"),
        "zarr_url": loaded_row.get("zarr_url"),
    }, indent=2))

    print("\n---- identity audit after load ----")
    audit = assert_audit_ok("after production load", expected_loaded_count=1)
    print(json.dumps(audit, indent=2))

    print("\n---- unload production-registered F3 ----")
    unloaded_response = request_json("POST", f"/api/msi/representations/{F3_REPRESENTATION_ID}/unload")
    print(json.dumps(unloaded_response, indent=2))
    require(unloaded_response.get("loaded") is False, "Unload response did not mark loaded=false")

    print("\n---- final loaded rows ----")
    final_loaded_rows = request_json("GET", "/api/msi/viewer/loaded-volumes-compatible")
    require(
        not any(row.get("msi_representation_id") == F3_REPRESENTATION_ID for row in final_loaded_rows),
        "F3 remained in loaded rows after unload",
    )
    print(json.dumps(final_loaded_rows, indent=2))

    print("\n---- final identity audit ----")
    audit = assert_audit_ok("after production unload", expected_loaded_count=0)
    print(json.dumps(audit, indent=2))

    print("\nPASS MSI production registration regression test")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
