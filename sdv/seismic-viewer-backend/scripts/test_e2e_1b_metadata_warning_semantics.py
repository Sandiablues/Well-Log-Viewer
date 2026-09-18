#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any

BASE = "http://127.0.0.1:8000"
OLD_WARNING = "Dataset has no repository source metadata."
REPOSITORY_WARNING = "Repository-backed dataset is missing Source Repository metadata."


def fetch_json(path: str) -> Any:
    with urllib.request.urlopen(BASE + path, timeout=20) as response:
        body = response.read().decode("utf-8")
        try:
            return json.loads(body)
        except Exception as exc:
            raise AssertionError(f"Expected JSON from {path}, got: {body[:200]!r}") from exc


def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "items", "datasets", "volumes", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def first_3d_representation() -> str:
    payload = fetch_json("/api/managed-data/query?limit=200&offset=0")
    for row in rows(payload):
        mode = str(row.get("viewer_mode") or row.get("dataset_type") or row.get("mode") or "").lower()
        rid = row.get("representation_id") or row.get("msi_representation_id") or row.get("id")
        if rid and "3d" in mode:
            return str(rid)
    raise AssertionError("No managed 3D representation found for E2E-1B test.")


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def main() -> None:
    health = fetch_json("/api/msi/health")
    if not isinstance(health, dict) or not health.get("ok"):
        fail(f"MSI health failed: {health}")

    rid = first_3d_representation()
    summary = fetch_json(f"/api/msi/representations/{rid}/metadata-summary")
    info = fetch_json(f"/api/msi/representations/{rid}/info")

    if not isinstance(summary, dict):
        fail("metadata-summary did not return an object")
    if not isinstance(info, dict):
        fail("info did not return an object")

    source = summary.get("source") or {}
    warnings = summary.get("warnings") or []
    info_warnings = info.get("warnings") or []

    if OLD_WARNING in warnings or OLD_WARNING in info_warnings:
        fail("obsolete repository-source warning is still present")

    source_type = str(source.get("source_type") or "").lower()
    lineage_status = source.get("lineage_status")
    lineage_message = source.get("lineage_message")
    repository_required = bool(source.get("repository_required"))

    if source_type == "manual_upload":
        if repository_required:
            fail("manual_upload source incorrectly marks repository_required=true")
        if lineage_status != "manual_upload":
            fail(f"manual_upload source has wrong lineage_status: {lineage_status!r}")
        if not lineage_message or "Manual Upload" not in lineage_message:
            fail(f"manual_upload source missing lineage_message: {lineage_message!r}")
        if REPOSITORY_WARNING in warnings or REPOSITORY_WARNING in info_warnings:
            fail("manual_upload source incorrectly emits repository-backed warning")

    documents = ((summary.get("documents") or {}).get("supporting_documents") or [])
    if len(documents) <= 0:
        fail("expected supporting documents to remain linked")

    result = {
        "representation_id": rid,
        "source_type": source.get("source_type"),
        "lineage_status": lineage_status,
        "lineage_message": lineage_message,
        "repository_required": repository_required,
        "warnings": warnings,
        "info_warnings": info_warnings,
        "supporting_document_count": len(documents),
    }
    print("---- E2E-1B Metadata Warning Semantics ----")
    print(json.dumps(result, indent=2, sort_keys=True))
    print("PASS E2E-1B metadata warning semantics")


if __name__ == "__main__":
    main()
