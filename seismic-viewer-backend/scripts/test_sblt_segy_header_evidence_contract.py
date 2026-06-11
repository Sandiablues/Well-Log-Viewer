"""
SBLT-5 Contract Test: SEG-Y Header Evidence Extraction Using MDE.

Tests the POST /api/sblt/sessions/{session_id}/extract-segy-header-evidence endpoint.

Usage:
    BASE_URL="http://127.0.0.1:8001" python3 scripts/test_sblt_segy_header_evidence_contract.py

Environment:
    BASE_URL — base URL of the SBLT backend (default: http://127.0.0.1:8000)

Test cases:
    [1]  Valid binary header, metadata-rich match (sample_interval_ms=4.0 vs header 4000µs)
    [2]  Metadata-rich conflict (sample_interval_ms=4.0 vs header 2000µs → review_required)
    [3]  Metadata-sparse technical candidate (no submitted sample_interval_ms → auto_accepted)
    [4]  Textual header identity candidate (survey_name absent; found in textual header)
    [5]  Textual header submitted value match (survey_name present; found in textual)
    [6]  Header too small (< 3600 bytes → blocked, SEGY_HEADER_TOO_SMALL)
    [7]  Data sample format captured (code=5 → IEEE float)
    [8]  Samples per trace captured (1500 → auto_accepted)
    [9]  Endpoint before path validation → HTTP 400
    [10] Nonexistent session → HTTP 404
    [11] Preservation (source_values, canonical_fields, etc. unchanged)
    [12] Regression: existing SBLT-1 through SBLT-4 tests pass
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


def flag_codes(flags: list[dict]) -> list[str]:
    return [f.get("code", "") for f in flags]


# ---------------------------------------------------------------------------
# Synthetic SEG-Y file builder
# ---------------------------------------------------------------------------

def _make_binary_header_bytes(
    sample_interval_us: int = 4000,
    samples_per_trace: int = 500,
    data_sample_format_code: int = 5,
    measurement_system: int = 1,
    job_id: int = 1,
    line_number: int = 1,
    reel_number: int = 1,
) -> bytes:
    """
    Build a 400-byte SEG-Y binary header with specific field values.

    Offsets (0-indexed within the 400-byte block):
        0-3   job_id              (4-byte signed int, big-endian)
        4-7   line_number         (4-byte signed int, big-endian)
        8-11  reel_number         (4-byte signed int, big-endian)
        16-17 sample_interval_us  (2-byte unsigned int, big-endian)
        20-21 samples_per_trace   (2-byte unsigned int, big-endian)
        24-25 data_sample_format_code (2-byte unsigned int, big-endian)
        54-55 measurement_system  (2-byte unsigned int, big-endian)
    """
    buf = bytearray(400)
    struct.pack_into(">i", buf, 0, job_id)
    struct.pack_into(">i", buf, 4, line_number)
    struct.pack_into(">i", buf, 8, reel_number)
    struct.pack_into(">H", buf, 16, sample_interval_us)
    struct.pack_into(">H", buf, 20, samples_per_trace)
    struct.pack_into(">H", buf, 24, data_sample_format_code)
    struct.pack_into(">H", buf, 54, measurement_system)
    return bytes(buf)


def _make_ascii_textual_header(lines: list[str] | None = None) -> bytes:
    """
    Build a 3200-byte textual header (ASCII, 40 lines × 80 chars).

    Any provided lines are embedded; remainder padded with spaces.
    """
    fixed_lines: list[str] = []
    for i in range(40):
        if lines and i < len(lines):
            raw_line = lines[i]
        else:
            raw_line = f"C{i+1:02d} "
        # Pad / truncate to exactly 80 chars
        fixed_lines.append(f"{raw_line:<80.80}")
    text = "".join(fixed_lines)  # 3200 chars
    return text.encode("ascii", errors="replace")


def make_synthetic_segy(
    path: str,
    *,
    sample_interval_us: int = 4000,
    samples_per_trace: int = 500,
    data_sample_format_code: int = 5,
    measurement_system: int = 1,
    textual_lines: list[str] | None = None,
    include_trace_header: bool = False,
    total_size: int | None = None,
) -> None:
    """
    Write a synthetic SEG-Y file with real binary header fields but no trace data.

    Writes: 3200 textual + 400 binary = 3600 bytes minimum.
    Optionally pads to total_size bytes.
    """
    textual = _make_ascii_textual_header(textual_lines)  # 3200 bytes
    binary = _make_binary_header_bytes(
        sample_interval_us=sample_interval_us,
        samples_per_trace=samples_per_trace,
        data_sample_format_code=data_sample_format_code,
        measurement_system=measurement_system,
    )  # 400 bytes
    payload = textual + binary
    if include_trace_header:
        payload += b"\x00" * 240  # dummy first trace header, no sample data
    if total_size is not None and total_size > len(payload):
        payload += b"\x00" * (total_size - len(payload))
    Path(path).write_bytes(payload)


# ---------------------------------------------------------------------------
# Fixture CSV builder
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent
_FIXTURES_DIR = _SCRIPTS_DIR / "sblt_test_fixtures"


def _write_fixture(name: str, rows: list[dict]) -> Path:
    """Write a quoted CSV fixture."""
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

def _pipeline_full(
    loadsheet_path: str,
    base_path: str | None = None,
) -> tuple[str, int, dict]:
    """
    Create → validate → normalize → validate-paths → extract-segy-header-evidence.

    Returns (session_id, status_code, response_body).
    """
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

    status, body = post(f"/api/sblt/sessions/{sid}/validate-paths")
    if status != 200:
        print(f"  ERROR  validate-paths: {status} {body}")
        sys.exit(1)

    status, body = post(
        f"/api/sblt/sessions/{sid}/extract-segy-header-evidence"
    )
    return sid, status, body


def _pipeline_before_paths(loadsheet_path: str) -> tuple[str, int, dict]:
    """Create → validate → normalize (no validate-paths)."""
    status, body = post("/api/sblt/sessions", {"loadsheet_path": loadsheet_path})
    if status != 200:
        print(f"  ERROR  create_session: {status} {body}")
        sys.exit(1)
    sid = body["session_id"]
    for step in ("validate", "normalize"):
        status, body = post(f"/api/sblt/sessions/{sid}/{step}")
        if status != 200:
            print(f"  ERROR  {step}: {status} {body}")
            sys.exit(1)
    status, body = post(
        f"/api/sblt/sessions/{sid}/extract-segy-header-evidence"
    )
    return sid, status, body


# ---------------------------------------------------------------------------
# Temp file setup
# ---------------------------------------------------------------------------

TMPDIR = tempfile.mkdtemp(prefix="sblt5_test_")

def _tmp(name: str) -> str:
    return os.path.join(TMPDIR, name)


# Create SEG-Y fixtures
SEGY_4MS = _tmp("line_4ms.sgy")          # 4 ms sample interval
SEGY_2MS = _tmp("line_2ms.sgy")          # 2 ms sample interval (conflict for rich-4ms test)
SEGY_SURVEY = _tmp("survey_abc.sgy")     # textual header with survey name
SEGY_MATCH = _tmp("survey_present.sgy")  # submitted survey_name present + in textual
SEGY_FORMAT5 = _tmp("format5.sgy")       # IEEE float format code 5
SEGY_SPT1500 = _tmp("spt1500.sgy")       # samples_per_trace=1500
SEGY_SMALL = _tmp("tiny.sgy")            # too small (< 3600 bytes)

make_synthetic_segy(SEGY_4MS, sample_interval_us=4000, samples_per_trace=500,
                    data_sample_format_code=5)
make_synthetic_segy(SEGY_2MS, sample_interval_us=2000, samples_per_trace=500,
                    data_sample_format_code=5)
make_synthetic_segy(SEGY_SURVEY, sample_interval_us=4000,
                    textual_lines=[
                        "C01 SURVEY: ALPHA_PROSPECT",
                        "C02 LINE NAME: LINE_001",
                    ])
make_synthetic_segy(SEGY_MATCH, sample_interval_us=4000,
                    textual_lines=[
                        "C01 SURVEY: DELTA_BASIN",
                        "C02 This is a test dataset",
                    ])
make_synthetic_segy(SEGY_FORMAT5, sample_interval_us=4000, data_sample_format_code=5)
make_synthetic_segy(SEGY_SPT1500, sample_interval_us=4000, samples_per_trace=1500,
                    data_sample_format_code=5)
# Write too-small file (3000 bytes < 3600 minimum)
Path(SEGY_SMALL).write_bytes(b"\x00" * 3000)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def run_tests() -> None:
    global PASS, FAIL

    # ==================================================================== #
    # [1] Metadata-rich match: submitted 4.0 ms vs header 4000µs           #
    # ==================================================================== #
    print("\n[1] Metadata-rich match (sample_interval_ms=4.0 vs header 4000µs → match)")
    fx = _write_fixture("sblt5_t01.csv", [{
        "Survey Name": "Alpha Prospect",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_A",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_4MS,
    }])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[1a] HTTP 200")
    rows = body.get("rows", [])
    require(len(rows) == 1, "[1b] 1 row returned")
    if rows:
        row = rows[0]
        mde = row.get("metadata_evidence") or {}
        require(mde.get("schema_version") == "mde.bundle.v1",
                "[1c] metadata_evidence schema_version = mde.bundle.v1",
                f"got: {mde.get('schema_version')!r}")
        fr = mde.get("field_review") or {}
        si_review = fr.get("sample_interval_ms") or {}
        require(
            si_review.get("classification") in ("no_action_required", "match"),
            "[1d] sample_interval_ms classification no_action_required",
            f"got: {si_review.get('classification')!r}",
        )
        require(
            not si_review.get("requires_user_review", True),
            "[1e] sample_interval_ms does not require user review",
        )
        require(
            body.get("status") == "segy_header_evidence_extracted",
            "[1f] session status segy_header_evidence_extracted",
            f"got: {body.get('status')!r}",
        )
        # Verify evidence records exist for sample_interval_ms
        evs = mde.get("evidence_records") or []
        si_evs = [e for e in evs if e.get("field") == "sample_interval_ms"]
        require(len(si_evs) >= 1, "[1g] evidence record for sample_interval_ms present")
        if si_evs:
            require(
                si_evs[0].get("source_type") == "segy_binary_header",
                "[1h] evidence source_type = segy_binary_header",
                f"got: {si_evs[0].get('source_type')!r}",
            )

    # ==================================================================== #
    # [2] Metadata-rich conflict: submitted 4.0 vs header 2000µs           #
    # ==================================================================== #
    print("\n[2] Metadata-rich conflict (submitted 4.0 ms vs header 2000µs → review_required)")
    fx = _write_fixture("sblt5_t02.csv", [{
        "Survey Name": "Beta Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_B",
        "Sample Interval MS": "4.0",
        "SEG-Y File": SEGY_2MS,
    }])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[2a] HTTP 200")
    rows = body.get("rows", [])
    if rows:
        row = rows[0]
        mde = row.get("metadata_evidence") or {}
        fr = mde.get("field_review") or {}
        si_review = fr.get("sample_interval_ms") or {}
        require(
            si_review.get("classification") == "conflict",
            "[2b] sample_interval_ms classification = conflict",
            f"got: {si_review.get('classification')!r}",
        )
        require(
            si_review.get("requires_user_review", False),
            "[2c] sample_interval_ms requires_user_review = True",
        )
        require(
            row.get("status") == "review_required",
            "[2d] row status = review_required",
            f"got: {row.get('status')!r}",
        )
        # Check evidence records contain conflict
        evs = mde.get("evidence_records") or []
        si_evs = [e for e in evs if e.get("field") == "sample_interval_ms"]
        require(len(si_evs) >= 1, "[2e] evidence record for sample_interval_ms present")
        if si_evs:
            require(
                si_evs[0].get("comparison") == "conflict",
                "[2f] evidence comparison = conflict",
                f"got: {si_evs[0].get('comparison')!r}",
            )

    # ==================================================================== #
    # [3] Metadata-sparse technical candidate (no submitted sample_interval) #
    # ==================================================================== #
    print("\n[3] Metadata-sparse: no submitted sample_interval_ms → auto_accepted from header")
    fx = _write_fixture("sblt5_t03.csv", [{
        "Survey Name": "Gamma Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_C",
        "SEG-Y File": SEGY_4MS,
    }])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[3a] HTTP 200")
    rows = body.get("rows", [])
    if rows:
        row = rows[0]
        mde = row.get("metadata_evidence") or {}
        fr = mde.get("field_review") or {}
        si_review = fr.get("sample_interval_ms") or {}
        require(
            si_review.get("classification") == "auto_accepted",
            "[3b] sample_interval_ms classification = auto_accepted",
            f"got: {si_review.get('classification')!r}",
        )
        require(
            not si_review.get("requires_user_review", True),
            "[3c] sample_interval_ms does not require user review (auto_accepted)",
        )
        cm = mde.get("candidate_metadata") or {}
        si_cand = cm.get("sample_interval_ms") or {}
        require(
            abs(float(si_cand.get("candidate_value", 0)) - 4.0) < 0.01,
            "[3d] candidate_value for sample_interval_ms = 4.0",
            f"got: {si_cand.get('candidate_value')!r}",
        )
        require(
            si_cand.get("candidate_source_type") == "segy_binary_header",
            "[3e] candidate_source_type = segy_binary_header",
            f"got: {si_cand.get('candidate_source_type')!r}",
        )

    # ==================================================================== #
    # [4] Textual header identity candidate (survey_name absent)            #
    # ==================================================================== #
    print("\n[4] Textual header identity candidate (line_name absent; found in textual header)")
    # Survey Name is present (prevents SBLT-2 blocking).
    # line_name is NOT submitted and NOT required for 3d_volume.
    # SEGY_SURVEY textual header contains "LINE NAME: LINE_001" → textual candidate.
    fx = _write_fixture("sblt5_t04.csv", [{
        "Survey Name": "Alpha Prospect",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_D",
        "SEG-Y File": SEGY_SURVEY,
    }])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[4a] HTTP 200")
    rows = body.get("rows", [])
    if rows:
        row = rows[0]
        mde = row.get("metadata_evidence") or {}
        evs = mde.get("evidence_records") or []
        textual_evs = [
            e for e in evs
            if e.get("field") in ("survey_name", "line_name")
            and e.get("source_type") == "segy_textual_header"
        ]
        require(
            len(textual_evs) >= 1,
            "[4b] at least 1 textual header evidence record for identity field",
            f"textual_evs={textual_evs}",
        )
        fr = mde.get("field_review") or {}
        # line_name absent from loadsheet (not required for 3d_volume) →
        # textual candidate found → suggested_review
        ln_review = fr.get("line_name") or {}
        require(
            ln_review.get("classification") in (
                "suggested_review", "missing_required", "missing_recommended"
            ),
            "[4c] line_name classification is suggested_review or missing",
            f"got: {ln_review.get('classification')!r}",
        )
        # If candidate found, classification should be suggested_review
        cm = mde.get("candidate_metadata") or {}
        if "line_name" in cm:
            require(
                ln_review.get("classification") == "suggested_review",
                "[4d] line_name with textual candidate → suggested_review",
                f"got: {ln_review.get('classification')!r}",
            )

    # ==================================================================== #
    # [5] Textual header submitted value match                              #
    # ==================================================================== #
    print("\n[5] Textual header submitted value match (survey_name present and in textual)")
    fx = _write_fixture("sblt5_t05.csv", [{
        "Survey Name": "DELTA_BASIN",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_E",
        "SEG-Y File": SEGY_MATCH,
    }])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[5a] HTTP 200")
    rows = body.get("rows", [])
    if rows:
        row = rows[0]
        mde = row.get("metadata_evidence") or {}
        evs = mde.get("evidence_records") or []
        survey_textual_evs = [
            e for e in evs
            if e.get("field") == "survey_name"
            and e.get("source_type") == "segy_textual_header"
        ]
        require(
            len(survey_textual_evs) >= 1,
            "[5b] textual evidence record for survey_name present",
            f"survey_textual_evs={survey_textual_evs}",
        )
        if survey_textual_evs:
            require(
                survey_textual_evs[0].get("observed_value", "").upper() == "DELTA_BASIN",
                "[5c] observed_value matches submitted survey_name",
                f"got: {survey_textual_evs[0].get('observed_value')!r}",
            )
        fr = mde.get("field_review") or {}
        sn_review = fr.get("survey_name") or {}
        require(
            sn_review.get("classification") == "no_action_required",
            "[5d] survey_name classification = no_action_required",
            f"got: {sn_review.get('classification')!r}",
        )

    # ==================================================================== #
    # [6] Header too small                                                  #
    # ==================================================================== #
    print("\n[6] Header too small (< 3600 bytes → blocked, SEGY_HEADER_TOO_SMALL)")
    fx = _write_fixture("sblt5_t06.csv", [{
        "Survey Name": "Zeta Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_F",
        "SEG-Y File": SEGY_SMALL,
    }])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[6a] HTTP 200")
    rows = body.get("rows", [])
    if rows:
        row = rows[0]
        require(
            row.get("status") == "blocked",
            "[6b] row status = blocked",
            f"got: {row.get('status')!r}",
        )
        all_flags = row.get("qaqc_flags") or []
        codes = flag_codes(all_flags)
        require(
            "SEGY_HEADER_TOO_SMALL" in codes,
            "[6c] SEGY_HEADER_TOO_SMALL flag present",
            f"codes={codes}",
        )

    # ==================================================================== #
    # [7] Data sample format code captured                                  #
    # ==================================================================== #
    print("\n[7] Data sample format code captured (code=5 → IEEE float)")
    fx = _write_fixture("sblt5_t07.csv", [{
        "Survey Name": "Eta Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_G",
        "SEG-Y File": SEGY_FORMAT5,
    }])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[7a] HTTP 200")
    rows = body.get("rows", [])
    if rows:
        row = rows[0]
        mde = row.get("metadata_evidence") or {}
        cm = mde.get("candidate_metadata") or {}

        dsfc_cand = cm.get("data_sample_format_code") or {}
        require(
            dsfc_cand.get("candidate_value") == 5,
            "[7b] data_sample_format_code candidate_value = 5",
            f"got: {dsfc_cand.get('candidate_value')!r}",
        )

        dsfn_cand = cm.get("data_sample_format_name") or {}
        require(
            dsfn_cand.get("candidate_value") == "IEEE float",
            "[7c] data_sample_format_name candidate_value = 'IEEE float'",
            f"got: {dsfn_cand.get('candidate_value')!r}",
        )

        fr = mde.get("field_review") or {}
        dsfc_review = fr.get("data_sample_format_code") or {}
        require(
            dsfc_review.get("classification") in ("auto_accepted", "candidate_from_evidence"),
            "[7d] data_sample_format_code classification is auto_accepted or candidate",
            f"got: {dsfc_review.get('classification')!r}",
        )

    # ==================================================================== #
    # [8] Samples per trace captured (1500)                                 #
    # ==================================================================== #
    print("\n[8] Samples per trace captured (samples_per_trace=1500 → auto_accepted)")
    fx = _write_fixture("sblt5_t08.csv", [{
        "Survey Name": "Theta Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_H",
        "SEG-Y File": SEGY_SPT1500,
    }])
    sid, status, body = _pipeline_full(str(fx))
    require(status == 200, "[8a] HTTP 200")
    rows = body.get("rows", [])
    if rows:
        row = rows[0]
        mde = row.get("metadata_evidence") or {}
        cm = mde.get("candidate_metadata") or {}
        spt_cand = cm.get("samples_per_trace") or {}
        require(
            spt_cand.get("candidate_value") == 1500,
            "[8b] samples_per_trace candidate_value = 1500",
            f"got: {spt_cand.get('candidate_value')!r}",
        )
        fr = mde.get("field_review") or {}
        spt_review = fr.get("samples_per_trace") or {}
        require(
            spt_review.get("classification") == "auto_accepted",
            "[8c] samples_per_trace classification = auto_accepted",
            f"got: {spt_review.get('classification')!r}",
        )

    # ==================================================================== #
    # [9] Endpoint before path validation → HTTP 400                        #
    # ==================================================================== #
    print("\n[9] Endpoint before path validation → HTTP 400")
    fx = _write_fixture("sblt5_t09.csv", [{
        "Survey Name": "Iota Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_I",
        "SEG-Y File": SEGY_4MS,
    }])
    sid, status, body = _pipeline_before_paths(str(fx))
    require(status == 400, "[9a] HTTP 400 before path validation",
            f"got: {status}")
    detail_str = str(body.get("detail", "")).lower()
    require(
        "paths_validated" in detail_str or "normalized" in detail_str or "state" in detail_str,
        "[9b] error detail mentions required state",
        f"detail={body.get('detail')!r}",
    )

    # ==================================================================== #
    # [10] Nonexistent session → HTTP 404                                   #
    # ==================================================================== #
    print("\n[10] Nonexistent session → HTTP 404")
    status, body = post("/api/sblt/sessions/sblt_no_such_session_xyz/extract-segy-header-evidence")
    require(status == 404, "[10a] HTTP 404 for nonexistent session",
            f"got: {status}")

    # ==================================================================== #
    # [11] Preservation                                                     #
    # ==================================================================== #
    print("\n[11] Preservation: source_values, canonical_fields, normalized_metadata, "
          "identity_hints, path_validation unchanged")
    fx = _write_fixture("sblt5_t11.csv", [{
        "Survey Name": "Kappa Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_K",
        "Sample Interval MS": "2.0",
        "SEG-Y File": SEGY_4MS,
    }])
    # First run pipeline without extract to capture the baseline
    status_base, body_base = post("/api/sblt/sessions", {
        "loadsheet_path": str(fx),
    })
    sid_base = body_base["session_id"]
    for step in ("validate", "normalize"):
        post(f"/api/sblt/sessions/{sid_base}/{step}")
    _, body_paths = post(f"/api/sblt/sessions/{sid_base}/validate-paths")
    row_before = body_paths["rows"][0]

    # Now extract
    _, body_after = post(
        f"/api/sblt/sessions/{sid_base}/extract-segy-header-evidence"
    )
    row_after = body_after["rows"][0]

    require(
        row_after.get("source_values") == row_before.get("source_values"),
        "[11a] source_values preserved",
    )
    require(
        row_after.get("canonical_fields") == row_before.get("canonical_fields"),
        "[11b] canonical_fields preserved",
    )
    require(
        row_after.get("normalized_metadata") == row_before.get("normalized_metadata"),
        "[11c] normalized_metadata preserved",
    )
    require(
        row_after.get("identity_hints") == row_before.get("identity_hints"),
        "[11d] identity_hints preserved",
    )
    require(
        row_after.get("path_validation") == row_before.get("path_validation"),
        "[11e] path_validation preserved",
    )
    require(
        "metadata_evidence" in row_after,
        "[11f] metadata_evidence key added",
    )
    require(
        row_after.get("metadata_evidence", {}).get("schema_version") == "mde.bundle.v1",
        "[11g] metadata_evidence.schema_version = mde.bundle.v1",
    )

    # ==================================================================== #
    # [12] Regression: existing SBLT-1 through SBLT-4 endpoints unaffected  #
    # ==================================================================== #
    print("\n[12] Regression: create/validate/normalize/validate-paths still work")
    fx = _write_fixture("sblt5_t12.csv", [{
        "Survey Name": "Lambda Survey",
        "Data Type": "3d_volume",
        "Volume Name": "Vol_L",
        "SEG-Y File": SEGY_4MS,
    }])
    status, body = post("/api/sblt/sessions", {"loadsheet_path": str(fx)})
    require(status == 200, "[12a] SBLT-1 create session still works")
    sid12 = body.get("session_id", "")

    status, body = post(f"/api/sblt/sessions/{sid12}/validate")
    require(status == 200, "[12b] SBLT-2 validate still works")

    status, body = post(f"/api/sblt/sessions/{sid12}/normalize")
    require(status == 200, "[12c] SBLT-3 normalize still works")

    status, body = post(f"/api/sblt/sessions/{sid12}/validate-paths")
    require(status == 200, "[12d] SBLT-4 validate-paths still works")

    status, body = get(f"/api/sblt/sessions/{sid12}")
    require(status == 200, "[12e] SBLT-1 GET session still works")
    require(
        body.get("schema_version") == "sblt.session.v1",
        "[12f] schema_version unchanged",
        f"got: {body.get('schema_version')!r}",
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def main() -> None:
    run_tests()

    print(f"\n{'='*60}")
    print(f"SBLT-5 Contract Test Results: {PASS} PASS, {FAIL} FAIL")
    print(f"{'='*60}")

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
