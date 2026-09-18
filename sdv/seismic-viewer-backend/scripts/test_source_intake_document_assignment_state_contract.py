#!/usr/bin/env python3
from __future__ import annotations

import importlib
import sys
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    svc = importlib.import_module("app.services.source_intake_document_assignment_service")

    candidate_current = {
        "candidate_id": "candidate_current",
        "repository_id": "repo_test",
        "package_id": "pkg_current",
        "line_id": "line_current",
    }

    candidate_elsewhere = {
        "candidate_id": "candidate_elsewhere",
        "repository_id": "repo_test",
        "package_id": "pkg_elsewhere",
        "line_id": "line_elsewhere",
    }

    doc = {
        "document_id": "doc_shared",
        "filename": "shared_report.pdf",
        "relative_path": "shared_report.pdf",
        "document_type": "processing_report",
        "document_role": "processing_report",
        "repository_id": "repo_test",
        "package_id": "pkg_current",
        "mime_type": "application/pdf",
    }

    assignments = [
        {
            "assignment_id": "assign_elsewhere",
            "document_id": "doc_shared",
            "repository_id": "repo_test",
            "scope_type": "candidate",
            "scope_id": "candidate_elsewhere",
            "status": "assigned",
            "candidate_id": "candidate_elsewhere",
            "package_id": "pkg_elsewhere",
            "line_id": "line_elsewhere",
        }
    ]

    row_for_current = svc._document_public_row(
        doc,
        candidate=candidate_current,
        assignments=assignments,
    )

    require(row_for_current.get("assigned") is False, "current candidate should not be assigned")
    require(row_for_current.get("assigned_to_current_candidate") is False, "assigned_to_current_candidate should be false")
    require(row_for_current.get("assigned_elsewhere") is True, "assigned_elsewhere should be true")
    require(row_for_current.get("assignment_state") == "assigned_elsewhere", "assignment_state should be assigned_elsewhere")
    require(isinstance(row_for_current.get("assigned_scopes"), list), "assigned_scopes should be present")
    require(len(row_for_current.get("assigned_scopes")) == 0, "assigned_scopes should be empty for current candidate")
    require(isinstance(row_for_current.get("all_assigned_scopes"), list), "all_assigned_scopes should be present")
    require(len(row_for_current.get("all_assigned_scopes")) == 1, "all_assigned_scopes should include elsewhere assignment")

    row_for_elsewhere = svc._document_public_row(
        doc,
        candidate=candidate_elsewhere,
        assignments=assignments,
    )

    require(row_for_elsewhere.get("assigned") is True, "elsewhere candidate should be assigned")
    require(row_for_elsewhere.get("assigned_to_current_candidate") is True, "assigned_to_current_candidate should be true for owning candidate")
    require(row_for_elsewhere.get("assigned_elsewhere") is False, "assigned_elsewhere should be false for owning candidate")
    require(row_for_elsewhere.get("assignment_state") == "assigned_current", "assignment_state should be assigned_current")

    rows = [row_for_current]
    assigned_elsewhere_count = sum(1 for row in rows if row.get("assigned_elsewhere"))
    require(assigned_elsewhere_count == 1, "assigned_elsewhere count should be deterministic")

    print("PASS document assignment backend state contract")
    print("current_candidate_state:", row_for_current.get("assignment_state"))
    print("owning_candidate_state:", row_for_elsewhere.get("assignment_state"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
