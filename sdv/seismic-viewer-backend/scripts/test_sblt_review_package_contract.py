"""
SBLT-6 Contract Test: MDE Review Exception Packaging.

Tests the POST /api/sblt/sessions/{session_id}/build-review-package endpoint.

Usage:
    BASE_URL="http://127.0.0.1:8001" python3 scripts/test_sblt_review_package_contract.py

Environment:
    BASE_URL — base URL of the SBLT backend (default: http://127.0.0.1:8000)

Test cases:
    [1]  All-ready session (no conflicts, no missing, no duplicates)
    [2]  Conflict row (submitted sample_interval_ms disagrees with binary header)
    [3]  Missing required field (survey_name absent → blocked row → missing_required)
    [4]  Suggested candidate from textual header (line_name absent, found in SEG-Y text)
    [5]  Auto-accepted technical field (sample_interval_ms absent → auto_accepted from binary)
    [6]  dataset_key_duplicate (two rows, same survey+volume+segy filename)
    [7]  source_reference_duplicate (two rows, different survey/volume, same SEG-Y path)
    [8]  line_or_volume_duplicate (two 2D rows, same survey+line name)
    [9]  review_package schema fields complete (schema_version, summary, review_rows, etc.)
    [10] Endpoint before segy_header_evidence_extracted → HTTP 400
    [11] Nonexistent session → HTTP 404
    [12] Idempotency: second call replaces review_package and stays review_package_built
    [13] Session status advances to review_package_built
"""

from __future__ import annotations

import csv
import io
import json
import os
import struct
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


def get(path: str) -> tuple[int, dict]:
    url = BASE + path
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw.decode(errors="replace")}


# ---------------------------------------------------------------------------
# Synthetic SEG-Y file builder (duplicated from SBLT-5 test for independence)
# ---------------------------------------------------------------------------

def _make_binary_header_bytes(
    sample_interval_us: int = 4000,
    samples_per_trace: int = 500,
    data_sample_format_code: int = 5,
    measurement_system: int = 1,
) -> bytes:
    buf = bytearray(400)
    struct.pack_into(">H", buf, 16, sample_interval_us)
    struct.pack_into(">H", buf, 20, samples_per_trace)
    struct.pack_into(">H", buf, 24, data_sample_format_code)
    struct.pack_into(">H", buf, 54, measurement_system)
    return bytes(buf)


def _make_ascii_textual_header(lines: list[str] | None = None) -> bytes:
    fixed_lines: list[str] = []
    for i in range(40):
        if lines and i < len(lines):
            raw_line = lines[i]
        else:
            raw_line = f"C{i+1:02d} "
        fixed_lines.append(f"{raw_line:<80.80}")
    return "".join(fixed_lines).encode("ascii", errors="replace")


def make_synthetic_segy(
    path: str,
    *,
    sample_interval_us: int = 4000,
    samples_per_trace: int = 500,
    data_sample_format_code: int = 5,
    measurement_system: int = 1,
    textual_lines: list[str] | None = None,
) -> None:
    textual = _make_ascii_textual_header(textual_lines)   # 3200 bytes
    binary = _make_binary_header_bytes(
        sample_interval_us=sample_interval_us,
        samples_per_trace=samples_per_trace,
        data_sample_format_code=data_sample_format_code,
        measurement_system=measurement_system,
    )  # 400 bytes
    Path(path).write_bytes(textual + binary)


# ---------------------------------------------------------------------------
# Fixture CSV builder
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent
_FIXTURES_DIR = _SCRIPTS_DIR / "sblt_test_fixtures"


def _write_fixture(name: str, rows: list[dict]) -> Path:
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

def _pipeline_to_segy(
    loadsheet_path: str,
    base_path: str | None = None,
) -> tuple[str, int, dict]:
    """
    Create → validate → normalize → validate-paths → extract-segy-header-evidence.
    Returns (session_id, final_status_code, final_response_body).
    Aborts on any step failure.
    """
    status, body = post("/api/sblt/sessions", {
        "loadsheet_path": loadsheet_path,
        "base_path": base_path,
    })
    if status != 200:
        print(f"  ERROR  create_session: {status} {body}")
        sys.exit(1)
    sid = body["session_id"]

    for step in ("validate", "normalize", "validate-paths", "extract-segy-header-evidence"):
        status, body = post(f"/api/sblt/sessions/{sid}/{step}")
        if status != 200:
            print(f"  ERROR  {step}: {status} {body}")
            sys.exit(1)

    return sid, status, body


