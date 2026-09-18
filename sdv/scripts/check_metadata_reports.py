#!/usr/bin/env python3
from __future__ import annotations

import sys
import urllib.request
from urllib.error import HTTPError, URLError


BASE = "http://127.0.0.1:8000"
KNOWN_INDEXED_DATASET = "4ecf666d5ff82cde"


def check(path: str, expected_type: str | None = None) -> bool:
    url = BASE + path
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            status = r.status
            ctype = r.headers.get("content-type", "")
            body = r.read(4000).decode("utf-8", errors="replace")
    except HTTPError as e:
        print(f"FAIL {path}: HTTP {e.code}")
        return False
    except URLError as e:
        print(f"FAIL {path}: {e}")
        return False

    if status != 200:
        print(f"FAIL {path}: status {status}")
        return False

    if expected_type and expected_type not in ctype:
        print(f"FAIL {path}: content-type {ctype!r}, expected {expected_type!r}")
        return False

    if "metadata-score-report" in path and "<html" not in body.lower() and "<!doctype html" not in body.lower():
        print(f"FAIL {path}: report did not return HTML")
        return False

    print(f"PASS {path}: {status} {ctype}")
    return True


def main() -> int:
    ok = True
    ok &= check("/", "text/html")
    ok &= check("/api/datasets")
    ok &= check("/api/report-assets/metadata_score_report.css", "text/css")
    ok &= check(f"/api/datasets/{KNOWN_INDEXED_DATASET}/metadata-score-report", "text/html")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
