"""
MDE-1 Contract Foundation Tests.

stdlib-only. No server required. No file I/O. No SBLT imports. No SSI imports.
Run from seismic-viewer-backend/:
    python3 scripts/test_mde_contract_foundation.py
"""

from __future__ import annotations

import sys
import os
import traceback

# ---------------------------------------------------------------------------
# Path setup — allows running from seismic-viewer-backend/ directly
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# ---------------------------------------------------------------------------
# Import MDE package ONLY — no seismic_bulk_loader, no source_intake
# ---------------------------------------------------------------------------

from app.services.metadata_evidence import (
    SCHEMA_VERSION,
    build_metadata_evidence_bundle,
    detect_intake_mode,
    get_field_policy,
    validate_bundle_invariants,
)
from app.services.metadata_evidence.mde_models import (
    APPROVAL_NOT_REVIEWED,
    CANDIDATE_STATUS_AUTO_ACCEPTED,
    CANDIDATE_STATUS_SUGGESTED,
    COMPARISON_CANDIDATE_FROM_EVIDENCE,
    COMPARISON_CONFLICT,
    COMPARISON_MATCH,
    INTAKE_MODE_METADATA_RICH,
    INTAKE_MODE_METADATA_SPARSE,
    INTAKE_MODE_MIXED,
    REVIEW_AUTO_ACCEPTED,
    REVIEW_CONFLICT,
    REVIEW_MISSING_RECOMMENDED,
    REVIEW_MISSING_REQUIRED,
    REVIEW_NO_ACTION_REQUIRED,
    REVIEW_SUGGESTED_REVIEW,
    make_dataset_context,
    make_source_reference,
)
from app.services.metadata_evidence.mde_review_classifier import compare_values

# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

PASSED = 0
FAILED = 0
ERRORS: list[str] = []


def require(condition: bool, label: str) -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS  {label}")
    else:
        FAILED += 1
        msg = f"  FAIL  {label}"
        ERRORS.append(msg)
        print(msg)


def run_test(name: str, fn) -> None:
    print(f"\n[{name}]")
    try:
        fn()
    except Exception:
        global FAILED
        FAILED += 1
        tb = traceback.format_exc()
        ERRORS.append(f"  EXCEPTION in {name}:\n{tb}")
        print(f"  EXCEPTION:\n{tb}")


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_SOURCE_REF = make_source_reference(
    source_reference_type="local_path",
    source_reference_value="/data/Line001.sgy",
    resolved_reference="/data/Line001.sgy",
    source_status="validated",
)
_CTX_WITH_SOURCE = make_dataset_context(
    record_type="2d_line",
    dataset_label="Survey / Line001",
    source_reference=_SOURCE_REF,
)
_CTX_NO_SOURCE = make_dataset_context()


def _bundle(submitted: dict, observations: list, ctx=None) -> dict:
    return build_metadata_evidence_bundle(
        workflow_type="sblt",
        workflow_session_id="sblt_test_session",
        workflow_row_id="sblt_test_session_row_0001",
        dataset_context=ctx or _CTX_WITH_SOURCE,
        raw_submitted_metadata=submitted,
        candidate_observations=observations,
    )


# ---------------------------------------------------------------------------
# Test 1 — Metadata-rich match: sample_interval_ms submitted == candidate
# ---------------------------------------------------------------------------

def test_01_metadata_rich_match():
    b = _bundle(
        submitted={"sample_interval_ms": 4.0, "survey_name": "FN923", "record_type": "2d_line", "line_name": "L001"},
        observations=[{
            "field": "sample_interval_ms",
            "observed_value": 4.0,
            "source_type": "segy_binary_header",
            "source_label": "Binary header sample_interval_us",
            "confidence": "high",
            "evidence_detail": {"header_field": "sample_interval_us"},
        }],
    )
    fr_si = b["field_review"].get("sample_interval_ms", {})
    ev_si = next((e for e in b["evidence_records"] if e["field"] == "sample_interval_ms"), None)

    require(ev_si is not None, "evidence record created for sample_interval_ms")
    require(ev_si["comparison"] == COMPARISON_MATCH, "evidence comparison == match")
    require(fr_si.get("classification") == REVIEW_NO_ACTION_REQUIRED, "field classification no_action_required")
    require(not fr_si.get("requires_user_review"), "requires_user_review is False on match")
    conflict_findings = [f for f in b["qaqc_findings"] if f["code"] == "MDE_CONFLICT"]
    require(len(conflict_findings) == 0, "no MDE_CONFLICT finding on match")

