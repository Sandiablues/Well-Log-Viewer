from __future__ import annotations

from typing import Any, Dict, List, Optional


EVIDENCE_RANKS = {
    "manual_override": 5,
    "curated_registry": 5,
    "binary_header": 4,
    "trace_header_summary": 4,
    "viewer_metadata": 4,
    "conversion_metadata": 4,
    "zarr_metadata": 4,
    "registry": 3,
    "source_repository": 3,
    "supporting_documents": 2,
    "text_header": 1,
    "filename_inference": 0,
    "fallback": 0,
}


def _present(value: Any) -> bool:
    if value is None:
        return False
    if value == "":
        return False
    if isinstance(value, list) and len(value) == 0:
        return False
    if isinstance(value, dict) and len(value) == 0:
        return False
    return True


def _field(name: str, value: Any, *, derived: bool = False, not_applicable: bool = False) -> Dict[str, Any]:
    if not_applicable:
        status = "not_applicable"
    elif _present(value):
        status = "derived" if derived else "complete"
    else:
        status = "missing"

    return {
        "name": name,
        "status": status,
        "value": value,
    }


def _score_fields(fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    applicable = [f for f in fields if f.get("status") != "not_applicable"]
    complete = [f for f in applicable if f.get("status") in ("complete", "derived")]

    score = round(len(complete) / len(applicable), 3) if applicable else 1.0

    if score >= 0.95:
        status = "complete"
    elif score >= 0.75:
        status = "mostly_complete"
    elif score >= 0.50:
        status = "partial"
    else:
        status = "weak"

    return {
        "score": score,
        "percent": int(round(score * 100)),
        "status": status,
        "field_count": len(applicable),
        "complete_count": len(complete),
        "missing_fields": [f["name"] for f in applicable if f.get("status") == "missing"],
        "derived_fields": [f["name"] for f in applicable if f.get("status") == "derived"],
        "not_applicable_fields": [f["name"] for f in fields if f.get("status") == "not_applicable"],
        "fields": fields,
    }


def _status_label(score: float) -> str:
    if score >= 0.95:
        return "complete"
    if score >= 0.75:
        return "mostly_complete"
    if score >= 0.50:
        return "partial"
    return "weak"


def _build_completeness(summary: Dict[str, Any]) -> Dict[str, Any]:
    dataset_type = summary.get("dataset_type") or "unknown"
    source = summary.get("source") or {}
    geometry = summary.get("geometry") or {}
    coordinate_crs = summary.get("coordinate_crs") or {}
    headers = summary.get("headers") or {}
    documents = summary.get("documents") or {}
    supporting_documents = documents.get("supporting_documents") or []

    source_type = source.get("source_type")
    is_external = source_type == "external_repository"
    is_2d = dataset_type == "2d_line"
    is_3d = dataset_type == "3d_volume"

    identity_fields = [
        _field("dataset_type", dataset_type),
        _field("display_name", summary.get("display_name")),
        _field("source.filename", source.get("filename")),
        _field("source.source_type", source_type),
        _field("source.repository_id", source.get("repository_id"), not_applicable=not is_external),
        _field("source.package_id", source.get("package_id"), not_applicable=not is_external),
        _field("source.line_id", source.get("line_id"), not_applicable=not is_external),
        _field("source.segy_file_id", source.get("segy_file_id"), not_applicable=not is_external),
        _field("source.relative_path", source.get("relative_path"), not_applicable=not is_external),
    ]

    if is_3d:
        geometry_fields = [
            _field("geometry.shape", geometry.get("shape")),
            _field("geometry.axis_order", geometry.get("axis_order")),
            _field("geometry.inline_range", geometry.get("inline_range")),
            _field("geometry.crossline_range", geometry.get("crossline_range")),
            _field("geometry.sample_count", geometry.get("sample_count")),
            _field("geometry.sample_interval_ms", geometry.get("sample_interval_ms")),
            _field("geometry.time_range_ms", geometry.get("time_range_ms"), derived=bool(geometry.get("time_range_ms"))),
            _field("geometry.trace_count", geometry.get("trace_count")),
            _field("geometry.geometry_status", geometry.get("geometry_status")),
        ]
    elif is_2d:
        geometry_fields = [
            _field("geometry.shape", geometry.get("shape")),
            _field("geometry.axis_order", geometry.get("axis_order")),
            _field("geometry.inline_range", geometry.get("inline_range"), not_applicable=True),
            _field("geometry.crossline_range", geometry.get("crossline_range"), not_applicable=True),
            _field("geometry.trace_count", geometry.get("trace_count")),
            _field("geometry.sample_count", geometry.get("sample_count")),
            _field("geometry.sample_interval_ms", geometry.get("sample_interval_ms")),
            _field("geometry.time_range_ms", geometry.get("time_range_ms"), derived=bool(geometry.get("time_range_ms"))),
            _field("geometry.geometry_status", geometry.get("geometry_status")),
        ]
    else:
        geometry_fields = [
            _field("geometry.shape", geometry.get("shape")),
            _field("geometry.axis_order", geometry.get("axis_order")),
            _field("geometry.sample_count", geometry.get("sample_count")),
            _field("geometry.sample_interval_ms", geometry.get("sample_interval_ms")),
            _field("geometry.time_range_ms", geometry.get("time_range_ms"), derived=bool(geometry.get("time_range_ms"))),
            _field("geometry.trace_count", geometry.get("trace_count")),
            _field("geometry.geometry_status", geometry.get("geometry_status")),
        ]

    evidence_fields = [
        _field("headers.binary_header_available", headers.get("binary_header_available")),
        _field("headers.trace_header_summary_available", headers.get("trace_header_summary_available")),
        _field("headers.viewer_metadata_available", headers.get("viewer_metadata_available")),
        _field("headers.text_header_available", headers.get("text_header_available")),
        _field("headers.text_header_readable", headers.get("text_header_readable")),
        _field("headers.normalized_metadata_available", headers.get("normalized_metadata_available")),
        _field("documents.supporting_documents", len(supporting_documents) if supporting_documents else None),
    ]

    coordinate_crs_fields = [
        _field("coordinate_crs.x_min", coordinate_crs.get("x_min")),
        _field("coordinate_crs.x_max", coordinate_crs.get("x_max")),
        _field("coordinate_crs.y_min", coordinate_crs.get("y_min")),
        _field("coordinate_crs.y_max", coordinate_crs.get("y_max")),
        _field("coordinate_crs.crs_name", coordinate_crs.get("crs_name")),
        _field("coordinate_crs.epsg_code", coordinate_crs.get("epsg_code")),
    ]

    identity = _score_fields(identity_fields)
    geometry_score = _score_fields(geometry_fields)
    coordinate_crs_score = _score_fields(coordinate_crs_fields)
    evidence = _score_fields(evidence_fields)

    overall_score = round(
        (identity["score"] * 0.25)
        + (geometry_score["score"] * 0.35)
        + (coordinate_crs_score["score"] * 0.20)
        + (evidence["score"] * 0.20),
        3,
    )

    missing_fields = (
        identity["missing_fields"]
        + geometry_score["missing_fields"]
        + coordinate_crs_score["missing_fields"]
        + evidence["missing_fields"]
    )
    derived_fields = (
        identity["derived_fields"]
        + geometry_score["derived_fields"]
        + coordinate_crs_score["derived_fields"]
        + evidence["derived_fields"]
    )
    not_applicable_fields = (
        identity["not_applicable_fields"]
        + geometry_score["not_applicable_fields"]
        + coordinate_crs_score["not_applicable_fields"]
        + evidence["not_applicable_fields"]
    )

    return {
        "score": overall_score,
        "percent": int(round(overall_score * 100)),
        "status": _status_label(overall_score),
        "categories": {
            "identity": identity,
            "geometry": geometry_score,
            "coordinate_crs": coordinate_crs_score,
            "evidence": evidence,
        },
        "missing_fields": missing_fields,
        "derived_fields": derived_fields,
        "not_applicable_fields": not_applicable_fields,
        "scoring_basis": "viewer_and_spatial_qaqc_metadata_v1",
    }


def _build_evidence_strength(summary: Dict[str, Any]) -> Dict[str, Any]:
    source = summary.get("source") or {}
    headers = summary.get("headers") or {}
    documents = summary.get("documents") or {}
    geometry = summary.get("geometry") or {}

    sources = []

    if headers.get("binary_header_available"):
        sources.append({"source": "binary_header", "rank": EVIDENCE_RANKS["binary_header"]})

    if headers.get("trace_header_summary_available"):
        sources.append({"source": "trace_header_summary", "rank": EVIDENCE_RANKS["trace_header_summary"]})

    if headers.get("viewer_metadata_available"):
        sources.append({"source": "viewer_metadata", "rank": EVIDENCE_RANKS["viewer_metadata"]})

    if source.get("source_type") == "external_repository":
        sources.append({"source": "source_repository", "rank": EVIDENCE_RANKS["source_repository"]})

    if headers.get("text_header_available"):
        sources.append({"source": "text_header", "rank": EVIDENCE_RANKS["text_header"]})

    if documents.get("supporting_documents"):
        sources.append({"source": "supporting_documents", "rank": EVIDENCE_RANKS["supporting_documents"]})

    if geometry.get("geometry_status") in ("trace_sample_fallback", "fallback", "unknown"):
        sources.append({"source": "fallback", "rank": EVIDENCE_RANKS["fallback"]})

    ranks = [s["rank"] for s in sources]
    strongest_rank = max(ranks) if ranks else 0
    average_rank = round(sum(ranks) / len(ranks), 2) if ranks else 0.0

    if strongest_rank >= 4 and average_rank >= 3.0:
        status = "strong"
    elif strongest_rank >= 4:
        status = "moderate"
    elif strongest_rank >= 3:
        status = "limited"
    else:
        status = "weak"

    return {
        "status": status,
        "strongest_rank": strongest_rank,
        "average_rank": average_rank,
        "available_sources": sources,
        "ranking_basis": "metadata_quality_model_v0.1",
    }


def _check_equal(name: str, left: Any, right: Any, left_label: str, right_label: str) -> Dict[str, Any]:
    if left is None or right is None:
        status = "unknown"
    else:
        status = "passed" if left == right else "failed"

    return {
        "name": name,
        "status": status,
        "left": left,
        "right": right,
        "left_source": left_label,
        "right_source": right_label,
    }


def _as_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_consistency(summary: Dict[str, Any]) -> Dict[str, Any]:
    dataset_type = summary.get("dataset_type") or "unknown"
    geometry = summary.get("geometry") or {}
    headers = summary.get("headers") or {}
    binary = headers.get("binary_header_summary") or {}
    trace = headers.get("trace_header_summary") or {}

    checks = []

    geom_sample_count = _as_int(geometry.get("sample_count"))
    geom_trace_count = _as_int(geometry.get("trace_count"))
    geom_sample_interval_ms = _as_float(geometry.get("sample_interval_ms"))

    binary_samples = _as_int(binary.get("samples_per_trace"))
    binary_sample_interval_us = _as_int(binary.get("sample_interval_us"))
    binary_sample_interval_ms = binary_sample_interval_us / 1000.0 if binary_sample_interval_us is not None else None

    trace_count = _as_int(trace.get("trace_count"))
    first_trace = trace.get("first_trace_header") or {}
    trace_samples = _as_int(first_trace.get("samples_in_trace"))
    trace_sample_interval_us = _as_int(first_trace.get("sample_interval_us"))
    trace_sample_interval_ms = trace_sample_interval_us / 1000.0 if trace_sample_interval_us is not None else None

    checks.append(_check_equal(
        "geometry.sample_count equals binary.samples_per_trace",
        geom_sample_count,
        binary_samples,
        "geometry",
        "binary_header",
    ))

    checks.append(_check_equal(
        "binary.samples_per_trace equals trace.samples_in_trace",
        binary_samples,
        trace_samples,
        "binary_header",
        "trace_header_summary",
    ))

    checks.append(_check_equal(
        "geometry.trace_count equals trace_header_summary.trace_count",
        geom_trace_count,
        trace_count,
        "geometry",
        "trace_header_summary",
    ))

    checks.append(_check_equal(
        "geometry.sample_interval_ms equals binary.sample_interval_us",
        geom_sample_interval_ms,
        binary_sample_interval_ms,
        "geometry",
        "binary_header",
    ))

    checks.append(_check_equal(
        "binary.sample_interval_us equals trace.sample_interval_us",
        binary_sample_interval_ms,
        trace_sample_interval_ms,
        "binary_header",
        "trace_header_summary",
    ))

    if dataset_type == "3d_volume":
        inline_range = geometry.get("inline_range")
        crossline_range = geometry.get("crossline_range")

        trace_inline_range = None
        if trace.get("inline_min_sampled") is not None and trace.get("inline_max_sampled") is not None:
            trace_inline_range = [trace.get("inline_min_sampled"), trace.get("inline_max_sampled")]

        trace_crossline_range = None
        if trace.get("crossline_min_sampled") is not None and trace.get("crossline_max_sampled") is not None:
            trace_crossline_range = [trace.get("crossline_min_sampled"), trace.get("crossline_max_sampled")]

        checks.append(_check_equal(
            "geometry.inline_range equals trace sampled inline range",
            inline_range,
            trace_inline_range,
            "geometry",
            "trace_header_summary",
        ))

        checks.append(_check_equal(
            "geometry.crossline_range equals trace sampled crossline range",
            crossline_range,
            trace_crossline_range,
            "geometry",
            "trace_header_summary",
        ))

    passed = len([c for c in checks if c["status"] == "passed"])
    failed = len([c for c in checks if c["status"] == "failed"])
    unknown = len([c for c in checks if c["status"] == "unknown"])

    applicable = passed + failed
    score = round(passed / applicable, 3) if applicable else 0.0

    if failed == 0 and passed > 0 and unknown <= 1:
        status = "consistent"
    elif failed == 0 and passed > 0:
        status = "mostly_consistent"
    elif failed > 0 and passed >= failed:
        status = "inconsistent_with_warnings"
    elif failed > 0:
        status = "inconsistent"
    else:
        status = "unknown"

    return {
        "score": score,
        "percent": int(round(score * 100)),
        "status": status,
        "checks_passed": passed,
        "checks_failed": failed,
        "checks_unknown": unknown,
        "issues": [c for c in checks if c["status"] == "failed"],
        "checks": checks,
    }


def _build_metadata_status(completeness: Dict[str, Any], evidence: Dict[str, Any], consistency: Dict[str, Any]) -> Dict[str, Any]:
    comp_score = completeness.get("score", 0)
    evidence_status = evidence.get("status")
    consistency_status = consistency.get("status")
    failed_checks = consistency.get("checks_failed", 0)

    if comp_score < 0.50:
        status = "weak"
        summary = "Required viewer metadata is substantially incomplete."
    elif failed_checks > 0:
        status = "needs_review"
        summary = "Metadata has consistency conflicts that should be reviewed."
    elif comp_score < 0.75:
        status = "incomplete"
        summary = "Some required viewer metadata is missing."
    elif evidence_status in ("weak", "limited"):
        status = "usable_with_warnings"
        summary = "Required viewer metadata is mostly present, but evidence strength is limited."
    elif consistency_status in ("consistent", "mostly_consistent"):
        status = "usable"
        summary = "Required viewer metadata is present and internally consistent for viewer use."
    else:
        status = "usable_with_warnings"
        summary = "Required viewer metadata is mostly present, with some unknown consistency checks."

    return {
        "status": status,
        "summary": summary,
    }


def build_metadata_quality_report(summary: Dict[str, Any]) -> Dict[str, Any]:
    completeness = _build_completeness(summary)
    evidence_strength = _build_evidence_strength(summary)
    consistency = _build_consistency(summary)
    metadata_status = _build_metadata_status(completeness, evidence_strength, consistency)

    return {
        "completeness": completeness,
        "evidence_strength": evidence_strength,
        "consistency": consistency,
        "metadata_status": metadata_status,
        "model_version": "metadata_quality_model.v0.1",
    }
