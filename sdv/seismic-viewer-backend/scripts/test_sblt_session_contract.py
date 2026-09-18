#!/usr/bin/env python3
"""
SBLT-1 session contract test.

Tests:
 1. POST with a valid CSV — assert 200 and full contract shape.
 2. GET by session_id — assert same invariants.
 3. GET nonexistent session — assert 404.
 4. POST missing loadsheet_path — assert 400.
 5. POST relative loadsheet_path — assert 400.
 6. POST unsupported extension — assert 400.
 7. POST non-existent file — assert 400.
 8. POST empty CSV (header only) — assert 200 with zero rows.
 9. Row-level invariants: row_id, source_row_number, source_values, status, actions.
10. summary.parsed == len(rows) for all-parsed sessions.

Style: stdlib only — no pytest. Backend must be running.

Base URL: read from BASE_URL environment variable; defaults to http://127.0.0.1:8000.
Usage:
    python3 scripts/test_sblt_session_contract.py
    BASE_URL="http://127.0.0.1:8001" python3 scripts/test_sblt_session_contract.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")

PASS = 0
FAIL = 0


def _ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  PASS  {label}")


def _fail(label: str, detail: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  FAIL  {label}")
    print(f"        {detail}")


def request_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    expected_status: int = 200,
) -> tuple[int, Any]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return -1, str(exc)
    try:
        return status, json.loads(body)
    except Exception:
        return status, body


def require(condition: bool, label: str, detail: str = "") -> bool:
    if condition:
        _ok(label)
        return True
    else:
        _fail(label, detail or "condition was False")
        return False


def assert_session_invariants(session: dict[str, Any], label_prefix: str) -> None:
    require(
        session.get("schema_version") == "sblt.session.v1",
        f"{label_prefix}: schema_version == 'sblt.session.v1'",
        f"got {session.get('schema_version')!r}",
    )
    session_id = session.get("session_id", "")
    require(
        isinstance(session_id, str) and session_id.startswith("sblt_"),
        f"{label_prefix}: session_id starts with 'sblt_'",
        f"got {session_id!r}",
    )
    require(
        session.get("status") == "parsed",
        f"{label_prefix}: status == 'parsed'",
        f"got {session.get('status')!r}",
    )
    rows = session.get("rows", [])
    row_count = session.get("row_count")
    require(
        row_count == len(rows),
        f"{label_prefix}: row_count == len(rows)",
        f"row_count={row_count} len(rows)={len(rows)}",
    )
    summary = session.get("summary", {})
    require(
        summary.get("total") == len(rows),
        f"{label_prefix}: summary.total == len(rows)",
        f"summary.total={summary.get('total')} len(rows)={len(rows)}",
    )
    require(
        summary.get("parsed") == len(rows),
        f"{label_prefix}: summary.parsed == len(rows)",
        f"summary.parsed={summary.get('parsed')} len(rows)={len(rows)}",
    )
    require(
        isinstance(session.get("actions"), dict),
        f"{label_prefix}: actions is a dict",
    )
    require(
        isinstance(session.get("source"), dict),
        f"{label_prefix}: source is a dict",
    )
    require(
        bool(session.get("created_at")),
        f"{label_prefix}: created_at is present",
    )
    require(
        bool(session.get("updated_at")),
        f"{label_prefix}: updated_at is present",
    )


def assert_row_invariants(rows: list[dict[str, Any]], label_prefix: str) -> None:
    for i, row in enumerate(rows):
        row_label = f"{label_prefix}: row[{i}]"
        require(
            bool(row.get("row_id")),
            f"{row_label}: row_id present",
            f"got {row.get('row_id')!r}",
        )
        require(
            isinstance(row.get("source_row_number"), int),
            f"{row_label}: source_row_number is int",
            f"got {row.get('source_row_number')!r}",
        )
        require(
            row.get("status") == "parsed",
            f"{row_label}: status == 'parsed'",
            f"got {row.get('status')!r}",
        )
        require(
            isinstance(row.get("source_values"), dict),
            f"{row_label}: source_values is dict",
        )
        require(
            isinstance(row.get("actions"), dict),
            f"{row_label}: actions is dict",
        )
        require(
            isinstance(row.get("qaqc_flags"), list),
            f"{row_label}: qaqc_flags is list",
        )
        require(
            isinstance(row.get("normalized_metadata"), dict),
            f"{row_label}: normalized_metadata is dict",
        )
        require(
            isinstance(row.get("validation"), dict),
            f"{row_label}: validation is dict",
        )


def main() -> None:
    global PASS, FAIL

    # -----------------------------------------------------------------------
    # Check backend is reachable
    # -----------------------------------------------------------------------
    print(f"\n  BASE_URL = {BASE}")
    print("\n[0] Backend health check")
    status, body = request_json("GET", "/api/msi/health")
    if status == -1:
        print(f"  ERROR: Backend not reachable at {BASE}: {body}")
        print("  Start the backend first, then re-run this test.")
        print(f"  Tip: set BASE_URL env var if the backend is on a non-default port.")
        print(f"  Example: BASE_URL=\"http://127.0.0.1:8001\" python3 {sys.argv[0]}")
        sys.exit(1)
    print(f"  Backend reachable (status={status})")

    # -----------------------------------------------------------------------
    # Create a temp CSV loadsheet for testing
    # -----------------------------------------------------------------------
    tmp_dir = tempfile.mkdtemp(prefix="sblt_test_")
    csv_path = os.path.join(tmp_dir, "test_loadsheet.csv")
    with open(csv_path, "w", encoding="utf-8") as fh:
        fh.write("Survey Name,Line Name,SEG-Y File,Data Type\n")
        fh.write("SurveyA,Line001,/data/seismic/SurveyA_Line001.segy,2D\n")
        fh.write("SurveyA,Line002,/data/seismic/SurveyA_Line002.segy,2D\n")
        fh.write("SurveyB,Vol001,/data/seismic/SurveyB.segy,3D\n")

    empty_csv_path = os.path.join(tmp_dir, "empty_loadsheet.csv")
    with open(empty_csv_path, "w", encoding="utf-8") as fh:
        fh.write("Survey Name,Line Name,SEG-Y File,Data Type\n")

    txt_path = os.path.join(tmp_dir, "test.txt")
    with open(txt_path, "w") as fh:
        fh.write("not a loadsheet\n")

    print(f"\n  Temp CSV: {csv_path}")
    print(f"  Empty CSV: {empty_csv_path}")

    # -----------------------------------------------------------------------
    # Test 1: POST valid CSV → 200 + full contract
    # -----------------------------------------------------------------------
    print("\n[1] POST valid CSV loadsheet")
    status, session = request_json(
        "POST",
        "/api/sblt/sessions",
        payload={"loadsheet_path": csv_path},
    )
    require(status == 200, "POST /api/sblt/sessions → HTTP 200", f"got HTTP {status}: {session}")

    if status == 200 and isinstance(session, dict):
        assert_session_invariants(session, "POST valid CSV")
        rows = session.get("rows", [])
        require(
            len(rows) == 3,
            "POST valid CSV: 3 data rows parsed",
            f"got {len(rows)} rows",
        )
        assert_row_invariants(rows, "POST valid CSV")

        # Check source values preserve original column names
        if rows:
            first_sv = rows[0].get("source_values", {})
            require(
                "Survey Name" in first_sv,
                "POST valid CSV: source_values preserves original column name 'Survey Name'",
                f"keys={list(first_sv.keys())}",
            )
            require(
                first_sv.get("Survey Name") == "SurveyA",
                "POST valid CSV: source_values['Survey Name'] == 'SurveyA'",
                f"got {first_sv.get('Survey Name')!r}",
            )

        saved_session_id = session.get("session_id", "")
    else:
        saved_session_id = ""
        print("  (skipping row-level checks — session creation failed)")

    # -----------------------------------------------------------------------
    # Test 2: GET by session_id
    # -----------------------------------------------------------------------
    print("\n[2] GET /api/sblt/sessions/{session_id}")
    if saved_session_id:
        status2, session2 = request_json("GET", f"/api/sblt/sessions/{saved_session_id}")
        require(status2 == 200, f"GET session → HTTP 200", f"got HTTP {status2}: {session2}")
        if status2 == 200 and isinstance(session2, dict):
            assert_session_invariants(session2, "GET session")
            require(
                session2.get("session_id") == saved_session_id,
                "GET session: session_id matches",
                f"got {session2.get('session_id')!r}",
            )
    else:
        print("  SKIP (no session_id from test 1)")

    # -----------------------------------------------------------------------
    # Test 3: GET nonexistent session → 404
    # -----------------------------------------------------------------------
    print("\n[3] GET nonexistent session → 404")
    status3, body3 = request_json("GET", "/api/sblt/sessions/sblt_does_not_exist_0000000000")
    require(status3 == 404, "GET nonexistent → HTTP 404", f"got HTTP {status3}")

    # -----------------------------------------------------------------------
    # Test 4: POST missing loadsheet_path → 400
    # -----------------------------------------------------------------------
    print("\n[4] POST missing loadsheet_path → 400")
    status4, body4 = request_json("POST", "/api/sblt/sessions", payload={"loadsheet_path": ""})
    require(status4 == 400, "POST empty path → HTTP 400", f"got HTTP {status4}: {body4}")

    # -----------------------------------------------------------------------
    # Test 5: POST relative loadsheet_path → 400
    # -----------------------------------------------------------------------
    print("\n[5] POST relative loadsheet_path → 400")
    status5, body5 = request_json(
        "POST",
        "/api/sblt/sessions",
        payload={"loadsheet_path": "relative/path/file.csv"},
    )
    require(status5 == 400, "POST relative path → HTTP 400", f"got HTTP {status5}: {body5}")

    # -----------------------------------------------------------------------
    # Test 6: POST unsupported extension → 400
    # -----------------------------------------------------------------------
    print("\n[6] POST unsupported extension (.txt) → 400")
    status6, body6 = request_json(
        "POST",
        "/api/sblt/sessions",
        payload={"loadsheet_path": txt_path},
    )
    require(status6 == 400, "POST unsupported ext → HTTP 400", f"got HTTP {status6}: {body6}")

    # -----------------------------------------------------------------------
    # Test 7: POST file that does not exist → 400
    # -----------------------------------------------------------------------
    print("\n[7] POST non-existent file → 400")
    status7, body7 = request_json(
        "POST",
        "/api/sblt/sessions",
        payload={"loadsheet_path": "/tmp/sblt_test_does_not_exist_9999.csv"},
    )
    require(status7 == 400, "POST missing file → HTTP 400", f"got HTTP {status7}: {body7}")

    # -----------------------------------------------------------------------
    # Test 8: POST empty CSV (header only) → 200 with zero rows
    # -----------------------------------------------------------------------
    print("\n[8] POST CSV with header only (zero data rows)")
    status8, session8 = request_json(
        "POST",
        "/api/sblt/sessions",
        payload={"loadsheet_path": empty_csv_path},
    )
    require(status8 == 200, "POST header-only CSV → HTTP 200", f"got HTTP {status8}: {session8}")
    if status8 == 200 and isinstance(session8, dict):
        require(
            session8.get("row_count") == 0,
            "header-only CSV: row_count == 0",
            f"got {session8.get('row_count')}",
        )
        require(
            session8.get("summary", {}).get("total") == 0,
            "header-only CSV: summary.total == 0",
        )
        require(
            session8.get("summary", {}).get("parsed") == 0,
            "header-only CSV: summary.parsed == 0",
        )
        require(
            session8.get("rows") == [],
            "header-only CSV: rows == []",
        )

    # -----------------------------------------------------------------------
    # Test 9: POST with base_path and profile stored correctly
    # -----------------------------------------------------------------------
    print("\n[9] POST with base_path and profile")
    status9, session9 = request_json(
        "POST",
        "/api/sblt/sessions",
        payload={
            "loadsheet_path": csv_path,
            "base_path": "/data/seismic",
            "profile": "custom_profile",
        },
    )
    require(status9 == 200, "POST with base_path/profile → HTTP 200", f"got HTTP {status9}")
    if status9 == 200 and isinstance(session9, dict):
        src = session9.get("source", {})
        require(
            src.get("base_path") == "/data/seismic",
            "source.base_path stored correctly",
            f"got {src.get('base_path')!r}",
        )
        require(
            src.get("profile") == "custom_profile",
            "source.profile stored correctly",
            f"got {src.get('profile')!r}",
        )
        require(
            src.get("format") == "csv",
            "source.format == 'csv'",
            f"got {src.get('format')!r}",
        )

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    total = PASS + FAIL
    print(f"\n{'='*60}")
    print(f"  SBLT-1 contract test: {PASS}/{total} passed, {FAIL} failed")
    print(f"{'='*60}\n")

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
