#!/usr/bin/env python3
"""
SBLT-2 schema validation contract test.

Tests the POST /api/sblt/sessions/{session_id}/validate endpoint.

Required test cases (per work order):
 1. Valid 2D row: Data Type=2D, Line Name present → record_type=2d_line, status=ready
 2. Valid 3D row: Dataset Type=3D, Volume Name present → record_type=3d_volume, status=ready
 3. Missing required survey_name → status=blocked, MISSING_REQUIRED_FIELD
 4. Unknown record_type value → status=review_required, UNKNOWN_RECORD_TYPE
 5. 2D row missing line_name → status=blocked, MISSING_CONDITIONAL_FIELD
 6. 3D row missing volume_name → status=blocked, MISSING_CONDITIONAL_FIELD
 7. Alias mapping: Project→survey_name, SEGY File→segy_path, Dataset Type→record_type
 8. Source preservation: original source_values unchanged after validation
 9. Summary invariants: row_count==len(rows), total==len(rows), counts reconcile
10. Session-level: validate returns sblt.session.v1, status=validated
11. Validate nonexistent session → 404
12. Session actions after validation: can_approve=True when ready rows exist

Style: stdlib only — no pytest. Backend must be running.

Base URL: read from BASE_URL env var; defaults to http://127.0.0.1:8000.
Usage:
    python3 scripts/test_sblt_schema_validation_contract.py
    BASE_URL="http://127.0.0.1:8001" python3 scripts/test_sblt_schema_validation_contract.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from typing import Any

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")

PASS = 0
FAIL = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  PASS  {label}")


def _fail(label: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    print(f"  FAIL  {label}")
    if detail:
        print(f"        {detail}")


def require(condition: bool, label: str, detail: str = "") -> bool:
    if condition:
        _ok(label)
        return True
    _fail(label, detail or "condition was False")
    return False


def request_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
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


def create_session(csv_path: str) -> tuple[int, Any]:
    return request_json("POST", "/api/sblt/sessions", {"loadsheet_path": csv_path})


def validate_session(session_id: str) -> tuple[int, Any]:
    return request_json("POST", f"/api/sblt/sessions/{session_id}/validate")


def write_csv(path: str, rows: list[dict[str, str]], columns: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(",".join(columns) + "\n")
        for row in rows:
            fh.write(",".join(row.get(c, "") for c in columns) + "\n")


def find_flags_by_code(flags: list[dict], code: str) -> list[dict]:
    return [f for f in flags if f.get("code") == code]


def assert_session_invariants(session: dict[str, Any], label: str) -> None:
    require(session.get("schema_version") == "sblt.session.v1",
            f"{label}: schema_version == sblt.session.v1")
    require(session.get("status") == "validated",
            f"{label}: status == validated", f"got {session.get('status')!r}")
    rows = session.get("rows", [])
    row_count = session.get("row_count")
    require(row_count == len(rows),
            f"{label}: row_count == len(rows)",
            f"row_count={row_count} len={len(rows)}")
    summary = session.get("summary", {})
    require(summary.get("total") == len(rows),
            f"{label}: summary.total == len(rows)",
            f"total={summary.get('total')} len={len(rows)}")
    # Summary counts must reconcile with actual row statuses
    status_counts: dict[str, int] = {}
    for r in rows:
        s = r.get("status", "")
        status_counts[s] = status_counts.get(s, 0) + 1
    for skey, scount in status_counts.items():
        require(summary.get(skey) == scount,
                f"{label}: summary.{skey} == {scount}",
                f"got summary.{skey}={summary.get(skey)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global PASS, FAIL

    print(f"\n  BASE_URL = {BASE}")

    # Backend health check
    print("\n[0] Backend health check")
    status, body = request_json("GET", "/api/msi/health")
    if status == -1:
        print(f"  ERROR: Backend not reachable at {BASE}: {body}")
        print(f"  Tip: BASE_URL=\"http://127.0.0.1:8001\" python3 {sys.argv[0]}")
        sys.exit(1)
    print(f"  Backend reachable (status={status})")

    tmp_dir = tempfile.mkdtemp(prefix="sblt2_test_")
    print(f"  Temp dir: {tmp_dir}")

    # -----------------------------------------------------------------------
    # Helper: create a session from a CSV, then validate it.
    # Returns (create_status, validated_session_or_error) or (-1, msg).
    # -----------------------------------------------------------------------
    def make_and_validate(csv_path: str) -> tuple[int, Any]:
        cs, sess = create_session(csv_path)
        if cs != 200:
            return cs, sess
        sid = sess.get("session_id", "")
        vs, vsess = validate_session(sid)
        return vs, vsess

    # -----------------------------------------------------------------------
    # [1] Valid 2D row → record_type=2d_line, status=ready
    # -----------------------------------------------------------------------
    print("\n[1] Valid 2D row: record_type=2d_line, status=ready")
    p1 = f"{tmp_dir}/test_2d_valid.csv"
    write_csv(p1,
              [{"Survey Name": "Alpha", "Data Type": "2D",
                "Line Name": "L001", "SEG-Y File": "/data/alpha.segy",
                "Processing Stage": "PSTM", "CRS": "EPSG:4326",
                "Datum": "GDA94", "Sample Interval": "2",
                "Operator": "OperatorA", "Area": "Block12"}],
              ["Survey Name", "Data Type", "Line Name", "SEG-Y File",
               "Processing Stage", "CRS", "Datum", "Sample Interval",
               "Operator", "Area"])
    s1, v1 = make_and_validate(p1)
    require(s1 == 200, "[1] POST validate → HTTP 200", f"got {s1}: {v1}")
    if s1 == 200 and isinstance(v1, dict):
        assert_session_invariants(v1, "[1]")
        rows1 = v1.get("rows", [])
        r1 = rows1[0] if rows1 else {}
        require(r1.get("status") == "ready",
                "[1] row status == ready", f"got {r1.get('status')!r}")
        require(r1.get("record_type") == "2d_line",
                "[1] row record_type == 2d_line", f"got {r1.get('record_type')!r}")
        cf1 = r1.get("canonical_fields", {})
        require(cf1.get("record_type") == "2d_line",
                "[1] canonical_fields.record_type == 2d_line")
        require(cf1.get("survey_name") == "Alpha",
                "[1] canonical_fields.survey_name == Alpha",
                f"got {cf1.get('survey_name')!r}")
        require(cf1.get("line_name") == "L001",
                "[1] canonical_fields.line_name == L001",
                f"got {cf1.get('line_name')!r}")
        require(cf1.get("segy_path") == "/data/alpha.segy",
                "[1] canonical_fields.segy_path correct",
                f"got {cf1.get('segy_path')!r}")
        # No required_missing
        val1 = r1.get("validation", {})
        require(val1.get("required_missing") == [],
                "[1] validation.required_missing == []",
                f"got {val1.get('required_missing')!r}")
        require(val1.get("schema_validated") is True,
                "[1] validation.schema_validated == True")

    # -----------------------------------------------------------------------
    # [2] Valid 3D row → record_type=3d_volume, status=ready
    # -----------------------------------------------------------------------
    print("\n[2] Valid 3D row: record_type=3d_volume, status=ready")
    p2 = f"{tmp_dir}/test_3d_valid.csv"
    write_csv(p2,
              [{"Project": "Beta", "Dataset Type": "3D",
                "Volume Name": "FullStack", "SEGY File": "/data/beta.segy",
                "Processing Stage": "PSDM", "CRS": "EPSG:4283",
                "Datum": "WGS84", "Sample Rate": "4",
                "Operator": "OperatorB", "Block": "Block7"}],
              ["Project", "Dataset Type", "Volume Name", "SEGY File",
               "Processing Stage", "CRS", "Datum", "Sample Rate",
               "Operator", "Block"])
    s2, v2 = make_and_validate(p2)
    require(s2 == 200, "[2] POST validate → HTTP 200", f"got {s2}: {v2}")
    if s2 == 200 and isinstance(v2, dict):
        rows2 = v2.get("rows", [])
        r2 = rows2[0] if rows2 else {}
        require(r2.get("status") == "ready",
                "[2] row status == ready", f"got {r2.get('status')!r}")
        require(r2.get("record_type") == "3d_volume",
                "[2] row record_type == 3d_volume", f"got {r2.get('record_type')!r}")
        cf2 = r2.get("canonical_fields", {})
        require(cf2.get("record_type") == "3d_volume",
                "[2] canonical_fields.record_type == 3d_volume")
        require(cf2.get("survey_name") == "Beta",
                "[2] canonical_fields.survey_name == Beta (via Project alias)",
                f"got {cf2.get('survey_name')!r}")
        require(cf2.get("volume_name") == "FullStack",
                "[2] canonical_fields.volume_name == FullStack",
                f"got {cf2.get('volume_name')!r}")
        require(cf2.get("segy_path") == "/data/beta.segy",
                "[2] canonical_fields.segy_path correct (via SEGY File alias)",
                f"got {cf2.get('segy_path')!r}")

    # -----------------------------------------------------------------------
    # [3] Missing required survey_name → blocked, MISSING_REQUIRED_FIELD
    # -----------------------------------------------------------------------
    print("\n[3] Missing required survey_name → blocked, MISSING_REQUIRED_FIELD")
    p3 = f"{tmp_dir}/test_missing_survey.csv"
    write_csv(p3,
              [{"Data Type": "2D", "Line Name": "L001",
                "SEG-Y File": "/data/x.segy"}],
              ["Data Type", "Line Name", "SEG-Y File"])
    s3, v3 = make_and_validate(p3)
    require(s3 == 200, "[3] POST validate → HTTP 200", f"got {s3}: {v3}")
    if s3 == 200 and isinstance(v3, dict):
        rows3 = v3.get("rows", [])
        r3 = rows3[0] if rows3 else {}
        require(r3.get("status") == "blocked",
                "[3] row status == blocked", f"got {r3.get('status')!r}")
        flags3 = r3.get("qaqc_flags", [])
        rf3 = find_flags_by_code(flags3, "MISSING_REQUIRED_FIELD")
        require(len(rf3) > 0,
                "[3] qaqc_flags contains MISSING_REQUIRED_FIELD")
        rf3_fields = [f.get("field") for f in rf3]
        require("survey_name" in rf3_fields,
                "[3] MISSING_REQUIRED_FIELD.field == survey_name",
                f"got fields={rf3_fields}")
        val3 = r3.get("validation", {})
        require("survey_name" in (val3.get("required_missing") or []),
                "[3] validation.required_missing contains survey_name")
        require(r3.get("actions", {}).get("can_approve") is False,
                "[3] blocked row: can_approve == False")

    # -----------------------------------------------------------------------
    # [4] Unknown record_type value → review_required, UNKNOWN_RECORD_TYPE
    # -----------------------------------------------------------------------
    print("\n[4] Unknown record_type → review_required, UNKNOWN_RECORD_TYPE")
    p4 = f"{tmp_dir}/test_unknown_type.csv"
    write_csv(p4,
              [{"Survey Name": "Gamma", "Data Type": "4D",
                "SEG-Y File": "/data/gamma.segy"}],
              ["Survey Name", "Data Type", "SEG-Y File"])
    s4, v4 = make_and_validate(p4)
    require(s4 == 200, "[4] POST validate → HTTP 200", f"got {s4}: {v4}")
    if s4 == 200 and isinstance(v4, dict):
        rows4 = v4.get("rows", [])
        r4 = rows4[0] if rows4 else {}
        require(r4.get("status") == "review_required",
                "[4] row status == review_required", f"got {r4.get('status')!r}")
        flags4 = r4.get("qaqc_flags", [])
        uk4 = find_flags_by_code(flags4, "UNKNOWN_RECORD_TYPE")
        require(len(uk4) > 0,
                "[4] qaqc_flags contains UNKNOWN_RECORD_TYPE")

    # -----------------------------------------------------------------------
    # [5] 2D row missing line_name → blocked, MISSING_CONDITIONAL_FIELD
    # -----------------------------------------------------------------------
    print("\n[5] 2D row missing line_name → blocked, MISSING_CONDITIONAL_FIELD")
    p5 = f"{tmp_dir}/test_2d_no_line.csv"
    write_csv(p5,
              [{"Survey Name": "Delta", "Data Type": "2D",
                "SEG-Y File": "/data/delta.segy"}],
              ["Survey Name", "Data Type", "SEG-Y File"])
    s5, v5 = make_and_validate(p5)
    require(s5 == 200, "[5] POST validate → HTTP 200", f"got {s5}: {v5}")
    if s5 == 200 and isinstance(v5, dict):
        rows5 = v5.get("rows", [])
        r5 = rows5[0] if rows5 else {}
        require(r5.get("status") == "blocked",
                "[5] row status == blocked", f"got {r5.get('status')!r}")
        flags5 = r5.get("qaqc_flags", [])
        cf5 = find_flags_by_code(flags5, "MISSING_CONDITIONAL_FIELD")
        require(len(cf5) > 0,
                "[5] qaqc_flags contains MISSING_CONDITIONAL_FIELD")
        cf5_fields = [f.get("field") for f in cf5]
        require("line_name" in cf5_fields,
                "[5] MISSING_CONDITIONAL_FIELD.field == line_name",
                f"got {cf5_fields}")

    # -----------------------------------------------------------------------
    # [6] 3D row missing volume_name → blocked, MISSING_CONDITIONAL_FIELD
    # -----------------------------------------------------------------------
    print("\n[6] 3D row missing volume_name → blocked, MISSING_CONDITIONAL_FIELD")
    p6 = f"{tmp_dir}/test_3d_no_volume.csv"
    write_csv(p6,
              [{"Survey Name": "Epsilon", "Data Type": "3D",
                "SEG-Y File": "/data/eps.segy"}],
              ["Survey Name", "Data Type", "SEG-Y File"])
    s6, v6 = make_and_validate(p6)
    require(s6 == 200, "[6] POST validate → HTTP 200", f"got {s6}: {v6}")
    if s6 == 200 and isinstance(v6, dict):
        rows6 = v6.get("rows", [])
        r6 = rows6[0] if rows6 else {}
        require(r6.get("status") == "blocked",
                "[6] row status == blocked", f"got {r6.get('status')!r}")
        flags6 = r6.get("qaqc_flags", [])
        cf6 = find_flags_by_code(flags6, "MISSING_CONDITIONAL_FIELD")
        require(len(cf6) > 0,
                "[6] qaqc_flags contains MISSING_CONDITIONAL_FIELD")
        cf6_fields = [f.get("field") for f in cf6]
        require("volume_name" in cf6_fields,
                "[6] MISSING_CONDITIONAL_FIELD.field == volume_name",
                f"got {cf6_fields}")

    # -----------------------------------------------------------------------
    # [7] Alias mapping verification
    # -----------------------------------------------------------------------
    print("\n[7] Alias mapping: Project→survey_name, SEGY File→segy_path, Dataset Type→record_type")
    p7 = f"{tmp_dir}/test_aliases.csv"
    write_csv(p7,
              [{"Project": "Zeta", "Dataset Type": "3D",
                "Dataset Name": "ZetaVol", "SEGY File": "/data/zeta.segy"}],
              ["Project", "Dataset Type", "Dataset Name", "SEGY File"])
    s7, v7 = make_and_validate(p7)
    require(s7 == 200, "[7] POST validate → HTTP 200", f"got {s7}: {v7}")
    if s7 == 200 and isinstance(v7, dict):
        rows7 = v7.get("rows", [])
        r7 = rows7[0] if rows7 else {}
        cf7 = r7.get("canonical_fields", {})
        require(cf7.get("survey_name") == "Zeta",
                "[7] Project → survey_name = Zeta",
                f"got {cf7.get('survey_name')!r}")
        require(cf7.get("segy_path") == "/data/zeta.segy",
                "[7] SEGY File → segy_path correct",
                f"got {cf7.get('segy_path')!r}")
        require(cf7.get("record_type") == "3d_volume",
                "[7] Dataset Type=3D → record_type=3d_volume",
                f"got {cf7.get('record_type')!r}")
        require(cf7.get("volume_name") == "ZetaVol",
                "[7] Dataset Name → volume_name = ZetaVol",
                f"got {cf7.get('volume_name')!r}")
        val7 = r7.get("validation", {})
        mapped7 = val7.get("mapped_columns", {})
        require(mapped7.get("survey_name") == "Project",
                "[7] validation.mapped_columns.survey_name == 'Project'",
                f"got {mapped7.get('survey_name')!r}")
        require(mapped7.get("segy_path") == "SEGY File",
                "[7] validation.mapped_columns.segy_path == 'SEGY File'",
                f"got {mapped7.get('segy_path')!r}")
        require(mapped7.get("record_type") == "Dataset Type",
                "[7] validation.mapped_columns.record_type == 'Dataset Type'",
                f"got {mapped7.get('record_type')!r}")

    # -----------------------------------------------------------------------
    # [8] Source preservation: source_values unchanged
    # -----------------------------------------------------------------------
    print("\n[8] Source preservation: original source_values unchanged after validation")
    p8 = f"{tmp_dir}/test_source_preserve.csv"
    original_cols = ["Survey Name", "Data Type", "Line Name", "SEG-Y File"]
    original_row = {
        "Survey Name": "Eta",
        "Data Type": "2D",
        "Line Name": "L999",
        "SEG-Y File": "/data/eta.segy",
    }
    write_csv(p8, [original_row], original_cols)
    cs8, sess8 = create_session(p8)
    require(cs8 == 200, "[8] create session → 200", f"got {cs8}")
    if cs8 == 200:
        # Capture source_values before validation
        pre_sv = dict(sess8.get("rows", [{}])[0].get("source_values", {}))
        sid8 = sess8.get("session_id", "")
        vs8, val8 = validate_session(sid8)
        require(vs8 == 200, "[8] validate → 200", f"got {vs8}")
        if vs8 == 200 and isinstance(val8, dict):
            post_sv = dict(val8.get("rows", [{}])[0].get("source_values", {}))
            require(post_sv == pre_sv,
                    "[8] source_values unchanged after validation",
                    f"before={pre_sv}\nafter={post_sv}")
            # Verify source_values still has original column name (not canonical)
            require("Survey Name" in post_sv,
                    "[8] source_values still has original 'Survey Name' key")
            require("Data Type" in post_sv,
                    "[8] source_values still has original 'Data Type' key")

    # -----------------------------------------------------------------------
    # [9] Summary invariants on a multi-row mixed session
    # -----------------------------------------------------------------------
    print("\n[9] Summary invariants on a mixed session (ready + blocked + review_required)")
    p9 = f"{tmp_dir}/test_mixed.csv"
    write_csv(p9, [
        # Row 1: ready (all required + conditional present; missing recommended is OK)
        {"Survey Name": "Iota", "Data Type": "2D", "Line Name": "L1",
         "SEG-Y File": "/data/iota.segy"},
        # Row 2: blocked (survey_name missing)
        {"Data Type": "2D", "Line Name": "L2", "SEG-Y File": "/data/iota2.segy"},
        # Row 3: review_required (unknown record type value)
        {"Survey Name": "Iota", "Data Type": "XYZ", "SEG-Y File": "/data/iota3.segy"},
    ], ["Survey Name", "Data Type", "Line Name", "SEG-Y File"])
    s9, v9 = make_and_validate(p9)
    require(s9 == 200, "[9] POST validate → HTTP 200", f"got {s9}: {v9}")
    if s9 == 200 and isinstance(v9, dict):
        assert_session_invariants(v9, "[9]")
        rows9 = v9.get("rows", [])
        require(len(rows9) == 3, "[9] 3 rows returned", f"got {len(rows9)}")
        statuses9 = [r.get("status") for r in rows9]
        require("ready" in statuses9,         "[9] at least one ready row")
        require("blocked" in statuses9,       "[9] at least one blocked row")
        require("review_required" in statuses9, "[9] at least one review_required row")
        summary9 = v9.get("summary", {})
        require(summary9.get("ready", 0) >= 1,         "[9] summary.ready >= 1")
        require(summary9.get("blocked", 0) >= 1,       "[9] summary.blocked >= 1")
        require(summary9.get("review_required", 0) >= 1, "[9] summary.review_required >= 1")
        require(summary9.get("parsed", 0) == 0,
                "[9] summary.parsed == 0 (rows no longer parsed after validation)")
        actions9 = v9.get("actions", {})
        require(actions9.get("can_approve") is True,
                "[9] session actions.can_approve == True (ready rows exist)")
        require(actions9.get("can_register") is False,
                "[9] session actions.can_register == False")

    # -----------------------------------------------------------------------
    # [10] validate returns sblt.session.v1, status=validated
    # -----------------------------------------------------------------------
    print("\n[10] Validate endpoint returns sblt.session.v1 with status=validated")
    p10 = f"{tmp_dir}/test_validated_shape.csv"
    write_csv(p10,
              [{"Survey Name": "Kappa", "Data Type": "2D",
                "Line Name": "L1", "SEG-Y File": "/data/k.segy"}],
              ["Survey Name", "Data Type", "Line Name", "SEG-Y File"])
    s10, v10 = make_and_validate(p10)
    require(s10 == 200, "[10] POST validate → HTTP 200", f"got {s10}")
    if s10 == 200 and isinstance(v10, dict):
        require(v10.get("schema_version") == "sblt.session.v1",
                "[10] schema_version == sblt.session.v1")
        require(v10.get("status") == "validated",
                "[10] session status == validated", f"got {v10.get('status')!r}")
        require(isinstance(v10.get("source"), dict),
                "[10] source is a dict")
        require(isinstance(v10.get("rows"), list),
                "[10] rows is a list")
        require(isinstance(v10.get("summary"), dict),
                "[10] summary is a dict")
        require(isinstance(v10.get("actions"), dict),
                "[10] actions is a dict")

    # -----------------------------------------------------------------------
    # [11] Validate nonexistent session → 404
    # -----------------------------------------------------------------------
    print("\n[11] Validate nonexistent session → 404")
    s11, b11 = validate_session("sblt_does_not_exist_0000000000")
    require(s11 == 404, "[11] validate nonexistent → HTTP 404", f"got {s11}")

    # -----------------------------------------------------------------------
    # [12] Session actions after validation
    # -----------------------------------------------------------------------
    print("\n[12] Session and row actions after validation")
    p12 = f"{tmp_dir}/test_actions.csv"
    write_csv(p12, [
        # Row 1: ready — all required + conditional fields present
        {"Survey Name": "Lambda", "Data Type": "2D",
         "Line Name": "L1", "SEG-Y File": "/data/lam.segy"},
        # Row 2: blocked — survey_name missing
        {"Data Type": "2D", "Line Name": "L2",
         "SEG-Y File": "/data/lam2.segy"},
    ], ["Survey Name", "Data Type", "Line Name", "SEG-Y File"])
    s12, v12 = make_and_validate(p12)
    require(s12 == 200, "[12] POST validate → HTTP 200", f"got {s12}")
    if s12 == 200 and isinstance(v12, dict):
        # Session-level actions
        sa12 = v12.get("actions", {})
        require(sa12.get("can_approve") is True,
                "[12] session can_approve == True (ready row exists)")
        require(sa12.get("can_validate") is True,
                "[12] session can_validate == True")
        require(sa12.get("can_register") is False,
                "[12] session can_register == False")
        # Row-level actions
        rows12 = v12.get("rows", [])
        ready_rows = [r for r in rows12 if r.get("status") == "ready"]
        blocked_rows = [r for r in rows12 if r.get("status") == "blocked"]
        if ready_rows:
            ra = ready_rows[0].get("actions", {})
            require(ra.get("can_approve") is True,
                    "[12] ready row: can_approve == True")
            require(ra.get("requires_review") is False,
                    "[12] ready row: requires_review == False")
        if blocked_rows:
            ba = blocked_rows[0].get("actions", {})
            require(ba.get("can_approve") is False,
                    "[12] blocked row: can_approve == False")
            require(ba.get("requires_review") is True,
                    "[12] blocked row: requires_review == True")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    total = PASS + FAIL
    print(f"\n{'='*60}")
    print(f"  SBLT-2 schema validation test: {PASS}/{total} passed, {FAIL} failed")
    print(f"{'='*60}\n")

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
