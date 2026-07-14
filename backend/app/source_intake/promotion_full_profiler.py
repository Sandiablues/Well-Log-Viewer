"""One-shot deterministic profiler for one real WSI -> MWD promotion request.

The profiler is activated only when:
    WLV_PROFILE_NEXT_WSI_MWD_PROMOTION=1

It profiles:
1. The full FastAPI route handler, including request handling and response serialization.
2. The synchronous Source Intake -> MWD promotion operation in its worker thread.

The two cProfile streams are merged into one report.
"""

from __future__ import annotations

import asyncio
import contextvars
import cProfile
import gc
import hashlib
import json
import os
import pstats
import resource
import shutil
import subprocess
import threading
import time
import traceback
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import Request
from fastapi.routing import APIRoute


_PROFILE_PATH = "/api/wlv/source-intake/register"
_PROFILE_ENV = "WLV_PROFILE_NEXT_WSI_MWD_PROMOTION"
_PROFILE_ONCE_LOCK = threading.Lock()
_PROFILE_CONSUMED = False
_SESSION_VAR: contextvars.ContextVar["ProfileSession | None"] = contextvars.ContextVar(
    "wlv_wsi_mwd_profile_session",
    default=None,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json(v) for v in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _safe_json(model_dump(mode="json"))
        except TypeError:
            return _safe_json(model_dump())
    return repr(value)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(_safe_json(value), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _project_root() -> Path:
    # .../backend/app/source_intake/promotion_full_profiler.py -> project root
    return Path(__file__).resolve().parents[3]


def _backend_root() -> Path:
    return _project_root() / "backend"


def _downloads_root() -> Path:
    return Path.home() / "Downloads"


def _run_command(args: list[str], cwd: Path) -> str:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        return (
            "$ " + " ".join(args) + "\n"
            + completed.stdout
            + ("\nSTDERR\n" + completed.stderr if completed.stderr else "")
        )
    except Exception as exc:
        return "$ " + " ".join(args) + f"\nERROR: {exc}\n"


def _process_metrics() -> dict[str, Any]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    metrics: dict[str, Any] = {
        "timestamp": _utc_now(),
        "wall_monotonic": time.perf_counter(),
        "process_cpu_seconds": time.process_time(),
        "thread_count": threading.active_count(),
        "gc_counts": list(gc.get_count()),
        "ru_utime": usage.ru_utime,
        "ru_stime": usage.ru_stime,
        "ru_maxrss": usage.ru_maxrss,
        "ru_inblock": usage.ru_inblock,
        "ru_oublock": usage.ru_oublock,
        "ru_nvcsw": usage.ru_nvcsw,
        "ru_nivcsw": usage.ru_nivcsw,
    }
    try:
        import psutil  # type: ignore

        process = psutil.Process(os.getpid())
        memory = process.memory_info()
        io = process.io_counters()
        metrics.update(
            {
                "rss_bytes": memory.rss,
                "vms_bytes": memory.vms,
                "num_threads": process.num_threads(),
                "cpu_percent_instant": process.cpu_percent(interval=None),
                "io_read_count": getattr(io, "read_count", None),
                "io_write_count": getattr(io, "write_count", None),
                "io_read_bytes": getattr(io, "read_bytes", None),
                "io_write_bytes": getattr(io, "write_bytes", None),
            }
        )
    except Exception:
        metrics["psutil_available"] = False
    return metrics


def _profile_rows(stats: pstats.Stats) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, values in stats.stats.items():
        cc, nc, tt, ct, _callers = values
        filename, line, function = key
        rows.append(
            {
                "filename": filename,
                "line": line,
                "function": function,
                "primitive_calls": cc,
                "calls": nc,
                "self_time": tt,
                "cumulative_time": ct,
            }
        )
    return rows


def _format_rows(rows: list[dict[str, Any]], sort_key: str, limit: int = 100) -> str:
    ordered = sorted(rows, key=lambda row: row[sort_key], reverse=True)[:limit]
    lines = [
        f"{'Rank':>4} {'Calls':>10} {'Self(s)':>12} {'Cum(s)':>12} Function",
        "-" * 140,
    ]
    for index, row in enumerate(ordered, start=1):
        label = f"{row['filename']}:{row['line']}({row['function']})"
        lines.append(
            f"{index:>4} {row['calls']:>10} "
            f"{row['self_time']:>12.6f} {row['cumulative_time']:>12.6f} {label}"
        )
    return "\n".join(lines) + "\n"


def _architectural_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    patterns = {
        "runtime_snapshot_build": ("runtime_resolver.py", "build_snapshot"),
        "runtime_record_list": ("runtime_resolver.py", "list_runtime_records"),
        "runtime_alias_enrichment_list": (
            "runtime_resolver.py",
            "list_approved_alias_enrichments",
        ),
        "runtime_classify_curve": (
            "runtime_classification_service.py",
            "classify_curve",
        ),
        "runtime_classify_curves": (
            "runtime_classification_service.py",
            "classify_curves",
        ),
        "runtime_classify_one": (
            "runtime_classification_service.py",
            "_classify_one",
        ),
        "contextual_resolution": ("contextual", "resolve"),
        "orchestration": ("classification_orchestration", ""),
        "shadow_observer": ("live_shadow_observer.py", ""),
        "inventory_list_records": ("repository", "list_records"),
        "inventory_upsert": ("inventory", "upsert"),
        "json_decode": ("json/decoder.py", ""),
        "json_encode": ("json/encoder.py", ""),
        "uuid_generation": ("uuid", ""),
        "hashlib": ("hashlib", ""),
    }

    result: dict[str, Any] = {}
    for name, (file_fragment, function_fragment) in patterns.items():
        matched = [
            row
            for row in rows
            if file_fragment.lower() in row["filename"].lower()
            and (
                not function_fragment
                or function_fragment.lower() in row["function"].lower()
            )
        ]
        result[name] = {
            "calls": sum(int(row["calls"]) for row in matched),
            "self_time": round(sum(float(row["self_time"]) for row in matched), 6),
            "cumulative_time": round(
                sum(float(row["cumulative_time"]) for row in matched),
                6,
            ),
            "matched_functions": [
                {
                    "file": row["filename"],
                    "line": row["line"],
                    "function": row["function"],
                    "calls": row["calls"],
                    "self_time": row["self_time"],
                    "cumulative_time": row["cumulative_time"],
                }
                for row in sorted(
                    matched,
                    key=lambda item: item["cumulative_time"],
                    reverse=True,
                )[:20]
            ],
        }
    return result


def _source_hashes(project: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    roots = [
        project / "backend/app",
        project / "backend/tests/source_intake",
        project / "backend/tests/inventory",
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            try:
                hashes[str(path.relative_to(project))] = _sha256(path)
            except Exception:
                continue
    return hashes


def _find_candidate(snapshot: Any, candidate_id: str) -> Any | None:
    for candidate in getattr(snapshot, "candidates", []) or []:
        if getattr(candidate, "source_file_id", None) == candidate_id:
            return candidate
    return None


def _candidate_summary(candidate: Any | None) -> dict[str, Any]:
    if candidate is None:
        return {"found": False}
    parsed = getattr(candidate, "parsed_metadata", None)
    curve_headers = getattr(parsed, "curve_headers", []) if parsed is not None else []
    return {
        "found": True,
        "candidate_id": getattr(candidate, "source_file_id", None),
        "occurrence_id": getattr(candidate, "occurrence_id", None),
        "file_name": getattr(candidate, "file_name", None),
        "checksum": getattr(candidate, "checksum", None),
        "content_fingerprint": getattr(candidate, "content_fingerprint", None),
        "detected_file_type": _safe_json(getattr(candidate, "detected_file_type", None)),
        "parsed_curve_count": len(curve_headers or []),
        "registration_status": getattr(candidate, "registration_status", None),
        "managed_well_id": getattr(candidate, "managed_well_id", None),
        "registered_curve_count": getattr(candidate, "registered_curve_count", None),
        "registered_product_count": getattr(candidate, "registered_product_count", None),
    }


def _record_id(record: Any) -> str | None:
    return (
        getattr(record, "managed_well_id", None)
        or getattr(record, "managed_well_uid", None)
        or getattr(record, "well_id", None)
    )


def _record_curve_manifest(record: Any | None) -> list[dict[str, Any]]:
    if record is None:
        return []
    rows: list[dict[str, Any]] = []
    for group in getattr(record, "product_groups", []) or []:
        for item in getattr(group, "items", []) or []:
            rows.append(
                {
                    "group_key": getattr(group, "group_key", None),
                    "group_label": getattr(group, "group_label", None),
                    "mnemonic": (
                        getattr(item, "mnemonic", None)
                        or getattr(item, "source_mnemonic", None)
                        or getattr(item, "name", None)
                    ),
                    "source_curve_index": getattr(item, "source_curve_index", None),
                    "curve_family": getattr(item, "curve_family", None),
                    "curve_family_key": getattr(item, "curve_family_key", None),
                    "measurement_domain_key": getattr(item, "measurement_domain_key", None),
                    "measurement_domain_label": getattr(item, "measurement_domain_label", None),
                    "destination_key": getattr(item, "destination_key", None),
                    "destination_owner": getattr(item, "destination_owner", None),
                    "display_in_wdv": getattr(item, "display_in_wdv", None),
                    "classification_provenance": (
                        getattr(item, "classification_provenance", None)
                        or getattr(item, "classification_source", None)
                    ),
                    "classification_confidence": getattr(item, "classification_confidence", None),
                    "managed_curve_uid": getattr(item, "managed_curve_uid", None),
                }
            )
    return rows


@dataclass
class ProfileSession:
    session_id: str
    output_dir: Path
    zip_path: Path
    started_at: str = field(default_factory=_utc_now)
    wall_started: float = field(default_factory=time.perf_counter)
    cpu_started: float = field(default_factory=time.process_time)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    inner_profile_path: Path | None = None
    outer_profile_path: Path | None = None
    request_model: Any = None
    response_model: Any = None
    candidate_id: str | None = None
    candidate_checksum: str | None = None
    managed_well_id: str | None = None
    precondition_status: str = "unknown"
    precondition_messages: list[str] = field(default_factory=list)
    exception_text: str | None = None

    def event(self, name: str, **payload: Any) -> None:
        self.timeline.append(
            {
                "event": name,
                "timestamp": _utc_now(),
                "elapsed_ms": round((time.perf_counter() - self.wall_started) * 1000.0, 3),
                **_safe_json(payload),
            }
        )


def _create_session(request: Request) -> ProfileSession:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = _downloads_root() / f"wlv_wsi_mwd_promotion_full_profile_{stamp}"
    zip_path = Path(str(output_dir) + ".zip")
    output_dir.mkdir(parents=True, exist_ok=False)
    session = ProfileSession(
        session_id=stamp,
        output_dir=output_dir,
        zip_path=zip_path,
    )
    session.event(
        "request_entered",
        method=request.method,
        path=request.url.path,
        query=str(request.url.query),
    )
    _write_json(output_dir / "process_metrics_before_request.json", _process_metrics())
    return session


def _write_preflight(session: ProfileSession, request_model: Any, service: Any, inventory_service: Any) -> None:
    session.request_model = request_model
    _write_json(session.output_dir / "request.json", request_model)

    candidate_ids = list(getattr(request_model, "candidate_ids", []) or [])
    if len(candidate_ids) != 1:
        session.precondition_status = "FAIL"
        session.precondition_messages.append(
            f"Expected exactly one candidate_id; found {len(candidate_ids)}."
        )
        return

    candidate_id = candidate_ids[0]
    session.candidate_id = candidate_id

    snapshot = service._load_snapshot()
    candidate = _find_candidate(snapshot, candidate_id)
    summary = _candidate_summary(candidate)
    _write_json(session.output_dir / "pre_promotion_candidate.json", summary)

    session.candidate_checksum = summary.get("checksum")
    parsed_curve_count = summary.get("parsed_curve_count")
    if parsed_curve_count != 67:
        session.precondition_messages.append(
            f"Expected 67 parsed curves for the controlled F 21-31 test; found {parsed_curve_count}."
        )

    records = inventory_service.repository.list_records()
    _write_json(
        session.output_dir / "pre_promotion_managed_inventory.json",
        [_safe_json(record) for record in records],
    )

    session.precondition_status = (
        "PASS"
        if len(candidate_ids) == 1 and parsed_curve_count == 67
        else "FAIL"
    )


def _write_post_state(session: ProfileSession, service: Any, inventory_service: Any) -> None:
    snapshot = service._load_snapshot()
    candidate = _find_candidate(snapshot, session.candidate_id or "")
    candidate_summary = _candidate_summary(candidate)
    _write_json(session.output_dir / "post_promotion_candidate.json", candidate_summary)

    session.managed_well_id = candidate_summary.get("managed_well_id")

    records = inventory_service.repository.list_records()
    _write_json(
        session.output_dir / "post_promotion_managed_inventory.json",
        [_safe_json(record) for record in records],
    )

    matched = None
    if session.managed_well_id:
        for record in records:
            if _record_id(record) == session.managed_well_id:
                matched = record
                break

    manifest = _record_curve_manifest(matched)
    _write_json(session.output_dir / "semantic_curve_manifest.json", manifest)

    semantic_lines = [
        f"PRECONDITION: {session.precondition_status}",
        *[f"PRECONDITION NOTE: {message}" for message in session.precondition_messages],
        f"CANDIDATE ID: {session.candidate_id}",
        f"SOURCE CHECKSUM: {session.candidate_checksum}",
        f"MANAGED WELL ID: {session.managed_well_id}",
        f"RESULT CURVE COUNT: {len(manifest)}",
        f"EXPECTED CURVE COUNT: 67",
        f"SEMANTIC VALIDATION: {'PASS' if len(manifest) == 67 else 'FAIL'}",
    ]
    (session.output_dir / "semantic_invariant_report.txt").write_text(
        "\n".join(semantic_lines) + "\n",
        encoding="utf-8",
    )


def profile_promotion_endpoint(
    *,
    request_model: Any,
    service: Any,
    inventory_service: Any,
    operation: Callable[[], Any],
) -> Any:
    session = _SESSION_VAR.get()
    if session is None:
        return operation()

    session.event("endpoint_worker_entered")
    _write_preflight(session, request_model, service, inventory_service)
    session.event(
        "preflight_completed",
        precondition=session.precondition_status,
        messages=session.precondition_messages,
    )

    if session.precondition_status != "PASS":
        raise RuntimeError(
            "Definitive promotion profile aborted: controlled test preconditions failed. "
            + " | ".join(session.precondition_messages)
        )

    profiler = cProfile.Profile()
    inner_path = session.output_dir / "profile_endpoint_worker.pstats"
    session.inner_profile_path = inner_path

    _write_json(
        session.output_dir / "process_metrics_before_endpoint.json",
        _process_metrics(),
    )
    session.event("endpoint_profile_started")

    try:
        profiler.enable()
        response = operation()
        profiler.disable()
    except Exception:
        profiler.disable()
        profiler.dump_stats(str(inner_path))
        session.exception_text = traceback.format_exc()
        (session.output_dir / "exception.txt").write_text(
            session.exception_text,
            encoding="utf-8",
        )
        session.event("endpoint_profile_failed")
        raise

    profiler.dump_stats(str(inner_path))
    session.response_model = response
    _write_json(session.output_dir / "response.json", response)
    session.event("endpoint_profile_completed")
    _write_json(
        session.output_dir / "process_metrics_after_endpoint.json",
        _process_metrics(),
    )

    _write_post_state(session, service, inventory_service)
    session.event("post_state_captured")
    return response


def _generate_profile_reports(session: ProfileSession) -> None:
    profile_paths = [
        path
        for path in (session.inner_profile_path, session.outer_profile_path)
        if path is not None and path.exists()
    ]
    if not profile_paths:
        raise RuntimeError("No cProfile data was produced.")

    merged_path = session.output_dir / "profile.pstats"
    stats = pstats.Stats(str(profile_paths[0]))
    for extra in profile_paths[1:]:
        stats.add(str(extra))
    stats.dump_stats(str(merged_path))

    rows = _profile_rows(stats)
    _write_json(session.output_dir / "profile_rows.json", rows)

    (session.output_dir / "profile_by_cumulative.txt").write_text(
        _format_rows(rows, "cumulative_time", limit=200),
        encoding="utf-8",
    )
    (session.output_dir / "profile_by_self_time.txt").write_text(
        _format_rows(rows, "self_time", limit=200),
        encoding="utf-8",
    )
    (session.output_dir / "profile_by_call_count.txt").write_text(
        _format_rows(rows, "calls", limit=200),
        encoding="utf-8",
    )

    with (session.output_dir / "profile_callers.txt").open("w", encoding="utf-8") as handle:
        caller_stats = pstats.Stats(str(merged_path), stream=handle)
        caller_stats.sort_stats("cumulative")
        caller_stats.print_callers()

    with (session.output_dir / "profile_callees.txt").open("w", encoding="utf-8") as handle:
        callee_stats = pstats.Stats(str(merged_path), stream=handle)
        callee_stats.sort_stats("cumulative")
        callee_stats.print_callees()

    architecture = _architectural_counts(rows)
    _write_json(
        session.output_dir / "architectural_call_counts.json",
        architecture,
    )

    top_cum = sorted(rows, key=lambda row: row["cumulative_time"], reverse=True)[:10]
    top_self = sorted(rows, key=lambda row: row["self_time"], reverse=True)[:10]
    top_calls = sorted(rows, key=lambda row: row["calls"], reverse=True)[:10]

    wall_seconds = time.perf_counter() - session.wall_started
    cpu_seconds = time.process_time() - session.cpu_started

    def one_line(row: dict[str, Any]) -> str:
        return (
            f"{row['filename']}:{row['line']}({row['function']}) "
            f"calls={row['calls']} self={row['self_time']:.6f}s "
            f"cum={row['cumulative_time']:.6f}s"
        )

    summary = [
        "WSI -> MWD DEFINITIVE PROMOTION PROFILE",
        "",
        f"TOTAL WALL TIME: {wall_seconds:.6f} s",
        f"TOTAL PROCESS CPU TIME: {cpu_seconds:.6f} s",
        f"PRECONDITION: {session.precondition_status}",
        f"SEMANTIC RESULT: {'PASS' if len(_read_json_list(session.output_dir / 'semantic_curve_manifest.json')) == 67 else 'FAIL'}",
        "",
        "TOP 10 SELF-TIME FUNCTIONS:",
        *[f"{i+1}. {one_line(row)}" for i, row in enumerate(top_self)],
        "",
        "TOP 10 CUMULATIVE-TIME FUNCTIONS:",
        *[f"{i+1}. {one_line(row)}" for i, row in enumerate(top_cum)],
        "",
        "TOP 10 CALL COUNTS:",
        *[f"{i+1}. {one_line(row)}" for i, row in enumerate(top_calls)],
        "",
        "CONFIRMED HIGHEST SELF-TIME FUNCTION:",
        one_line(top_self[0]) if top_self else "No profile rows.",
        "",
        "CONFIRMED HIGHEST CUMULATIVE-TIME FUNCTION:",
        one_line(top_cum[0]) if top_cum else "No profile rows.",
        "",
        "NOTE:",
        "This summary is generated mechanically from the merged deterministic profile.",
        "Use profile_callers.txt and profile_callees.txt to attribute the expensive function to its exact call path.",
    ]
    (session.output_dir / "ANALYSIS_SUMMARY.txt").write_text(
        "\n".join(summary) + "\n",
        encoding="utf-8",
    )


def _read_json_list(path: Path) -> list[Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _write_environment(session: ProfileSession) -> None:
    project = _project_root()
    env = {
        key: value
        for key, value in sorted(os.environ.items())
        if key.startswith("WLV_")
        or "CLASSIFICATION" in key.upper()
        or "CUTOVER" in key.upper()
    }
    _write_json(session.output_dir / "environment.json", env)

    (session.output_dir / "git_head.txt").write_text(
        _run_command(["git", "rev-parse", "HEAD"], project),
        encoding="utf-8",
    )
    (session.output_dir / "git_branch.txt").write_text(
        _run_command(["git", "branch", "--show-current"], project),
        encoding="utf-8",
    )
    (session.output_dir / "git_status.txt").write_text(
        _run_command(["git", "status", "--short"], project),
        encoding="utf-8",
    )
    _write_json(
        session.output_dir / "source_hashes.json",
        _source_hashes(project),
    )


def _finalize(session: ProfileSession) -> None:
    try:
        session.event("response_serialization_completed")
        _write_json(
            session.output_dir / "process_metrics_after_request.json",
            _process_metrics(),
        )
        _write_environment(session)
        _write_json(session.output_dir / "request_timeline.json", session.timeline)
        _generate_profile_reports(session)

        manifest = {
            "profile_contract": "wlv-wsi-mwd-definitive-request-profile-v1",
            "session_id": session.session_id,
            "started_at": session.started_at,
            "completed_at": _utc_now(),
            "request_path": _PROFILE_PATH,
            "candidate_id": session.candidate_id,
            "source_checksum": session.candidate_checksum,
            "managed_well_id": session.managed_well_id,
            "precondition_status": session.precondition_status,
            "precondition_messages": session.precondition_messages,
            "exception": session.exception_text,
            "output_directory": str(session.output_dir),
            "zip_path": str(session.zip_path),
        }
        _write_json(session.output_dir / "manifest.json", manifest)

        if session.zip_path.exists():
            session.zip_path.unlink()
        with zipfile.ZipFile(
            session.zip_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for path in sorted(session.output_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(session.output_dir.parent))

        (session.output_dir / "EVIDENCE_READY.txt").write_text(
            f"Evidence ZIP: {session.zip_path}\n",
            encoding="utf-8",
        )
    except Exception:
        failure = traceback.format_exc()
        (session.output_dir / "FINALIZATION_ERROR.txt").write_text(
            failure,
            encoding="utf-8",
        )


class PromotionProfilingRoute(APIRoute):
    """Profile exactly one /register request when the one-shot env flag is enabled."""

    def get_route_handler(self):
        original_route_handler = super().get_route_handler()

        async def profiled_route_handler(request: Request):
            global _PROFILE_CONSUMED

            if (
                request.url.path != _PROFILE_PATH
                or os.getenv(_PROFILE_ENV, "").strip() != "1"
            ):
                return await original_route_handler(request)

            with _PROFILE_ONCE_LOCK:
                if _PROFILE_CONSUMED:
                    return await original_route_handler(request)
                _PROFILE_CONSUMED = True

            session = _create_session(request)
            token = _SESSION_VAR.set(session)
            outer_profiler = cProfile.Profile()
            outer_path = session.output_dir / "profile_fastapi_request.pstats"
            session.outer_profile_path = outer_path

            try:
                session.event("fastapi_request_profile_started")
                outer_profiler.enable()
                response = await original_route_handler(request)
                outer_profiler.disable()
                outer_profiler.dump_stats(str(outer_path))
                session.event("fastapi_request_profile_completed")
                return response
            except Exception:
                outer_profiler.disable()
                outer_profiler.dump_stats(str(outer_path))
                session.exception_text = traceback.format_exc()
                (session.output_dir / "exception.txt").write_text(
                    session.exception_text,
                    encoding="utf-8",
                )
                session.event("fastapi_request_profile_failed")
                raise
            finally:
                _SESSION_VAR.reset(token)
                # Finalization is deliberately outside cProfile so report generation
                # does not contaminate the measured request profile.
                await asyncio.to_thread(_finalize, session)

        return profiled_route_handler
