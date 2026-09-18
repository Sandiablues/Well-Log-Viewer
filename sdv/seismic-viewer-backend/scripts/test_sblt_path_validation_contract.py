"""
SBLT-4 Contract Test: File / Path Reference Validation.

Tests the POST /api/sblt/sessions/{session_id}/validate-paths endpoint.

Usage:
    BASE_URL="http://127.0.0.1:8001" python3 scripts/test_sblt_path_validation_contract.py

Environment:
    BASE_URL — base URL of the SBLT backend (default: http://127.0.0.1:8000)

Test cases:
    [1]  Valid absolute .sgy path → ready, SEGY_PATH_VALIDATED, size_bytes set
    [2]  Missing SEG-Y path (blank) → blocked, MISSING_SEGY_PATH
    [3]  SEG-Y file not found → blocked, SEGY_FILE_NOT_FOUND
    [4]  SEG-Y path is directory → blocked, SEGY_PATH_NOT_FILE
    [5]  Invalid extension (.txt) but file exists/readable → warning only, not blocked
    [6]  Relative SEG-Y path with base_path → resolved, ready
    [7]  Relative SEG-Y path without base_path → blocked, RELATIVE_PATH_WITHOUT_BASE_PATH
    [8]  Supporting documents valid → SUPPORTING_DOCUMENT_PATH_VALIDATED flags
    [9]  Supporting document missing → warning, row remains ready
    [10] Supporting document path is directory → warning, row remains ready
    [11] validate-paths before normalize → HTTP 400
    [12] validate-paths nonexistent session → HTTP 404
    [13] Field preservation: source_values, canonical_fields, normalized_metadata,
         identity_hints unchanged after path validation
    [14] Summary invariants: row_count == len(rows), counts reconcile
    [15] Actions: ready→can_approve, blocked→no approve, can_register always False
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import sys
import tempfile
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
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw.decode(errors="replace")}


def flag_codes(flags: list[dict]) -> list[str]:
    return [f.get("code", "") for f in flags]


# ---------------------------------------------------------------------------
# Fixture writer (RFC 4180-compliant CSV quoting)
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent
_FIXTURES_DIR = _SCRIPTS_DIR / "sblt_test_fixtures"


def _write_fixture(name: str, rows: list[dict]) -> Path:
    """Write a quoted CSV fixture; values with commas are correctly quoted."""
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
# Pipeline helpers
# ---------------------------------------------------------------------------

def _pipeline(loadsheet_path: str, base_path: str | None = None) -> tuple[int, dict]:
    """Create → validate → normalize → validate-paths. Returns final status+body."""
    status, body = post("/api/sblt/sessions", {
        "loadsheet_path": loadsheet_path,
        "base_path": base_path,
    })
    if status != 200:
        print(f"  ERROR  create_session: {status} {body}")
        sys.exit(1)
    sid = body["session_id"]

    status, body = post(f"/api/sblt/sessions/{sid}/validate")
    if status != 200:
        print(f"  ERROR  validate: {status} {body}")
        sys.exit(1)

    status, body = post(f"/api/sblt/sessions/{sid}/normalize")
    if status != 200:
        print(f"  ERROR  normalize: {status} {body}")
        sys.exit(1)

    return post(f"/api/sblt/sessions/{sid}/validate-paths")


def _pipeline_create_validate_only(loadsheet_path: str) -> dict:
    """Create → validate only (no normalize, no validate-paths)."""
    status, body = post("/api/sblt/sessions", {"loadsheet_path": loadsheet_path})
    if status != 200:
        print(f"  ERROR  create_session: {status} {body}")
        sys.exit(1)
    sid = body["session_id"]
    status, body = post(f"/api/sblt/sessions/{sid}/validate")
    if status != 200:
        print(f"  ERROR  validate: {status} {body}")
        sys.exit(1)
    return body


# ---------------------------------------------------------------------------
# Temp-file setup
# ---------------------------------------------------------------------------

TMPDIR = tempfile.mkdtemp(prefix="sblt4_test_")

def _tmp(name: str) -> str:
    return os.path.join(TMPDIR, name)

# Real files
SEGY_VALID    = _tmp("Line001.sgy")
SEGY_VALID2   = _tmp("Line002.segy")   # .segy extension variant
SEGY_WRONG_EXT = _tmp("data.txt")
DOC1          = _tmp("report_a.pdf")
DOC2          = _tmp("report_b.pdf")
DOC_MISSING   = _tmp("does_not_exist.pdf")

# Directories (not files)
SEGY_DIR      = _tmp("a_directory")
DOC_DIR       = _tmp("doc_directory")

# Non-existent SEG-Y
SEGY_MISSING  = _tmp("no_such_file.sgy")

for path in (SEGY_VALID, SEGY_VALID2, SEGY_WRONG_EXT, DOC1, DOC2):
    with open(path, "wb") as fh:
        fh.write(b"\x00" * 64)   # minimal real file content

os.makedirs(SEGY_DIR,  exist_ok=True)
os.makedirs(DOC_DIR,   exist_ok=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def run_tests() -> None:

    # ------------------------------------------------------------------
    # [1] Valid absolute .sgy path → ready, SEGY_PATH_VALIDATED, size_bytes
    # ------------------------------------------------------------------
    print("\n[1] Valid absolute .sgy path → ready, SEGY_PATH_VALIDATED, size_bytes set")
    p = _write_fixture("t4_01_valid_segy.csv", [{
        "Survey Name": "Survey Alpha", "Data Type": "2D",
        "Line Name": "Line001", "SEG-Y File": SEGY_VALID,
    }])
    status, body = _pipeline(str(p))
    require(status == 200, "HTTP 200")
    require(body.get("status") == "paths_validated", f"session status=paths_validated (got {body.get('status')!r})")
    row = body["rows"][0]
    require(row["status"] == "ready", f"row status=ready (got {row['status']!r})")
    pv = row.get("path_validation", {})
    segy = pv.get("segy", {})
    require(segy.get("exists") is True, "segy.exists=True")
    require(segy.get("is_file") is True, "segy.is_file=True")
    require(segy.get("readable") is True, "segy.readable=True")
    require(isinstance(segy.get("size_bytes"), int), f"segy.size_bytes is int (got {segy.get('size_bytes')!r})")
    require(segy.get("extension") == ".sgy", f"segy.extension='.sgy' (got {segy.get('extension')!r})")
    codes = flag_codes(row.get("qaqc_flags", []))
    require("SEGY_PATH_VALIDATED" in codes, "SEGY_PATH_VALIDATED flag present")
    require("PATH_VALIDATION_COMPLETED" in codes, "PATH_VALIDATION_COMPLETED flag present")
    require(pv.get("summary", {}).get("segy_valid") is True, "path_validation.summary.segy_valid=True")

    # ------------------------------------------------------------------
    # [2] Missing SEG-Y path (blank in loadsheet) → blocked, MISSING_SEGY_PATH
    # ------------------------------------------------------------------
    print("\n[2] Missing SEG-Y path → blocked, MISSING_SEGY_PATH blocker")
    p = _write_fixture("t4_02_missing_segy.csv", [{
        "Survey Name": "Survey B", "Data Type": "2D",
        "Line Name": "L1", "SEG-Y File": "",
    }])
    status, body = _pipeline(str(p))
    require(status == 200, "HTTP 200")
    # Row will be blocked from SBLT-2 (segy_path required). Path validation
    # also produces MISSING_SEGY_PATH. Row stays blocked.
    row = body["rows"][0]
    require(row["status"] == "blocked", f"row status=blocked (got {row['status']!r})")
    codes = flag_codes(row.get("qaqc_flags", []))
    require("MISSING_SEGY_PATH" in codes, "MISSING_SEGY_PATH flag present")

    # ------------------------------------------------------------------
    # [3] SEG-Y file not found → blocked, SEGY_FILE_NOT_FOUND
    # ------------------------------------------------------------------
    print("\n[3] SEG-Y file not found → blocked, SEGY_FILE_NOT_FOUND")
    p = _write_fixture("t4_03_not_found.csv", [{
        "Survey Name": "Survey C", "Data Type": "2D",
        "Line Name": "L1", "SEG-Y File": SEGY_MISSING,
    }])
    status, body = _pipeline(str(p))
    require(status == 200, "HTTP 200")
    row = body["rows"][0]
    require(row["status"] == "blocked", f"row status=blocked (got {row['status']!r})")
    pv = row.get("path_validation", {})
    segy = pv.get("segy", {})
    require(segy.get("exists") is False, "segy.exists=False")
    codes = flag_codes(row.get("qaqc_flags", []))
    require("SEGY_FILE_NOT_FOUND" in codes, "SEGY_FILE_NOT_FOUND flag present")

    # ------------------------------------------------------------------
    # [4] SEG-Y path is directory → blocked, SEGY_PATH_NOT_FILE
    # ------------------------------------------------------------------
    print("\n[4] SEG-Y path is directory → blocked, SEGY_PATH_NOT_FILE")
    p = _write_fixture("t4_04_dir.csv", [{
        "Survey Name": "Survey D", "Data Type": "2D",
        "Line Name": "L1", "SEG-Y File": SEGY_DIR,
    }])
    status, body = _pipeline(str(p))
    require(status == 200, "HTTP 200")
    row = body["rows"][0]
    require(row["status"] == "blocked", f"row status=blocked (got {row['status']!r})")
    pv = row.get("path_validation", {})
    segy = pv.get("segy", {})
    require(segy.get("exists") is True, "segy.exists=True (dir exists)")
    require(segy.get("is_file") is False, "segy.is_file=False")
    codes = flag_codes(row.get("qaqc_flags", []))
    require("SEGY_PATH_NOT_FILE" in codes, "SEGY_PATH_NOT_FILE flag present")

    # ------------------------------------------------------------------
    # [5] Invalid extension (.txt) but file exists/readable → warning, not blocked
    # ------------------------------------------------------------------
    print("\n[5] Invalid extension (.txt) but file exists → INVALID_SEGY_EXTENSION warning, row not blocked")
    p = _write_fixture("t4_05_wrong_ext.csv", [{
        "Survey Name": "Survey E", "Data Type": "2D",
        "Line Name": "L1", "SEG-Y File": SEGY_WRONG_EXT,
    }])
    status, body = _pipeline(str(p))
    require(status == 200, "HTTP 200")
    row = body["rows"][0]
    require(row["status"] == "ready", f"row status=ready (extension warning does not block) (got {row['status']!r})")
    pv = row.get("path_validation", {})
    segy = pv.get("segy", {})
    require(segy.get("exists") is True, "segy.exists=True")
    require(segy.get("readable") is True, "segy.readable=True")
    codes = flag_codes(row.get("qaqc_flags", []))
    require("INVALID_SEGY_EXTENSION" in codes, "INVALID_SEGY_EXTENSION warning flag present")
    require("SEGY_FILE_NOT_FOUND" not in codes, "SEGY_FILE_NOT_FOUND NOT present (file exists)")

    # ------------------------------------------------------------------
    # [6] Relative SEG-Y path with base_path → resolved, ready
    # ------------------------------------------------------------------
    print("\n[6] Relative SEG-Y path with base_path set → resolved correctly, row ready")
    rel_name = os.path.basename(SEGY_VALID)   # "Line001.sgy"
    p = _write_fixture("t4_06_relative_with_base.csv", [{
        "Survey Name": "Survey F", "Data Type": "2D",
        "Line Name": "L1", "SEG-Y File": rel_name,
    }])
    status, body = _pipeline(str(p), base_path=TMPDIR)
    require(status == 200, "HTTP 200")
    row = body["rows"][0]
    require(row["status"] == "ready", f"row status=ready (got {row['status']!r})")
    pv = row.get("path_validation", {})
    segy = pv.get("segy", {})
    require(segy.get("exists") is True, "segy.exists=True")
    require(segy.get("readable") is True, "segy.readable=True")
    # resolved_path should be the absolute path
    require(
        segy.get("resolved_path", "").endswith(rel_name),
        f"resolved_path ends with '{rel_name}' (got {segy.get('resolved_path')!r})",
    )

    # ------------------------------------------------------------------
    # [7] Relative SEG-Y path without base_path → blocked, RELATIVE_PATH_WITHOUT_BASE_PATH
    # ------------------------------------------------------------------
    print("\n[7] Relative SEG-Y path without base_path → blocked, RELATIVE_PATH_WITHOUT_BASE_PATH")
    p = _write_fixture("t4_07_relative_no_base.csv", [{
        "Survey Name": "Survey G", "Data Type": "2D",
        "Line Name": "L1", "SEG-Y File": rel_name,
    }])
    status, body = _pipeline(str(p), base_path=None)
    require(status == 200, "HTTP 200")
    row = body["rows"][0]
    require(row["status"] == "blocked", f"row status=blocked (got {row['status']!r})")
    codes = flag_codes(row.get("qaqc_flags", []))
    require("RELATIVE_PATH_WITHOUT_BASE_PATH" in codes, "RELATIVE_PATH_WITHOUT_BASE_PATH flag present")

    # ------------------------------------------------------------------
    # [8] Supporting documents valid → SUPPORTING_DOCUMENT_PATH_VALIDATED
    # ------------------------------------------------------------------
    print("\n[8] Supporting documents valid → SUPPORTING_DOCUMENT_PATH_VALIDATED flags")
    p = _write_fixture("t4_08_docs_valid.csv", [{
        "Survey Name": "Survey H", "Data Type": "2D",
        "Line Name": "L1", "SEG-Y File": SEGY_VALID,
        "Documents": f"{DOC1}; {DOC2}",
    }])
    status, body = _pipeline(str(p))
    require(status == 200, "HTTP 200")
    row = body["rows"][0]
    require(row["status"] == "ready", "row status=ready")
    pv = row.get("path_validation", {})
    require(pv.get("summary", {}).get("supporting_document_count") == 2,
            f"supporting_document_count=2 (got {pv.get('summary', {}).get('supporting_document_count')!r})")
    require(pv.get("summary", {}).get("supporting_documents_valid") == 2,
            "supporting_documents_valid=2")
    codes = flag_codes(row.get("qaqc_flags", []))
    require("SUPPORTING_DOCUMENT_PATH_VALIDATED" in codes, "SUPPORTING_DOCUMENT_PATH_VALIDATED present")
    docs = pv.get("supporting_documents", [])
    require(len(docs) == 2, f"2 doc results (got {len(docs)})")
    require(all(d.get("readable") for d in docs), "all docs readable=True")

    # ------------------------------------------------------------------
    # [9] Supporting document missing → warning, row remains ready
    # ------------------------------------------------------------------
    print("\n[9] Supporting document missing → SUPPORTING_DOCUMENT_NOT_FOUND warning, row stays ready")
    p = _write_fixture("t4_09_doc_missing.csv", [{
        "Survey Name": "Survey I", "Data Type": "2D",
        "Line Name": "L1", "SEG-Y File": SEGY_VALID,
        "Documents": DOC_MISSING,
    }])
    status, body = _pipeline(str(p))
    require(status == 200, "HTTP 200")
    row = body["rows"][0]
    require(row["status"] == "ready", f"row status=ready (doc warning does not block) (got {row['status']!r})")
    codes = flag_codes(row.get("qaqc_flags", []))
    require("SUPPORTING_DOCUMENT_NOT_FOUND" in codes, "SUPPORTING_DOCUMENT_NOT_FOUND flag present")
    require("SEGY_PATH_VALIDATED" in codes, "SEGY_PATH_VALIDATED still present (SEG-Y valid)")

    # ------------------------------------------------------------------
    # [10] Supporting document path is directory → warning, row stays ready
    # ------------------------------------------------------------------
    print("\n[10] Supporting document is directory → SUPPORTING_DOCUMENT_PATH_NOT_FILE warning, row stays ready")
    p = _write_fixture("t4_10_doc_is_dir.csv", [{
        "Survey Name": "Survey J", "Data Type": "2D",
        "Line Name": "L1", "SEG-Y File": SEGY_VALID,
        "Documents": DOC_DIR,
    }])
    status, body = _pipeline(str(p))
    require(status == 200, "HTTP 200")
    row = body["rows"][0]
    require(row["status"] == "ready", f"row status=ready (got {row['status']!r})")
    codes = flag_codes(row.get("qaqc_flags", []))
    require("SUPPORTING_DOCUMENT_PATH_NOT_FILE" in codes, "SUPPORTING_DOCUMENT_PATH_NOT_FILE flag present")

    # ------------------------------------------------------------------
    # [11] validate-paths before normalize → HTTP 400
    # ------------------------------------------------------------------
    print("\n[11] validate-paths on non-normalized session → HTTP 400")
    p = _write_fixture("t4_11_not_normalized.csv", [{
        "Survey Name": "Survey K", "Data Type": "2D",
        "Line Name": "L1", "SEG-Y File": SEGY_VALID,
    }])
    validated_only = _pipeline_create_validate_only(str(p))
    sid = validated_only["session_id"]
    status, body = post(f"/api/sblt/sessions/{sid}/validate-paths")
    require(status == 400, f"HTTP 400 for validated-only session (got {status})")

    # ------------------------------------------------------------------
    # [12] validate-paths nonexistent session → HTTP 404
    # ------------------------------------------------------------------
    print("\n[12] validate-paths on nonexistent session → HTTP 404")
    status, body = post("/api/sblt/sessions/sblt_99999999_000000_ffffffff/validate-paths")
    require(status == 404, f"HTTP 404 (got {status})")

    # ------------------------------------------------------------------
    # [13] Field preservation
    # ------------------------------------------------------------------
    print("\n[13] source_values, canonical_fields, normalized_metadata, identity_hints unchanged")
    p = _write_fixture("t4_13_preservation.csv", [{
        "Survey Name": "Survey L", "Data Type": "2D",
        "Line Name": "L1", "SEG-Y File": SEGY_VALID,
        "Sample Interval": "4 ms",
    }])
    # Capture normalized session first for comparison
    status0, body0 = post("/api/sblt/sessions", {"loadsheet_path": str(p)})
    if status0 != 200:
        print(f"  ERROR  create_session failed: {status0}")
        sys.exit(1)
    sid = body0["session_id"]
    post(f"/api/sblt/sessions/{sid}/validate")
    _, norm_body = post(f"/api/sblt/sessions/{sid}/normalize")
    norm_row = norm_body["rows"][0]

    _, pv_body = post(f"/api/sblt/sessions/{sid}/validate-paths")
    pv_row = pv_body["rows"][0]

    require(pv_row.get("source_values") == norm_row.get("source_values"),
            "source_values preserved")
    require(pv_row.get("canonical_fields") == norm_row.get("canonical_fields"),
            "canonical_fields preserved")
    require(pv_row.get("normalized_metadata") == norm_row.get("normalized_metadata"),
            "normalized_metadata preserved")
    require(pv_row.get("identity_hints") == norm_row.get("identity_hints"),
            "identity_hints preserved")
    require("path_validation" in pv_row and pv_row["path_validation"].get("validated") is True,
            "path_validation block added")

    # ------------------------------------------------------------------
    # [14] Summary invariants
    # ------------------------------------------------------------------
    print("\n[14] Summary invariants")
    p = _write_fixture("t4_14_invariants.csv", [
        {"Survey Name": "S1", "Data Type": "2D", "Line Name": "L1", "SEG-Y File": SEGY_VALID},
        {"Survey Name": "S2", "Data Type": "2D", "Line Name": "L2", "SEG-Y File": SEGY_MISSING},
        {"Survey Name": "S3", "Data Type": "2D", "Line Name": "L3", "SEG-Y File": SEGY_VALID2},
    ])
    status, body = _pipeline(str(p))
    require(status == 200, "HTTP 200")
    row_count = body.get("row_count")
    rows = body.get("rows", [])
    summary = body.get("summary", {})
    require(row_count == len(rows), f"row_count ({row_count}) == len(rows) ({len(rows)})")
    require(summary.get("total") == len(rows), f"summary.total ({summary.get('total')}) == len(rows) ({len(rows)})")
    statuses = [r["status"] for r in rows]
    for s in set(statuses):
        in_summary = summary.get(s, 0)
        in_rows = statuses.count(s)
        require(in_summary == in_rows, f"summary[{s!r}]={in_summary} matches rows ({in_rows})")

    # ------------------------------------------------------------------
    # [15] Actions: ready→can_approve, blocked→no approve, can_register=False
    # ------------------------------------------------------------------
    print("\n[15] Row and session actions after path validation")
    p = _write_fixture("t4_15_actions.csv", [
        {"Survey Name": "S1", "Data Type": "2D", "Line Name": "L1", "SEG-Y File": SEGY_VALID},
        {"Survey Name": "S2", "Data Type": "2D", "Line Name": "L2", "SEG-Y File": SEGY_MISSING},
    ])
    status, body = _pipeline(str(p))
    require(status == 200, "HTTP 200")
    sess_actions = body.get("actions", {})
    require(sess_actions.get("can_validate") is True, "session.can_validate=True")
    require(sess_actions.get("can_approve") is True, "session.can_approve=True (has ready row)")
    require(sess_actions.get("can_register") is False, "session.can_register=False")

    ready_row = next((r for r in body["rows"] if r["status"] == "ready"), None)
    blocked_row = next((r for r in body["rows"] if r["status"] == "blocked"), None)

    if ready_row:
        ra = ready_row.get("actions", {})
        require(ra.get("can_approve") is True, "ready row.can_approve=True")
        require(ra.get("can_register") is False, "ready row.can_register=False")
        require(ra.get("requires_review") is False, "ready row.requires_review=False")
    else:
        print("  WARN  no ready row found in [15]")

    if blocked_row:
        ba = blocked_row.get("actions", {})
        require(ba.get("can_approve") is False, "blocked row.can_approve=False")
        require(ba.get("requires_review") is True, "blocked row.requires_review=True")
    else:
        print("  WARN  no blocked row found in [15]")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        run_tests()
    finally:
        shutil.rmtree(TMPDIR, ignore_errors=True)
        print(f"\nCleaned up temp dir: {TMPDIR}")

    print(f"\n{'=' * 50}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        sys.exit(1)
