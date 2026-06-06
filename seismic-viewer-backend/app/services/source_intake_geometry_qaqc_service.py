from __future__ import annotations

import json
import math
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import segyio

from app.services.package_registry_service import list_segy_files
from app.services.repository_registry_service import get_repository


INLINE_CANDIDATE_BYTES = [9, 189, 181, 5, 17]
CROSSLINE_CANDIDATE_BYTES = [21, 193, 185, 37, 41]
GENERAL_HEADER_BYTES = sorted(set(INLINE_CANDIDATE_BYTES + CROSSLINE_CANDIDATE_BYTES + [73, 77, 81, 85, 197, 201]))
DEFAULT_SAMPLE_LIMIT = 20000


@dataclass(frozen=True)
class CandidateRef:
    candidate_id: str
    row: dict[str, Any]
    path: Path


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _project_root() -> Path:
    return _backend_root().parent


def _report_dir() -> Path:
    path = _backend_root() / "data" / "source_intake_qaqc"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _report_path(candidate_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(candidate_id))
    return _report_dir() / f"{safe}__geometry_qaqc.json"


def _segysak_executable() -> Path:
    return _project_root() / "third_party" / "segysak_sandbox" / "venv" / "bin" / "segysak"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _candidate_id_for_row(row: dict[str, Any]) -> str:
    return _clean_text(row.get("source_segy_file_id") or row.get("segy_file_id") or row.get("candidate_id"))


def _resolve_candidate(candidate_id: str) -> CandidateRef:
    clean_id = _clean_text(candidate_id)
    if not clean_id:
        raise FileNotFoundError("Missing Source Intake candidate id.")

    for row in list_segy_files(repository_id=None):
        row_id = _candidate_id_for_row(row)
        if clean_id != row_id:
            continue

        path = _resolve_candidate_path(row)
        if not path:
            raise FileNotFoundError(f"Could not resolve source path for Source Intake candidate: {clean_id}")
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Source SEG-Y file does not exist: {path}")
        if path.suffix.lower() not in {".sgy", ".segy"}:
            raise ValueError(f"Source path is not a SEG-Y file: {path}")

        return CandidateRef(candidate_id=clean_id, row=dict(row), path=path)

    raise FileNotFoundError(f"Source Intake candidate not found: {clean_id}")


def _resolve_candidate_path(row: dict[str, Any]) -> Path | None:
    for key in ("source_path", "absolute_path", "path", "file_path"):
        raw = row.get(key)
        if raw:
            return Path(str(raw)).expanduser()

    repo_id = row.get("repository_id")
    rel = row.get("relative_path") or row.get("source_relative_path")
    if repo_id and rel:
        repo = get_repository(str(repo_id))
        root_path = repo.get("root_path") if repo else None
        if root_path:
            return Path(str(root_path)).expanduser() / str(rel)
    return None


