#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.request


BASE = "http://127.0.0.1:8000"


def fetch_json(path: str):
    with urllib.request.urlopen(BASE + path, timeout=8) as r:
        body = r.read().decode("utf-8", errors="replace")
        return r.status, r.headers.get("content-type", ""), json.loads(body)


def main() -> int:
    status, ctype, data = fetch_json("/api/runtime/identity")
    print("identity status:", status, ctype)
    print(json.dumps(data, indent=2)[:5000])

    flags = data.get("report_loader_flags", {})
    ok = True

    if status != 200:
        print("FAIL: identity endpoint did not return 200")
        ok = False

    if not flags.get("uses_build_metadata_summary"):
        print("FAIL: live backend report loader does not use build_metadata_summary")
        ok = False

    if flags.get("contains_missing_viewer_metadata"):
        print("FAIL: live backend report loader still contains stale missing_viewer_metadata path")
        ok = False

    if not flags.get("contains_converted_volume_resolved"):
        print("FAIL: live backend report loader does not contain converted_volume_resolved path")
        ok = False

    status, ctype, routes = fetch_json("/api/runtime/routes")
    print("\nroutes status:", status, ctype)
    interesting = [
        r for r in routes.get("routes", [])
        if "metadata-score-report" in r.get("path", "") or "runtime" in r.get("path", "")
    ]
    print(json.dumps(interesting, indent=2))

    if status != 200:
        print("FAIL: routes endpoint did not return 200")
        ok = False

    if ok:
        print("\nPASS: runtime identity checks accepted")
        return 0

    print("\nFAIL: runtime identity checks rejected")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
