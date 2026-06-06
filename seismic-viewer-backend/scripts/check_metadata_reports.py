#!/usr/bin/env python3
from __future__ import annotations

import sys
import urllib.request
from urllib.error import HTTPError, URLError

BASE_URL = "http://localhost:8000"
INDEXED_DATASET_ID = "4ecf666d5ff82cde"


def fetch(path: str) -> tuple[int, str, bytes]:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.headers.get("content-type", ""), resp.read()
    except HTTPError as exc:
        return exc.code, exc.headers.get("content-type", ""), exc.read()
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


def assert_ok(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    checks = []

    css_status, css_type, css_body = fetch("/api/report-assets/metadata_score_report.css")
    checks.append(("report css status", css_status == 200))
    checks.append(("report css content-type", "text/css" in css_type))
    checks.append(("report css non-empty", len(css_body) > 100))

    report_path = f"/api/datasets/{INDEXED_DATASET_ID}/metadata-score-report"
    report_status, report_type, report_body = fetch(report_path)
    report_text = report_body.decode("utf-8", errors="replace")

    checks.append(("indexed report status", report_status == 200))
    checks.append(("indexed report content-type", "text/html" in report_type))
    checks.append(("indexed report stylesheet link", "/api/report-assets/metadata_score_report.css" in report_text))
    checks.append(("indexed report has no inline style", "<style>" not in report_text))
    checks.append(("indexed report not raw json detail", '{"detail"' not in report_text))
    checks.append(("indexed report title", "Metadata Score Report" in report_text))

    failed = [name for name, ok in checks if not ok]

    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")

    if failed:
        print("\nFAILED CHECKS:")
        for name in failed:
            print(f"- {name}")
        return 1

    print("\nMetadata report checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