def load_geometry_qaqc_report(candidate_id: str) -> dict[str, Any] | None:
    path = _report_path(candidate_id)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _sample_header_values(f: Any, byte: int, sample_limit: int = DEFAULT_SAMPLE_LIMIT) -> list[int]:
    trace_count = int(f.tracecount)
    limit = max(1, min(trace_count, int(sample_limit)))
    step = max(1, trace_count // limit)
    values: list[int] = []
    for idx in range(0, trace_count, step):
        try:
            values.append(int(f.header[idx][byte]))
        except Exception:
            pass
        if len(values) >= limit:
            break
    return values


def _basic_stats(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"available": False, "unique": 0, "min": None, "max": None, "range": None, "first10": []}
    mn = min(values)
    mx = max(values)
    return {
        "available": True,
        "unique": len(set(values)),
        "min": mn,
        "max": mx,
        "range": mx - mn,
        "first10": values[:10],
    }


def _coordinate_like(stats: dict[str, Any]) -> bool:
    if not stats.get("available"):
        return False
    mn = abs(int(stats.get("min") or 0))
    mx = abs(int(stats.get("max") or 0))
    span = int(stats.get("range") or 0)
    unique = int(stats.get("unique") or 0)
    return max(mn, mx) >= 100000 or (span >= 10000 and unique >= 1000)


def _score_pair(
    *,
    inline_byte: int,
    crossline_byte: int,
    inline_values: list[int],
    crossline_values: list[int],
    trace_count: int,
    sample_count: int,
) -> dict[str, Any]:
    inline_stats = _basic_stats(inline_values)
    crossline_stats = _basic_stats(crossline_values)
    pairs = list(zip(inline_values, crossline_values))
    pair_unique_sample = len(set(pairs))
    inline_unique = int(inline_stats.get("unique") or 0)
    crossline_unique = int(crossline_stats.get("unique") or 0)
    expected_trace_positions = inline_unique * crossline_unique
    occupancy_estimate = (trace_count / expected_trace_positions) if expected_trace_positions else 0.0
    dense_sample_count = expected_trace_positions * sample_count
    estimated_dense_gb_float = dense_sample_count * 4 / (1024 ** 3)
    estimated_dense_gb = round(estimated_dense_gb_float, 3)

    warnings: list[str] = []
    score = 0.0

    if inline_unique > 1 and crossline_unique > 1:
        score += 0.20
    else:
        warnings.append("one_or_both_candidate_headers_do_not_vary")

    if inline_unique >= 10 and crossline_unique >= 10:
        score += 0.15

    if pair_unique_sample > max(inline_unique, crossline_unique):
        score += 0.15
    else:
        warnings.append("candidate_pair_does_not_form_grid_like_pairs_in_sample")

    if expected_trace_positions:
        ratio = trace_count / expected_trace_positions
        if 0.50 <= ratio <= 1.60:
            score += 0.30
        elif 0.20 <= ratio <= 3.00:
            score += 0.15
            warnings.append("grid_occupancy_is_marginal")
        else:
            warnings.append("grid_occupancy_is_implausible")

    inline_coord = _coordinate_like(inline_stats)
    crossline_coord = _coordinate_like(crossline_stats)
    if inline_coord or crossline_coord:
        score -= 0.35
        warnings.append("candidate_headers_look_coordinate_like")
    else:
        score += 0.15

    if expected_trace_positions > trace_count * 20:
        score -= 0.35
        warnings.append("candidate_implies_absurd_sparse_grid")
    if estimated_dense_gb_float > 10_000:
        score -= 0.20
        warnings.append("candidate_implies_extreme_dense_cube_size")

    score = max(0.0, min(1.0, score))
    confidence = "high" if score >= 0.70 else "medium" if score >= 0.45 else "low"

    return {
        "inline_byte": inline_byte,
        "crossline_byte": crossline_byte,
        "inline": inline_stats,
        "crossline": crossline_stats,
        "pair_unique_sample": pair_unique_sample,
        "expected_trace_positions": expected_trace_positions,
        "occupancy_estimate": occupancy_estimate,
        "estimated_dense_gb_float32": estimated_dense_gb,
        "score": round(score, 4),
        "confidence": confidence,
        "warnings": warnings,
        "accepted": score >= 0.70 and "candidate_implies_absurd_sparse_grid" not in warnings,
    }


def _run_segysak_scan(path: Path, timeout_seconds: int = 45) -> dict[str, Any]:
    exe = _segysak_executable()
    if not exe.exists() or not exe.is_file():
        return {
            "available": False,
            "ran": False,
            "ok": False,
            "message": "SEGY-SAK sandbox executable is not available.",
        }

    cmd = [str(exe), "--file", str(path), "scan"]
    started = time.monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired as exc:
        return {
            "available": True,
            "ran": True,
            "ok": False,
            "timed_out": True,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "command": cmd,
            "stdout_excerpt": (exc.stdout or "")[:4000],
            "stderr_excerpt": (exc.stderr or f"SEGY-SAK scan timed out after {timeout_seconds} seconds.")[:4000],
        }
    except Exception as exc:
        return {
            "available": True,
            "ran": False,
            "ok": False,
            "message": f"SEGY-SAK scan failed to start: {exc}",
            "command": cmd,
        }

    return {
        "available": True,
        "ran": True,
        "ok": result.returncode == 0,
        "timed_out": False,
        "return_code": result.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "command": cmd,
        "stdout_excerpt": (result.stdout or "")[:8000],
        "stderr_excerpt": (result.stderr or "")[:4000],
    }


def run_geometry_qaqc(candidate_id: str, *, include_segysak: bool = True) -> dict[str, Any]:
    ref = _resolve_candidate(candidate_id)
    generated_at = datetime.now(timezone.utc).isoformat()

    with segyio.open(str(ref.path), "r", ignore_geometry=True) as f:
        trace_count = int(f.tracecount)
        sample_count = len(f.samples)
        sample_min = float(f.samples[0]) if sample_count else None
        sample_max = float(f.samples[-1]) if sample_count else None

        sampled_headers = {byte: _sample_header_values(f, byte) for byte in GENERAL_HEADER_BYTES}
        header_stats = {str(byte): _basic_stats(values) for byte, values in sampled_headers.items()}

        candidates: list[dict[str, Any]] = []
        for inline_byte in INLINE_CANDIDATE_BYTES:
            for crossline_byte in CROSSLINE_CANDIDATE_BYTES:
                candidates.append(
                    _score_pair(
                        inline_byte=inline_byte,
                        crossline_byte=crossline_byte,
                        inline_values=sampled_headers.get(inline_byte, []),
                        crossline_values=sampled_headers.get(crossline_byte, []),
                        trace_count=trace_count,
                        sample_count=sample_count,
                    )
                )

    ranked = sorted(candidates, key=lambda item: float(item.get("score") or 0.0), reverse=True)
    selected = ranked[0] if ranked else None
    rejected = ranked[1:]

    status = "failed"
    summary = "No acceptable 3D geometry candidate was found."
    flags: list[dict[str, Any]] = []

    if selected:
        score = float(selected.get("score") or 0.0)
        warnings = list(selected.get("warnings") or [])
        if score >= 0.70 and "candidate_implies_absurd_sparse_grid" not in warnings:
            status = "passed"
            summary = "Geometry QAQC passed with a plausible 3D inline/crossline candidate."
        elif score >= 0.45:
            status = "review_required"
            summary = "Geometry QAQC found a possible 3D candidate, but review is required before using it as authoritative geometry."
        else:
            status = "review_required"
            summary = "Geometry QAQC rejected the strongest automatic candidate as low confidence."

        for warning in warnings:
            flags.append({"severity": "warning", "code": warning, "message": warning.replace("_", " ").capitalize() + "."})

    segysak = _run_segysak_scan(ref.path) if include_segysak else {"available": False, "ran": False, "ok": False, "message": "SEGY-SAK scan disabled for this run."}

    report = {
        "schema_version": "source_intake.geometry_qaqc.v1",
        "candidate_id": ref.candidate_id,
        "status": status,
        "summary": summary,
        "generated_at": generated_at,
        "source": {
            "path": str(ref.path),
            "filename": ref.path.name,
            "size_bytes": ref.path.stat().st_size,
            "repository_id": ref.row.get("repository_id"),
            "relative_path": ref.row.get("relative_path") or ref.row.get("source_relative_path"),
            "candidate_kind": ref.row.get("candidate_kind"),
            "candidate_role": ref.row.get("candidate_role"),
        },
        "segy": {
            "trace_count": trace_count,
            "sample_count": sample_count,
            "sample_min": sample_min,
            "sample_max": sample_max,
        },
        "selected_candidate": selected,
        "candidate_rankings": ranked,
        "rejected_candidates": rejected,
        "header_stats": header_stats,
        "flags": flags,
        "segysak": segysak,
        "authority": {
            "decision_owner": "backend_geometry_qaqc_service",
            "segysak_role": "optional_read_only_evidence_generator",
            "mutates_source_intake": False,
            "mutates_managed_data": False,
            "gates_build_index": False,
        },
    }

    path = _report_path(ref.candidate_id)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report




def _unique_text(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _range_from_stats(stats: dict[str, Any] | None) -> list[Any] | None:
    if not isinstance(stats, dict) or not stats.get("available"):
        return None
    return [stats.get("min"), stats.get("max")]


def _geometry_contract_from_candidate(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None

    inline = candidate.get("inline") if isinstance(candidate.get("inline"), dict) else {}
    crossline = candidate.get("crossline") if isinstance(candidate.get("crossline"), dict) else {}

    return {
        "inline_byte": candidate.get("inline_byte"),
        "crossline_byte": candidate.get("crossline_byte"),
        "inline_range": _range_from_stats(inline),
        "crossline_range": _range_from_stats(crossline),
        "inline_count": inline.get("unique"),
        "crossline_count": crossline.get("unique"),
        "expected_trace_positions": candidate.get("expected_trace_positions"),
        "occupancy_estimate": candidate.get("occupancy_estimate"),
        "estimated_dense_gb_float32": candidate.get("estimated_dense_gb_float32"),
        "score": candidate.get("score"),
        "confidence": candidate.get("confidence"),
        "warnings": list(candidate.get("warnings") or []),
        "accepted": bool(candidate.get("accepted")),
    }


def normalize_geometry_qaqc_report(report: dict[str, Any] | None, candidate_id: str) -> dict[str, Any]:
    """
    Return the stable public API contract for Source Intake geometry QAQC.

    The persisted report remains evidence-rich and may evolve. This public
    contract gives Build Index gating and the frontend one predictable shape.
    """
    clean_id = _clean_text(candidate_id)

    if not isinstance(report, dict):
        return {
            "schema_version": "source_intake.geometry_qaqc.public.v1",
            "candidate_id": clean_id,
            "status": "not_run",
            "summary": "Geometry QAQC has not been run for this Source Intake candidate.",
            "source_path": None,
            "classification": None,
            "selected_geometry": None,
            "confidence": None,
            "requires_review": True,
            "warnings": [],
            "errors": [],
            "segysak": None,
            "top_candidates": [],
            "rejected_candidates": [],
            "selected_candidate": None,
            "candidate_rankings": [],
            "raw_report": None,
            "authority": {
                "decision_owner": "backend_geometry_qaqc_service",
                "segysak_role": "optional_read_only_evidence_generator",
                "mutates_source_intake": False,
                "mutates_managed_data": False,
                "gates_build_index": False,
            },
        }

    status = _clean_text(report.get("status")) or "unknown"
    source = report.get("source") if isinstance(report.get("source"), dict) else {}
    selected = report.get("selected_candidate") if isinstance(report.get("selected_candidate"), dict) else None
    rankings = report.get("candidate_rankings") if isinstance(report.get("candidate_rankings"), list) else []
    rejected = report.get("rejected_candidates") if isinstance(report.get("rejected_candidates"), list) else []
    flags = report.get("flags") if isinstance(report.get("flags"), list) else []
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []

    selected_geometry = _geometry_contract_from_candidate(selected)
    confidence = _clean_text((selected or {}).get("confidence")) if selected else None

    warning_values: list[Any] = []
    if selected:
        warning_values.extend(selected.get("warnings") or [])
    for flag in flags:
        if isinstance(flag, dict):
            if _clean_text(flag.get("severity")) in {"warning", "error"}:
                warning_values.append(flag.get("code") or flag.get("message"))
        else:
            warning_values.append(flag)
    warnings = _unique_text(warning_values)

    error_values: list[Any] = list(errors)
    for flag in flags:
        if isinstance(flag, dict) and _clean_text(flag.get("severity")) == "error":
            error_values.append(flag.get("code") or flag.get("message"))
    normalized_errors = _unique_text(error_values)

    requires_review = True
    if status == "passed" and confidence == "high" and not normalized_errors:
        requires_review = False

    classification = {
        "candidate_kind": source.get("candidate_kind"),
        "candidate_role": source.get("candidate_role"),
        "geometry_status": status,
    }

    return {
        "schema_version": "source_intake.geometry_qaqc.public.v1",
        "raw_schema_version": report.get("schema_version"),
        "candidate_id": report.get("candidate_id") or clean_id,
        "status": status,
        "summary": report.get("summary"),
        "generated_at": report.get("generated_at"),
        "source_path": source.get("path"),
        "source": source,
        "classification": classification,
        "segy": report.get("segy"),
        "selected_geometry": selected_geometry,
        "confidence": confidence,
        "requires_review": requires_review,
        "warnings": warnings,
        "errors": normalized_errors,
        "segysak": report.get("segysak"),
        "top_candidates": rankings[:6],
        "rejected_candidates": rejected[:12],
        "selected_candidate": selected,
        "candidate_rankings": rankings,
        "header_stats": report.get("header_stats"),
        "flags": flags,
        "authority": report.get("authority") or {
            "decision_owner": "backend_geometry_qaqc_service",
            "segysak_role": "optional_read_only_evidence_generator",
            "mutates_source_intake": False,
            "mutates_managed_data": False,
            "gates_build_index": False,
        },
        "raw_report": report,
    }

def get_geometry_qaqc(candidate_id: str) -> dict[str, Any]:
    clean_id = _clean_text(candidate_id)
    if not clean_id:
        raise FileNotFoundError("Missing Source Intake candidate id.")
    report = load_geometry_qaqc_report(clean_id)
    return normalize_geometry_qaqc_report(report, clean_id)

