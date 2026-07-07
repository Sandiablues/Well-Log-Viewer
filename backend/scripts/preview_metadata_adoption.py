#!/usr/bin/env python
"""Preview source_metadata_v1 adoption for existing managed records.

This script is read-only. It writes no managed inventory or source files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.source_intake.metadata_adoption import adoption_summary


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    if isinstance(payload, dict):
        values = payload.get("records", payload.get("wells", []))
        if isinstance(values, list):
            return [dict(item) for item in values]
    raise ValueError("Unsupported managed-wells payload")


def build_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    report: list[dict[str, Any]] = []

    for well in _records(payload):
        for source in well.get("source_references", []) or []:
            metadata = source.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            report.append({
                "managed_well_uid": well.get("managed_well_uid"),
                "well_name": well.get("well_name"),
                "managed_source_uid": source.get("managed_source_uid"),
                "file_name": source.get("file_name"),
                "plan": adoption_summary(metadata),
            })

    return {
        "schema_version": "metadata_adoption_preview_v1",
        "mode": "read_only",
        "source_count": len(report),
        "sources": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--managed-wells",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    args = parser.parse_args()

    report = build_report(args.managed_wells)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote read-only adoption preview: {args.output}")
    print(f"Sources reviewed: {report['source_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
