#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any

BASE = "http://127.0.0.1:8000"


def fetch_json(path: str) -> Any:
    with urllib.request.urlopen(BASE + path, timeout=30) as response:
        body = response.read().decode("utf-8")
        return json.loads(body)


def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "items", "datasets", "volumes", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def find_3d_representation() -> str:
    payload = fetch_json("/api/managed-data/query?limit=200&offset=0")
    for row in rows(payload):
        mode = str(row.get("viewer_mode") or row.get("dataset_type") or row.get("mode") or "").lower()
        rep_id = row.get("representation_id") or row.get("msi_representation_id") or row.get("id")
        if rep_id and "3d" in mode:
            return str(rep_id)
    raise AssertionError("No 3D MSI representation found in Managed Data")


def missing_fields_from_quality(summary: dict[str, Any]) -> list[str]:
    quality = summary.get("metadata_quality") or {}
    fields = quality.get("missing_fields") or []
    return [str(x) for x in fields]


def main() -> int:
    health = fetch_json("/api/msi/health")
    if not isinstance(health, dict) or not health.get("ok"):
        raise AssertionError(f"MSI health failed: {health}")

    rep_id = find_3d_representation()

    docs = fetch_json(f"/api/msi/representations/{rep_id}/documents")
    summary = fetch_json(f"/api/msi/representations/{rep_id}/metadata-summary")

    docs_count = int(docs.get("document_count", len(docs.get("documents", [])))) if isinstance(docs, dict) else 0
    meta_docs = (((summary or {}).get("documents") or {}).get("supporting_documents") or [])
    meta_count = len(meta_docs) if isinstance(meta_docs, list) else 0

    missing_fields = missing_fields_from_quality(summary)
    document_missing = [
        item for item in missing_fields
        if item.lower() == "documents.supporting_documents"
    ]

    result = {
        "representation_id": rep_id,
        "documents_count": docs_count,
        "metadata_summary_documents_count": meta_count,
        "missing_fields": missing_fields,
        "document_missing_entries": document_missing,
        "metadata_quality_recalculated_after_document_enrichment": not document_missing,
        "document_authority": "msi_metadata_summary_document_context",
    }

    print("---- E2E-1C Metadata Completeness Document Authority ----")
    print(json.dumps(result, indent=2, sort_keys=True))

    if docs_count <= 0:
        raise AssertionError("Expected resolved supporting documents for selected representation")
    if docs_count != meta_count:
        raise AssertionError(f"Document count mismatch: documents={docs_count}, metadata-summary={meta_count}")
    if document_missing:
        raise AssertionError("Documents.Supporting Documents still appears in metadata_quality.missing_fields")

    print()
    print("PASS E2E-1C Metadata Completeness Document Authority")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL E2E-1C Metadata Completeness Document Authority: {exc}", file=sys.stderr)
        raise
