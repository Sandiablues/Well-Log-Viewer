from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any


BASE_URL = "http://127.0.0.1:8000"


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


def main() -> int:
    print("---- storage migration-plan contract ----")

    payload = request_json("/api/storage/migration-plan")

    summary = {
        "ok": payload.get("ok"),
        "service": payload.get("service"),
        "plan_mode": payload.get("plan_mode"),
        "summary": payload.get("summary"),
        "policy": payload.get("policy"),
        "resolved_by": payload.get("resolved_by"),
    }
    print(json.dumps(summary, indent=2))

    require(payload.get("ok") is True, "migration plan ok != true")
    require(payload.get("service") == "storage", "migration plan service marker mismatch")
    require(payload.get("plan_mode") == "read_only", "migration plan must be read_only")
    require(payload.get("resolved_by") == "end_seismic_repository_storage_service", "wrong resolver marker")

    candidates = payload.get("candidates")
    require(isinstance(candidates, list), "candidates must be a list")

    summary_payload = payload.get("summary") or {}
    require(summary_payload.get("candidate_count") == len(candidates), "candidate_count mismatch")
    require(summary_payload.get("copy_or_move_performed") is False, "migration plan must not copy or move")
    require(summary_payload.get("msi_rewrite_performed") is False, "migration plan must not rewrite MSI")

    policy = payload.get("policy") or {}
    require(policy.get("status") == "plan_only", "migration plan policy must be plan_only")
    require(policy.get("copy_or_move_performed") is False, "policy must not copy or move")
    require(policy.get("msi_rewrite_performed") is False, "policy must not rewrite MSI")
    require(policy.get("requires_review_before_execution") is True, "policy must require review before execution")

    required_candidate_keys = {
        "artifact_kind",
        "current_path",
        "current_uri",
        "name",
        "exists",
        "is_dir",
        "size_bytes",
        "inferred_dimension",
        "suggested_endrepo_uri",
        "migration_status",
        "confidence",
        "review_required",
        "notes",
    }

    for candidate in candidates:
        require(isinstance(candidate, dict), "candidate must be dict")
        missing = required_candidate_keys - set(candidate.keys())
        require(not missing, f"candidate missing keys: {sorted(missing)}")
        require(candidate.get("confidence") in {"high", "medium", "low"}, "invalid confidence value")
        require(isinstance(candidate.get("review_required"), bool), "review_required must be bool")
        require(isinstance(candidate.get("notes"), list), "notes must be list")

    print("\nPASS storage migration-plan contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