run_test("Test 01 — metadata-rich match", test_01_metadata_rich_match)


# ---------------------------------------------------------------------------
# Test 2 — Metadata-rich conflict: submitted 4.0, candidate 2.0
# ---------------------------------------------------------------------------

def test_02_metadata_rich_conflict():
    b = _bundle(
        submitted={"sample_interval_ms": 4.0},
        observations=[{
            "field": "sample_interval_ms",
            "observed_value": 2.0,
            "source_type": "segy_binary_header",
            "source_label": "Binary header",
            "confidence": "high",
        }],
    )
    fr_si = b["field_review"].get("sample_interval_ms", {})
    ev_si = next((e for e in b["evidence_records"] if e["field"] == "sample_interval_ms"), None)

    require(ev_si is not None, "evidence record created")
    require(ev_si["comparison"] == COMPARISON_CONFLICT, "evidence comparison == conflict")
    require(fr_si.get("classification") == REVIEW_CONFLICT, "field classification conflict")
    require(fr_si.get("requires_user_review"), "requires_user_review True on conflict")
    conflict_findings = [f for f in b["qaqc_findings"] if f["code"] == "MDE_CONFLICT"]
    require(len(conflict_findings) == 1, "one MDE_CONFLICT finding created")
    require(conflict_findings[0]["severity"] == "warning", "conflict finding severity warning")

run_test("Test 02 — metadata-rich conflict", test_02_metadata_rich_conflict)


# ---------------------------------------------------------------------------
# Test 3 — Metadata-sparse technical auto-accept
# ---------------------------------------------------------------------------

def test_03_sparse_technical_auto_accept():
    b = _bundle(
        submitted={"sample_interval_ms": None},  # absent
        observations=[{
            "field": "sample_interval_ms",
            "observed_value": 4.0,
            "source_type": "segy_binary_header",
            "source_label": "Binary header",
            "confidence": "high",
        }],
    )
    fr_si = b["field_review"].get("sample_interval_ms", {})
    ev_si = next((e for e in b["evidence_records"] if e["field"] == "sample_interval_ms"), None)
    cand_si = b["candidate_metadata"].get("sample_interval_ms", {})

    require(ev_si is not None, "evidence record created")
    require(ev_si["comparison"] == COMPARISON_CANDIDATE_FROM_EVIDENCE, "comparison candidate_from_evidence")
    require(fr_si.get("classification") == REVIEW_AUTO_ACCEPTED, "classification auto_accepted")
    require(not fr_si.get("requires_user_review"), "requires_user_review False on auto_accept")
    require(cand_si.get("candidate_status") == CANDIDATE_STATUS_AUTO_ACCEPTED, "candidate_status auto_accepted")

run_test("Test 03 — metadata-sparse technical auto-accept", test_03_sparse_technical_auto_accept)


# ---------------------------------------------------------------------------
# Test 4 — Metadata-sparse identity suggestion (survey_name from textual header)
# ---------------------------------------------------------------------------

def test_04_sparse_identity_suggested_review():
    b = _bundle(
        submitted={"survey_name": None},  # absent
        observations=[{
            "field": "survey_name",
            "observed_value": "FN923F0001",
            "source_type": "segy_textual_header",
            "source_label": "Textual header line 3",
            "confidence": "medium",
        }],
    )
    fr_sn = b["field_review"].get("survey_name", {})
    cand_sn = b["candidate_metadata"].get("survey_name", {})

    require(fr_sn.get("classification") == REVIEW_SUGGESTED_REVIEW, "classification suggested_review")
    require(fr_sn.get("requires_user_review"), "requires_user_review True for identity field")
    require(cand_sn.get("candidate_status") == CANDIDATE_STATUS_SUGGESTED, "candidate_status suggested")

