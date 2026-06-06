from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = "http://127.0.0.1:8000"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def request_json(path: str, method: str = "GET") -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method=method)

    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{method} {path} failed: HTTP {exc.code}: {body}") from exc

    return json.loads(raw)


def main() -> int:
    print("---- storage migration-plan review export contract ----")

    payload = request_json("/api/storage/migration-plan/export", method="POST")

    summary = {
        "ok": payload.get("ok"),
        "service": payload.get("service"),
        "export_mode": payload.get("export_mode"),
        "candidate_count": payload.get("candidate_count"),
        "json_uri": payload.get("json_uri"),
        "csv_uri": payload.get("csv_uri"),
        "copy_or_move_performed": payload.get("copy_or_move_performed"),
        "msi_rewrite_performed": payload.get("msi_rewrite_performed"),
        "artifact_migration_performed": payload.get("artifact_migration_performed"),
        "resolved_by": payload.get("resolved_by"),
    }
    print(json.dumps(summary, indent=2))

    require(payload.get("ok") is True, "export ok != true")
    require(payload.get("service") == "storage", "wrong service marker")
    require(payload.get("export_mode") == "review_manifest_only", "wrong export mode")
    require(payload.get("resolved_by") == "end_seismic_repository_storage_service", "wrong resolver marker")
    require(payload.get("copy_or_move_performed") is False, "export must not copy or move artifacts")
    require(payload.get("msi_rewrite_performed") is False, "export must not rewrite MSI")
    require(payload.get("artifact_migration_performed") is False, "export must not migrate artifacts")

    json_path = Path(str(payload.get("json_path") or ""))
    csv_path = Path(str(payload.get("csv_path") or ""))

    require(json_path.exists() and json_path.is_file(), "JSON review export file was not created")
    require(csv_path.exists() and csv_path.is_file(), "CSV review export file was not created")
    require("End_Seismic_Data_Repository" in str(json_path), "JSON export is outside End repository")
    require("End_Seismic_Data_Repository" in str(csv_path), "CSV export is outside End repository")
    require("/manifests/" in str(json_path), "JSON export is not under manifests")
    require("/manifests/" in str(csv_path), "CSV export is not under manifests")

    exported = json.loads(json_path.read_text(encoding="utf-8"))
    require(exported.get("export_mode") == "review_manifest_only", "exported JSON mode mismatch")
    require(exported.get("policy", {}).get("copy_or_move_performed") is False, "exported JSON must not indicate copy/move")
    require(exported.get("policy", {}).get("msi_rewrite_performed") is False, "exported JSON must not indicate MSI rewrite")
    require(isinstance(exported.get("candidates"), list), "exported candidates must be a list")
    require(exported.get("candidate_count") == len(exported.get("candidates")), "exported candidate_count mismatch")

    csv_text = csv_path.read_text(encoding="utf-8")
    require("artifact_kind,name,current_path" in csv_text.splitlines()[0], "CSV header is missing expected fields")

    print("\nPASS storage migration-plan review export contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
