#!/usr/bin/env python3
"""E2E-3: Source Intake document continuity to MSI Info Page.

Read-only harness. It validates that Source Intake/Workbench document state,
MSI representation documents, metadata-summary supporting_documents, and
metadata-quality missing fields agree for the current managed 3D dataset.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

BASE = os.environ.get("SEISMIC_VIEWER_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
PROJECT = Path(os.environ.get("SEISMIC_VIEWER_PROJECT", str(Path.home() / "Applications/MultiViewer/seismic_viewer_project")))
BACKEND = PROJECT / "seismic-viewer-backend"
DOWNLOADS = Path.home() / "Downloads"
STAMP = time.strftime("%Y%m%d_%H%M%S")
OUTDIR = DOWNLOADS / f"e2e_3_source_intake_document_continuity_{STAMP}"
ZIP_PATH = DOWNLOADS / f"e2e_3_source_intake_document_continuity_{STAMP}.zip"


def fail(message: str) -> None:
    raise AssertionError(message)


def request(path_or_url: str, *, method: str = "GET", payload: Optional[dict] = None, headers: Optional[dict] = None, read_limit: Optional[int] = None) -> Tuple[int, Dict[str, str], bytes]:
    url = path_or_url if path_or_url.startswith("http") else BASE + path_or_url
    body = None
    req_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers["content-type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if read_limit is None:
                data = response.read()
            else:
                data = response.read(read_limit)
            return response.status, {k.lower(): v for k, v in response.headers.items()}, data
    except urllib.error.HTTPError as exc:
        data = exc.read(read_limit or 4096)
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, data


def fetch_json(path: str) -> Any:
    status, headers, body = request(path)
    if status < 200 or status >= 300:
        fail(f"{path} returned HTTP {status}: {body[:300]!r}")
    try:
        return json.loads(body.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        fail(f"{path} did not return JSON: {exc}; content-type={headers.get('content-type')}; sample={body[:300]!r}")


def write_json(name: str, payload: Any) -> None:
    (OUTDIR / f"{name}.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def as_rows(payload: Any) -> List[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "items", "datasets", "volumes", "repositories", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def get_first(row: dict, keys: Iterable[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def extract_source_segy_id(representation_id: str) -> Optional[str]:
    marker = "msi_repr:source_segy_"
    if not representation_id.startswith(marker):
        return None
    remainder = representation_id[len(marker):]
    return remainder.split(":", 1)[0] if ":" in remainder else remainder


def doc_count_from_documents_payload(payload: Any) -> Tuple[int, List[dict]]:
    if isinstance(payload, dict):
        docs = payload.get("documents")
        if isinstance(docs, list):
            return int(payload.get("document_count", len(docs)) or len(docs)), [x for x in docs if isinstance(x, dict)]
        supporting = payload.get("supporting_documents")
        if isinstance(supporting, list):
            return len(supporting), [x for x in supporting if isinstance(x, dict)]
    if isinstance(payload, list):
        docs = [x for x in payload if isinstance(x, dict)]
        return len(docs), docs
    return 0, []


def supporting_docs_from_metadata_summary(payload: Any) -> List[dict]:
    if not isinstance(payload, dict):
        return []
    candidates = [
        payload.get("supporting_documents"),
        (payload.get("documents") or {}).get("supporting_documents") if isinstance(payload.get("documents"), dict) else None,
    ]
    for value in candidates:
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def flatten_missing_fields(metadata_summary: Any) -> List[str]:
    if not isinstance(metadata_summary, dict):
        return []
    mq = metadata_summary.get("metadata_quality") or metadata_summary.get("quality") or {}
    result: List[str] = []
    if isinstance(mq, dict):
        for key in ("missing_fields", "missing", "missing_required", "required_missing"):
            value = mq.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        result.append(item)
                    elif isinstance(item, dict):
                        result.append(str(item.get("field") or item.get("name") or item))
    return result


def route_from_doc(doc: dict, kind: str) -> Optional[str]:
    keys = {
        "open": ("open_url", "open", "url"),
        "view": ("view_url", "view"),
        "download": ("download_url", "download"),
    }[kind]
    value = get_first(doc, keys)
    if isinstance(value, str) and value:
        return value
    doc_id = doc.get("document_id") or doc.get("id")
    if isinstance(doc_id, str) and doc_id:
        return f"/api/documents/{urllib.parse.quote(doc_id)}/{kind}"
    return None


def validate_document_link(doc: dict, kind: str) -> dict:
    route = route_from_doc(doc, kind)
    if not route:
        return {"kind": kind, "status": None, "ok": False, "reason": "missing route"}
    status, headers, body = request(route, headers={"Range": "bytes=0-1023"}, read_limit=2048)
    ok = status in (200, 206)
    return {
        "kind": kind,
        "route": route,
        "status": status,
        "content_type": headers.get("content-type"),
        "body_length_sample": len(body),
        "ok": ok,
    }


def bundle_output() -> None:
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in OUTDIR.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(OUTDIR.parent))


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    summary: List[str] = []
    failures: List[str] = []

    def check(condition: bool, message: str) -> None:
        if condition:
            summary.append(f"PASS: {message}")
        else:
            summary.append(f"FAIL: {message}")
            failures.append(message)

    readme = [
        "E2E-3 — SOURCE INTAKE DOCUMENT / INFO PAGE CONTINUITY",
        f"Timestamp: {time.ctime()}",
        f"Project: {PROJECT}",
        f"Base URL: {BASE}",
        "Read-only harness. No upload/delete/convert/rebuild/clear/load/unload.",
        "",
    ]
    (OUTDIR / "README.txt").write_text("\n".join(readme), encoding="utf-8")

    health = fetch_json("/api/msi/health")
    write_json("msi_health", health)
    check(bool(isinstance(health, dict) and health.get("ok")), "MSI health is OK")

    managed = fetch_json("/api/managed-data/query?limit=200&offset=0")
    loaded = fetch_json("/api/managed-data/loaded")
    msi_datasets = fetch_json("/api/msi/datasets")
    viewer = fetch_json("/api/msi/viewer/managed-volumes-compatible")
    repos = fetch_json("/api/source-intake/repositories?mode=3d")
    write_json("managed_data_query", managed)
    write_json("managed_data_loaded", loaded)
    write_json("msi_datasets", msi_datasets)
    write_json("viewer_managed_volumes_compatible", viewer)
    write_json("source_intake_repositories_3d", repos)

    managed_rows = as_rows(managed)
    loaded_rows = as_rows(loaded)
    viewer_rows = as_rows(viewer)
    repo_rows = as_rows(repos)

    selected: Optional[dict] = None
    for row in managed_rows:
        mode = str(get_first(row, ("viewer_mode", "dataset_type", "mode")) or "").lower()
        rid = get_first(row, ("representation_id", "msi_representation_id", "id"))
        loaded_flag = row.get("loaded") if "loaded" in row else row.get("is_loaded")
        lifecycle = str(get_first(row, ("lifecycle", "lifecycle_state", "state", "status")) or "").lower()
        if rid and "3d" in mode and loaded_flag is True and "viewer_ready" in lifecycle:
            selected = row
            break
    if selected is None:
        for row in managed_rows:
            mode = str(get_first(row, ("viewer_mode", "dataset_type", "mode")) or "").lower()
            rid = get_first(row, ("representation_id", "msi_representation_id", "id"))
            if rid and "3d" in mode:
                selected = row
                break

    check(selected is not None, "selected 3D managed representation exists")
    if selected is None:
        raise AssertionError("No 3D managed representation available for E2E-3")

    representation_id = str(get_first(selected, ("representation_id", "msi_representation_id", "id")))
    source_segy_id = extract_source_segy_id(representation_id)
    selected_info = {
        "representation_id": representation_id,
        "source_segy_id": source_segy_id,
        "display_name": selected.get("display_name") or selected.get("name"),
        "raw": selected,
    }
    write_json("selected_representation", selected_info)
    summary.append(f"selected representation: {representation_id}")
    summary.append(f"source SEG-Y id: {source_segy_id}")

    repo_id = None
    for repo in repo_rows:
        candidate_count = int(repo.get("candidate_count") or repo.get("line_count") or repo.get("segy_file_count") or 0)
        doc_count = int(repo.get("document_count") or repo.get("documents_count") or 0)
        rid = repo.get("repository_id") or repo.get("id")
        if rid and (candidate_count > 0 or doc_count > 0):
            repo_id = rid
            break
    check(repo_id is not None, "3D source repository is discoverable")
    if repo_id is None:
        raise AssertionError("No 3D source repository found")
    summary.append(f"selected repository: {repo_id}")

    workbench = fetch_json(f"/api/source-intake/workbench?mode=3d&repository_id={urllib.parse.quote(str(repo_id))}")
    write_json("source_intake_workbench_3d", workbench)
    workbench_rows = as_rows(workbench)
    check(len(workbench_rows) > 0, "Workbench has active rows for selected 3D repository")

    matching_row = None
    if source_segy_id:
        for row in workbench_rows:
            ids = [row.get("source_segy_file_id"), row.get("candidate_id"), row.get("line_id")]
            managed_output = row.get("managed_output") if isinstance(row.get("managed_output"), dict) else {}
            ids.append(managed_output.get("representation_id"))
            if source_segy_id in ids or representation_id in ids:
                matching_row = row
                break
    check(matching_row is not None, "Workbench row matches selected MSI/source SEG-Y representation")
    if matching_row is None:
        write_json("workbench_rows_no_match", workbench_rows)
        raise AssertionError("Could not match selected MSI representation to Workbench row")
    write_json("matching_workbench_row", matching_row)

    wb_doc_count = int(matching_row.get("supporting_document_count") or matching_row.get("document_count") or 0)
    check(wb_doc_count > 0, f"Workbench matching row reports supporting documents > 0 (found {wb_doc_count})")

    docs_payload = fetch_json(f"/api/msi/representations/{urllib.parse.quote(representation_id, safe='')}/documents")
    metadata_summary = fetch_json(f"/api/msi/representations/{urllib.parse.quote(representation_id, safe='')}/metadata-summary")
    normalized = fetch_json(f"/api/msi/representations/{urllib.parse.quote(representation_id, safe='')}/metadata/normalized")
    write_json("msi_documents", docs_payload)
    write_json("msi_metadata_summary", metadata_summary)
    write_json("msi_metadata_normalized", normalized)

    docs_count, docs = doc_count_from_documents_payload(docs_payload)
    metadata_docs = supporting_docs_from_metadata_summary(metadata_summary)
    metadata_count = len(metadata_docs)

    summary.append(f"workbench supporting document count: {wb_doc_count}")
    summary.append(f"MSI documents count: {docs_count}")
    summary.append(f"metadata-summary supporting document count: {metadata_count}")

    check(docs_count > 0, "MSI /documents returns supporting documents")
    check(metadata_count > 0, "metadata-summary returns supporting documents")
    check(docs_count == metadata_count, "/documents count equals metadata-summary supporting_documents count")
    check(docs_count >= wb_doc_count, "MSI document count includes at least the Workbench source documents")

    missing_fields = flatten_missing_fields(metadata_summary)
    write_json("metadata_quality_missing_fields", missing_fields)
    check("Documents.Supporting Documents" not in missing_fields, "Supporting documents are not listed as missing")
    repo_warning_text = json.dumps(metadata_summary).lower()
    check("dataset has no repository source metadata" not in repo_warning_text, "stale repository-source warning is absent")

    doc_summaries = []
    for doc in docs:
        doc_summaries.append({
            "document_id": doc.get("document_id") or doc.get("id"),
            "filename": doc.get("filename") or doc.get("name"),
            "open_url": route_from_doc(doc, "open"),
            "view_url": route_from_doc(doc, "view"),
            "download_url": route_from_doc(doc, "download"),
        })
    write_json("document_url_inventory", doc_summaries)

    check(all(d.get("document_id") for d in doc_summaries), "Every document has a document_id")
    check(all(d.get("open_url") for d in doc_summaries), "Every document has an open URL or resolvable open route")
    check(all(d.get("download_url") for d in doc_summaries), "Every document has a download URL or resolvable download route")

    link_results = []
    for doc in docs[: min(3, len(docs))]:
        for kind in ("open", "download"):
            link_results.append(validate_document_link(doc, kind))
    write_json("document_link_probe_results", link_results)
    check(all(x.get("ok") for x in link_results), "Sample document open/download routes return 200 or 206")

    before_counts = {
        "managed": len(managed_rows),
        "loaded": len(loaded_rows),
        "msi_datasets": len(as_rows(msi_datasets)),
    }
    managed_after = fetch_json("/api/managed-data/query?limit=200&offset=0")
    loaded_after = fetch_json("/api/managed-data/loaded")
    msi_after = fetch_json("/api/msi/datasets")
    after_counts = {
        "managed": len(as_rows(managed_after)),
        "loaded": len(as_rows(loaded_after)),
        "msi_datasets": len(as_rows(msi_after)),
    }
    write_json("state_counts_before_after", {"before": before_counts, "after": after_counts})
    check(before_counts == after_counts, "Managed/loaded/MSI counts unchanged by E2E-3")

    bundle_check = {}
    for label, index_path in {
        "frontend": PROJECT / "seismic-viewer-frontend/dist/index.html",
        "packaged": BACKEND / "packaged_dist/index.html",
    }.items():
        text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        marker = "assets/index-"
        start = text.find(marker)
        bundle_check[label] = text[start:text.find('.js', start)+3] if start >= 0 else None
    status, headers, body = request("/", read_limit=4096)
    body_text = body.decode("utf-8", errors="replace")
    marker = "assets/index-"
    start = body_text.find(marker)
    bundle_check["served"] = body_text[start:body_text.find('.js', start)+3] if start >= 0 else None
    write_json("frontend_bundle_check", bundle_check)
    check(bundle_check.get("frontend") == bundle_check.get("packaged") == bundle_check.get("served") and bundle_check.get("served"), "frontend/packaged/served bundles match")

    manual = f"""E2E-3 MANUAL CHECKLIST\n\nOpen app:\nopen -na \"Google Chrome\" --args --new-window \"{BASE}/\"\n\nManual checks:\n1. Go to Sources / Source Intake.\n2. Confirm the selected 3D repository workbench contains the managed FN923F0001 row.\n3. Confirm that row shows supporting/source documents count, not zero.\n4. Go to Data / Managed Data.\n5. Open Info Page for the same 3D row.\n6. Confirm Supporting Documents shows {docs_count} documents.\n7. Confirm Documents.Supporting Documents is not listed under Missing.\n8. Confirm the stale repository-source warning is absent.\n9. Open at least two document links.\n10. Confirm no 'Registered document file is not available' error.\n\nDo not upload, delete, clear, convert, rebuild, load, or unload during this test.\n"""
    (OUTDIR / "manual_browser_checklist.txt").write_text(manual, encoding="utf-8")

    status_text = "PASS" if not failures else "FAIL"
    summary.insert(0, f"E2E-3 SOURCE INTAKE DOCUMENT / INFO PAGE CONTINUITY: {status_text}")
    if failures:
        summary.append("")
        summary.append("Failures:")
        summary.extend(f"- {x}" for x in failures)
    (OUTDIR / "e2e_3_summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))

    bundle_output()
    print(f"\nResult bundle: {ZIP_PATH}")
    return 0 if not failures else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        OUTDIR.mkdir(parents=True, exist_ok=True)
        (OUTDIR / "harness_exception.txt").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        print(f"E2E-3 HARNESS ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        try:
            bundle_output()
            print(f"Result bundle: {ZIP_PATH}", file=sys.stderr)
        except Exception:
            pass
        raise