run_test("Test 04 — metadata-sparse identity suggested review", test_04_sparse_identity_suggested_review)


# ---------------------------------------------------------------------------
# Test 5 — Missing required identity field (record_type absent, no candidate)
# ---------------------------------------------------------------------------

def test_05_missing_required_identity():
    b = _bundle(
        submitted={"record_type": None},
        observations=[],
    )
    fr = b["field_review"].get("record_type", {})
    rs = b["review_summary"]

    require(fr.get("classification") == REVIEW_MISSING_REQUIRED, "classification missing_required")
    require(fr.get("requires_user_review"), "requires_user_review True")
    require(rs.get("approval_blocked"), "approval_blocked True when required field missing")
    require(rs.get("missing_required_count", 0) >= 1, "missing_required_count >= 1")

run_test("Test 05 — missing required identity field", test_05_missing_required_identity)


# ---------------------------------------------------------------------------
# Test 6 — Missing CRS / datum (submitted absent, no candidate)
# ---------------------------------------------------------------------------

def test_06_missing_crs_datum():
    b = _bundle(
        submitted={"crs": None, "datum": None},
        observations=[],
    )
    fr_crs = b["field_review"].get("crs", {})
    fr_datum = b["field_review"].get("datum", {})

    require(fr_crs.get("classification") == REVIEW_MISSING_REQUIRED,
            "crs missing_required per policy")
    require(fr_datum.get("classification") == REVIEW_MISSING_RECOMMENDED,
            "datum missing_recommended per policy")
    require(fr_crs.get("requires_user_review"), "crs requires_user_review True")
    require(b["review_summary"].get("approval_blocked"), "approval_blocked True (crs required)")

run_test("Test 06 — missing CRS/datum", test_06_missing_crs_datum)


# ---------------------------------------------------------------------------
# Test 7 — Intake mode: metadata_rich
# ---------------------------------------------------------------------------

def test_07_intake_mode_metadata_rich():
    # All 4 signals: source_reference + survey_name + record_type + line_name
    b = _bundle(
        submitted={
            "survey_name": "FN923",
            "record_type": "2d_line",
            "line_name": "L001",
        },
        observations=[],
        ctx=_CTX_WITH_SOURCE,
    )
    mode = b["workflow"]["intake_mode"]
    require(mode == INTAKE_MODE_METADATA_RICH, f"intake mode metadata_rich (got {mode!r})")

run_test("Test 07 — intake mode metadata_rich", test_07_intake_mode_metadata_rich)


# ---------------------------------------------------------------------------
# Test 8 — Intake mode: metadata_sparse
# ---------------------------------------------------------------------------

def test_08_intake_mode_metadata_sparse():
    # source_reference only — no identity fields
    mode = detect_intake_mode({}, _CTX_WITH_SOURCE)
    require(mode == INTAKE_MODE_METADATA_SPARSE, f"intake mode metadata_sparse (got {mode!r})")

run_test("Test 08 — intake mode metadata_sparse", test_08_intake_mode_metadata_sparse)


# ---------------------------------------------------------------------------
# Test 9 — Intake mode: mixed
# ---------------------------------------------------------------------------

def test_09_intake_mode_mixed():
    # source_reference + survey_name, but no record_type or line/volume → score 2 → mixed
    mode = detect_intake_mode(
        {
            "survey_name": {"present": True, "value": "FN923"},
            "record_type": {"present": False, "value": None},
        },
        _CTX_WITH_SOURCE,
    )
    require(mode == INTAKE_MODE_MIXED, f"intake mode mixed (got {mode!r})")

run_test("Test 09 — intake mode mixed", test_09_intake_mode_mixed)