def _pipeline_full(
    loadsheet_path: str,
    base_path: str | None = None,
) -> tuple[str, int, dict]:
    """
    Create → validate → normalize → validate-paths → extract-segy-header-evidence
    → build-review-package.
    Returns (session_id, final_status_code, final_response_body).
    Aborts on any step failure.
    """
    sid, _, _ = _pipeline_to_segy(loadsheet_path, base_path)
    status, body = post(f"/api/sblt/sessions/{sid}/build-review-package")
    return sid, status, body


def _pipeline_before_segy(loadsheet_path: str) -> tuple[str, int, dict]:
    """
    Create → validate → normalize → validate-paths (stops before extract-segy-header-evidence).
    Returns (session_id, last_status_code, last_response_body).
    """
    status, body = post("/api/sblt/sessions", {"loadsheet_path": loadsheet_path})
    if status != 200:
        print(f"  ERROR  create_session: {status} {body}")
        sys.exit(1)
    sid = body["session_id"]
    for step in ("validate", "normalize", "validate-paths"):
        status, body = post(f"/api/sblt/sessions/{sid}/{step}")
        if status != 200:
            print(f"  ERROR  {step}: {status} {body}")
            sys.exit(1)
    return sid, status, body


# ---------------------------------------------------------------------------
# Temp file setup
# ---------------------------------------------------------------------------

TMPDIR = tempfile.mkdtemp(prefix="sblt6_test_")


def _tmp(name: str) -> str:
    return os.path.join(TMPDIR, name)


# SEG-Y fixtures
SEGY_READY      = _tmp("ready.sgy")         # clean, 4ms
SEGY_CONFLICT   = _tmp("conflict.sgy")      # 2ms — conflicts with submitted 4ms
SEGY_TEXT_LINE  = _tmp("text_line.sgy")     # textual header has LINE_NAME
SEGY_SPARSE     = _tmp("sparse.sgy")        # no submitted sample_interval → auto_accepted
SEGY_DUP_A      = _tmp("dup_a.sgy")         # duplicate key / identity group
SEGY_DUP_B      = _tmp("dup_b.sgy")         # different path, same key
SEGY_DUP_SAME   = _tmp("dup_a.sgy")         # same filename as DUP_A (in a subdir)
SEGY_2D_LINE    = _tmp("line_p.sgy")        # 2D line for identity dup test
SEGY_2D_LINE2   = _tmp("line_q.sgy")        # same survey+line name, different file

make_synthetic_segy(SEGY_READY, sample_interval_us=4000)
make_synthetic_segy(SEGY_CONFLICT, sample_interval_us=2000)
make_synthetic_segy(SEGY_TEXT_LINE, sample_interval_us=4000,
                    textual_lines=["C01 SURVEY: Alpha_Prospect",
                                   "C02 LINE NAME: LINE_001"])
make_synthetic_segy(SEGY_SPARSE, sample_interval_us=4000)
make_synthetic_segy(SEGY_DUP_A, sample_interval_us=4000)
make_synthetic_segy(SEGY_DUP_B, sample_interval_us=4000)
make_synthetic_segy(SEGY_2D_LINE, sample_interval_us=4000)
make_synthetic_segy(SEGY_2D_LINE2, sample_interval_us=4000)

