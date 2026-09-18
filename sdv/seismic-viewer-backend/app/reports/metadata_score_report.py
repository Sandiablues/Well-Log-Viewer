from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from app.reports.models import (
    indexed_metadata_score,
    indexed_technical_readiness,
    indexed_validation_state,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = BACKEND_ROOT / "data"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def _read_text(path: Path, limit: int = 6000) -> str:
    try:
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            return text[:limit]
    except Exception:
        return ""
    return ""


def _safe(value: Any, default: str = "—") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        try:
            return html.escape(json.dumps(value, indent=2, ensure_ascii=False))
        except Exception:
            return default
    return html.escape(str(value))


def _label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"

    labels = {
        "headers_only": "Headers only",
        "not_started": "Not started",
        "indexed_provisional": "Indexed provisional",
        "provisional_headers_only": "Indexed provisional",
        "indexed_preview_available": "Indexed preview available",
        "missing_index": "Missing index",
        "converted_volume_resolved": "Converted volume resolved",
        "metadata_summary_unavailable": "Metadata summary unavailable",
        "available": "Available",
        "missing": "Missing",
        "complete": "Complete",
        "partial": "Partial",
        "unknown": "Unknown",
        "unavailable": "Unavailable",
        "provisional": "Provisional",
    }

    return labels.get(raw, raw.replace("_", " ").replace("-", " ").title())


def _format_report_value(key: str, value: Any) -> str:
    if value is None or value == "":
        return "—"

    if isinstance(value, bool):
        return "Yes" if value else "No"

    key_l = str(key or "").lower()

    if isinstance(value, list):
        if len(value) == 2 and ("range" in key_l or key_l.endswith("_min_max")):
            return f"{_safe(value[0])} – {_safe(value[1])}"
        return " × ".join(_safe(v) for v in value)

    if isinstance(value, dict):
        if not value:
            return "—"
        if "binary" in key_l:
            return f"Available ({len(value)} fields)"
        if "trace" in key_l:
            return f"Available ({len(value)} fields)"
        if "header" in key_l:
            return f"Available ({len(value)} fields)"
        if "files" in key_l or "paths" in key_l or "artifacts" in key_l:
            return f"Available ({len(value)} items)"
        return f"Available ({len(value)} fields)"

    text_value = str(value)
    if len(text_value) > 220:
        return _safe(text_value[:220] + "…")

    return _safe(text_value)


def _percent(value: Any) -> str:
    try:
        return f"{float(value):.0f}%"
    except Exception:
        return "—"


def _list_items(items: Iterable[Any]) -> str:
    values = [f"<li>{_safe(item)}</li>" for item in items or []]
    return "\n".join(values) if values else "<li>None reported</li>"


def _kv_rows(mapping: Dict[str, Any], *, skip_keys: Optional[set[str]] = None) -> str:
    if not mapping:
        return '<tr><td colspan="2">No data available</td></tr>'

    skip_keys = skip_keys or set()
    rows = []

    for key, value in mapping.items():
        key_text = str(key)
        if key_text in skip_keys:
            continue
        rows.append(
            f"<tr><th>{_safe(_label(key_text))}</th><td>{_format_report_value(key_text, value)}</td></tr>"
        )

    return "\n".join(rows) if rows else '<tr><td colspan="2">No data available</td></tr>'


def _category_cards(categories: Dict[str, Any]) -> str:
    if not categories:
        return '<div class="muted">No category scoring available.</div>'

    cards = []
    for name, data in categories.items():
        if not isinstance(data, dict):
            data = {"value": data}
        score = data.get("score")
        score_label = _percent(float(score) * 100) if isinstance(score, (int, float)) and score <= 1 else _percent(score)
        cards.append(
            f"""
            <div class="category-card">
              <div class="category-title">{_safe(_label(name))}</div>
              <div class="category-score">{score_label}</div>
              <div class="category-status">{_safe(_label(data.get("status")))}</div>
            </div>
            """
        )
    return "\n".join(cards)


def _extract_text_header(payload: Dict[str, Any]) -> str:
    direct = payload.get("text_header")
    if isinstance(direct, str) and direct.strip():
        return direct

    headers = payload.get("headers") or {}
    if not isinstance(headers, dict):
        return ""

    for key in (
        "text_header",
        "textual_header",
        "decoded_text_header",
        "segy_text_header",
        "ebcdic_header",
    ):
        value = headers.get(key)
        if isinstance(value, str) and value.strip():
            return value

    return ""


TEXT_HEADER_KEYS = {
    "text_header",
    "textual_header",
    "decoded_text_header",
    "segy_text_header",
    "ebcdic_header",
}


def _truthy_header_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _first_present(mapping: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) not in (None, ""):
            return mapping.get(key)
    return None


def _normalize_header_evidence(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return one report-facing Header Evidence model for all dataset workflows."""
    headers = payload.get("headers") or {}
    if not isinstance(headers, dict):
        headers = {}

    source = payload.get("source") or {}
    if not isinstance(source, dict):
        source = {}

    text_header = _extract_text_header(payload)

    sidecar_paths = (
        headers.get("sidecar_paths")
        or headers.get("sidecars")
        or headers.get("paths")
        or source.get("sidecar_paths")
        or source.get("index_paths")
    )

    binary_value = _first_present(
        headers,
        (
            "binary_header",
            "binary_header_summary",
            "segy_binary_header",
        ),
    )

    trace_value = _first_present(
        headers,
        (
            "trace_header_summary",
            "segy_trace_header_summary",
            "trace_summary",
        ),
    )

    readable = _first_present(
        headers,
        (
            "text_header_readable",
            "textual_header_readable",
            "readable_text_header",
        ),
    )
    if readable is None and text_header:
        readable = True

    replacement_count = _first_present(
        headers,
        (
            "text_header_replacement_char_count",
            "replacement_char_count",
        ),
    )

    replacement_ratio = _first_present(
        headers,
        (
            "text_header_replacement_char_ratio",
            "replacement_char_ratio",
        ),
    )

    normalized = {
        "viewer_metadata_available": _truthy_header_value(
            _first_present(headers, ("viewer_metadata_available", "viewer_metadata"))
        ),
        "text_header_available": bool(text_header) or _truthy_header_value(
            _first_present(headers, ("text_header_available", "textual_header_available"))
        ),
        "text_header_readable": readable,
        "text_header_encoding": _first_present(
            headers,
            (
                "text_header_encoding",
                "textual_header_encoding",
                "selected_encoding",
                "encoding",
            ),
        ),
        "text_header_confidence": _first_present(
            headers,
            (
                "text_header_confidence",
                "textual_header_confidence",
                "confidence",
            ),
        ),
        "text_header_replacement_char_count": replacement_count,
        "text_header_replacement_char_ratio": replacement_ratio,
        "binary_header_available": _truthy_header_value(
            _first_present(headers, ("binary_header_available",))
        ) or bool(binary_value),
        "binary_header_summary": binary_value,
        "trace_header_summary_available": _truthy_header_value(
            _first_present(headers, ("trace_header_summary_available",))
        ) or bool(trace_value),
        "trace_header_summary": trace_value,
        "sidecar_paths": sidecar_paths,
    }

    # Keep rows stable, but omit empty optional detail rows that add noise.
    return {
        key: value
        for key, value in normalized.items()
        if value not in (None, "", {}, [])
    }


def _load_indexed_dataset_payload(dataset_id: str) -> Dict[str, Any]:
    base = DATA_ROOT / "segy_index" / dataset_id
    index = _read_json(base / "segy_index.json")
    binary = _read_json(base / "segy_binary_header.json")
    trace_summary = (
        _read_json(base / "trace_header_summary.json")
        or _read_json(base / "segy_trace_header_summary.json")
    )
    text_decode = _read_json(base / "segy_text_header_decode.json")
    text_header = _read_text(base / "segy_text_header.txt")

    trace_count = index.get("trace_count")
    sample_count = index.get("sample_count")
    inline_count = index.get("inline_count")
    crossline_count = index.get("crossline_count")

    geometry = {
        "shape": index.get("shape"),
        "axis_order": index.get("axis_order"),
        "trace_count": trace_count,
        "sample_count": sample_count,
        "sample_interval_ms": index.get("sample_interval_ms"),
        "inline_range": [index.get("inline_min"), index.get("inline_max")],
        "crossline_range": [index.get("crossline_min"), index.get("crossline_max")],
        "inline_count": inline_count,
        "crossline_count": crossline_count,
        "read_mode": index.get("read_mode", "indexed_segy"),
    }

    categories = {
        "geometry": {"score": 1.0 if index else 0.0, "status": "available" if index else "missing"},
        "headers": {"score": 1.0 if binary or text_header else 0.0, "status": "available" if binary or text_header else "missing"},
        "documents": {"score": 0.0, "status": "not_started"},
        "optimized_cache": {"score": 0.0, "status": index.get("optimized_cache_status", "not_started")},
    }

    return {
        "dataset_id": dataset_id,
        "display_name": index.get("source_path") or dataset_id,
        "dataset_type": "indexed_segy_3d" if index.get("is_3d") else "indexed_segy",
        "metadata_score": indexed_metadata_score(bool(index)),
        "technical_readiness": indexed_technical_readiness(bool(index)),
        "validation": indexed_validation_state(),
        "categories": categories,
        "source": {
            "source_path": index.get("source_path"),
            "status": index.get("status"),
            "optimized_cache_status": index.get("optimized_cache_status", "not_started"),
        },
        "geometry": geometry,
        "headers": {
            "viewer_metadata_available": False,
            "text_header_available": bool(text_header),
            "text_header_readable": bool(text_header),
            "text_header_encoding": text_decode.get("selected_encoding") or text_decode.get("encoding") or "unknown",
            "text_header_confidence": text_decode.get("confidence") or "unknown",
            "binary_header_available": bool(binary),
            "binary_header_summary": binary,
            "trace_header_summary_available": bool(trace_summary),
            "trace_header_summary": trace_summary,
            "sidecar_paths": {
                "index": str(base / "segy_index.json"),
                "text_header": str(base / "segy_text_header.txt"),
                "text_header_decode": str(base / "segy_text_header_decode.json"),
                "binary_header": str(base / "segy_binary_header.json"),
                "trace_header_summary": str(base / "trace_header_summary.json"),
            },
        },
        "text_header": text_header,
        "missing_fields": [
            "optimized_zarr_cache",
            "document_validation",
            "business_metadata",
            "crs_validation",
        ],
        "derived_fields": [
            "shape",
            "inline_range",
            "crossline_range",
            "sample_interval_ms",
            "time_range_ms",
            "trace_count",
        ],
        "warnings": [
            "Indexed SEG-Y metadata is provisional and header-derived.",
            "CRS, business metadata, and document validation have not yet been completed.",
        ],
    }


def _load_volume_payload(volume_id: str) -> Dict[str, Any]:
    """
    Load converted-volume metadata through the existing canonical metadata summary
    service instead of assuming data/zarr/<volume_id>/viewer_metadata.json exists.

    Converted volumes may be registered/resolved by the app even when their
    physical storage path does not match the URL volume_id directly.
    """
    try:
        from app.services.metadata_summary_service import build_metadata_summary

        summary, error = build_metadata_summary(volume_id)
    except Exception as exc:
        summary, error = None, str(exc)

    if error or not summary:
        return {
            "dataset_id": volume_id,
            "display_name": volume_id,
            "dataset_type": "zarr_volume",
            "metadata_score": {
                "overall_percent": 0,
                "status": "metadata_summary_unavailable",
                "label": "Metadata Score Rating",
            },
            "technical_readiness": {
                "percent": 0,
                "status": f"metadata_summary_unavailable: {error or 'unknown_error'}",
            },
            "validation": {
                "status": "unavailable",
                "document_validation": "not_started",
                "crs_validation": "not_started",
            },
            "categories": {
                "identity": {"score": None, "status": "unknown"},
                "geometry": {"score": 0.0, "status": "missing"},
                "headers": {"score": None, "status": "unknown"},
                "documents": {"score": 0.0, "status": "not_started"},
            },
            "source": {"volume_id": volume_id},
            "geometry": {},
            "headers": {},
            "missing_fields": ["metadata_summary"],
            "derived_fields": [],
            "warnings": [f"Metadata summary service could not resolve this converted volume: {error or 'unknown error'}"],
        }

    quality = summary.get("metadata_quality") or {}
    completeness = quality.get("completeness") or {}
    evidence_strength = quality.get("evidence_strength") or {}
    consistency = quality.get("consistency") or {}
    metadata_status = quality.get("metadata_status") or {}

    categories = completeness.get("categories") or {}
    if not isinstance(categories, dict) or not categories:
        categories = {
            "identity": {"score": None, "status": "available" if summary.get("display_name") else "unknown"},
            "geometry": {"score": None, "status": "available" if summary.get("shape") or summary.get("geometry") else "unknown"},
            "headers": {"score": None, "status": "unknown"},
            "documents": {"score": 0.0, "status": "not_started"},
        }

    score_percent = (
        completeness.get("percent")
        or completeness.get("overall_percent")
        or quality.get("overall_percent")
        or summary.get("metadata_score")
        or 0
    )

    geometry = summary.get("geometry") or {}
    if not geometry:
        geometry = {
            "shape": summary.get("shape"),
            "axis_order": summary.get("axis_order"),
            "sample_rate": summary.get("sample_rate"),
            "sample_interval_ms": summary.get("sample_interval_ms"),
            "trace_count": summary.get("trace_count"),
            "is_3d": summary.get("is_3d"),
            "dataset_type": summary.get("dataset_type"),
        }

    source = summary.get("source") or {}
    if not source:
        source = {
            "volume_id": volume_id,
            "source_file": summary.get("source_file"),
            "source_path": summary.get("source_path"),
            "zarr_path": summary.get("zarr_path"),
        }

    validation_summary = metadata_status.get("summary") or quality.get("summary") or ""

    return {
        "dataset_id": volume_id,
        "display_name": summary.get("display_name") or summary.get("name") or volume_id,
        "dataset_type": summary.get("dataset_type") or "zarr_volume",
        "metadata_score": {
            "overall_percent": score_percent,
            "status": completeness.get("status") or metadata_status.get("status") or "provisional",
            "label": "Metadata Score Rating",
        },
        "technical_readiness": {
            "percent": 100,
            "status": "converted_volume_resolved",
        },
        "validation": {
            "status": metadata_status.get("status") or "provisional",
            "summary": validation_summary,
            "evidence_strength": evidence_strength.get("status"),
            "consistency": consistency.get("status"),
            "document_validation": "not_started",
            "crs_validation": "not_started",
        },
        "categories": categories,
        "source": source,
        "geometry": geometry,
        "headers": summary.get("headers") or {},
        "missing_fields": completeness.get("missing_fields") or [],
        "derived_fields": completeness.get("derived_fields") or [],
        "warnings": quality.get("warnings") or [],
    }


def render_indexed_dataset_metadata_score_report(dataset_id: str) -> str:
    return render_metadata_score_report(_load_indexed_dataset_payload(dataset_id))


def render_volume_metadata_score_report(volume_id: str) -> str:
    return render_metadata_score_report(_load_volume_payload(volume_id))


def render_metadata_score_report(payload: Dict[str, Any]) -> str:
    score = payload.get("metadata_score", {}) or {}
    readiness = payload.get("technical_readiness", {}) or {}
    validation = payload.get("validation", {}) or {}

    css_href = "/api/report-assets/metadata_score_report.css?v=e5i"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Metadata Score Report</title>
  <link rel="stylesheet" href="{css_href}">
</head>
<body>
  <main class="report">
    <header class="hero">
      <div>
        <div class="eyebrow">Seismic Viewer</div>
        <h1>Metadata Score Report</h1>
        <p>{_safe(payload.get("display_name"))}</p>
      </div>
      <div class="score-box">
        <div class="score-label">{_safe(score.get("label", "Metadata Score Rating"))}</div>
        <div class="score-value">{_percent(score.get("overall_percent"))}</div>
        <div class="score-status">{_safe(score.get("status"))}</div>
      </div>
    </header>

    <section class="grid two">
      <div class="panel">
        <h2>Preview Status</h2>
        <p class="status-line">{_safe(_label(readiness.get("status")))}</p>
        <p class="muted">Indicates whether the dataset is currently usable for viewer preview.</p>
      </div>
      <div class="panel">
        <h2>Validation State</h2>
        <table>
          {_kv_rows(validation)}
        </table>
      </div>
    </section>

    <section class="panel">
      <h2>Category Status</h2>
      <div class="category-grid">
        {_category_cards(payload.get("categories", {}) or {})}
      </div>
    </section>

    <section class="grid two">
      <div class="panel">
        <h2>Dataset Identity</h2>
        <table>
          {_kv_rows({
            "dataset_id": payload.get("dataset_id"),
            "dataset_type": payload.get("dataset_type"),
            "display_name": payload.get("display_name"),
          })}
        </table>
      </div>
      <div class="panel">
        <h2>Source</h2>
        <table>
          {_kv_rows(payload.get("source", {}) or {})}
        </table>
      </div>
    </section>

    <section class="panel">
      <h2>Geometry</h2>
      <table>
        {_kv_rows(payload.get("geometry", {}) or {})}
      </table>
    </section>

    <section class="panel">
      <h2>Header Evidence</h2>
      <table>
        {_kv_rows(_normalize_header_evidence(payload), skip_keys=TEXT_HEADER_KEYS)}
      </table>
    </section>

    <section class="grid two">
      <div class="panel">
        <h2>Missing Fields</h2>
        <ul>{_list_items(payload.get("missing_fields", []) or [])}</ul>
      </div>
      <div class="panel">
        <h2>Derived Fields</h2>
        <ul>{_list_items(payload.get("derived_fields", []) or [])}</ul>
      </div>
    </section>

    <section class="panel">
      <h2>Warnings</h2>
      <ul>{_list_items(payload.get("warnings", []) or [])}</ul>
    </section>

    {"<section class='panel'><h2>Text Header Preview</h2><pre>" + _safe(_extract_text_header(payload)) + "</pre></section>" if _extract_text_header(payload) else ""}

  </main>
</body>
</html>"""