# ---------------------------------------------------------------------------
# Test 10 — Evidence record shape
# ---------------------------------------------------------------------------

def test_10_evidence_record_shape():
    b = _bundle(
        submitted={},
        observations=[{
            "field": "sample_interval_ms",
            "observed_value": 4.0,
            "source_type": "segy_binary_header",
            "source_label": "Binary header",
            "confidence": "high",
            "evidence_detail": {"header_field": "sample_interval_us"},
        }],
    )
    ev = next((e for e in b["evidence_records"] if e["field"] == "sample_interval_ms"), None)
    require(ev is not None, "evidence record present")
    for key in ("evidence_id", "field", "source_type", "observed_value", "confidence", "comparison"):
        require(key in ev, f"evidence record has key {key!r}")
    require(ev["evidence_id"].startswith("ev_"), "evidence_id has ev_ prefix")

run_test("Test 10 — evidence record shape", test_10_evidence_record_shape)


# ---------------------------------------------------------------------------
# Test 11 — QAQC finding shape
# ---------------------------------------------------------------------------

def test_11_qaqc_finding_shape():
    b = _bundle(
        submitted={"sample_interval_ms": 4.0},
        observations=[{
            "field": "sample_interval_ms",
            "observed_value": 2.0,
            "source_type": "segy_binary_header",
            "source_label": "Binary header",
            "confidence": "high",
        }],
    )
    f = next((x for x in b["qaqc_findings"] if x["code"] == "MDE_CONFLICT"), None)
    require(f is not None, "MDE_CONFLICT finding present")
    for key in ("finding_id", "severity", "code", "field", "message", "source"):
        require(key in f, f"finding has key {key!r}")
    require(f["finding_id"].startswith("qaqc_"), "finding_id has qaqc_ prefix")
    require(f["source"] == "mde", "finding source is mde")

run_test("Test 11 — QAQC finding shape", test_11_qaqc_finding_shape)


# ---------------------------------------------------------------------------
# Test 12 — Review summary counts reconcile with field_review
# ---------------------------------------------------------------------------

def test_12_review_summary_counts():
    b = _bundle(
        submitted={
            "sample_interval_ms": 4.0,     # match → no_action_required
            "survey_name": None,             # missing_required
            "record_type": None,             # missing_required
            "crs": None,                     # missing_required
        },
        observations=[{
            "field": "sample_interval_ms",
            "observed_value": 4.0,
            "source_type": "segy_binary_header",
            "source_label": "Binary header",
            "confidence": "high",
        }],
    )
    rs = b["review_summary"]
    fr = b["field_review"]

    total = rs["total_fields"]
    require(total == len(fr), f"total_fields ({total}) == len(field_review) ({len(fr)})")

    # Count missing_required manually
    manual_missing_req = sum(1 for v in fr.values() if v["classification"] == REVIEW_MISSING_REQUIRED)
    require(rs["missing_required_count"] == manual_missing_req,
            f"missing_required_count reconciles ({rs['missing_required_count']} == {manual_missing_req})")

    no_action = sum(1 for v in fr.values() if v["classification"] == REVIEW_NO_ACTION_REQUIRED)
    require(rs["no_action_required_count"] == no_action,
            f"no_action_required_count reconciles ({rs['no_action_required_count']} == {no_action})")

run_test("Test 12 — review summary counts reconcile", test_12_review_summary_counts)


# ---------------------------------------------------------------------------
# Test 13 — Approval defaults
# ---------------------------------------------------------------------------

def test_13_approval_defaults():
    b = _bundle(submitted={}, observations=[])
    appr = b["approval"]

    require(appr["approval_status"] == APPROVAL_NOT_REVIEWED, "approval_status not_reviewed")
    require(appr["approved_for_loading"] is False, "approved_for_loading False")
    require(appr["approved_for_registration"] is False, "approved_for_registration False")

run_test("Test 13 — approval defaults", test_13_approval_defaults)