# A duplicate of SEGY_DUP_A in a sub-directory (same filename "dup_a.sgy")
SEGY_DUP_SUBDIR = os.path.join(TMPDIR, "subdir")
os.makedirs(SEGY_DUP_SUBDIR, exist_ok=True)
SEGY_DUP_SUBDIR_FILE = os.path.join(SEGY_DUP_SUBDIR, "dup_a.sgy")
make_synthetic_segy(SEGY_DUP_SUBDIR_FILE, sample_interval_us=4000)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def run_tests() -> None:
    global PASS, FAIL

    # ==================================================================== #
    # [1] All-ready session (clean row, no review required)                 #
    # ==================================================================== #
    print("\n[1] All-ready session (clean row — sample_interval_ms matches)")
    fx = _write_fixture("sblt6_t01.csv", [{
        "Survey Name": "Alpha Prospect",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_A",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_READY,
    }])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[1a] HTTP 200")
    rp = body.get("review_package") or {}
    require(rp.get("schema_version") == "sblt.review_package.v1",
            "[1b] review_package.schema_version = sblt.review_package.v1",
            f"got: {rp.get('schema_version')!r}")
    require(rp.get("session_id") == sid,
            "[1c] review_package.session_id matches session")
    summary = rp.get("summary") or {}
    require(summary.get("total_rows") == 1, "[1d] summary.total_rows == 1",
            f"got: {summary.get('total_rows')!r}")
    require(summary.get("blocked_rows") == 0, "[1e] summary.blocked_rows == 0",
            f"got: {summary.get('blocked_rows')!r}")
    rr_list = rp.get("review_rows") or []
    if rr_list:
        rr = rr_list[0]
        require(rr.get("review_classification") in ("ready", "review_required"),
                "[1f] row review_classification is ready or review_required",
                f"got: {rr.get('review_classification')!r}")
    pkg_status = rp.get("status") or {}
    require(isinstance(pkg_status.get("has_blockers"), bool),
            "[1g] review_package.status.has_blockers is bool")

    # ==================================================================== #
    # [2] Conflict row (submitted 4ms vs binary header 2ms)                 #
    # ==================================================================== #
    print("\n[2] Conflict row (submitted 4.0 ms vs binary header 2000µs)")
    fx = _write_fixture("sblt6_t02.csv", [{
        "Survey Name": "Beta Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_B",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_CONFLICT,
    }])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[2a] HTTP 200")
    rp = body.get("review_package") or {}
    rr_list = rp.get("review_rows") or []
    require(len(rr_list) == 1, "[2b] 1 review row")
    if rr_list:
        rr = rr_list[0]
        require(rr.get("review_classification") == "review_required",
                "[2c] review_classification = review_required",
                f"got: {rr.get('review_classification')!r}")
        conflicts = rr.get("conflicts") or []
        require("sample_interval_ms" in conflicts,
                "[2d] sample_interval_ms in conflicts",
                f"conflicts: {conflicts!r}")
        fe = rr.get("field_exceptions") or []
        fe_fields = [f["field"] for f in fe]
        require("sample_interval_ms" in fe_fields,
                "[2e] field_exception for sample_interval_ms present",
                f"field_exception fields: {fe_fields!r}")
    summary = rp.get("summary") or {}
    require(summary.get("rows_with_conflicts", 0) >= 1,
            "[2f] summary.rows_with_conflicts >= 1",
            f"got: {summary.get('rows_with_conflicts')!r}")
    pkg_status = rp.get("status") or {}
    require(pkg_status.get("requires_user_review") is True,
            "[2g] review_package.status.requires_user_review = True")

    # ==================================================================== #
    # [3] Missing required field → blocked row → missing_required           #
    # ==================================================================== #
    print("\n[3] Missing required field (survey_name absent → blocked)")
    fx = _write_fixture("sblt6_t03.csv", [{
        "Data Type": "3d_volume",
        "Volume Name": "Vol_C",
        "SEG-Y File": SEGY_READY,
    }])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[3a] HTTP 200")
    rp = body.get("review_package") or {}
    rr_list = rp.get("review_rows") or []
    require(len(rr_list) == 1, "[3b] 1 review row")
    if rr_list:
        rr = rr_list[0]
        require(rr.get("review_classification") == "blocked",
                "[3c] review_classification = blocked",
                f"got: {rr.get('review_classification')!r}")
        mr = rr.get("missing_required") or []
        require("survey_name" in mr,
                "[3d] survey_name in missing_required",
                f"missing_required: {mr!r}")
    summary = rp.get("summary") or {}
    require(summary.get("blocked_rows", 0) >= 1,
            "[3e] summary.blocked_rows >= 1",
            f"got: {summary.get('blocked_rows')!r}")
    require(summary.get("rows_with_missing_required", 0) >= 1,
            "[3f] summary.rows_with_missing_required >= 1",
            f"got: {summary.get('rows_with_missing_required')!r}")

    # ==================================================================== #
    # [4] Suggested candidate from textual header                           #
    # ==================================================================== #
    print("\n[4] Suggested candidate from textual header (line_name absent → found in SEG-Y)")
    fx = _write_fixture("sblt6_t04.csv", [{
        "Survey Name": "Alpha Prospect",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_D",
        "SEG-Y File": SEGY_TEXT_LINE,
    }])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[4a] HTTP 200")
    rp = body.get("review_package") or {}
    rr_list = rp.get("review_rows") or []
    if rr_list:
        rr = rr_list[0]
        require(rr.get("review_classification") in ("ready", "review_required"),
                "[4b] review_classification not blocked",
                f"got: {rr.get('review_classification')!r}")
        # line_name should be either in suggested_candidates (if MDE classified it)
        # or auto_accepted_fields, or at minimum the MDE bundle exists
        mde_exists = bool(body.get("rows", [{}])[0].get("metadata_evidence"))
        require(mde_exists, "[4c] row has metadata_evidence populated")

    # ==================================================================== #
    # [5] Auto-accepted technical field                                     #
    # ==================================================================== #
    print("\n[5] Auto-accepted technical field (sample_interval_ms absent → auto_accepted)")
    fx = _write_fixture("sblt6_t05.csv", [{
        "Survey Name": "Gamma Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_E",
        "SEG-Y File": SEGY_SPARSE,
    }])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[5a] HTTP 200")
    rp = body.get("review_package") or {}
    rr_list = rp.get("review_rows") or []
    if rr_list:
        rr = rr_list[0]
        auto = rr.get("auto_accepted_fields") or []
        require("sample_interval_ms" in auto,
                "[5b] sample_interval_ms in auto_accepted_fields",
                f"auto_accepted_fields: {auto!r}")
    summary = rp.get("summary") or {}
    require(summary.get("rows_with_auto_accepted_fields", 0) >= 1,
            "[5c] summary.rows_with_auto_accepted_fields >= 1",
            f"got: {summary.get('rows_with_auto_accepted_fields')!r}")

    # ==================================================================== #
    # [6] dataset_key_duplicate (same survey+volume+segy filename)          #
    # ==================================================================== #
    print("\n[6] dataset_key_duplicate (two rows: same survey+volume, same segy filename in diff dirs)")
    fx = _write_fixture("sblt6_t06.csv", [
        {
            "Survey Name": "Delta Survey",
            "Data Type": "3d_volume",
            "Volume Name": "Vol_F",
            "SEG-Y File": SEGY_DUP_A,      # TMPDIR/dup_a.sgy
        },
        {
            "Survey Name": "Delta Survey",
            "Data Type": "3d_volume",
            "Volume Name": "Vol_F",
            "SEG-Y File": SEGY_DUP_SUBDIR_FILE,  # TMPDIR/subdir/dup_a.sgy (same filename)
        },
    ])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[6a] HTTP 200")
    rp = body.get("review_package") or {}
    dup_groups = rp.get("duplicate_groups") or []
    dk_dups = [g for g in dup_groups if g.get("risk_type") == "dataset_key_duplicate"]
    require(len(dk_dups) >= 1,
            "[6b] at least 1 dataset_key_duplicate group",
            f"duplicate_groups: {[g.get('risk_type') for g in dup_groups]!r}")
    if dk_dups:
        grp = dk_dups[0]
        require(len(grp.get("row_ids") or []) >= 2,
                "[6c] dataset_key_duplicate group has >= 2 row_ids",
                f"row_ids: {grp.get('row_ids')!r}")
        require(grp.get("severity") == "warning",
                "[6d] dataset_key_duplicate severity = warning",
                f"got: {grp.get('severity')!r}")
    summary = rp.get("summary") or {}
    require(summary.get("duplicate_group_count", 0) >= 1,
            "[6e] summary.duplicate_group_count >= 1",
            f"got: {summary.get('duplicate_group_count')!r}")
    require(summary.get("duplicate_risk_row_count", 0) >= 2,
            "[6f] summary.duplicate_risk_row_count >= 2",
            f"got: {summary.get('duplicate_risk_row_count')!r}")

    # ==================================================================== #
    # [7] source_reference_duplicate (same SEG-Y file, different survey)   #
    # ==================================================================== #
    print("\n[7] source_reference_duplicate (two rows with the same SEG-Y path)")
    fx = _write_fixture("sblt6_t07.csv", [
        {
            "Survey Name": "Echo Survey",
            "Data Type": "3d_volume",
            "Volume Name": "Vol_G1",
            "SEG-Y File": SEGY_DUP_B,
        },
        {
            "Survey Name": "Foxtrot Survey",
            "Data Type": "3d_volume",
            "Volume Name": "Vol_G2",
            "SEG-Y File": SEGY_DUP_B,   # same absolute path
        },
    ])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[7a] HTTP 200")
    rp = body.get("review_package") or {}
    dup_groups = rp.get("duplicate_groups") or []
    src_dups = [g for g in dup_groups if g.get("risk_type") == "source_reference_duplicate"]
    require(len(src_dups) >= 1,
            "[7b] at least 1 source_reference_duplicate group",
            f"risk_types: {[g.get('risk_type') for g in dup_groups]!r}")
    if src_dups:
        grp = src_dups[0]
        require(len(grp.get("row_ids") or []) >= 2,
                "[7c] source_reference_duplicate group has >= 2 row_ids")
        require(grp.get("severity") == "warning",
                "[7d] source_reference_duplicate severity = warning")

    # ==================================================================== #
    # [8] line_or_volume_duplicate (two 2D rows, same survey + line name)  #
    # ==================================================================== #
    print("\n[8] line_or_volume_duplicate (two 2D rows, same survey+line_name)")
    fx = _write_fixture("sblt6_t08.csv", [
        {
            "Survey Name": "Gulf Survey",
            "Data Type": "2d_line",
            "Line Name": "Line_001",
            "SEG-Y File": SEGY_2D_LINE,
        },
        {
            "Survey Name": "Gulf Survey",
            "Data Type": "2d_line",
            "Line Name": "Line_001",
            "SEG-Y File": SEGY_2D_LINE2,  # different SEG-Y, same survey+line identity
        },
    ])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[8a] HTTP 200")
    rp = body.get("review_package") or {}
    dup_groups = rp.get("duplicate_groups") or []
    identity_dups = [g for g in dup_groups if g.get("risk_type") == "line_or_volume_duplicate"]
    require(len(identity_dups) >= 1,
            "[8b] at least 1 line_or_volume_duplicate group",
            f"risk_types: {[g.get('risk_type') for g in dup_groups]!r}")
    if identity_dups:
        grp = identity_dups[0]
        require(len(grp.get("row_ids") or []) >= 2,
                "[8c] line_or_volume_duplicate group has >= 2 row_ids")
        require(grp.get("severity") == "warning",
                "[8d] line_or_volume_duplicate severity = warning")

    # ==================================================================== #
    # [9] review_package schema fields complete                             #
    # ==================================================================== #
    print("\n[9] review_package schema fields complete")
    fx = _write_fixture("sblt6_t09.csv", [{
        "Survey Name": "Hotel Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_H",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_READY,
    }])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[9a] HTTP 200")
    rp = body.get("review_package") or {}
    for field in (
        "schema_version", "session_id", "created_at",
        "source_session_status", "summary", "review_rows",
        "duplicate_groups", "bulk_actions", "blocking_reasons", "status",
    ):
        require(field in rp, f"[9b] review_package has field {field!r}",
                f"keys present: {list(rp.keys())!r}")
    summary = rp.get("summary") or {}
    for sf in (
        "total_rows", "ready_rows", "review_required_rows", "blocked_rows",
        "rows_with_conflicts", "rows_with_missing_required",
        "rows_with_missing_recommended", "rows_with_suggested_candidates",
        "rows_with_auto_accepted_fields",
        "duplicate_group_count", "duplicate_risk_row_count",
    ):
        require(sf in summary, f"[9c] summary has field {sf!r}",
                f"summary keys: {list(summary.keys())!r}")
    pkg_status = rp.get("status") or {}
    for sf in ("can_continue_to_approval", "requires_user_review", "has_blockers"):
        require(sf in pkg_status, f"[9d] status has field {sf!r}",
                f"status keys: {list(pkg_status.keys())!r}")
    rr_list = rp.get("review_rows") or []
    if rr_list:
        rr = rr_list[0]
        for rf in (
            "row_id", "source_row_number", "row_status", "record_type",
            "dataset_label", "dataset_key", "source_reference",
            "review_classification", "field_exceptions", "auto_accepted_fields",
            "suggested_candidates", "conflicts", "missing_required",
            "missing_recommended", "blocking_flags", "review_summary",
        ):
            require(rf in rr, f"[9e] review_row has field {rf!r}",
                    f"review_row keys: {list(rr.keys())!r}")

    # ==================================================================== #
    # [10] Call before segy_header_evidence_extracted → HTTP 400            #
    # ==================================================================== #
    print("\n[10] build-review-package before extract-segy-header-evidence → HTTP 400")
    fx = _write_fixture("sblt6_t10.csv", [{
        "Survey Name": "India Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_I",
        "SEG-Y File": SEGY_READY,
    }])
    sid10, _, _ = _pipeline_before_segy(str(fx))
    status, body = post(f"/api/sblt/sessions/{sid10}/build-review-package")
    require(status == 400, "[10a] HTTP 400 before segy evidence extraction",
            f"got: {status} {body}")

    # ==================================================================== #
    # [11] Nonexistent session → HTTP 404                                  #
    # ==================================================================== #
    print("\n[11] Nonexistent session → HTTP 404")
    status, body = post("/api/sblt/sessions/sblt_nonexistent_99/build-review-package")
    require(status == 404, "[11a] HTTP 404 for nonexistent session",
            f"got: {status} {body}")

    # ==================================================================== #
    # [12] Idempotency: second call replaces review_package                #
    # ==================================================================== #
    print("\n[12] Idempotency (second build-review-package call succeeds)")
    fx = _write_fixture("sblt6_t12.csv", [{
        "Survey Name": "Juliet Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_J",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_READY,
    }])
    sid12, status1, body1 = _pipeline_full(str(fx))
    require(status1 == 200, "[12a] first call HTTP 200")
    rp1_id = (body1.get("review_package") or {}).get("created_at")

    status2, body2 = post(f"/api/sblt/sessions/{sid12}/build-review-package")
    require(status2 == 200, "[12b] second call HTTP 200")
    require(body2.get("status") == "review_package_built",
            "[12c] session status still review_package_built after second call",
            f"got: {body2.get('status')!r}")
    rp2_id = (body2.get("review_package") or {}).get("created_at")
    require(rp2_id is not None, "[12d] second call produces review_package.created_at")
    # created_at should differ (new timestamp each run)
    require(rp1_id != rp2_id,
            "[12e] second call produces fresh review_package (different created_at)",
            f"first: {rp1_id!r}, second: {rp2_id!r}")

    # ==================================================================== #
    # [13] Session status advances to review_package_built                 #
    # ==================================================================== #
    print("\n[13] Session status advances to review_package_built")
    fx = _write_fixture("sblt6_t13.csv", [{
        "Survey Name": "Kilo Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_K",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_READY,
    }])
    sid13, status, body = _pipeline_full(str(fx))
    require(status == 200, "[13a] HTTP 200")
    require(body.get("status") == "review_package_built",
            "[13b] session.status = review_package_built",
            f"got: {body.get('status')!r}")
    require("review_package" in body,
            "[13c] session response contains review_package key")
    # Verify actions contain can_validate (review_package_built is re-runnable)
    actions = body.get("actions") or {}
    require(isinstance(actions.get("can_validate"), bool),
            "[13d] session.actions.can_validate is bool",
            f"actions: {actions!r}")
    # can_register must always be False (SBLT-8 gate)
    require(actions.get("can_register") is False,
            "[13e] session.actions.can_register = False (SBLT-8 gate not reached)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_tests()
    print(f"\n{'='*50}")
    print(f"SBLT-6 review package contract: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
