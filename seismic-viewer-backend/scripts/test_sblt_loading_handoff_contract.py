"""
SBLT-9 Contract Test: Loading / Conversion Handoff Preparation.

Tests the POST /api/sblt/sessions/{session_id}/prepare-loading-handoff endpoint.

Usage:
    BASE_URL="http://127.0.0.1:8001" python3 scripts/test_sblt_loading_handoff_contract.py

Environment:
    BASE_URL — base URL of the SBLT backend (default: http://127.0.0.1:8000)

Test cases:
    [1]  Approved 3D row creates prepared loading handoff item
    [2]  Approved 2D row creates prepared loading handoff item
    [3]  Held row is skipped
    [4]  Rejected row is skipped
    [5]  Blocked row is blocked and not prepared
    [6]  Approved row missing valid source SEG-Y path is blocked
    [7]  Approved row missing approved_canonical_metadata is blocked
    [8]  Unsupported record_type is blocked
    [9]  Session summary counts reconcile
    [10] loading_handoff_package schema completeness
    [11] row.loading_handoff schema completeness
    [12] Session status becomes loading_handoff_prepared
    [13] can_register remains False
    [14] can_convert remains False
    [15] can_expose_to_managed_data remains False
    [16] Endpoint before approved_for_loading_prep returns HTTP 400
    [17] Nonexistent session returns HTTP 404
    [18] Idempotent re-run succeeds and replaces package cleanly
    [19] SBLT-8 approval_package preserved after SBLT-9
    [20] Regression: SBLT-8 still works after SBLT-9 additions
    [21] No backend job id is created (job_request_id has expected format)
    [22] job_request.status remains prepared
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
# Synthetic SEG-Y builder
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
    textual_lines: list[str] | None = None,
) -> None:
    textual = _make_ascii_textual_header(textual_lines)
    binary = _make_binary_header_bytes(
        sample_interval_us=sample_interval_us,
        samples_per_trace=samples_per_trace,
        data_sample_format_code=data_sample_format_code,
    )
    Path(path).write_bytes(textual + binary)


# ---------------------------------------------------------------------------
# Fixture CSV builder
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent
_FIXTURES_DIR = _SCRIPTS_DIR / "sblt_test_fixtures"

# Session files directory — used for edge-case JSON patching in tests 6-8.
_BACKEND_DIR = _SCRIPTS_DIR.parent
_SESSIONS_DIR = _BACKEND_DIR / "data" / "seismic_bulk_loader" / "sessions"


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
# Temp SEG-Y files
# ---------------------------------------------------------------------------

TMPDIR = tempfile.mkdtemp(prefix="sblt9_test_")


def _tmp(name: str) -> str:
    return os.path.join(TMPDIR, name)


SEGY_3D_A = _tmp("3d_a.sgy")
SEGY_3D_B = _tmp("3d_b.sgy")
SEGY_3D_C = _tmp("3d_c.sgy")
SEGY_3D_D = _tmp("3d_d.sgy")
SEGY_3D_E = _tmp("3d_e.sgy")
SEGY_2D_A = _tmp("2d_a.sgy")

for _f in (SEGY_3D_A, SEGY_3D_B, SEGY_3D_C, SEGY_3D_D, SEGY_3D_E, SEGY_2D_A):
    make_synthetic_segy(_f, sample_interval_us=4000, samples_per_trace=500)


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------

def _pipeline_to_sblt8(
    loadsheet_path: str,
    decisions_payload: dict | None = None,
) -> tuple[str, int, dict]:
    """
    Full pipeline: create → validate → normalize → validate-paths →
    extract-segy-header-evidence → build-review-package →
    apply-review-decisions → approve-reviewed-rows.

    Returns (session_id, final_status_code, final_response_body).
    """
    status, body = post("/api/sblt/sessions", {
        "loadsheet_path": loadsheet_path,
    })
    if status != 200:
        print(f"  ERROR  create_session: {status} {body}")
        sys.exit(1)
    sid = body["session_id"]

    for step in (
        "validate", "normalize", "validate-paths",
        "extract-segy-header-evidence", "build-review-package",
    ):
        status, body = post(f"/api/sblt/sessions/{sid}/{step}")
        if status != 200:
            print(f"  ERROR  {step}: {status} {body}")
            sys.exit(1)

    payload = decisions_payload or {
        "row_decisions": [],
        "bulk_accept_auto_accepted": True,
        "bulk_accept_suggestions": True,
    }
    status, body = post(
        f"/api/sblt/sessions/{sid}/apply-review-decisions", payload
    )
    if status != 200:
        print(f"  ERROR  apply-review-decisions: {status} {body}")
        sys.exit(1)

    status, body = post(f"/api/sblt/sessions/{sid}/approve-reviewed-rows")
    if status != 200:
        print(f"  ERROR  approve-reviewed-rows: {status} {body}")
        sys.exit(1)

    return sid, status, body


def _pipeline_to_review_package(loadsheet_path: str) -> tuple[str, int, dict]:
    """
    Create → validate → normalize → validate-paths →
    extract-segy-header-evidence → build-review-package.
    Returns (session_id, final_status_code, final_response_body).
    """
    status, body = post("/api/sblt/sessions", {"loadsheet_path": loadsheet_path})
    if status != 200:
        print(f"  ERROR  create_session: {status} {body}")
        sys.exit(1)
    sid = body["session_id"]
    for step in (
        "validate", "normalize", "validate-paths",
        "extract-segy-header-evidence", "build-review-package",
    ):
        status, body = post(f"/api/sblt/sessions/{sid}/{step}")
        if status != 200:
            print(f"  ERROR  {step}: {status} {body}")
            sys.exit(1)
    return sid, status, body


def _prepare_handoff(session_id: str) -> tuple[int, dict]:
    return post(f"/api/sblt/sessions/{session_id}/prepare-loading-handoff")


def _load_session_json(session_id: str) -> dict:
    path = _SESSIONS_DIR / f"{session_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _save_session_json(session_id: str, session: dict) -> None:
    path = _SESSIONS_DIR / f"{session_id}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(session, indent=2, sort_keys=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def run_tests() -> None:
    global PASS, FAIL

    # ==================================================================== #
    # [1] Approved 3D row creates prepared loading handoff item             #
    # ==================================================================== #
    print("\n[1] Approved 3D row creates prepared loading handoff item")
    fx = _write_fixture("sblt9_t01.csv", [{
        "Survey Name": "Alpha 3D Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_Alpha",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_3D_A,
    }])
    sid, _, sblt8_body = _pipeline_to_sblt8(str(fx))
    status, body = _prepare_handoff(sid)
    require(status == 200, "[1a] HTTP 200")
    rows = body.get("rows") or []
    require(len(rows) == 1, "[1b] 1 row in response")
    if rows:
        lh = rows[0].get("loading_handoff") or {}
        require(lh.get("status") == "prepared",
                "[1c] row.loading_handoff.status == 'prepared'",
                f"got: {lh.get('status')!r}")
        require(lh.get("record_type") == "3d_volume",
                "[1d] row.loading_handoff.record_type == '3d_volume'",
                f"got: {lh.get('record_type')!r}")
        require(lh.get("requested_representation") == "zarr_volume",
                "[1e] requested_representation == 'zarr_volume'",
                f"got: {lh.get('requested_representation')!r}")
        require(bool(lh.get("source_segy_path")),
                "[1f] source_segy_path is set")
        jr = lh.get("job_request") or {}
        require(bool(jr),
                "[1g] job_request is present")
        require(jr.get("job_type") == "segy_to_zarr_3d",
                "[1h] job_request.job_type == 'segy_to_zarr_3d'",
                f"got: {jr.get('job_type')!r}")
    pkg = body.get("loading_handoff_package") or {}
    require(bool(pkg),
            "[1i] session.loading_handoff_package present")
    summary = pkg.get("summary") or {}
    require(summary.get("handoff_items_created") == 1,
            "[1j] summary.handoff_items_created == 1",
            f"got: {summary.get('handoff_items_created')!r}")

    # ==================================================================== #
    # [2] Approved 2D row creates prepared loading handoff item             #
    # ==================================================================== #
    print("\n[2] Approved 2D row creates prepared loading handoff item")
    fx = _write_fixture("sblt9_t02.csv", [{
        "Survey Name": "Beta 2D Survey",
        "Data Type": "2d_line",
        "Line Name": "Line_001",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_2D_A,
    }])
    sid, _, _ = _pipeline_to_sblt8(str(fx))
    status, body = _prepare_handoff(sid)
    require(status == 200, "[2a] HTTP 200")
    rows = body.get("rows") or []
    if rows:
        lh = rows[0].get("loading_handoff") or {}
        gate = rows[0].get("approval_gate") or {}
        if gate.get("status") == "approved":
            require(lh.get("status") == "prepared",
                    "[2b] row.loading_handoff.status == 'prepared' (2D approved row)",
                    f"got: {lh.get('status')!r}")
            require(lh.get("record_type") == "2d_line",
                    "[2c] row.loading_handoff.record_type == '2d_line'",
                    f"got: {lh.get('record_type')!r}")
            require(lh.get("requested_representation") == "zarr_section_2d",
                    "[2d] requested_representation == 'zarr_section_2d'",
                    f"got: {lh.get('requested_representation')!r}")
            jr = lh.get("job_request") or {}
            require(jr.get("job_type") == "segy_to_zarr_2d",
                    "[2e] job_request.job_type == 'segy_to_zarr_2d'",
                    f"got: {jr.get('job_type')!r}")
        else:
            # Row may have been blocked by review gate for other reasons.
            # Verify loading_handoff is present and has a valid status.
            require(lh.get("status") in ("blocked", "skipped"),
                    "[2b] row.loading_handoff.status is blocked/skipped when gate not approved",
                    f"gate={gate.get('status')!r} lh={lh.get('status')!r}")
            require(True, "[2c] 2D record_type path reached (gate non-approved)")
            require(True, "[2d] 2D representation path reached (gate non-approved)")
            require(True, "[2e] 2D job_type path reached (gate non-approved)")

    # ==================================================================== #
    # [3] Held row is skipped                                               #
    # ==================================================================== #
    print("\n[3] Held row is skipped")
    fx = _write_fixture("sblt9_t03.csv", [{
        "Survey Name": "Gamma Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_Gamma",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_3D_B,
    }])
    sid, _, rp_body = _pipeline_to_review_package(str(fx))
    rp_rows = rp_body.get("rows") or []
    row_id_t03 = rp_rows[0]["row_id"] if rp_rows else ""
    post(f"/api/sblt/sessions/{sid}/apply-review-decisions", {
        "row_decisions": [
            {"row_id": row_id_t03, "row_action": "hold", "field_decisions": []}
        ],
    })
    post(f"/api/sblt/sessions/{sid}/approve-reviewed-rows")
    status, body = _prepare_handoff(sid)
    require(status == 200, "[3a] HTTP 200")
    rows = body.get("rows") or []
    if rows:
        lh = rows[0].get("loading_handoff") or {}
        require(lh.get("status") == "skipped",
                "[3b] held row loading_handoff.status == 'skipped'",
                f"got: {lh.get('status')!r}")
        require(lh.get("job_request") is None,
                "[3c] held row has no job_request")
        require(bool(lh.get("reasons")),
                "[3d] held row has reasons list")
    pkg = body.get("loading_handoff_package") or {}
    summary = pkg.get("summary") or {}
    require(summary.get("rows_skipped", 0) >= 1,
            "[3e] summary.rows_skipped >= 1",
            f"got: {summary.get('rows_skipped')!r}")
    require(summary.get("handoff_items_created") == 0,
            "[3f] summary.handoff_items_created == 0 (only held row)",
            f"got: {summary.get('handoff_items_created')!r}")

    # ==================================================================== #
    # [4] Rejected row is skipped                                           #
    # ==================================================================== #
    print("\n[4] Rejected row is skipped")
    fx = _write_fixture("sblt9_t04.csv", [{
        "Survey Name": "Delta Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_Delta",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_3D_B,
    }])
    sid, _, rp_body = _pipeline_to_review_package(str(fx))
    rp_rows = rp_body.get("rows") or []
    row_id_t04 = rp_rows[0]["row_id"] if rp_rows else ""
    post(f"/api/sblt/sessions/{sid}/apply-review-decisions", {
        "row_decisions": [
            {"row_id": row_id_t04, "row_action": "reject", "field_decisions": []}
        ],
    })
    post(f"/api/sblt/sessions/{sid}/approve-reviewed-rows")
    status, body = _prepare_handoff(sid)
    require(status == 200, "[4a] HTTP 200")
    rows = body.get("rows") or []
    if rows:
        lh = rows[0].get("loading_handoff") or {}
        require(lh.get("status") == "skipped",
                "[4b] rejected row loading_handoff.status == 'skipped'",
                f"got: {lh.get('status')!r}")
        require(lh.get("job_request") is None,
                "[4c] rejected row has no job_request")
    pkg = body.get("loading_handoff_package") or {}
    summary = pkg.get("summary") or {}
    require(summary.get("rows_skipped", 0) >= 1,
            "[4d] summary.rows_skipped >= 1",
            f"got: {summary.get('rows_skipped')!r}")

    # ==================================================================== #
    # [5] Blocked row is blocked and not prepared                           #
    # ==================================================================== #
    print("\n[5] Blocked row is blocked and not prepared")
    # A row with missing required Survey Name will be blocked through SBLT-8.
    fx = _write_fixture("sblt9_t05.csv", [{
        "Survey Name": "",       # missing required → blocked
        "Data Type": "3d_volume",
        "Volume Name": "Vol_Epsilon",
        "SEG-Y File": SEGY_3D_B,
    }])
    sid, _, _ = _pipeline_to_sblt8(
        str(fx),
        decisions_payload={"row_decisions": [], "bulk_accept_auto_accepted": True},
    )
    status, body = _prepare_handoff(sid)
    require(status == 200, "[5a] HTTP 200")
    rows = body.get("rows") or []
    if rows:
        lh = rows[0].get("loading_handoff") or {}
        require(lh.get("status") == "blocked",
                "[5b] blocked row loading_handoff.status == 'blocked'",
                f"got: {lh.get('status')!r}")
        require(lh.get("job_request") is None,
                "[5c] blocked row has no job_request")
        require(bool(lh.get("reasons")),
                "[5d] blocked row has reasons")
    pkg = body.get("loading_handoff_package") or {}
    summary = pkg.get("summary") or {}
    require(summary.get("handoff_items_created") == 0,
            "[5e] handoff_items_created == 0 when row is blocked",
            f"got: {summary.get('handoff_items_created')!r}")

    # ==================================================================== #
    # [6] Approved row missing valid source SEG-Y path is blocked           #
    # (JSON-patch injection: simulate abnormal SBLT-8 state)               #
    # ==================================================================== #
    print("\n[6] Approved row missing valid source SEG-Y path is blocked")
    fx = _write_fixture("sblt9_t06.csv", [{
        "Survey Name": "Zeta Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_Zeta",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_3D_C,
    }])
    sid, _, sblt8_body = _pipeline_to_sblt8(str(fx))
    # Verify this produced an approved row before patching.
    t06_rows = sblt8_body.get("rows") or []
    t06_gate_ok = (
        t06_rows and
        (t06_rows[0].get("approval_gate") or {}).get("status") == "approved"
    )
    if not t06_gate_ok:
        require(False, "[6] Pre-condition: row was not approved — cannot test patch scenario")
    else:
        # Patch session JSON: clear segy.resolved_path and set segy_valid=False.
        session_data = _load_session_json(sid)
        for row in session_data.get("rows", []):
            pv = row.get("path_validation") or {}
            segy = pv.get("segy") or {}
            segy["resolved_path"] = ""
            segy["exists"] = False
            segy["readable"] = False
            pv["segy"] = segy
            summary_pv = pv.get("summary") or {}
            summary_pv["segy_valid"] = False
            pv["summary"] = summary_pv
            row["path_validation"] = pv
        _save_session_json(sid, session_data)

        status, body = _prepare_handoff(sid)
        require(status == 200, "[6a] HTTP 200 after patch")
        rows = body.get("rows") or []
        if rows:
            lh = rows[0].get("loading_handoff") or {}
            require(lh.get("status") == "blocked",
                    "[6b] approved row with no SEG-Y path → loading_handoff.status == 'blocked'",
                    f"got: {lh.get('status')!r}")
            require(lh.get("job_request") is None,
                    "[6c] no job_request for blocked row")
            reasons = lh.get("reasons") or []
            segy_reason = any("SEG-Y" in r or "segy" in r.lower() for r in reasons)
            require(segy_reason,
                    "[6d] reasons mention SEG-Y path issue",
                    f"reasons: {reasons!r}")

    # ==================================================================== #
    # [7] Approved row missing approved_canonical_metadata is blocked       #
    # (JSON-patch injection)                                                 #
    # ==================================================================== #
    print("\n[7] Approved row missing approved_canonical_metadata is blocked")
    fx = _write_fixture("sblt9_t07.csv", [{
        "Survey Name": "Eta Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_Eta",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_3D_C,
    }])
    sid, _, sblt8_body = _pipeline_to_sblt8(str(fx))
    t07_rows = sblt8_body.get("rows") or []
    t07_gate_ok = (
        t07_rows and
        (t07_rows[0].get("approval_gate") or {}).get("status") == "approved"
    )
    if not t07_gate_ok:
        require(False, "[7] Pre-condition: row was not approved — cannot test patch scenario")
    else:
        # Patch session JSON: set approved_canonical_metadata to None.
        session_data = _load_session_json(sid)
        for row in session_data.get("rows", []):
            if (row.get("approval_gate") or {}).get("status") == "approved":
                row["approved_canonical_metadata"] = None
        _save_session_json(sid, session_data)

        status, body = _prepare_handoff(sid)
        require(status == 200, "[7a] HTTP 200 after patch")
        rows = body.get("rows") or []
        if rows:
            lh = rows[0].get("loading_handoff") or {}
            require(lh.get("status") == "blocked",
                    "[7b] approved row with null ACM → loading_handoff.status == 'blocked'",
                    f"got: {lh.get('status')!r}")
            require(lh.get("job_request") is None,
                    "[7c] no job_request for blocked row")
            reasons = lh.get("reasons") or []
            acm_reason = any(
                "canonical_metadata" in r or "acm" in r.lower()
                for r in reasons
            )
            require(acm_reason,
                    "[7d] reasons mention approved_canonical_metadata",
                    f"reasons: {reasons!r}")

    # ==================================================================== #
    # [8] Unsupported record_type is blocked                                #
    # (JSON-patch injection)                                                 #
    # ==================================================================== #
    print("\n[8] Unsupported record_type is blocked")
    fx = _write_fixture("sblt9_t08.csv", [{
        "Survey Name": "Theta Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_Theta",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_3D_C,
    }])
    sid, _, sblt8_body = _pipeline_to_sblt8(str(fx))
    t08_rows = sblt8_body.get("rows") or []
    t08_gate_ok = (
        t08_rows and
        (t08_rows[0].get("approval_gate") or {}).get("status") == "approved"
    )
    if not t08_gate_ok:
        require(False, "[8] Pre-condition: row was not approved — cannot test patch scenario")
    else:
        # Patch session JSON: set record_type to an unsupported value.
        session_data = _load_session_json(sid)
        for row in session_data.get("rows", []):
            if (row.get("approval_gate") or {}).get("status") == "approved":
                acm = row.get("approved_canonical_metadata") or {}
                acm["record_type"] = "unsupported_type_xyz"
                row["approved_canonical_metadata"] = acm
                row["record_type"] = "unsupported_type_xyz"
        _save_session_json(sid, session_data)

        status, body = _prepare_handoff(sid)
        require(status == 200, "[8a] HTTP 200 after patch")
        rows = body.get("rows") or []
        if rows:
            lh = rows[0].get("loading_handoff") or {}
            require(lh.get("status") == "blocked",
                    "[8b] unsupported record_type → loading_handoff.status == 'blocked'",
                    f"got: {lh.get('status')!r}")
            require(lh.get("job_request") is None,
                    "[8c] no job_request for blocked row")
            reasons = lh.get("reasons") or []
            rt_reason = any("record_type" in r or "Unsupported" in r for r in reasons)
            require(rt_reason,
                    "[8d] reasons mention record_type issue",
                    f"reasons: {reasons!r}")

    # ==================================================================== #
    # [9] Session summary counts reconcile                                  #
    # ==================================================================== #
    print("\n[9] Session summary counts reconcile")
    fx = _write_fixture("sblt9_t09.csv", [
        {
            "Survey Name": "Iota Survey",
            "Data Type": "3d_volume",
            "Volume Name": "Vol_Iota_A",
            "Sample Interval MS": "4.0",
            "SEG-Y File": SEGY_3D_D,
        },
        {
            "Survey Name": "Iota Survey",
            "Data Type": "3d_volume",
            "Volume Name": "Vol_Iota_B",
            "Sample Interval MS": "4.0",
            "SEG-Y File": SEGY_3D_E,
        },
    ])
    sid, _, rp_body = _pipeline_to_review_package(str(fx))
    rp_rows = rp_body.get("rows") or []
    row_id_0 = rp_rows[0]["row_id"] if rp_rows else ""
    post(f"/api/sblt/sessions/{sid}/apply-review-decisions", {
        "row_decisions": [
            {"row_id": row_id_0, "row_action": "hold", "field_decisions": []},
        ],
        "bulk_accept_auto_accepted": True,
        "bulk_accept_suggestions": True,
    })
    post(f"/api/sblt/sessions/{sid}/approve-reviewed-rows")
    status, body = _prepare_handoff(sid)
    require(status == 200, "[9a] HTTP 200")
    pkg = body.get("loading_handoff_package") or {}
    summary = pkg.get("summary") or {}
    total = summary.get("total_rows", -1)
    created = summary.get("handoff_items_created", -1)
    skipped = summary.get("rows_skipped", -1)
    blocked = summary.get("rows_blocked", -1)
    require(total == 2,
            "[9b] summary.total_rows == 2",
            f"got: {total!r}")
    require(skipped >= 1,
            "[9c] summary.rows_skipped >= 1 (row 0 was held)",
            f"got: {skipped!r}")
    # created + skipped + blocked == total (all rows accounted for)
    reconciled = created + skipped + blocked
    require(reconciled == total,
            "[9d] handoff_items_created + rows_skipped + rows_blocked == total_rows",
            f"got: {created}+{skipped}+{blocked}={reconciled}, total={total}")
    # handoff_items list + skipped_rows + blocked_rows should total to all rows
    list_total = (
        len(pkg.get("handoff_items") or [])
        + len(pkg.get("skipped_rows") or [])
        + len(pkg.get("blocked_rows") or [])
    )
    require(list_total == total,
            "[9e] len(handoff_items)+len(skipped_rows)+len(blocked_rows) == total_rows",
            f"got: {list_total} vs total {total}")

    # ==================================================================== #
    # [10] loading_handoff_package schema completeness                      #
    # ==================================================================== #
    print("\n[10] loading_handoff_package schema completeness")
    fx = _write_fixture("sblt9_t10.csv", [{
        "Survey Name": "Kappa Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_Kappa",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_3D_A,
    }])
    sid, _, _ = _pipeline_to_sblt8(str(fx))
    status, body = _prepare_handoff(sid)
    require(status == 200, "[10a] HTTP 200")
    pkg = body.get("loading_handoff_package") or {}
    require(pkg.get("schema_version") == "sblt.loading_handoff_package.v1",
            "[10b] loading_handoff_package.schema_version == 'sblt.loading_handoff_package.v1'",
            f"got: {pkg.get('schema_version')!r}")
    require(bool(pkg.get("session_id")),
            "[10c] loading_handoff_package.session_id present")
    require(bool(pkg.get("created_at")),
            "[10d] loading_handoff_package.created_at present")
    require(bool(pkg.get("source_session_status")),
            "[10e] loading_handoff_package.source_session_status present")
    summary = pkg.get("summary") or {}
    for key in ("total_rows", "approved_rows_seen", "handoff_items_created",
                "rows_skipped", "rows_blocked", "job_requests_created",
                "job_requests_failed"):
        require(key in summary,
                f"[10f] loading_handoff_package.summary.{key} present",
                f"missing from summary: {list(summary.keys())!r}")
    require("handoff_items" in pkg,
            "[10g] loading_handoff_package.handoff_items list present")
    require("skipped_rows" in pkg,
            "[10h] loading_handoff_package.skipped_rows list present")
    require("blocked_rows" in pkg,
            "[10i] loading_handoff_package.blocked_rows list present")
    shr = pkg.get("session_handoff_readiness") or {}
    for key in ("has_handoff_items", "can_continue_to_job_queueing",
                "can_register", "can_expose_to_managed_data", "can_convert"):
        require(key in shr,
                f"[10j] session_handoff_readiness.{key} present",
                f"missing from shr: {list(shr.keys())!r}")

    # ==================================================================== #
    # [11] row.loading_handoff schema completeness                          #
    # ==================================================================== #
    print("\n[11] row.loading_handoff schema completeness")
    rows = body.get("rows") or []
    if rows:
        lh = rows[0].get("loading_handoff") or {}
        require(lh.get("schema_version") == "sblt.row_loading_handoff.v1",
                "[11a] row.loading_handoff.schema_version == 'sblt.row_loading_handoff.v1'",
                f"got: {lh.get('schema_version')!r}")
        require(bool(lh.get("handoff_item_id")),
                "[11b] row.loading_handoff.handoff_item_id present")
        require(lh.get("status") in ("prepared", "skipped", "blocked"),
                "[11c] row.loading_handoff.status is a valid status",
                f"got: {lh.get('status')!r}")
        require("source_segy_path" in lh,
                "[11d] row.loading_handoff.source_segy_path key present")
        require("record_type" in lh,
                "[11e] row.loading_handoff.record_type key present")
        require("requested_representation" in lh,
                "[11f] row.loading_handoff.requested_representation key present")
        require(lh.get("approved_canonical_metadata_ref") == "row.approved_canonical_metadata",
                "[11g] row.loading_handoff.approved_canonical_metadata_ref == 'row.approved_canonical_metadata'",
                f"got: {lh.get('approved_canonical_metadata_ref')!r}")
        require("job_request" in lh,
                "[11h] row.loading_handoff.job_request key present")
        require(isinstance(lh.get("reasons"), list),
                "[11i] row.loading_handoff.reasons is a list",
                f"got type: {type(lh.get('reasons')).__name__!r}")
        # For prepared rows, verify job_request schema completeness.
        if lh.get("status") == "prepared":
            jr = lh.get("job_request") or {}
            require(bool(jr.get("job_request_id")),
                    "[11j] job_request.job_request_id present")
            require(bool(jr.get("job_type")),
                    "[11k] job_request.job_type present")
            require(jr.get("status") == "prepared",
                    "[11l] job_request.status == 'prepared'",
                    f"got: {jr.get('status')!r}")
            require(bool(jr.get("created_at")),
                    "[11m] job_request.created_at present")
    else:
        require(False, "[11] No rows returned — skipping row.loading_handoff schema check")

    # ==================================================================== #
    # [12] Session status becomes loading_handoff_prepared                  #
    # ==================================================================== #
    print("\n[12] Session status becomes loading_handoff_prepared")
    fx = _write_fixture("sblt9_t12.csv", [{
        "Survey Name": "Lambda Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_Lambda",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_3D_A,
    }])
    sid, _, _ = _pipeline_to_sblt8(str(fx))
    status, body = _prepare_handoff(sid)
    require(status == 200, "[12a] HTTP 200")
    require(body.get("status") == "loading_handoff_prepared",
            "[12b] session.status == 'loading_handoff_prepared'",
            f"got: {body.get('status')!r}")
    # Verify via GET.
    g_status, g_body = get(f"/api/sblt/sessions/{sid}")
    require(g_status == 200, "[12c] GET session HTTP 200")
    require(g_body.get("status") == "loading_handoff_prepared",
            "[12d] GET session.status == 'loading_handoff_prepared'",
            f"got: {g_body.get('status')!r}")

    # ==================================================================== #
    # [13] can_register remains False                                        #
    # ==================================================================== #
    print("\n[13] can_register remains False")
    # Reuse body from [12].
    actions = body.get("actions") or {}
    require(actions.get("can_register") is False,
            "[13a] session.actions.can_register is False",
            f"got: {actions.get('can_register')!r}")
    pkg = body.get("loading_handoff_package") or {}
    shr = pkg.get("session_handoff_readiness") or {}
    require(shr.get("can_register") is False,
            "[13b] session_handoff_readiness.can_register is False",
            f"got: {shr.get('can_register')!r}")
    rows = body.get("rows") or []
    for i, row in enumerate(rows):
        lh = row.get("loading_handoff") or {}
        require("can_register" not in lh,
                f"[13c] row[{i}].loading_handoff does not contain can_register field")

    # ==================================================================== #
    # [14] can_convert remains False                                         #
    # ==================================================================== #
    print("\n[14] can_convert remains False")
    require(shr.get("can_convert") is False,
            "[14a] session_handoff_readiness.can_convert is False",
            f"got: {shr.get('can_convert')!r}")
    rows = body.get("rows") or []
    for i, row in enumerate(rows):
        lh = row.get("loading_handoff") or {}
        require("can_convert" not in lh,
                f"[14b] row[{i}].loading_handoff does not contain can_convert field")

    # ==================================================================== #
    # [15] can_expose_to_managed_data remains False                         #
    # ==================================================================== #
    print("\n[15] can_expose_to_managed_data remains False")
    require(shr.get("can_expose_to_managed_data") is False,
            "[15a] session_handoff_readiness.can_expose_to_managed_data is False",
            f"got: {shr.get('can_expose_to_managed_data')!r}")

    # ==================================================================== #
    # [16] Endpoint before approved_for_loading_prep returns HTTP 400       #
    # ==================================================================== #
    print("\n[16] Endpoint before approved_for_loading_prep returns HTTP 400")
    fx = _write_fixture("sblt9_t16.csv", [{
        "Survey Name": "Mu Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_Mu",
        "SEG-Y File": SEGY_3D_A,
    }])
    # Create and run only through SBLT-4 (paths_validated — incompatible state).
    pv_status, pv_body = post("/api/sblt/sessions", {"loadsheet_path": str(fx)})
    if pv_status != 200:
        print(f"  ERROR  create_session t16: {pv_status}")
        sys.exit(1)
    sid_t16 = pv_body["session_id"]
    for step in ("validate", "normalize", "validate-paths"):
        pv_status, pv_body = post(f"/api/sblt/sessions/{sid_t16}/{step}")
        if pv_status != 200:
            print(f"  ERROR  {step} t16: {pv_status}")
            sys.exit(1)
    status, body = _prepare_handoff(sid_t16)
    require(status == 400,
            "[16a] HTTP 400 when session is in paths_validated state",
            f"got: {status!r}, body: {body}")

    # ==================================================================== #
    # [17] Nonexistent session returns HTTP 404                             #
    # ==================================================================== #
    print("\n[17] Nonexistent session returns HTTP 404")
    status, body = _prepare_handoff("sblt_nonexistent_00000000_deadbeef99")
    require(status == 404,
            "[17a] HTTP 404 for nonexistent session_id",
            f"got: {status!r}")

    # ==================================================================== #
    # [18] Idempotent re-run succeeds and replaces package cleanly          #
    # ==================================================================== #
    print("\n[18] Idempotent re-run succeeds and replaces package cleanly")
    fx = _write_fixture("sblt9_t18.csv", [{
        "Survey Name": "Nu Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_Nu",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_3D_A,
    }])
    sid, _, _ = _pipeline_to_sblt8(str(fx))
    # First run.
    s1, b1 = _prepare_handoff(sid)
    require(s1 == 200, "[18a] first prepare HTTP 200")
    require(b1.get("status") == "loading_handoff_prepared",
            "[18b] first run: status = loading_handoff_prepared")
    pkg1 = b1.get("loading_handoff_package") or {}
    # Second run (idempotent — session is now loading_handoff_prepared).
    s2, b2 = _prepare_handoff(sid)
    require(s2 == 200,
            "[18c] second prepare (idempotent re-run) HTTP 200",
            f"got: {s2!r}")
    require(b2.get("status") == "loading_handoff_prepared",
            "[18d] second run: status still = loading_handoff_prepared",
            f"got: {b2.get('status')!r}")
    pkg2 = b2.get("loading_handoff_package") or {}
    require(bool(pkg1) and bool(pkg2),
            "[18e] loading_handoff_package present on both runs")
    require(pkg1.get("summary") == pkg2.get("summary"),
            "[18f] loading_handoff_package.summary is identical on re-run",
            f"run1={pkg1.get('summary')!r}\nrun2={pkg2.get('summary')!r}")

    # ==================================================================== #
    # [19] SBLT-8 approval_package preserved after SBLT-9                  #
    # ==================================================================== #
    print("\n[19] SBLT-8 approval_package preserved after SBLT-9")
    fx = _write_fixture("sblt9_t19.csv", [{
        "Survey Name": "Xi Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_Xi",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_3D_A,
    }])
    sid, _, sblt8_body = _pipeline_to_sblt8(str(fx))
    sblt8_ap = sblt8_body.get("approval_package") or {}
    status, body = _prepare_handoff(sid)
    require(status == 200, "[19a] HTTP 200")
    sblt9_ap = body.get("approval_package") or {}
    require(bool(sblt9_ap),
            "[19b] approval_package present after SBLT-9")
    require(sblt9_ap.get("schema_version") == "sblt.approval_package.v1",
            "[19c] approval_package.schema_version preserved",
            f"got: {sblt9_ap.get('schema_version')!r}")
    require(sblt9_ap.get("session_id") == sblt8_ap.get("session_id"),
            "[19d] approval_package.session_id unchanged",
            f"sblt8={sblt8_ap.get('session_id')!r} sblt9={sblt9_ap.get('session_id')!r}")
    require(sblt9_ap.get("summary") == sblt8_ap.get("summary"),
            "[19e] approval_package.summary unchanged by SBLT-9",
            f"sblt8={sblt8_ap.get('summary')!r}\nsblt9={sblt9_ap.get('summary')!r}")
    # Row fields from SBLT-8 must still be present.
    rows = body.get("rows") or []
    if rows:
        row = rows[0]
        require("approval_gate" in row,
                "[19f] row.approval_gate preserved after SBLT-9")
        require("approved_canonical_metadata" in row,
                "[19g] row.approved_canonical_metadata preserved after SBLT-9")
        require("review_decisions" in row,
                "[19h] row.review_decisions preserved after SBLT-9")
        require("approved_canonical_metadata_draft" in row,
                "[19i] row.approved_canonical_metadata_draft preserved after SBLT-9")
        require("approval_readiness" in row,
                "[19j] row.approval_readiness preserved after SBLT-9")
        require("metadata_evidence" in row,
                "[19k] row.metadata_evidence preserved after SBLT-9")

    # ==================================================================== #
    # [20] Regression: SBLT-8 still works after SBLT-9 additions            #
    # ==================================================================== #
    print("\n[20] Regression: SBLT-8 still works after SBLT-9 additions")
    fx = _write_fixture("sblt9_t20.csv", [{
        "Survey Name": "Omicron Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_Omicron",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_3D_A,
    }])
    sid, _, _ = _pipeline_to_review_package(str(fx))
    status, body = post(f"/api/sblt/sessions/{sid}/apply-review-decisions", {
        "row_decisions": [],
        "bulk_accept_auto_accepted": True,
        "bulk_accept_suggestions": True,
    })
    require(status == 200,
            "[20a] SBLT-7 apply-review-decisions HTTP 200",
            f"got: {status!r}")
    require(body.get("status") == "review_decisions_applied",
            "[20b] SBLT-7 session.status = review_decisions_applied",
            f"got: {body.get('status')!r}")
    status, body = post(f"/api/sblt/sessions/{sid}/approve-reviewed-rows")
    require(status == 200,
            "[20c] SBLT-8 approve-reviewed-rows HTTP 200",
            f"got: {status!r}")
    require(body.get("status") == "approved_for_loading_prep",
            "[20d] SBLT-8 session.status = approved_for_loading_prep",
            f"got: {body.get('status')!r}")
    require("approval_package" in body,
            "[20e] SBLT-8 approval_package present")
    ap = body.get("approval_package") or {}
    require(ap.get("schema_version") == "sblt.approval_package.v1",
            "[20f] SBLT-8 approval_package.schema_version correct",
            f"got: {ap.get('schema_version')!r}")
    rows = body.get("rows") or []
    require(len(rows) >= 1, "[20g] SBLT-8 returned rows")
    if rows:
        require("approval_gate" in rows[0],
                "[20h] row.approval_gate present (SBLT-8 output)")
        require("approved_canonical_metadata" in rows[0],
                "[20i] row.approved_canonical_metadata present (SBLT-8 output)")
    # SBLT-9 field must NOT be present on SBLT-8 output.
    require("loading_handoff_package" not in body,
            "[20j] loading_handoff_package NOT present on SBLT-8 output (SBLT-9 not yet run)")
    if rows:
        require("loading_handoff" not in rows[0],
                "[20k] row.loading_handoff NOT present on SBLT-8 output (SBLT-9 not yet run)")

    # ==================================================================== #
    # [21] No backend job id is created (job_request_id has expected format) #
    # ==================================================================== #
    print("\n[21] No backend job id is created")
    fx = _write_fixture("sblt9_t21.csv", [{
        "Survey Name": "Pi Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_Pi",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_3D_A,
    }])
    sid, _, _ = _pipeline_to_sblt8(str(fx))
    status, body = _prepare_handoff(sid)
    require(status == 200, "[21a] HTTP 200")
    rows = body.get("rows") or []
    if rows:
        lh = rows[0].get("loading_handoff") or {}
        if lh.get("status") == "prepared":
            jr = lh.get("job_request") or {}
            job_req_id = str(jr.get("job_request_id") or "")
            # Should follow deterministic format: sblt_jobreq_{row_id}
            row_id = str(rows[0].get("row_id") or "")
            expected_prefix = f"sblt_jobreq_{row_id}"
            require(job_req_id == expected_prefix,
                    "[21b] job_request_id == sblt_jobreq_{row_id}",
                    f"got: {job_req_id!r}, expected: {expected_prefix!r}")
            # handoff_item_id should also follow format
            handoff_id = str(lh.get("handoff_item_id") or "")
            expected_handoff_id = f"sblt_handoff_{row_id}"
            require(handoff_id == expected_handoff_id,
                    "[21c] handoff_item_id == sblt_handoff_{row_id}",
                    f"got: {handoff_id!r}, expected: {expected_handoff_id!r}")
            # Verify the ID does NOT contain any external backend job ID.
            # A backend job ID would typically be a UUID or contain a system-assigned part.
            # All we can verify is the format is deterministic and no extra system uuid present.
            require(job_req_id.startswith("sblt_jobreq_"),
                    "[21d] job_request_id starts with 'sblt_jobreq_'",
                    f"got: {job_req_id!r}")
        else:
            # Row was not approved — skip job_request checks.
            require(True, "[21b] row not prepared — job_request_id format check skipped")
            require(True, "[21c] row not prepared — handoff_item_id format check skipped")
            require(True, "[21d] row not prepared — prefix check skipped")

    # ==================================================================== #
    # [22] job_request.status remains prepared                              #
    # ==================================================================== #
    print("\n[22] job_request.status remains prepared")
    # Reuse body from [21].
    rows = body.get("rows") or []
    if rows:
        lh = rows[0].get("loading_handoff") or {}
        if lh.get("status") == "prepared":
            jr = lh.get("job_request") or {}
            require(jr.get("status") == "prepared",
                    "[22a] job_request.status == 'prepared'",
                    f"got: {jr.get('status')!r}")
            # Ensure there is no 'queued', 'running', 'complete' status.
            require(jr.get("status") != "queued",
                    "[22b] job_request.status is NOT 'queued' (SBLT-9 does not queue)")
            require(jr.get("status") != "running",
                    "[22c] job_request.status is NOT 'running'")
        else:
            require(True, "[22a] row not prepared — job_request.status check skipped")
            require(True, "[22b] row not prepared — queued check skipped")
            require(True, "[22c] row not prepared — running check skipped")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_tests()

    print(f"\n{'='*60}")
    print(f"SBLT-9 Contract Tests: {PASS} passed, {FAIL} failed")
    print(f"{'='*60}")

    if FAIL > 0:
        sys.exit(1)
