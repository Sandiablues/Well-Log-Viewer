#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def fetch_json(base_url: str, path: str, *, timeout: int = 30) -> Any:
    with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body.strip() else None


def post_json(base_url: str, path: str, payload: Any | None = None, *, timeout: int = 30) -> Any:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body.strip() else None


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "items", "datasets", "volumes", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        if all(isinstance(value, dict) for value in payload.values()):
            return [row for row in payload.values() if isinstance(row, dict)]
    return []


def first_id(row: dict[str, Any]) -> str | None:
    for key in ("representation_id", "msi_representation_id", "id", "volume_id", "dataset_id"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def row_mode(row: dict[str, Any]) -> str:
    for key in ("viewer_mode", "dataset_type", "mode", "type"):
        value = row.get(key)
        if value:
            return str(value).lower()
    return ""


def loaded_flag(row: dict[str, Any]) -> bool:
    for key in ("is_loaded", "loaded"):
        if key in row:
            return bool(row.get(key))
    return False


def row_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {rid for row in rows if (rid := first_id(row))}


def dump(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def choose_loaded_3d_row(managed_rows: list[dict[str, Any]], loaded_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    loaded_ids = row_ids(loaded_rows)
    for row in managed_rows:
        rid = first_id(row)
        if rid and "3d" in row_mode(row) and (rid in loaded_ids or loaded_flag(row)):
            return row
    return None


def endpoint_path(representation_id: str, action: str) -> str:
    return f"/api/managed-data/{urllib.parse.quote(representation_id, safe='')}/{action}"


def snapshot(base_url: str, outdir: Path, label: str) -> dict[str, Any]:
    managed_payload = fetch_json(base_url, "/api/managed-data/query?limit=500&offset=0")
    loaded_payload = fetch_json(base_url, "/api/managed-data/loaded")
    msi_payload = fetch_json(base_url, "/api/msi/datasets")
    viewer_payload = fetch_json(base_url, "/api/msi/viewer/managed-volumes-compatible")

    managed_rows = rows_from_payload(managed_payload)
    loaded_rows = rows_from_payload(loaded_payload)
    msi_rows = rows_from_payload(msi_payload)
    viewer_rows = rows_from_payload(viewer_payload)

    dump(outdir / f"managed_data_query_{label}.json", managed_payload)
    dump(outdir / f"managed_data_loaded_{label}.json", loaded_payload)
    dump(outdir / f"msi_datasets_{label}.json", msi_payload)
    dump(outdir / f"viewer_compatible_{label}.json", viewer_payload)

    state = {
        "managed_count": len(managed_rows),
        "loaded_count": len(loaded_rows),
        "msi_dataset_count": len(msi_rows),
        "viewer_compatible_count": len(viewer_rows),
        "managed_ids": sorted(row_ids(managed_rows)),
        "loaded_ids": sorted(row_ids(loaded_rows)),
        "viewer_ids": sorted(row_ids(viewer_rows)),
    }
    dump(outdir / f"state_{label}.json", state)
    return state


def add_failure(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    summary: list[str] = []
    failures: list[str] = []
    restore_messages: list[str] = []
    selected_representation_id: str | None = None
    restore_needed = False

    before: dict[str, Any] = {}
    after_unload: dict[str, Any] = {}
    after_load: dict[str, Any] = {}

    try:
        health = fetch_json(base_url, "/api/msi/health")
        dump(outdir / "msi_health.json", health)
        add_failure(failures, isinstance(health, dict) and bool(health.get("ok")), "MSI health failed")

        managed_payload = fetch_json(base_url, "/api/managed-data/query?limit=500&offset=0")
        loaded_payload = fetch_json(base_url, "/api/managed-data/loaded")
        managed_rows = rows_from_payload(managed_payload)
        loaded_rows = rows_from_payload(loaded_payload)

        before = snapshot(base_url, outdir, "before")
        selected = choose_loaded_3d_row(managed_rows, loaded_rows)
        if selected is None:
            raise RuntimeError("No currently loaded 3D Managed Data row found")

        selected_representation_id = first_id(selected)
        if not selected_representation_id:
            raise RuntimeError("Selected 3D row has no representation ID")

        dump(outdir / "selected_representation.json", selected)
        summary.append(f"selected representation: {selected_representation_id}")
        summary.append(f"display name: {selected.get('display_name') or selected.get('name')}")

        add_failure(failures, selected_representation_id in before["managed_ids"], "Selected row missing from Managed Data before unload")
        add_failure(failures, selected_representation_id in before["loaded_ids"], "Selected row missing from loaded state before unload")
        add_failure(failures, selected_representation_id in before["viewer_ids"], "Selected row missing from viewer-compatible rows before unload")

        dry_unload = post_json(base_url, "/api/managed-data/bulk/unload-selected", {"representation_ids": [selected_representation_id], "dry_run": True})
        dump(outdir / "dry_run_unload_selected.json", dry_unload)
        add_failure(failures, isinstance(dry_unload, dict) and bool(dry_unload.get("ok")) and bool(dry_unload.get("dry_run")), "Dry-run unload failed")

        unload_response = post_json(base_url, endpoint_path(selected_representation_id, "unload"))
        restore_needed = True
        dump(outdir / "unload_response.json", unload_response)
        time.sleep(0.5)

        after_unload = snapshot(base_url, outdir, "after_unload")
        add_failure(failures, selected_representation_id in after_unload["managed_ids"], "Unload removed row from Managed Data")
        add_failure(failures, selected_representation_id not in after_unload["loaded_ids"], "Unload did not remove row from loaded state")
        add_failure(failures, selected_representation_id not in after_unload["viewer_ids"], "Unload did not remove row from viewer-compatible rows")
        add_failure(failures, after_unload["managed_count"] == before["managed_count"], "Managed Data count changed during unload")
        add_failure(failures, after_unload["msi_dataset_count"] == before["msi_dataset_count"], "MSI dataset count changed during unload")

        dry_load = post_json(base_url, "/api/managed-data/bulk/load-selected", {"representation_ids": [selected_representation_id], "dry_run": True})
        dump(outdir / "dry_run_load_selected.json", dry_load)
        add_failure(failures, isinstance(dry_load, dict) and bool(dry_load.get("ok")) and bool(dry_load.get("dry_run")), "Dry-run load failed")

        load_response = post_json(base_url, endpoint_path(selected_representation_id, "load"))
        restore_needed = False
        dump(outdir / "load_response.json", load_response)
        time.sleep(0.5)

        after_load = snapshot(base_url, outdir, "after_load")
        add_failure(failures, selected_representation_id in after_load["managed_ids"], "Load restore removed row from Managed Data")
        add_failure(failures, selected_representation_id in after_load["loaded_ids"], "Load did not restore row to loaded state")
        add_failure(failures, selected_representation_id in after_load["viewer_ids"], "Load did not restore row to viewer-compatible rows")
        add_failure(failures, after_load["managed_count"] == before["managed_count"], "Managed Data count changed after load")
        add_failure(failures, after_load["msi_dataset_count"] == before["msi_dataset_count"], "MSI dataset count changed after load")
        add_failure(failures, set(after_load["loaded_ids"]) == set(before["loaded_ids"]), "Final loaded ID set differs from original")
        add_failure(failures, set(after_load["viewer_ids"]) == set(before["viewer_ids"]), "Final viewer-compatible ID set differs from original")

    except Exception as exc:
        failures.append(f"Unhandled harness exception: {exc}")
    finally:
        if restore_needed and selected_representation_id:
            try:
                post_json(base_url, endpoint_path(selected_representation_id, "load"))
                restore_messages.append("Restore load attempted after failure: completed")
            except Exception as exc:
                restore_messages.append(f"Restore load attempted after failure: FAILED: {exc}")

    try:
        final_state = snapshot(base_url, outdir, "final")
        dump(outdir / "state_final.json", final_state)
    except Exception as exc:
        failures.append(f"Final state fetch failed: {exc}")

    result = {
        "workflow": "E2E-4 Managed Data Load / Unload / Viewer Availability",
        "selected_representation_id": selected_representation_id,
        "before": before,
        "after_unload": after_unload,
        "after_load": after_load,
        "restore_messages": restore_messages,
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }
    dump(outdir / "e2e_4_result.json", result)

    summary.extend([
        f"managed before: {before.get('managed_count')}",
        f"loaded before: {before.get('loaded_count')}",
        f"viewer-compatible before: {before.get('viewer_compatible_count')}",
        f"managed after unload: {after_unload.get('managed_count')}",
        f"loaded after unload: {after_unload.get('loaded_count')}",
        f"viewer-compatible after unload: {after_unload.get('viewer_compatible_count')}",
        f"managed after load: {after_load.get('managed_count')}",
        f"loaded after load: {after_load.get('loaded_count')}",
        f"viewer-compatible after load: {after_load.get('viewer_compatible_count')}",
    ])
    summary.extend(restore_messages)
    if failures:
        summary.append("E2E-4 MANAGED DATA LOAD/UNLOAD: FAIL")
        summary.extend(f"FAIL: {failure}" for failure in failures)
    else:
        summary.append("E2E-4 MANAGED DATA LOAD/UNLOAD: PASS")

    (outdir / "e2e_4_summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))

    checklist = f'''E2E-4 MANUAL BROWSER CHECKLIST

Open app:
open -na "Google Chrome" --args --new-window "{base_url}/"

Manual checks after harness PASS:
1. Go to Data / Managed Data.
2. Confirm the selected 3D row is visible.
3. Confirm the row is loaded/viewer-ready again after the harness restored it.
4. Click eye/view and confirm the 3D viewer opens.
5. Confirm the volume renders.
6. Confirm the row was not deleted from Managed Data.
7. Do not delete, convert, rebuild, upload, clear, or edit data during this check.

Selected representation:
{selected_representation_id or ''}
'''
    (outdir / "manual_browser_checklist.txt").write_text(checklist, encoding="utf-8")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