# ---------------------------------------------------------------------------
# Test 14 — Bundle schema: schema_version and required top-level keys
# ---------------------------------------------------------------------------

def test_14_bundle_schema():
    b = _bundle(submitted={}, observations=[])

    require(b["schema_version"] == SCHEMA_VERSION, f"schema_version == {SCHEMA_VERSION!r}")
    for k in (
        "schema_version", "bundle_id", "created_at", "workflow",
        "dataset_context", "submitted_metadata", "candidate_metadata",
        "evidence_records", "qaqc_findings", "field_review",
        "review_summary", "approved_canonical_metadata", "approval",
    ):
        require(k in b, f"bundle has top-level key {k!r}")
    require(b["bundle_id"].startswith("mde_"), "bundle_id has mde_ prefix")

run_test("Test 14 — bundle schema", test_14_bundle_schema)


# ---------------------------------------------------------------------------
# Test 15 — No dependency on SBLT
# ---------------------------------------------------------------------------

def test_15_no_sblt_dependency():
    """
    Confirm that importing and using the MDE package does not require
    seismic_bulk_loader to be importable or present.
    """
    import importlib
    mde_mod = importlib.import_module("app.services.metadata_evidence")
    src = getattr(mde_mod, "__file__", "")
    require("seismic_bulk_loader" not in src, "MDE package path does not reference seismic_bulk_loader")

    # Verify no seismic_bulk_loader in sys.modules after our tests
    sblt_loaded = any("seismic_bulk_loader" in k for k in sys.modules)
    require(not sblt_loaded, "seismic_bulk_loader was not imported during MDE tests")

run_test("Test 15 — no SBLT dependency", test_15_no_sblt_dependency)


# ---------------------------------------------------------------------------
# Test 16 — No file I/O: builder uses only in-memory dicts
# ---------------------------------------------------------------------------

def test_16_no_file_io():
    """
    Builder operates on in-memory dicts only. Verify no FileNotFoundError
    when using paths that do not exist.
    """
    b = _bundle(
        submitted={
            "sample_interval_ms": None,
            "survey_name": "Ghost Survey",
        },
        observations=[{
            "field": "sample_interval_ms",
            "observed_value": 2.0,
            "source_type": "segy_binary_header",
            "source_label": "Hypothetical header",
            "confidence": "high",
        }],
    )
    require(isinstance(b, dict), "bundle returned without filesystem access")
    require(b["schema_version"] == SCHEMA_VERSION, "schema_version correct")
    require(len(b["evidence_records"]) == 1, "one evidence record created in-memory")

run_test("Test 16 — no file I/O", test_16_no_file_io)


# ---------------------------------------------------------------------------
# Bonus: validate_bundle_invariants on all generated bundles
# ---------------------------------------------------------------------------

def test_bonus_invariants():
    """Run validate_bundle_invariants on a representative bundle."""
    from app.services.metadata_evidence import validate_bundle_invariants

    b = _bundle(
        submitted={
            "survey_name": "FN923",
            "record_type": "2d_line",
            "line_name": "L001",
            "sample_interval_ms": 4.0,
            "crs": None,
        },
        observations=[
            {
                "field": "sample_interval_ms",
                "observed_value": 4.0,
                "source_type": "segy_binary_header",
                "source_label": "Binary header",
                "confidence": "high",
            },
            {
                "field": "crs",
                "observed_value": None,
                "source_type": "segy_textual_header",
                "source_label": "Textual header",
                "confidence": "low",
            },
        ],
    )
    try:
        validate_bundle_invariants(b)
        require(True, "validate_bundle_invariants passes without exception")
    except Exception as e:
        require(False, f"validate_bundle_invariants raised: {e}")

run_test("Test BONUS — validate_bundle_invariants", test_bonus_invariants)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"MDE-1 Contract Tests: {PASSED} passed, {FAILED} failed")
if ERRORS:
    print("\nFailures:")
    for e in ERRORS:
        print(e)
print("="*60)

sys.exit(0 if FAILED == 0 else 1)
