#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List

BASE = "http://127.0.0.1:8000"


def request_json(method: str, path: str, payload: Dict[str, Any] | None = None, expected: int = 200) -> Dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8")
    if status != expected:
        raise AssertionError(f"{method} {path} expected {expected}, got {status}: {body[:500]}")
    if not body:
        return {}
    return json.loads(body)


def first_repository(mode: str) -> str:
    payload = request_json("GET", f"/api/source-intake/repositories?mode={mode}")
    repos = payload.get("repositories")
    if not isinstance(repos, list) or not repos:
        raise AssertionError(f"No repositories available for mode={mode}")
    repo_id = str(repos[0].get("repository_id") or "").strip()
    if not repo_id:
        raise AssertionError(f"First repository for mode={mode} has no repository_id")
    return repo_id


def assert_workbench_payload(payload: Dict[str, Any], mode: str, repo_id: str) -> None:
    if payload.get("schema_version") != "source_intake.workbench.v2":
        raise AssertionError(f"schema_version mismatch: {payload.get('schema_version')}")
    if payload.get("public_contract") != "source_intake.workbench":
        raise AssertionError(f"public_contract mismatch: {payload.get('public_contract')}")
    if payload.get("mode") != mode:
        raise AssertionError(f"mode mismatch: {payload.get('mode')} != {mode}")
    if payload.get("repository_id") != repo_id:
        raise AssertionError(f"repository_id mismatch: {payload.get('repository_id')} != {repo_id}")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise AssertionError("rows must be a list")
    if payload.get("row_count") != len(rows):
        raise AssertionError(f"row_count must equal len(rows): {payload.get('row_count')} vs {len(rows)}")
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise AssertionError("summary must be a dict")
    if summary.get("total") != len(rows):
        raise AssertionError(f"summary.total must equal len(rows): {summary.get('total')} vs {len(rows)}")
    actions = payload.get("actions")
    if not isinstance(actions, dict):
        raise AssertionError("actions must be a dict")
    for key in ("use_repository", "clear_selected", "refresh"):
        action = actions.get(key)
        if not isinstance(action, dict):
            raise AssertionError(f"missing action: {key}")
        url = str(action.get("url") or "")
        if "/workbench-v2" in url:
            raise AssertionError(f"public action URL still exposes workbench-v2: {key} -> {url}")
        if "/api/source-intake/workbench" not in url:
            raise AssertionError(f"public action URL is not canonical: {key} -> {url}")


def main() -> None:
    health = request_json("GET", "/api/msi/health")
    if not health.get("ok"):
        raise AssertionError(f"MSI health failed: {health}")

    # Missing repository_id should fail as a validation problem, not as a dead route.
    request_json("GET", "/api/source-intake/workbench?mode=3d", expected=422)

    repo_id = first_repository("3d")
    payload = request_json(
        "POST",
        "/api/source-intake/workbench/use-repository",
        {"mode": "3d", "repository_id": repo_id},
    )
    assert_workbench_payload(payload, "3d", repo_id)

    payload = request_json("GET", f"/api/source-intake/workbench?mode=3d&repository_id={repo_id}")
    assert_workbench_payload(payload, "3d", repo_id)

    # Compatibility route remains backend-owned during migration, but it must return the same schema.
    compat = request_json("GET", f"/api/source-intake/workbench-v2?mode=3d&repository_id={repo_id}")
    if compat.get("schema_version") != "source_intake.workbench.v2":
        raise AssertionError("workbench-v2 compatibility route did not return V2 schema")
    if compat.get("row_count") != len(compat.get("rows") or []):
        raise AssertionError("workbench-v2 row_count invariant failed")

    print("PASS source intake workbench public contract")
    print(json.dumps({
        "mode": "3d",
        "repository_id": repo_id,
        "row_count": payload.get("row_count"),
        "schema_version": payload.get("schema_version"),
        "public_contract": payload.get("public_contract"),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
