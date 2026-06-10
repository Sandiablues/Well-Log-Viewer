"""
SBLT-4: File/path reference validator for SBLT normalized sessions.

Ownership: backend SBLT service.

Responsibilities:
- Resolve raw path strings to absolute paths.
- Expand ~ and resolve relative paths against the session base_path.
- Check existence, is_file, and read permission for SEG-Y paths.
- Check extension for SEG-Y paths (.sgy / .segy accepted, case-insensitive).
- Check existence, is_file, and read permission for supporting document paths.
- Produce structured QAQC flags for all findings.
- Return a per-row path_validation block.

SBLT-4 scope (this file does not):
- Read SEG-Y content, textual/EBCDIC headers, or trace data.
- Classify or extract metadata from supporting documents.
- Scan parent folders or infer dataset structures from directory listings.
- Detect duplicate records.
- Create or modify MSI records or managed representations.
- Touch Source Intake.
- Touch frontend.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

PATH_VALIDATION_VERSION = "sblt.path_validation.v1"

# Accepted SEG-Y file extensions (lower-case, include the dot).
SEGY_EXTENSIONS: frozenset[str] = frozenset({".sgy", ".segy"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _flag(
    severity: str,
    code: str,
    message: str,
    field: str | None = None,
) -> dict[str, Any]:
    """Build a structured SBLT-4 QAQC flag."""
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "field": field,
        "source": "path_validation",
    }


def _resolve_path(
    raw_path: str,
    base_path: str | None,
) -> tuple[Path | None, str | None]:
    """
    Resolve a raw path string to an absolute, normalised Path.

    Steps:
    1. Strip whitespace.
    2. Expand leading ~ to the home directory.
    3. If already absolute, resolve without touching the filesystem.
    4. If relative and base_path is set, join to base_path then resolve.
    5. If relative and base_path is None, return RELATIVE_WITHOUT_BASE error.

    Path.resolve(strict=False) canonicalises . and .. without requiring the
    path to exist.  It does not scan parent directories.

    Returns:
        (Path, None)                — success
        (None, "MISSING")           — raw_path is blank
        (None, "RELATIVE_WITHOUT_BASE") — relative path, no base_path
    """
    cleaned = str(raw_path or "").strip()
    if not cleaned:
        return None, "MISSING"

    p = Path(cleaned).expanduser()

    if not p.is_absolute():
        if not base_path or not str(base_path).strip():
            return None, "RELATIVE_WITHOUT_BASE"
        p = Path(str(base_path).strip()).expanduser() / p

    return p.resolve(strict=False), None


# ---------------------------------------------------------------------------
# SEG-Y path validation
# ---------------------------------------------------------------------------

def validate_segy_path(
    raw_path: str | None,
    base_path: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Validate a SEG-Y file path reference.

    Checks performed (in order):
    1. Path is non-blank.
    2. Path resolves (not relative without base_path).
    3. Extension is .sgy or .segy (warning only, does not block if file exists).
    4. Path exists.
    5. Path is a file (not a directory or other non-file).
    6. File is readable (os.access R_OK).
    7. If all pass: record size_bytes, emit SEGY_PATH_VALIDATED info flag.

    Blocker flags:  MISSING_SEGY_PATH, RELATIVE_PATH_WITHOUT_BASE_PATH,
                    SEGY_FILE_NOT_FOUND, SEGY_PATH_NOT_FILE, SEGY_FILE_UNREADABLE
    Warning flags:  INVALID_SEGY_EXTENSION
    Info flags:     SEGY_PATH_VALIDATED

    Args:
        raw_path  — segy_path_raw from normalized_metadata (may be None or blank).
        base_path — session source.base_path for relative-path resolution.

    Returns:
        (segy_result_dict, qaqc_flags)
    """
    flags: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    raw = str(raw_path or "").strip()

    # ------------------------------------------------------------------ #
    # 1. Missing / blank                                                   #
    # ------------------------------------------------------------------ #
    if not raw:
        flags.append(_flag(
            "blocker", "MISSING_SEGY_PATH",
            "SEG-Y path is missing or blank.",
            "segy_path",
        ))
        return {
            "raw_path": "",
            "resolved_path": "",
            "exists": False,
            "is_file": False,
            "readable": False,
            "size_bytes": None,
            "extension": "",
            "errors": ["MISSING_SEGY_PATH"],
            "warnings": [],
        }, flags

    # ------------------------------------------------------------------ #
    # 2. Resolution                                                         #
    # ------------------------------------------------------------------ #
    resolved, resolve_err = _resolve_path(raw, base_path)

    if resolve_err == "RELATIVE_WITHOUT_BASE":
        flags.append(_flag(
            "blocker", "RELATIVE_PATH_WITHOUT_BASE_PATH",
            (
                f"SEG-Y path '{raw}' is a relative path but no base_path is "
                "set for this session.  Set base_path when creating the session, "
                "or supply an absolute path in the loadsheet."
            ),
            "segy_path",
        ))
        return {
            "raw_path": raw,
            "resolved_path": "",
            "exists": False,
            "is_file": False,
            "readable": False,
            "size_bytes": None,
            "extension": Path(raw).suffix.lower(),
            "errors": ["RELATIVE_PATH_WITHOUT_BASE_PATH"],
            "warnings": [],
        }, flags

    # ------------------------------------------------------------------ #
    # 3. Extension (warning; does not short-circuit further checks)        #
    # ------------------------------------------------------------------ #
    ext = resolved.suffix.lower()
    if ext not in SEGY_EXTENSIONS:
        flags.append(_flag(
            "warning", "INVALID_SEGY_EXTENSION",
            (
                f"SEG-Y path has extension '{ext or '(none)'}'; "
                "expected .sgy or .segy (case-insensitive).  "
                "File existence and readability will still be checked."
            ),
            "segy_path",
        ))
        warnings.append("INVALID_SEGY_EXTENSION")

    # ------------------------------------------------------------------ #
    # 4–6. Existence → is_file → readable                                  #
    # ------------------------------------------------------------------ #
    exists: bool = resolved.exists()
    is_file: bool = resolved.is_file() if exists else False
    readable: bool = False
    size_bytes: int | None = None

    if not exists:
        flags.append(_flag(
            "blocker", "SEGY_FILE_NOT_FOUND",
            f"SEG-Y file not found: '{resolved}'.",
            "segy_path",
        ))
        errors.append("SEGY_FILE_NOT_FOUND")

    elif not is_file:
        flags.append(_flag(
            "blocker", "SEGY_PATH_NOT_FILE",
            f"SEG-Y path exists but is not a file: '{resolved}'.",
            "segy_path",
        ))
        errors.append("SEGY_PATH_NOT_FILE")

    else:
        readable = os.access(resolved, os.R_OK)
        if not readable:
            flags.append(_flag(
                "blocker", "SEGY_FILE_UNREADABLE",
                f"SEG-Y file exists but is not readable: '{resolved}'.",
                "segy_path",
            ))
            errors.append("SEGY_FILE_UNREADABLE")
        else:
            size_bytes = resolved.stat().st_size
            flags.append(_flag(
                "info", "SEGY_PATH_VALIDATED",
                f"SEG-Y path validated: '{resolved}'.",
                "segy_path",
            ))

    return {
        "raw_path": raw,
        "resolved_path": str(resolved),
        "exists": exists,
        "is_file": is_file,
        "readable": readable,
        "size_bytes": size_bytes,
        "extension": ext,
        "errors": errors,
        "warnings": warnings,
    }, flags


