"""
SBLT-3 Contract Test: Row Normalization and QAQC Skeleton.

Tests the POST /api/sblt/sessions/{session_id}/normalize endpoint.

Usage:
    BASE_URL="http://127.0.0.1:8001" python3 scripts/test_sblt_row_normalization_contract.py

Environment:
    BASE_URL — base URL of the SBLT backend (default: http://127.0.0.1:8000)

Test cases:
    [1]  Valid 2D row → normalized_metadata populated, dataset_key built, status=ready
    [2]  Valid 3D row (volume) → normalized_metadata populated, dataset_key built, status=ready
    [3]  Blocked row stays blocked after normalization
    [4]  review_required row stays review_required after normalization
    [5]  Alias column names normalize correctly
    [6]  NORMALIZATION_COMPLETED flag appended to every row
    [7]  sample_interval_ms "4 ms" parsed to 4.0
    [8]  Unparseable sample_interval_ms → UNPARSEABLE_RECOMMENDED_FIELD flag
    [9]  supporting_document_paths split on semicolon
    [10] supporting_document_paths split on comma (no semicolon)
    [11] SBLT-2 QAQC flags preserved (merged, not replaced)
    [12] Session summary invariants: row_count == len(rows), summary.total == len(rows)
    [13] Normalize nonexistent session → HTTP 404
    [14] Normalize un-validated (parsed) session → HTTP 400
    [15] Session status = "normalized" after normalization
    [16] Session actions: can_validate=True, can_approve=True (has ready rows)
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
print(f"BASE_URL: {BASE}")

PASS = 0
FAIL = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def require(condition: bool, label: str, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        msg = f"  FAIL  {label}"
        if detail:
            msg += f"\n        {detail}"
        print(msg)


def post(path: str, body: dict | None = None) -> tuple[int, dict]:
    url = BASE + path
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_bytes = exc.read()
        try:
            return exc.code, json.loads(body_bytes)
        except Exception:
            return exc.code, {"raw": body_bytes.decode(errors="replace")}


def get(path: str) -> tuple[int, dict]:
    url = BASE + path
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_bytes = exc.read()
        try:
            return exc.code, json.loads(body_bytes)
        except Exception:
            return exc.code, {"raw": body_bytes.decode(errors="replace")}


def create_and_validate_session(loadsheet_path: str) -> dict:
    """Create a session, validate it, and return the validated session."""
    status, body = post("/api/sblt/sessions", {"loadsheet_path": loadsheet_path})
    if status != 200:
        print(f"  ERROR  Failed to create session: {status} {body}")
        sys.exit(1)
    session_id = body["session_id"]
    status, body = post(f"/api/sblt/sessions/{session_id}/validate")
    if status != 200:
        print(f"  ERROR  Failed to validate session: {status} {body}")
        sys.exit(1)
    return body


def flag_codes(flags: list[dict]) -> list[str]:
    return [f.get("code", "") for f in flags]


# ---------------------------------------------------------------------------
# Loadsheet fixtures
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent
_FIXTURES_DIR = _SCRIPTS_DIR / "sblt_test_fixtures"


def _write_fixture(name: str, rows: list[dict]) -> Path:
    """Write a CSV fixture and return its absolute path.

    Uses csv.writer so that field values containing commas, quotes, or
    newlines are correctly RFC 4180-quoted.  This is required for test cases
    where a Documents field contains comma-separated paths — without quoting
    the CSV parser would split them into extra columns.
    """
    _FIXTURES_DIR.mkdir(exist_ok=True)
    path = _FIXTURES_DIR / name
    if not rows:
        path.write_text("Survey Name,Data Type,SEG-Y File\n", encoding="utf-8")
        return path
    headers = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([str(row.get(h, "")) for h in headers])
    path.write_text(buf.getvalue(), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_tests() -> None:
    # ------------------------------------------------------------------
    # Test [1]: Valid 2D row — normalized_metadata populated, status=ready
    # ------------------------------------------------------------------
    print("\n[1] Valid 2D row → normalized_metadata populated, dataset_key built, status=ready")
    p = _write_fixture("t01_2d_ready.csv", [{
        "Survey Name": "Survey Alpha",
        "Data Type": "2D",
        "Line Name": "Line-001",
        "SEG-Y File": "/data/Line001.sgy",
    }])
    session = create_and_validate_session(str(p))
    status, body = post(f"/api/sblt/sessions/{session['session_id']}/normalize")
    require(status == 200, "HTTP 200")
    row = body["rows"][0]
    nm = row.get("normalized_metadata", {})
    require(nm.get("survey_name") == "Survey Alpha", "survey_name display correct")
    require(nm.get("survey_name_normalized") == "survey_alpha", "survey_name key correct")
    require(nm.get("line_name") == "Line-001", "line_name display correct")
    require(nm.get("line_name_normalized") == "line_001", "line_name key correct")
    require(nm.get("segy_filename") == "Line001.sgy", "segy_filename extracted")
    require(nm.get("dataset_label") == "Survey Alpha / Line-001", "dataset_label correct")
    require(nm.get("dataset_key") == "2d_line__survey_alpha__line_001__line001_sgy", "dataset_key correct")
    require(row.get("status") == "ready", "status=ready")

    # ------------------------------------------------------------------
    # Test [2]: Valid 3D row (volume)
    # ------------------------------------------------------------------
    print("\n[2] Valid 3D row → normalized_metadata populated, dataset_key built, status=ready")
    p = _write_fixture("t02_3d_ready.csv", [{
        "Survey Name": "Block 12",
        "Data Type": "3D",
        "Volume Name": "Full Stack",
        "SEG-Y File": "/data/fullstack.segy",
    }])
    session = create_and_validate_session(str(p))
    status, body = post(f"/api/sblt/sessions/{session['session_id']}/normalize")
    require(status == 200, "HTTP 200")
    row = body["rows"][0]
    nm = row.get("normalized_metadata", {})
    require(nm.get("record_type") == "3d_volume", "record_type=3d_volume")
    require(nm.get("volume_name") == "Full Stack", "volume_name display correct")
    require(nm.get("volume_name_normalized") == "full_stack", "volume_name key correct")
    require(nm.get("dataset_label") == "Block 12 / Full Stack", "dataset_label correct")
    require("3d_volume__block_12__full_stack__fullstack_segy" == nm.get("dataset_key"), "dataset_key correct")
    require(row.get("status") == "ready", "status=ready")

    # ------------------------------------------------------------------
    # Test [3]: Blocked row stays blocked
    # ------------------------------------------------------------------
    print("\n[3] Blocked row stays blocked after normalization")
    p = _write_fixture("t03_blocked.csv", [{
        "Data Type": "2D",
        "SEG-Y File": "/data/Line001.sgy",
        # Survey Name intentionally omitted → blocked
    }])
    session = create_and_validate_session(str(p))
    status, body = post(f"/api/sblt/sessions/{session['session_id']}/normalize")
    require(status == 200, "HTTP 200")
    row = body["rows"][0]
    require(row.get("status") == "blocked", "blocked row stays blocked")

    # ------------------------------------------------------------------
    # Test [4]: review_required row stays review_required
    # ------------------------------------------------------------------
    print("\n[4] review_required row stays review_required")
    p = _write_fixture("t04_review_req.csv", [{
        "Survey Name": "Survey Beta",
        "Data Type": "4D",           # unknown → review_required
        "SEG-Y File": "/data/line.sgy",
    }])
    session = create_and_validate_session(str(p))
    status, body = post(f"/api/sblt/sessions/{session['session_id']}/normalize")
    require(status == 200, "HTTP 200")
    row = body["rows"][0]
    require(row.get("status") == "review_required", "review_required row stays review_required")

    # ------------------------------------------------------------------
    # Test [5]: Alias column names normalize correctly
    # ------------------------------------------------------------------
    print("\n[5] Alias column names normalize correctly")
    p = _write_fixture("t05_aliases.csv", [{
        "Project": "Alias Survey",      # → survey_name
        "Dataset Type": "3D",           # → record_type
        "Dataset Name": "Near Angle",   # → volume_name
        "SEGY File": "/data/near.segy", # → segy_path
    }])
    session = create_and_validate_session(str(p))
    status, body = post(f"/api/sblt/sessions/{session['session_id']}/normalize")
    require(status == 200, "HTTP 200")
    row = body["rows"][0]
    nm = row.get("normalized_metadata", {})
    require(nm.get("survey_name") == "Alias Survey", "Project alias → survey_name")
    require(nm.get("volume_name") == "Near Angle", "Dataset Name alias → volume_name")
    require(nm.get("segy_filename") == "near.segy", "SEGY File alias → segy_path filename")

    # ------------------------------------------------------------------
    # Test [6]: NORMALIZATION_COMPLETED flag appended to every row
    # ------------------------------------------------------------------
    print("\n[6] NORMALIZATION_COMPLETED flag appended to every row")
    p = _write_fixture("t06_norm_flag.csv", [
        {"Survey Name": "S1", "Data Type": "2D", "Line Name": "L1", "SEG-Y File": "/d/a.sgy"},
        {"Survey Name": "S2", "Data Type": "3D", "Volume Name": "V1", "SEG-Y File": "/d/b.sgy"},
    ])
    session = create_and_validate_session(str(p))
    status, body = post(f"/api/sblt/sessions/{session['session_id']}/normalize")
    require(status == 200, "HTTP 200")
    for i, row in enumerate(body["rows"]):
        codes = flag_codes(row.get("qaqc_flags", []))
        require(
            "NORMALIZATION_COMPLETED" in codes,
            f"row[{i}] has NORMALIZATION_COMPLETED flag",
        )

    # ------------------------------------------------------------------
    # Test [7]: sample_interval_ms "4 ms" parsed to 4.0
    # ------------------------------------------------------------------
    print('\n[7] sample_interval_ms "4 ms" parsed to 4.0')
    p = _write_fixture("t07_sample_interval.csv", [{
        "Survey Name": "S1",
        "Data Type": "2D",
        "Line Name": "L1",
        "SEG-Y File": "/d/a.sgy",
        "Sample Interval": "4 ms",
    }])
    session = create_and_validate_session(str(p))
    status, body = post(f"/api/sblt/sessions/{session['session_id']}/normalize")
    require(status == 200, "HTTP 200")
    nm = body["rows"][0].get("normalized_metadata", {})
    require(nm.get("sample_interval_ms") == 4.0, f"sample_interval_ms=4.0 (got {nm.get('sample_interval_ms')!r})")

    # ------------------------------------------------------------------
    # Test [8]: Unparseable sample_interval_ms → UNPARSEABLE_RECOMMENDED_FIELD
    # ------------------------------------------------------------------
    print("\n[8] Unparseable sample_interval_ms → UNPARSEABLE_RECOMMENDED_FIELD flag")
    p = _write_fixture("t08_bad_sample_interval.csv", [{
        "Survey Name": "S1",
        "Data Type": "2D",
        "Line Name": "L1",
        "SEG-Y File": "/d/a.sgy",
        "Sample Interval": "fast",
    }])
    session = create_and_validate_session(str(p))
    status, body = post(f"/api/sblt/sessions/{session['session_id']}/normalize")
    require(status == 200, "HTTP 200")
    codes = flag_codes(body["rows"][0].get("qaqc_flags", []))
    require("UNPARSEABLE_RECOMMENDED_FIELD" in codes, "UNPARSEABLE_RECOMMENDED_FIELD flag present")
    nm = body["rows"][0].get("normalized_metadata", {})
    require(nm.get("sample_interval_ms") is None, "sample_interval_ms=None for unparseable value")

    # ------------------------------------------------------------------
    # Test [9]: supporting_document_paths split on semicolon
    # ------------------------------------------------------------------
    print("\n[9] supporting_document_paths split on semicolon")
    p = _write_fixture("t09_docs_semi.csv", [{
        "Survey Name": "S1",
        "Data Type": "2D",
        "Line Name": "L1",
        "SEG-Y File": "/d/a.sgy",
        "Documents": "/docs/a.pdf; /docs/b.pdf; /docs/c.pdf",
    }])
    session = create_and_validate_session(str(p))
    status, body = post(f"/api/sblt/sessions/{session['session_id']}/normalize")
    require(status == 200, "HTTP 200")
    nm = body["rows"][0].get("normalized_metadata", {})
    docs = nm.get("supporting_document_paths", [])
    require(docs == ["/docs/a.pdf", "/docs/b.pdf", "/docs/c.pdf"], f"3 paths split on semicolon (got {docs!r})")

    # ------------------------------------------------------------------
    # Test [10]: supporting_document_paths split on comma (no semicolon)
    # ------------------------------------------------------------------
    print("\n[10] supporting_document_paths split on comma (no semicolon)")
    p = _write_fixture("t10_docs_comma.csv", [{
        "Survey Name": "S1",
        "Data Type": "2D",
        "Line Name": "L1",
        "SEG-Y File": "/d/a.sgy",
        "Documents": "/docs/x.pdf, /docs/y.pdf",
    }])
    session = create_and_validate_session(str(p))
    status, body = post(f"/api/sblt/sessions/{session['session_id']}/normalize")
    require(status == 200, "HTTP 200")
    nm = body["rows"][0].get("normalized_metadata", {})
    docs = nm.get("supporting_document_paths", [])
    require(docs == ["/docs/x.pdf", "/docs/y.pdf"], f"2 paths split on comma (got {docs!r})")

    # ------------------------------------------------------------------
    # Test [11]: SBLT-2 QAQC flags preserved (merged, not replaced)
    # ------------------------------------------------------------------
    print("\n[11] SBLT-2 QAQC flags preserved after normalization")
    p = _write_fixture("t11_flags_preserved.csv", [{
        "Survey Name": "S1",
        "Data Type": "2D",
        "Line Name": "L1",
        "SEG-Y File": "/d/a.sgy",
        # Intentionally omit all recommended fields so SBLT-2 produces MISSING_RECOMMENDED_FIELD flags.
    }])
    session = create_and_validate_session(str(p))
    # Confirm SBLT-2 flags exist on validated row.
    validated_codes = flag_codes(session["rows"][0].get("qaqc_flags", []))
    require("MISSING_RECOMMENDED_FIELD" in validated_codes, "SBLT-2 produced MISSING_RECOMMENDED_FIELD before normalize")

    status, body = post(f"/api/sblt/sessions/{session['session_id']}/normalize")
    require(status == 200, "HTTP 200")
    norm_codes = flag_codes(body["rows"][0].get("qaqc_flags", []))
    require("MISSING_RECOMMENDED_FIELD" in norm_codes, "MISSING_RECOMMENDED_FIELD preserved after normalization")
    require("NORMALIZATION_COMPLETED" in norm_codes, "NORMALIZATION_COMPLETED appended")

    # ------------------------------------------------------------------
    # Test [12]: Summary invariants
    # ------------------------------------------------------------------
    print("\n[12] Summary invariants: row_count == len(rows), summary.total == len(rows)")
    p = _write_fixture("t12_invariants.csv", [
        {"Survey Name": "S1", "Data Type": "2D", "Line Name": "L1", "SEG-Y File": "/d/a.sgy"},
        {"Survey Name": "S2", "Data Type": "3D", "Volume Name": "V1", "SEG-Y File": "/d/b.sgy"},
        {"Data Type": "2D", "SEG-Y File": "/d/c.sgy"},  # blocked
    ])
    session = create_and_validate_session(str(p))
    status, body = post(f"/api/sblt/sessions/{session['session_id']}/normalize")
    require(status == 200, "HTTP 200")
    row_count = body.get("row_count")
    rows = body.get("rows", [])
    summary = body.get("summary", {})
    require(row_count == len(rows), f"row_count ({row_count}) == len(rows) ({len(rows)})")
    require(summary.get("total") == len(rows), f"summary.total ({summary.get('total')}) == len(rows) ({len(rows)})")
    statuses = [r.get("status") for r in rows]
    for s in set(statuses):
        count_in_summary = summary.get(s, 0)
        count_in_rows = statuses.count(s)
        require(
            count_in_summary == count_in_rows,
            f"summary[{s!r}]={count_in_summary} matches rows with status={s!r} ({count_in_rows})",
        )

    # ------------------------------------------------------------------
    # Test [13]: Normalize nonexistent session → HTTP 404
    # ------------------------------------------------------------------
    print("\n[13] Normalize nonexistent session → HTTP 404")
    status, body = post("/api/sblt/sessions/sblt_99999999_000000_ffffffff/normalize")
    require(status == 404, f"HTTP 404 (got {status})")

    # ------------------------------------------------------------------
    # Test [14]: Normalize un-validated (parsed) session → HTTP 400
    # ------------------------------------------------------------------
    print("\n[14] Normalize parsed (un-validated) session → HTTP 400")
    p = _write_fixture("t14_parsed_only.csv", [{
        "Survey Name": "S1", "Data Type": "2D", "Line Name": "L1", "SEG-Y File": "/d/a.sgy",
    }])
    create_status, create_body = post("/api/sblt/sessions", {"loadsheet_path": str(p)})
    require(create_status == 200, "Session created successfully")
    session_id = create_body["session_id"]
    # Do NOT validate — normalize should reject it.
    status, body = post(f"/api/sblt/sessions/{session_id}/normalize")
    require(status == 400, f"HTTP 400 for parsed session (got {status})")

    # ------------------------------------------------------------------
    # Test [15]: Session status = "normalized" after normalization
    # ------------------------------------------------------------------
    print('\n[15] Session status = "normalized" after normalization')
    p = _write_fixture("t15_status.csv", [{
        "Survey Name": "S1", "Data Type": "2D", "Line Name": "L1", "SEG-Y File": "/d/a.sgy",
    }])
    session = create_and_validate_session(str(p))
    status, body = post(f"/api/sblt/sessions/{session['session_id']}/normalize")
    require(status == 200, "HTTP 200")
    require(body.get("status") == "normalized", f"status=normalized (got {body.get('status')!r})")
    require(body.get("schema_version") == "sblt.session.v1", "schema_version=sblt.session.v1")

    # ------------------------------------------------------------------
    # Test [16]: Session actions after normalization
    # ------------------------------------------------------------------
    print("\n[16] Session actions: can_validate=True, can_approve=True (has ready rows)")
    p = _write_fixture("t16_actions.csv", [{
        "Survey Name": "S1", "Data Type": "2D", "Line Name": "L1", "SEG-Y File": "/d/a.sgy",
    }])
    session = create_and_validate_session(str(p))
    status, body = post(f"/api/sblt/sessions/{session['session_id']}/normalize")
    require(status == 200, "HTTP 200")
    actions = body.get("actions", {})
    require(actions.get("can_validate") is True, "can_validate=True")
    require(actions.get("can_approve") is True, "can_approve=True (has ready row)")
    require(actions.get("can_register") is False, "can_register=False (SBLT-8)")
    row_actions = body["rows"][0].get("actions", {})
    require(row_actions.get("can_approve") is True, "row.can_approve=True (ready row)")
    require(row_actions.get("requires_review") is False, "row.requires_review=False (ready row)")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_tests()
    print(f"\n{'=' * 50}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        sys.exit(1)
