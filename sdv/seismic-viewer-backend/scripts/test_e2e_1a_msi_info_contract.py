#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE_URL = "http://127.0.0.1:8000"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def request(method: str, path: str) -> tuple[int, str, bytes]:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            body = response.read()
            content_type = response.headers.get("content-type", "")
            return response.status, content_type, body
    except urllib.error.HTTPError as exc:
        body = exc.read()
        content_type = exc.headers.get("content-type", "")
        return exc.code, content_type, body


def request_json(path: str) -> dict[str, Any] | list[Any]:
    status, content_type, body = request("GET", path)
    text = body.decode("utf-8", errors="replace")
    require(status == 200, f"GET {path} expected 200, got {status}: {text[:500]}")
    try:
        return json.loads(text)
    except Exception as exc:
        raise AssertionError(f"GET {path} did not return JSON. content_type={content_type}, body={text[:500]}") from exc


def encoded(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def as_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "items", "datasets", "volumes", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def first_id(row: dict[str, Any]) -> str | None:
    for key in ("representation_id", "msi_representation_id", "id", "volume_id", "dataset_id"):
        value = row.get(key)
        if value:
            return str(value)
    return None


def select_loaded_3d_representation() -> str:
    payload = request_json("/api/managed-data/query?limit=200&offset=0")
    rows = as_rows(payload)
    for row in rows:
        mode = str(row.get("viewer_mode") or row.get("dataset_type") or row.get("mode") or "").lower()
        rid = first_id(row)
        if rid and "3d" in mode and row.get("loaded") is True:
            return rid
    for row in rows:
        mode = str(row.get("viewer_mode") or row.get("dataset_type") or row.get("mode") or "").lower()
        rid = first_id(row)
        if rid and "3d" in mode:
            return rid
    raise AssertionError("No 3D MSI representation found in Managed Data")


def documents_from_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
    documents_block = summary.get("documents") if isinstance(summary.get("documents"), dict) else {}
    supporting = documents_block.get("supporting_documents")
    return [item for item in supporting if isinstance(item, dict)] if isinstance(supporting, list) else []


def document_keys(items: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (
            str(item.get("document_id") or "").strip(),
            str(item.get("filename") or item.get("original_filename") or "").strip(),
        )
        for item in items
    }


def check_document_access_urls(documents: list[dict[str, Any]]) -> None:
    for item in documents:
        document_id = str(item.get("document_id") or "").strip()
        require(document_id, f"document missing document_id: {item}")
        for key in ("open_url", "download_url"):
            url = str(item.get(key) or "").strip()
            require(url.startswith("/api/documents/"), f"{document_id}: invalid {key}: {url}")
            status, content_type, body = request("GET", url)
            require(status in (200, 206), f"{document_id}: GET {url} expected 200/206, got {status}: {body[:120]!r}")


def main() -> int:
    print("---- E2E-1A MSI Info Page contract ----")
    representation_id = select_loaded_3d_representation()
    encoded_id = encoded(representation_id)
    base = f"/api/msi/representations/{encoded_id}"

    info = request_json(f"{base}/info")
    documents = request_json(f"{base}/documents")
    summary = request_json(f"{base}/metadata-summary")
    normalized = request_json(f"{base}/metadata/normalized")

    require(isinstance(info, dict), "info response is not an object")
    require(isinstance(documents, dict), "documents response is not an object")
    require(isinstance(summary, dict), "metadata-summary response is not an object")
    require(isinstance(normalized, dict), "metadata/normalized response is not an object")

    docs_list = documents.get("documents")
    require(isinstance(docs_list, list), "/documents missing documents list")
    summary_docs = documents_from_summary(summary)

    require(documents.get("msi_representation_id") == representation_id, "/documents representation id mismatch")
    require(documents.get("resolved_by") == "msi_representation_documents_service", "/documents wrong resolver")
    require(documents.get("document_count") == len(docs_list), "/documents document_count mismatch")
    require(documents.get("supporting_document_count") == len(docs_list), "/documents supporting_document_count mismatch")
    require(len(docs_list) == len(summary_docs), f"document count diverges: /documents={len(docs_list)} metadata-summary={len(summary_docs)}")
    require(document_keys(docs_list) == document_keys(summary_docs), "document identities diverge between /documents and metadata-summary")

    check_document_access_urls(docs_list)

    status, content_type, body = request("GET", f"{base}/metadata-score-report")
    text = body.decode("utf-8", errors="replace")
    require(status == 200, f"metadata-score-report expected 200, got {status}")
    require("text/html" in content_type.lower(), f"metadata-score-report expected HTML content-type, got {content_type}")
    require("metadata score report" in text.lower() and ("<html" in text.lower() or "<!doctype html" in text.lower()), "metadata-score-report body does not look like HTML report")

    print(json.dumps({
        "representation_id": representation_id,
        "physical_volume_id": documents.get("physical_volume_id"),
        "documents_count": len(docs_list),
        "metadata_summary_documents_count": len(summary_docs),
        "metadata_score_report_content_type": content_type,
        "metadata_score_report_status": status,
        "document_authority": documents.get("document_authority"),
        "resolved_by": documents.get("resolved_by"),
    }, indent=2, sort_keys=True))

    print("\nPASS E2E-1A MSI Info Page contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