# ---------------------------------------------------------------------------
# Supporting document path validation
# ---------------------------------------------------------------------------

def _validate_supporting_document(
    raw_path: str,
    base_path: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Validate a single supporting document path reference.

    All failures produce warning-level flags.  Supporting document issues
    do NOT block a row in SBLT-4; they require review later.

    Content is not inspected, classified, or extracted.

    Returns:
        (doc_result_dict, qaqc_flags)
    """
    flags: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    raw = str(raw_path or "").strip()

    # Resolution
    resolved, resolve_err = _resolve_path(raw, base_path)

    if resolve_err == "RELATIVE_WITHOUT_BASE":
        flags.append(_flag(
            "warning", "RELATIVE_PATH_WITHOUT_BASE_PATH",
            (
                f"Supporting document path '{raw}' is relative but no "
                "base_path is set for this session."
            ),
            "supporting_document_paths",
        ))
        warnings.append("RELATIVE_PATH_WITHOUT_BASE_PATH")
        return {
            "raw_path": raw,
            "resolved_path": "",
            "exists": False,
            "is_file": False,
            "readable": False,
            "size_bytes": None,
            "errors": errors,
            "warnings": warnings,
        }, flags

    exists: bool = resolved.exists()
    is_file: bool = resolved.is_file() if exists else False
    readable: bool = False
    size_bytes: int | None = None

    if not exists:
        flags.append(_flag(
            "warning", "SUPPORTING_DOCUMENT_NOT_FOUND",
            f"Supporting document not found: '{resolved}'.",
            "supporting_document_paths",
        ))
        errors.append("SUPPORTING_DOCUMENT_NOT_FOUND")

    elif not is_file:
        flags.append(_flag(
            "warning", "SUPPORTING_DOCUMENT_PATH_NOT_FILE",
            f"Supporting document path exists but is not a file: '{resolved}'.",
            "supporting_document_paths",
        ))
        errors.append("SUPPORTING_DOCUMENT_PATH_NOT_FILE")

    else:
        readable = os.access(resolved, os.R_OK)
        if not readable:
            flags.append(_flag(
                "warning", "SUPPORTING_DOCUMENT_UNREADABLE",
                f"Supporting document is not readable: '{resolved}'.",
                "supporting_document_paths",
            ))
            errors.append("SUPPORTING_DOCUMENT_UNREADABLE")
        else:
            size_bytes = resolved.stat().st_size
            flags.append(_flag(
                "info", "SUPPORTING_DOCUMENT_PATH_VALIDATED",
                f"Supporting document path validated: '{resolved}'.",
                "supporting_document_paths",
            ))

    return {
        "raw_path": raw,
        "resolved_path": str(resolved),
        "exists": exists,
        "is_file": is_file,
        "readable": readable,
        "size_bytes": size_bytes,
        "errors": errors,
        "warnings": warnings,
    }, flags


# ---------------------------------------------------------------------------
# Public: validate_row_paths
# ---------------------------------------------------------------------------

def validate_row_paths(
    row: dict[str, Any],
    base_path: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """
    Validate all file/path references for a single SBLT row.

    Uses paths from normalized_metadata (populated by SBLT-3 normalization).

    Args:
        row       — current normalized row dict (must have normalized_metadata).
        base_path — session source.base_path for relative-path resolution;
                    None means relative paths are invalid.

    Returns:
        A 3-tuple of:
            path_validation — the path_validation block to add to the row.
            new_qaqc_flags  — path-validation-stage flags to append
                              (existing SBLT-2/SBLT-3 flags are NOT repeated;
                              the caller merges them).
            new_status      — updated row status.

    Status rules:
        blocked         → stays blocked (path validation cannot promote).
        review_required → stays review_required unless SEG-Y blocker → blocked.
        ready           → stays ready if SEG-Y valid, else blocked.

    Supporting document failures produce warning flags only; they never block.
    """
    current_status: str = str(row.get("status") or "blocked")
    nm: dict[str, Any] = row.get("normalized_metadata") or {}

    segy_raw: str = str(nm.get("segy_path_raw") or "")
    supporting_docs: list[str] = list(nm.get("supporting_document_paths") or [])

    all_flags: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    # SEG-Y validation                                                      #
    # ------------------------------------------------------------------ #
    segy_result, segy_flags = validate_segy_path(segy_raw, base_path)
    all_flags.extend(segy_flags)

    # ------------------------------------------------------------------ #
    # Supporting document validation                                        #
    # ------------------------------------------------------------------ #
    doc_results: list[dict[str, Any]] = []
    for doc_raw in supporting_docs:
        if not str(doc_raw or "").strip():
            continue  # blank entries already filtered by SBLT-3; safe guard
        doc_result, doc_flags = _validate_supporting_document(doc_raw, base_path)
        doc_results.append(doc_result)
        all_flags.extend(doc_flags)

    # ------------------------------------------------------------------ #
    # PATH_VALIDATION_COMPLETED — always appended                           #
    # ------------------------------------------------------------------ #
    all_flags.append(_flag(
        "info", "PATH_VALIDATION_COMPLETED",
        "Path validation completed.",
        None,
    ))

    # ------------------------------------------------------------------ #
    # Status determination                                                  #
    # ------------------------------------------------------------------ #
    segy_valid: bool = bool(
        segy_result.get("exists")
        and segy_result.get("is_file")
        and segy_result.get("readable")
    )

    new_status: str = current_status
    if current_status == "blocked":
        pass  # blocked stays blocked; path validation cannot promote a row
    elif current_status == "review_required":
        if not segy_valid:
            new_status = "blocked"
        # else stays review_required
    elif current_status == "ready":
        if not segy_valid:
            new_status = "blocked"
        # else stays ready

    # ------------------------------------------------------------------ #
    # Build path_validation block                                           #
    # ------------------------------------------------------------------ #
    docs_valid: int = sum(
        1 for d in doc_results
        if d.get("exists") and d.get("is_file") and d.get("readable")
    )
    docs_with_warnings: int = sum(
        1 for d in doc_results
        if d.get("errors") or d.get("warnings")
    )

    path_validation: dict[str, Any] = {
        "path_validation_version": PATH_VALIDATION_VERSION,
        "validated": True,
        "base_path": base_path or "",
        "segy": segy_result,
        "supporting_documents": doc_results,
        "summary": {
            "segy_valid": segy_valid,
            "supporting_document_count": len(doc_results),
            "supporting_documents_valid": docs_valid,
            "supporting_documents_with_warnings": docs_with_warnings,
        },
    }

    return path_validation, all_flags, new_status
