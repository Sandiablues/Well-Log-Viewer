#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.document_metadata_evidence_service import build_package_document_evidence, build_metadata_apply_preview


EXPECTED = {
    "FN923F0001": {
        "recommendations": 19,
        "discrepancies": 5,
        "must_have_recommendations": {
            ("spatial.crs", "ED50 / UTM Zone 31"),
            ("spatial.utm_zone", 31),
            ("spatial.central_meridian", "3°E"),
            ("geometry.sample_interval_ms", 4),
            ("geometry.record_length_ms", 4000),
        },
        "must_have_discrepancies": {
            ("identity.package_id", "candidate_conflicts_with_package_context"),
            ("spatial.crs", "incomplete_crs_candidate"),
        },
    },
    "AM923F0002": {
        "recommendations": 9,
        "discrepancies": 2,
        "must_have_recommendations": {
            ("spatial.crs", "ED50 / UTM Zone 31"),
            ("spatial.utm_zone", 31),
            ("spatial.central_meridian", "3°E"),
            ("geometry.sample_interval_ms", 2),
        },
        "must_have_discrepancies": {
            ("geometry.record_length_ms", "conflicting_record_length_candidates"),
            ("spatial.crs", "incomplete_crs_candidate"),
        },
    },
}


def normalize_value(value):
    return str(value)


def main() -> int:
    failures: list[str] = []

    print("==== DOCUMENT EVIDENCE REGRESSION CHECK ====")

    for pkg, expected in EXPECTED.items():
        print()
        print(f"PACKAGE: {pkg}")

        report = build_package_document_evidence(pkg)
        preview = build_metadata_apply_preview(pkg)
        summary = report.get("summary", {})

        rec_count = summary.get("grouped_recommendations")
        disc_count = summary.get("discrepancy_count")

        print("  validation_layer_version:", report.get("validation_layer_version"))
        print("  recommendations:", rec_count)
        print("  discrepancies:", disc_count)
        print("  target_status:", preview.get("target", {}).get("target_status"))
        print("  apply_allowed:", preview.get("target", {}).get("apply_allowed"))

        if rec_count != expected["recommendations"]:
            failures.append(f"{pkg}: expected {expected['recommendations']} recommendations, got {rec_count}")

        if disc_count != expected["discrepancies"]:
            failures.append(f"{pkg}: expected {expected['discrepancies']} discrepancies, got {disc_count}")

        if preview.get("target", {}).get("target_status") != "package_only_no_volume_link":
            failures.append(f"{pkg}: apply target status is not package_only_no_volume_link")

        if preview.get("target", {}).get("apply_allowed") is not False:
            failures.append(f"{pkg}: apply_allowed should be False")

        recs = {
            (r.get("field"), normalize_value(r.get("recommended_value")))
            for r in report.get("recommended_actions", [])
        }

        for field, value in expected["must_have_recommendations"]:
            if (field, normalize_value(value)) not in recs:
                failures.append(f"{pkg}: missing recommendation {field} = {value}")

        discrepancies = {
            (d.get("field"), d.get("status"))
            for d in report.get("discrepancies", [])
        }

        for field, status in expected["must_have_discrepancies"]:
            if (field, status) not in discrepancies:
                failures.append(f"{pkg}: missing discrepancy {field} / {status}")

        print("  status:", "PASS" if not any(f.startswith(pkg + ":") for f in failures) else "FAIL")

    print()
    print("==== RESULT ====")

    if failures:
        print("FAIL")
        for failure in failures:
            print(" -", failure)
        return 1

    print("PASS")
    print("All document evidence regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
