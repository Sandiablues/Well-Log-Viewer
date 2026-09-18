#!/usr/bin/env python3
"""
E2E-HARNESS-1 — Existing Managed 3D Viewer Workflow Contract Test

Read-only contract harness for the demo-critical existing managed 3D viewer path.
It validates backend contracts and writes a result bundle for manual browser QA.

This script must not upload, delete, clear, convert, rebuild, load, or unload data.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
from pathlib import Path
import sys
import textwrap
import urllib.error
import urllib.request
import zipfile

JSON = dict[str, object] | list[object] | str | int | float | bool | None


def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


class HttpResult:
    def __init__(self, url: str, status: int, content_type: str, body: bytes):
        self.url = url
        self.status = status
        self.content_type = content_type
        self.body = body

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def as_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "status": self.status,
            "content_type": self.content_type,
            "body_length": len(self.body),
            "body_sample": self.text[:500],
        }


class Harness:
    def __init__(self, base_url: str, outdir: Path):
        self.base = base_url.rstrip("/")
        self.outdir = outdir
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.summary: list[str] = []

    def record(self, message: str) -> None:
        self.summary.append(message)
        print(message)

    def fail(self, message: str) -> None:
        self.failures.append(message)
        self.record(f"FAIL: {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        self.record(f"WARN: {message}")

    def request(self, path: str, timeout: int = 25) -> HttpResult:
        url = self.base + path
        req = urllib.request.Request(url, headers={"Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read()
                return HttpResult(
                    url=url,
                    status=response.status,
                    content_type=response.headers.get("content-type", ""),
                    body=body,
                )
        except urllib.error.HTTPError as exc:
            body = exc.read()
            return HttpResult(
                url=url,
                status=exc.code,
                content_type=exc.headers.get("content-type", ""),
                body=body,
            )

    def fetch_json(self, name: str, path: str, require_2xx: bool = True) -> JSON | None:
        result = self.request(path)
        write_text(self.outdir / f"{name}.raw", result.text)
        write_json(self.outdir / f"{name}.response.json", result.as_dict())
        if require_2xx and not (200 <= result.status < 300):
            self.fail(f"{name} returned HTTP {result.status} for {path}")
            return None
        try:
            payload = json.loads(result.text)
        except Exception as exc:
            self.fail(f"{name} did not return JSON for {path}: {exc}")
            return None
        write_json(self.outdir / f"{name}.json", payload)
        self.record(f"PASS: {name} JSON {path}")
        return payload

    def fetch_html_report(self, name: str, path: str) -> None:
        result = self.request(path)
        write_text(self.outdir / f"{name}.html", result.text)
        write_json(self.outdir / f"{name}.response.json", result.as_dict())
        if result.status != 200:
            self.fail(f"{name} returned HTTP {result.status}")
            return
        if "text/html" not in result.content_type.lower():
            self.fail(f"{name} content-type is not text/html: {result.content_type}")
            return
        if len(result.body) <= 0:
            self.fail(f"{name} returned empty HTML body")
            return
        self.record(f"PASS: {name} HTML report route {path}")

    @staticmethod
    def as_rows(payload: JSON | None) -> list[dict[str, object]]:
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            for key in ("rows", "items", "datasets", "volumes", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [x for x in value if isinstance(x, dict)]
        return []

    @staticmethod
    def first_value(row: dict[str, object], keys: tuple[str, ...]) -> object | None:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return value
        return None

    @classmethod
    def representation_id(cls, row: dict[str, object]) -> str | None:
        value = cls.first_value(
            row,
            (
                "representation_id",
                "msi_representation_id",
                "id",
                "volume_id",
                "dataset_id",
            ),
        )
        return str(value) if value else None

    @classmethod
    def mode(cls, row: dict[str, object]) -> str:
        value = cls.first_value(row, ("viewer_mode", "dataset_type", "mode", "type"))
        return str(value or "").lower()

    @classmethod
    def lifecycle(cls, row: dict[str, object]) -> str:
        value = cls.first_value(row, ("lifecycle", "lifecycle_state", "state", "status"))
        return str(value or "").lower()

    @staticmethod
    def loaded(row: dict[str, object]) -> bool:
        value = row.get("loaded", row.get("is_loaded", False))
        return bool(value)

    def select_existing_managed_3d(self, managed_rows: list[dict[str, object]]) -> dict[str, object] | None:
        candidates = []
        for row in managed_rows:
            rid = self.representation_id(row)
            if rid and "3d" in self.mode(row):
                candidates.append(row)
        write_json(self.outdir / "selected_3d_candidates.json", candidates)
        self.record(f"3D managed candidate rows: {len(candidates)}")
        if not candidates:
            self.fail("No 3D managed rows found")
            return None

        for row in candidates:
            lifecycle = self.lifecycle(row)
            if self.loaded(row) and ("viewer_ready" in lifecycle or lifecycle in {"ready", "loaded", ""}):
                return row
        self.warn("No loaded viewer_ready 3D row found; selecting first 3D candidate for diagnostics")
        return candidates[0]

    @staticmethod
    def document_count(payload: JSON | None) -> int:
        if isinstance(payload, dict):
            value = payload.get("document_count")
            if isinstance(value, int):
                return value
            docs = payload.get("documents")
            if isinstance(docs, list):
                return len(docs)
        if isinstance(payload, list):
            return len(payload)
        return 0

    @staticmethod
    def metadata_summary_document_count(payload: JSON | None) -> int:
        if not isinstance(payload, dict):
            return 0
        docs_node = payload.get("documents")
        if isinstance(docs_node, dict):
            supporting = docs_node.get("supporting_documents")
            if isinstance(supporting, list):
                return len(supporting)
        supporting = payload.get("supporting_documents")
        if isinstance(supporting, list):
            return len(supporting)
        return 0

    def validate_viewer_match(self, rid: str, viewer_rows: list[dict[str, object]]) -> None:
        direct_match = False
        inventory: list[list[object]] = []
        for row in viewer_rows:
            ids = [
                row.get(key)
                for key in ("id", "volume_id", "representation_id", "msi_representation_id", "dataset_id")
                if row.get(key)
            ]
            inventory.append(ids)
            if rid in ids:
                direct_match = True
        write_json(self.outdir / "viewer_id_inventory.json", inventory)
        if direct_match:
            self.record("PASS: selected MSI representation appears in viewer-compatible rows")
        else:
            self.fail("Selected MSI representation does not appear in viewer-compatible rows")

    def write_manual_checklist(self) -> None:
        checklist = f"""
        E2E-1 MANUAL BROWSER CHECKLIST

        Open app:
        open -na "Google Chrome" --args --new-window "{self.base}/"

        Manual checks:
        1. Go to Data / Managed Data.
        2. Confirm the existing 3D row is visible.
        3. Confirm it is shown as loaded/viewer-ready.
        4. Click the eye/view action.
        5. Confirm the app opens the 3D viewer, not the 2D viewer.
        6. Confirm the volume renders.
        7. Open the Info Page for the same row.
        8. Confirm metadata loads.
        9. Confirm Supporting Documents section appears once only.
        10. Click one SR-origin document, if present.
        11. Click one MD-uploaded document, if present.
        12. Confirm no "Registered document file is not available" error.

        Do not upload, delete, clear, convert, rebuild, load, or unload during this test.
        """
        write_text(self.outdir / "manual_browser_checklist.txt", textwrap.dedent(checklist).strip() + "\n")

    def run(self) -> int:
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.record("E2E-1 — Existing Managed 3D Viewer Workflow")
        self.record(f"Timestamp: {_dt.datetime.now()}")
        self.record(f"Base URL: {self.base}")
        self.record("Read-only harness: no upload/delete/convert/rebuild/clear/load/unload")

        health = self.fetch_json("msi_health", "/api/msi/health")
        if not isinstance(health, dict) or not health.get("ok"):
            self.fail("MSI health did not return ok=true")

        managed = self.fetch_json("managed_data_query", "/api/managed-data/query?limit=200&offset=0")
        loaded = self.fetch_json("managed_data_loaded", "/api/managed-data/loaded")
        datasets = self.fetch_json("msi_datasets", "/api/msi/datasets")
        viewer = self.fetch_json("viewer_managed_volumes_compatible", "/api/msi/viewer/managed-volumes-compatible")
        volumes = self.fetch_json("volumes", "/api/volumes")

        managed_rows = self.as_rows(managed)
        loaded_rows = self.as_rows(loaded)
        dataset_rows = self.as_rows(datasets)
        viewer_rows = self.as_rows(viewer)
        volume_rows = self.as_rows(volumes)

        write_json(self.outdir / "normalized_managed_rows.json", managed_rows)
        write_json(self.outdir / "normalized_loaded_rows.json", loaded_rows)
        write_json(self.outdir / "normalized_msi_datasets.json", dataset_rows)
        write_json(self.outdir / "normalized_viewer_rows.json", viewer_rows)
        write_json(self.outdir / "normalized_volumes.json", volume_rows)

        self.record(f"managed rows: {len(managed_rows)}")
        self.record(f"loaded rows: {len(loaded_rows)}")
        self.record(f"MSI datasets: {len(dataset_rows)}")
        self.record(f"viewer-compatible rows: {len(viewer_rows)}")
        self.record(f"legacy /api/volumes rows: {len(volume_rows)}")

        selected = self.select_existing_managed_3d(managed_rows)
        if not selected:
            return self.finish()

        rid = self.representation_id(selected)
        assert rid is not None
        display_name = selected.get("display_name") or selected.get("name")
        self.record(f"selected representation: {rid}")
        self.record(f"display name: {display_name}")
        self.record(f"loaded: {self.loaded(selected)}")
        self.record(f"lifecycle: {self.lifecycle(selected)}")

        write_json(self.outdir / "selected_managed_3d_row.json", selected)

        json_paths = {
            "msi_info": f"/api/msi/representations/{rid}/info",
            "msi_documents": f"/api/msi/representations/{rid}/documents",
            "msi_metadata_summary": f"/api/msi/representations/{rid}/metadata-summary",
            "msi_metadata_normalized": f"/api/msi/representations/{rid}/metadata/normalized",
        }
        outputs: dict[str, JSON | None] = {}
        for name, path in json_paths.items():
            outputs[name] = self.fetch_json(name, path)

        self.fetch_html_report("msi_metadata_score_report", f"/api/msi/representations/{rid}/metadata-score-report")

        docs_count = self.document_count(outputs.get("msi_documents"))
        meta_docs_count = self.metadata_summary_document_count(outputs.get("msi_metadata_summary"))
        self.record(f"documents count: {docs_count}")
        self.record(f"metadata-summary document count: {meta_docs_count}")
        if docs_count == meta_docs_count:
            self.record("PASS: /documents and /metadata-summary document counts agree")
        else:
            self.fail("/documents count differs from /metadata-summary supporting_documents count")

        self.validate_viewer_match(rid, viewer_rows)
        if not self.failures:
            self.write_manual_checklist()
            self.record("PASS: manual_browser_checklist.txt generated")
        return self.finish()

    def finish(self) -> int:
        result = {
            "status": "PASS" if not self.failures else "FAIL",
            "failure_count": len(self.failures),
            "warning_count": len(self.warnings),
            "failures": self.failures,
            "warnings": self.warnings,
            "summary": self.summary,
        }
        write_json(self.outdir / "e2e_1_result.json", result)
        write_text(self.outdir / "e2e_1_contract_summary.txt", "\n".join(self.summary) + "\n")
        self.record(f"E2E-1 CONTRACT STATUS: {result['status']}")
        return 0 if not self.failures else 1


def zip_dir(src: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in src.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(src.parent))


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only E2E harness for existing managed 3D viewer workflow")
    parser.add_argument("--base-url", default=os.environ.get("SEISMIC_VIEWER_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--outdir", default="")
    parser.add_argument("--zip", action="store_true", help="Create a zip bundle beside the output directory")
    args = parser.parse_args()

    if args.outdir:
        outdir = Path(args.outdir).expanduser().resolve()
    else:
        outdir = Path.home() / "Downloads" / f"e2e_1_existing_managed_3d_viewer_{now_stamp()}"
    harness = Harness(args.base_url, outdir)
    code = harness.run()
    if args.zip:
        zip_path = outdir.with_suffix(".zip")
        zip_dir(outdir, zip_path)
        print(f"E2E result bundle: {zip_path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
