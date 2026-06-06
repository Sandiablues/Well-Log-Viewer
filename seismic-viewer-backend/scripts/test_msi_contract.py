#!/usr/bin/env python3
"""
MSI contract regression test.

Purpose:
- Verify MSI seed/load/unload behavior.
- Verify MSI frontend-compatible identity contract.
- Verify MSI rows point only to existing Zarr artifacts.
- Verify loaded rows disappear after unload.
- Verify no stale deleted artifact IDs are exposed.

This is intentionally backend/API-level. It does not test browser rendering.
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

STALE_ARTIFACT_IDS = {
    "1e920789-6ca3-4802-aeb3-2667740621a1",
    "f3198bdd-1d1a-4ce0-8f2b-2300cbcf1ce1",
}


def request_json(method: str, path: str) -> Any:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
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


def physical_id_from_zarr_url(zarr_url: str | None) -> str | None:
    if not zarr_url:
        return None
    name = zarr_url.rstrip("/").split("/")[-1]
    if name.endswith(".zarr"):
        return name[:-5]
    return name or None


def assert_identity_row(row: dict[str, Any], context: str) -> None:
    rep = row.get("msi_representation_id")
    require(bool(rep), f"{context}: missing msi_representation_id")
    require(row.get("id") == rep, f"{context}: id must equal msi_representation_id")
    require(row.get("volume_id") == rep, f"{context}: volume_id must equal msi_representation_id")
    require(row.get("source") == "msi", f"{context}: source must be msi")
    require(row.get("registry_source") == "msi", f"{context}: registry_source must be msi")
    require(bool(row.get("physical_volume_id")), f"{context}: missing physical_volume_id")
    require(bool(row.get("zarr_url")), f"{context}: missing zarr_url")
    require(zarr_exists_from_url(row.get("zarr_url")), f"{context}: zarr_url does not exist: {row.get('zarr_url')}")

    physical_from_url = physical_id_from_zarr_url(row.get("zarr_url"))
    require(
        row.get("physical_volume_id") == physical_from_url,
        f"{context}: physical_volume_id does not match zarr_url. "
        f"physical_volume_id={row.get('physical_volume_id')}, zarr_url={row.get('zarr_url')}",
    )

    require(
        row.get("physical_volume_id") not in STALE_ARTIFACT_IDS,
        f"{context}: stale deleted artifact exposed: {row.get('physical_volume_id')}",
    )








def request_status(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    import urllib.error
    import urllib.request

    body = None
    headers = {}

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except Exception:
            data = {"raw": raw}
        return exc.code, data




def assert_representation_resolver_ok(representation_id: str) -> dict[str, Any]:
    import urllib.parse

    encoded = urllib.parse.quote(representation_id, safe="")
    payload = request_json("GET", f"/api/msi/representations/{encoded}/resolved-volume")

    require(payload.get("ok") is True, f"Resolver did not return ok=true: {json.dumps(payload, indent=2)}")
    require(payload.get("representation_id") == representation_id, "Resolver representation_id mismatch")
    require(payload.get("physical_volume_id"), "Resolver missing physical_volume_id")
    require(payload.get("zarr_url"), "Resolver missing zarr_url")
    require(payload.get("zarr_exists") is True, "Resolver expected zarr_exists=true")
    require(payload.get("viewer_ready") is True, "Resolver expected viewer_ready=true")
    require(payload.get("lifecycle_state") == "viewer_ready", "Resolver expected lifecycle_state=viewer_ready")
    require(payload.get("legacy_volume_exists") is True, "Resolver expected legacy_volume_exists=true during bridge phase")

    urls = payload.get("urls") or {}
    require(urls.get("volume_info", "").startswith("/api/msi/representations/"), "Resolver missing MSI-native volume_info URL")

    legacy_urls_for_info = payload.get("legacy_bridge_urls") or {}
    require(legacy_urls_for_info.get("volume_info", "").startswith("/api/volumes/"), "Resolver missing legacy volume_info bridge URL")
    require(urls.get("metadata_summary", "").startswith("/api/msi/representations/"), "Resolver missing MSI-native metadata_summary URL")
    require(urls.get("normalized_metadata", "").startswith("/api/msi/representations/"), "Resolver missing MSI-native normalized_metadata URL")
    require(urls.get("metadata_score_report", "").startswith("/api/msi/representations/"), "Resolver missing MSI-native metadata_score_report URL")
    require(urls.get("documents", "").startswith("/api/msi/representations/"), "Resolver missing MSI-native documents URL")

    legacy_urls = payload.get("legacy_bridge_urls") or {}
    require(legacy_urls.get("metadata_summary", "").startswith("/api/volumes/"), "Resolver missing legacy metadata_summary bridge URL")
    require(legacy_urls.get("normalized_metadata", "").startswith("/api/volumes/"), "Resolver missing legacy normalized_metadata bridge URL")
    require(legacy_urls.get("documents", "").startswith("/api/volumes/"), "Resolver missing legacy documents bridge URL")

    return payload


def assert_legacy_write_guard_blocks_msi_ids(representation_id: str) -> None:
    patch_status, patch_body = request_status(
        "PATCH",
        f"/api/volumes/{representation_id}",
        {"display_name": "SHOULD_NOT_WRITE"},
    )
    require(
        patch_status == 409,
        f"Expected PATCH legacy write guard to return 409, got {patch_status}: {json.dumps(patch_body, indent=2)}",
    )

    delete_status, delete_body = request_status(
        "DELETE",
        f"/api/volumes/{representation_id}",
    )
    require(
        delete_status == 409,
        f"Expected DELETE legacy write guard to return 409, got {delete_status}: {json.dumps(delete_body, indent=2)}",
    )


def assert_converted_reconcile_ok(label: str) -> dict[str, Any]:
    result = request_json("POST", "/api/msi/registration/reconcile-converted?dry_run=false")
    require(result.get("ok") is True, f"{label}: converted reconcile not ok: {json.dumps(result, indent=2)}")
    require(result.get("test_seed") is False, f"{label}: converted reconcile must not be test seed")
    require(result.get("writes_performed") is True, f"{label}: expected reconcile writes_performed=true")
    require(result.get("candidate_count", 0) >= 2, f"{label}: expected at least two converted candidates")
    require(result.get("failed_count", 0) == 0, f"{label}: reconcile failed_count != 0")
    return result


def assert_ownership_audit_ok(label: str) -> dict[str, Any]:
    audit = request_json("GET", "/api/msi/audit/ownership")
    require(audit.get("ok") is True, f"{label}: ownership audit not ok: {json.dumps(audit, indent=2)}")
    require(audit.get("issue_count") == 0, f"{label}: ownership audit issue_count != 0")
    require(audit.get("audited_count", 0) >= 2, f"{label}: expected at least two audited converted rows")
    return audit


def assert_audit_ok(label: str) -> dict[str, Any]:
    audit = request_json("GET", "/api/msi/viewer/compatibility-identity-audit")
    require(audit.get("ok") is True, f"{label}: audit not ok: {json.dumps(audit, indent=2)}")
    require(not audit.get("issues"), f"{label}: audit issues present: {audit.get('issues')}")
    return audit



def unload_all_loaded_msi_rows(label: str) -> None:
    import urllib.parse

    loaded = request_json("GET", "/api/msi/viewer/loaded-volumes-compatible")
    if not loaded:
        print(f"{label}: no loaded MSI rows to unload")
        return

    for row in loaded:
        representation_id = row.get("msi_representation_id") or row.get("id")
        if not representation_id:
            continue

        encoded = urllib.parse.quote(str(representation_id), safe="")
        print(f"{label}: unloading {representation_id}")
        request_json("POST", f"/api/msi/representations/{encoded}/unload")

    remaining = request_json("GET", "/api/msi/viewer/loaded-volumes-compatible")
    require(
        remaining == [],
        f"{label}: expected no loaded MSI rows after cleanup, got {json.dumps(remaining, indent=2)}",
    )

def main() -> int:
    print("---- MSI health ----")
    health = request_json("GET", "/api/msi/health")
    require(health.get("ok") is True, f"MSI health failed: {health}")
    print(json.dumps(health, indent=2))

    print("\n---- purge MSI test seed ----")
    purge = request_json("POST", "/api/msi/adapters/source-registry/purge-test-seed")
    print(json.dumps(purge, indent=2))

    print("\n---- seed preview ----")
    preview = request_json("GET", "/api/msi/adapters/source-registry/test-seed-plan-preview?sample_limit=50")
    print(json.dumps({
        "datasets_to_seed_count": preview.get("datasets_to_seed_count"),
        "representations_to_seed_count": preview.get("representations_to_seed_count"),
        "skipped_count": preview.get("skipped_count"),
    }, indent=2))

    reps = preview.get("representations_to_seed") or []
    require(len(reps) >= 2, f"Expected at least 2 seed representations, got {len(reps)}")

    for rep in reps:
        storage_uri = rep.get("storage_uri") or ""
        require("1e920789-6ca3-4802-aeb3-2667740621a1" not in storage_uri, "Preview exposes stale F3 artifact")
        require("f3198bdd-1d1a-4ce0-8f2b-2300cbcf1ce1" not in storage_uri, "Preview exposes stale Seismic_data artifact")

    print("\n---- production reconcile converted source rows into MSI ----")
    reconcile = assert_converted_reconcile_ok("contract regression")
    print(json.dumps({
        "ok": reconcile.get("ok"),
        "mode": reconcile.get("mode"),
        "candidate_count": reconcile.get("candidate_count"),
        "registered_count": reconcile.get("registered_count"),
        "failed_count": reconcile.get("failed_count"),
        "test_seed": reconcile.get("test_seed"),
    }, indent=2))

    print("\n---- execute MSI test seed; should not overwrite production rows ----")
    seed = request_json("POST", "/api/msi/adapters/source-registry/test-seed")
    print(json.dumps(seed, indent=2))
    # If production MSI rows already exist for the same artifacts, test-seed is
    # expected to skip overwriting them. The managed row assertions below are the
    # actual contract check.
    require(seed.get("writes_performed") is True, "Expected test seed write operation to complete")
    require(seed.get("test_seed") is True, "Expected test_seed=true for dev seed endpoint")
    require(seed.get("representation_upserts", 0) == 0, "Test seed must not overwrite production MSI representations")

    print("\n---- cleanup loaded MSI rows before managed-row assertions ----")
    unload_all_loaded_msi_rows("contract setup")

    print("\n---- managed rows after seed ----")
    managed = request_json("GET", "/api/msi/viewer/managed-volumes-compatible")
    require(len(managed) >= 2, f"Expected at least 2 managed rows, got {len(managed)}")

    for row in managed:
        assert_identity_row(row, f"managed:{row.get('display_name')}")
        require(row.get("is_loaded") is False, f"managed row should start unloaded: {row.get('display_name')}")
        require(row.get("hidden") is True, f"managed row should start hidden/unloaded: {row.get('display_name')}")

    print(json.dumps([
        {
            "display_name": row.get("display_name"),
            "dataset_type": row.get("dataset_type"),
            "id": row.get("id"),
            "physical_volume_id": row.get("physical_volume_id"),
            "hidden": row.get("hidden"),
            "is_loaded": row.get("is_loaded"),
            "zarr_url": row.get("zarr_url"),
        }
        for row in managed
    ], indent=2))

    print("\n---- identity audit before load ----")
    audit = assert_audit_ok("before load")
    require(audit.get("loaded_count") == 0, f"Expected loaded_count=0 before load, got {audit.get('loaded_count')}")
    print(json.dumps(audit, indent=2))

    target = next((row for row in managed if row.get("dataset_type") == "3d_volume"), managed[0])
    target_repr = target["msi_representation_id"]

    print("\n---- MSI representation resolver ----")
    resolved = assert_representation_resolver_ok(target_repr)
    print(json.dumps({
        "ok": resolved.get("ok"),
        "representation_id": resolved.get("representation_id"),
        "physical_volume_id": resolved.get("physical_volume_id"),
        "zarr_url": resolved.get("zarr_url"),
        "zarr_exists": resolved.get("zarr_exists"),
        "viewer_ready": resolved.get("viewer_ready"),
        "legacy_volume_exists": resolved.get("legacy_volume_exists"),
    }, indent=2))

    print("\n---- legacy write guard for MSI representation id ----")
    assert_legacy_write_guard_blocks_msi_ids(target_repr)
    print(json.dumps({
        "ok": True,
        "representation_id": target_repr,
        "legacy_patch_status": 409,
        "legacy_delete_status": 409,
    }, indent=2))

    print(f"\n---- load representation: {target_repr} ----")
    loaded_response = request_json("POST", f"/api/msi/representations/{target_repr}/load")
    print(json.dumps(loaded_response, indent=2))
    require(loaded_response.get("loaded") is True, "Load response did not mark loaded=true")

    print("\n---- loaded rows after load ----")
    loaded = request_json("GET", "/api/msi/viewer/loaded-volumes-compatible")
    require(len(loaded) == 1, f"Expected exactly one loaded row after loading one representation, got {len(loaded)}")

    for row in loaded:
        assert_identity_row(row, f"loaded:{row.get('display_name')}")
        require(row.get("is_loaded") is True, "Loaded row must have is_loaded=true")
        require(row.get("hidden") is False, "Loaded row must have hidden=false")

    print(json.dumps([
        {
            "display_name": row.get("display_name"),
            "dataset_type": row.get("dataset_type"),
            "id": row.get("id"),
            "volume_id": row.get("volume_id"),
            "physical_volume_id": row.get("physical_volume_id"),
            "msi_representation_id": row.get("msi_representation_id"),
            "hidden": row.get("hidden"),
            "is_loaded": row.get("is_loaded"),
            "zarr_url": row.get("zarr_url"),
        }
        for row in loaded
    ], indent=2))

    print("\n---- identity audit after load ----")
    audit = assert_audit_ok("after load")
    require(audit.get("loaded_count") == 1, f"Expected loaded_count=1 after load, got {audit.get('loaded_count')}")
    print(json.dumps(audit, indent=2))

    print(f"\n---- unload representation: {target_repr} ----")
    unloaded_response = request_json("POST", f"/api/msi/representations/{target_repr}/unload")
    print(json.dumps(unloaded_response, indent=2))
    require(unloaded_response.get("loaded") is False, "Unload response did not mark loaded=false")

    print("\n---- loaded rows after unload ----")
    loaded_after_unload = request_json("GET", "/api/msi/viewer/loaded-volumes-compatible")
    require(loaded_after_unload == [], f"Expected no loaded rows after unload, got {loaded_after_unload}")
    print(json.dumps(loaded_after_unload, indent=2))

    print("\n---- final identity audit ----")
    audit = assert_audit_ok("after unload")
    require(audit.get("loaded_count") == 0, f"Expected loaded_count=0 after unload, got {audit.get('loaded_count')}")
    print(json.dumps(audit, indent=2))

    print("\n---- MSI ownership audit ----")
    ownership = assert_ownership_audit_ok("contract regression")
    print(json.dumps({
        "ok": ownership.get("ok"),
        "converted_source_count": ownership.get("converted_source_count"),
        "audited_count": ownership.get("audited_count"),
        "issue_count": ownership.get("issue_count"),
    }, indent=2))

    print("\nPASS MSI contract regression test")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
