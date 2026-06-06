
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

from app.services.repository_registry_service import get_repository
from app.knowledge import classify_document_name, classify_segy_name, extract_processing_hints, build_qaqc_flags
from app.services.metadata_identity_extraction_service import extract_canonical_identity_from_segy_path


SEGY_EXTENSIONS = {".sgy", ".segy"}

DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".text",
    ".csv",
    ".tsv",
    ".xlsx",
    ".xls",
    ".docx",
    ".doc",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".gif",
    ".json",
    ".xml",
    ".las",
    ".asc",
    ".dat",
    ".nav",
    ".ukooa",
    ".p190",
    ".vel",
}


IGNORED_DIR_NAMES = {
    ".git",
    "__pycache__",
    "node_modules",
    ".zarr",
    "zarr",
    "zarr_tmp",
    "venv",
    ".venv",
}



# ---- F3J knowledge enrichment helpers ----

def _f3j_first_present(record: dict, keys: tuple[str, ...], default=None):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return default


def _f3j_merge_list(existing, incoming):
    if not existing:
        existing_items = []
    elif isinstance(existing, list):
        existing_items = list(existing)
    else:
        existing_items = [existing]

    if not incoming:
        incoming_items = []
    elif isinstance(incoming, list):
        incoming_items = list(incoming)
    else:
        incoming_items = [incoming]

    seen = set()
    merged = []
    for item in existing_items + incoming_items:
        marker = repr(item)
        if marker in seen:
            continue
        seen.add(marker)
        merged.append(_f3j_apply_knowledge_enrichment(item))
    return merged


def _f3j_is_segy_record(record: dict, filename: str, relative_path: str) -> bool:
    from pathlib import Path as _F3JPath

    ext = _F3JPath(filename).suffix.lower()
    if ext in {".sgy", ".segy"}:
        return True

    combined = f"{filename} {relative_path}".lower()
    if combined.endswith(".sgy") or combined.endswith(".segy"):
        return True

    file_type = str(record.get("file_type") or record.get("kind") or record.get("type") or "").lower()
    return file_type in {"segy", "seg-y", "seismic", "seismic_file"}


def _f3j_apply_knowledge_enrichment(record):
    """
    Backend-owned deterministic enrichment for repository scan records.

    This keeps F3J deliberately conservative:
    - It does not override strong existing scanner fields.
    - It adds document/SEG-Y hints where absent or shallow.
    - It marks filename/path-derived evidence as review-supporting, not truth.
    - Geometry probing remains a later block.
    """
    if not isinstance(record, dict):
        return record

    from pathlib import Path as _F3JPath

    path_value = _f3j_first_present(
        record,
        (
            "relative_path",
            "path",
            "file_path",
            "source_path",
            "absolute_path",
            "full_path",
        ),
        "",
    )

    filename = _f3j_first_present(
        record,
        (
            "filename",
            "file_name",
            "name",
            "basename",
        ),
        None,
    )

    if not filename and path_value:
        filename = _F3JPath(str(path_value)).name

    if not filename:
        return record

    relative_path = str(path_value or "")

    is_segy = _f3j_is_segy_record(record, str(filename), relative_path)

    if is_segy:
        kg = classify_segy_name(str(filename), relative_path)

        for key in (
            "candidate_kind",
            "candidate_role",
            "classification_source",
            "classification_confidence",
        ):
            current = record.get(key)
            incoming = kg.get(key)
            if current in (None, "", "unknown", "review_required") and incoming not in (None, ""):
                record[key] = incoming

        record["classification_reasons"] = _f3j_merge_list(
            record.get("classification_reasons"),
            kg.get("classification_reasons"),
        )

        record["matched_terms"] = _f3j_merge_list(
            record.get("matched_terms"),
            kg.get("matched_terms"),
        )

        record["processing_hints"] = _f3j_merge_list(
            record.get("processing_hints"),
            kg.get("processing_hints"),
        )

        qaqc_input = dict(record)
        if "geometry_probe_not_yet_run" not in qaqc_input:
            reasons = record.get("classification_reasons") or []
            qaqc_input["geometry_probe_not_yet_run"] = any(
                "geometry_probe_not_yet_run" in str(reason)
                for reason in reasons
            )

        record["qaqc_flags"] = _f3j_merge_list(
            record.get("qaqc_flags"),
            build_qaqc_flags(qaqc_input),
        )

        return record

    doc = classify_document_name(str(filename), relative_path)

    for key in (
        "document_type",
        "classification_source",
        "classification_confidence",
    ):
        current = record.get(key)
        incoming = doc.get(key)
        if current in (None, "", "unknown", "unknown_document") and incoming not in (None, ""):
            record[key] = incoming

    record["classification_reasons"] = _f3j_merge_list(
        record.get("classification_reasons"),
        doc.get("classification_reasons"),
    )

    record["matched_terms"] = _f3j_merge_list(
        record.get("matched_terms"),
        doc.get("matched_terms"),
    )

    # Document records are supporting evidence, not dataset candidates.
    # Do not apply dataset-candidate QAQC flags such as candidate_kind_unknown.
    existing_doc_flags = record.get("qaqc_flags") or []
    record["qaqc_flags"] = _f3j_merge_list(existing_doc_flags, [])

    return record


def _f3j_enrich_scan_collection(value):
    """
    Apply knowledge enrichment to common scanner return shapes.
    """
    if isinstance(value, list):
        return [_f3j_apply_knowledge_enrichment(item) for item in value]

    if isinstance(value, dict):
        for key in (
            "files",
            "items",
            "records",
            "candidates",
            "documents",
            "segy_files",
            "supporting_documents",
            "scan_records",
        ):
            if isinstance(value.get(key), list):
                value[key] = [_f3j_apply_knowledge_enrichment(item) for item in value[key]]
        return value

    return value

# ---- end F3J knowledge enrichment helpers ----


def _clean_label(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\s+", " ", value)
    return value


def _safe_stat(path: Path) -> Dict[str, Any]:
    try:
        stat = path.stat()
        return {
            "size_bytes": stat.st_size,
            "modified_epoch": stat.st_mtime,
        }
    except Exception:
        return {
            "size_bytes": None,
            "modified_epoch": None,
        }


def _classify_document(filename: str) -> str:
    name = filename.lower()

    if "processing" in name or "process" in name or "proc" in name:
        return "processing_report"
    if "observer" in name or "obs" in name:
        return "observer_log"
    if "navigation" in name or "nav" in name or "ukooa" in name or "p190" in name:
        return "navigation"
    if "velocity" in name or "vel" in name:
        return "velocity"
    if "acquisition" in name or "acq" in name:
        return "acquisition_report"
    if "map" in name or "location" in name:
        return "map"
    if name.endswith(".las"):
        return "well_log"
    if name.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif")):
        return "image"
    if name.endswith((".csv", ".xlsx", ".xls")):
        return "spreadsheet_or_table"
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith((".txt", ".text")):
        return "text"

    return "unknown"



def _source_structure_from_repo(repo: Dict[str, Any]) -> str:
    """
    Extract the source_structure_type recorded by SourceRepositoryManager.

    Current front end stores this in repository notes, e.g.
    source_structure_type=multi_version_3d_delivery; intended_use=3d_segy_intake

    This is intentionally conservative and deterministic. It is not a geometry
    probe and should not pretend to be one.
    """
    direct = str(repo.get("source_structure_type") or "").strip()
    if direct:
        return direct

    notes = str(repo.get("notes") or "")
    match = re.search(r"source_structure_type\s*=\s*([A-Za-z0-9_\\-]+)", notes)
    return match.group(1).strip() if match else ""


def _is_3d_source_structure(source_structure_type: str) -> bool:
    return source_structure_type in {
        "single_3d_volume",
        "single_3d_volume_with_docs",
        "multi_version_3d_delivery",
    }


def _is_2d_source_structure(source_structure_type: str) -> bool:
    return source_structure_type in {
        "single_isolated_line",
        "single_line_with_docs",
        "single_line_multi_version",
        "survey_with_line_folders",
        "survey_flat_lines",
    }


def _filename_suggests_2d(filename: str, relative_path: str = "") -> bool:
    text = f"{filename} {relative_path}".lower()
    return (
        ".2d." in text
        or "_2d" in text
        or "-2d" in text
        or text.endswith("2d.sgy")
        or text.endswith("2d.segy")
    )


def _filename_suggests_3d(filename: str, relative_path: str = "") -> bool:
    text = f"{filename} {relative_path}".lower()
    return (
        ".3d." in text
        or "_3d" in text
        or "-3d" in text
        or "3d_volume" in text
        or "volume" in text
        or "cube" in text
    )


def _classify_segy_candidate(
    *,
    repo: Dict[str, Any],
    filename: str,
    relative_path: str,
) -> Dict[str, Any]:
    """
    Backend-owned discovery classification for SEG-Y registry records.

    This is a first deterministic layer. It deliberately records confidence and
    reasons so the QAQC load sheet can present reviewable evidence instead of
    hiding guesses in the front end.

    Later blocks can upgrade this with a SEG-Y header/geometry probe.
    """
    source_structure_type = _source_structure_from_repo(repo)
    reasons: List[str] = []
    source = "source_structure_type"

    if source_structure_type:
        reasons.append(f"source_structure_type={source_structure_type}")

    name_says_2d = _filename_suggests_2d(filename, relative_path)
    name_says_3d = _filename_suggests_3d(filename, relative_path)

    if name_says_2d:
        reasons.append("filename_or_path_suggests_2d")
    if name_says_3d:
        reasons.append("filename_or_path_suggests_3d")

    if _is_3d_source_structure(source_structure_type):
        if name_says_2d:
            return {
                "candidate_kind": "2d_line",
                "candidate_role": "excluded_from_3d_intake",
                "classification_source": source,
                "classification_confidence": "medium",
                "classification_reasons": reasons + [
                    "3d_repository_context_but_filename_suggests_2d",
                    "requires_review_if_needed_for_2d_workflow",
                ],
            }

        return {
            "candidate_kind": "3d_volume",
            "candidate_role": "volume_candidate",
            "classification_source": source,
            "classification_confidence": "medium",
            "classification_reasons": reasons + [
                "repository_declared_for_3d_intake",
                "geometry_probe_not_yet_run",
            ],
        }

    if _is_2d_source_structure(source_structure_type):
        return {
            "candidate_kind": "2d_line",
            "candidate_role": "line_candidate",
            "classification_source": source,
            "classification_confidence": "medium",
            "classification_reasons": reasons + [
                "repository_declared_for_2d_intake",
                "geometry_probe_not_yet_run",
            ],
        }

    # No explicit repository structure. Fall back to filename hints only.
    if name_says_2d and not name_says_3d:
        return {
            "candidate_kind": "2d_line",
            "candidate_role": "line_candidate",
            "classification_source": "filename_hint",
            "classification_confidence": "low",
            "classification_reasons": reasons + [
                "no_source_structure_type",
                "filename_hint_only",
            ],
        }

    if name_says_3d and not name_says_2d:
        return {
            "candidate_kind": "3d_volume",
            "candidate_role": "volume_candidate",
            "classification_source": "filename_hint",
            "classification_confidence": "low",
            "classification_reasons": reasons + [
                "no_source_structure_type",
                "filename_hint_only",
            ],
        }

    return {
        "candidate_kind": "unknown",
        "candidate_role": "review_required",
        "classification_source": "unclassified",
        "classification_confidence": "low",
        "classification_reasons": reasons + [
            "no_source_structure_type",
            "no_reliable_filename_hint",
            "geometry_probe_not_yet_run",
        ],
    }



def _infer_line_key_from_filename(filename: str) -> str:
    """
    Conservative filename-based line grouping.

    Priority:
    1. Recognize common 2D line-code pattern inside filenames, e.g.
       AM812D1008-AUK81B-210 or AM872D1005-AUK87B-371.
    2. For single-line folders without a separate line code, use the survey/package code.
    3. Fall back to a cleaned filename stem.

    This remains an inference, not a confirmed line identity.
    """
    stem = Path(filename).stem
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")

    # Pattern: survey code + line code + numeric/suffix line number.
    # Examples:
    #   AM812D1008_AUK81B_210
    #   AM872D1005_AUK87B_371
    #   AM882D0001_AUK88A_101A
    match = re.search(
        r"(?i)(AM\d{2,3}[A-Z]\d{4})_([A-Z]{2,5}\d{2,3}[A-Z]?)_([0-9]{2,5}[A-Z]?(?:_[0-9]{2,5}[A-Z]?)?)",
        normalized,
    )
    if match:
        survey = match.group(1).upper()
        line_prefix = match.group(2).upper()
        line_number = match.group(3).upper().replace("_", "-")
        return f"{survey}_{line_prefix}_{line_number}"

    # Pattern: survey/package code only.
    # Useful for filenames such as:
    #   Poststack_Final_Migration-Full_AM923F0002-Final_Migration-Full-824061_0.sgy
    #
    # Do not use \b here because underscores are word characters in regex.
    # A normalized filename often looks like:
    #   Poststack_Final_Migration_Full_AM923F0002_Final_Migration_Full_824061_0
    match = re.search(r"(?i)(^|_)(AM\d{2,3}[A-Z]\d{4})(_|$)", normalized)
    if match:
        return match.group(2).upper()

    # Fallback cleanup.
    value = normalized
    value = re.sub(
        r"(?i)(poststack|prestack|final|filtered|filter|stack|stk|migration|mig|full|pstm|psdm|reprocess|reprocessed|raw|segy|sgy)",
        "_",
        value,
    )
    value = re.sub(r"_+", "_", value).strip("_")

    return value or stem


def _walk_repository(root: Path, max_files: int, include_subfolders: bool = False) -> Dict[str, Any]:
    files: List[Path] = []
    warnings: List[str] = []

    iterator = root.rglob("*") if include_subfolders else root.iterdir()

    count = 0
    for path in iterator:
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            rel_parts = path.parts

        if any(part in IGNORED_DIR_NAMES for part in rel_parts):
            continue

        if not path.is_file():
            continue

        count += 1
        if count > max_files:
            warnings.append(f"Scan stopped at max_files={max_files}")
            break

        files.append(path)

    return {
        "files": files,
        "warnings": warnings,
    }


def _package_key_for_file(root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    parts = rel.parts

    if len(parts) <= 1:
        return "__repository_root__"

    return parts[0]


def scan_repository_packages(repository_id: str, max_files: int = 100000, include_subfolders: bool | None = None) -> Dict[str, Any]:
    repo = get_repository(repository_id)
    if not repo:
        raise FileNotFoundError(f"Repository not found: {repository_id}")

    root = Path(repo["root_path"]).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Repository root missing: {root}")

    scan_subfolders = bool(repo.get("include_subfolders", False)) if include_subfolders is None else bool(include_subfolders)

    walked = _walk_repository(root, max_files=max_files, include_subfolders=scan_subfolders)
    files: List[Path] = walked["files"]
    warnings: List[str] = list(walked["warnings"])

    package_buckets: Dict[str, Dict[str, Any]] = {}

    for path in files:
        rel = path.relative_to(root)
        rel_str = str(rel)
        ext = path.suffix.lower()
        package_key = _package_key_for_file(root, path)

        if package_key not in package_buckets:
            display_name = root.name if package_key == "__repository_root__" else package_key
            package_buckets[package_key] = {
                "package_key": package_key,
                "display_name": display_name,
                "relative_path": "" if package_key == "__repository_root__" else package_key,
                "segy_files": [],
                "documents": [],
                "other_files_count": 0,
                "warnings": [],
            }

        pkg = package_buckets[package_key]
        stat = _safe_stat(path)

        if ext in SEGY_EXTENSIONS:
            inferred_line_key = _infer_line_key_from_filename(path.name)
            classification = _classify_segy_candidate(
                repo=repo,
                filename=path.name,
                relative_path=rel_str,
            )

            metadata_identity = extract_canonical_identity_from_segy_path(path)

            pkg["segy_files"].append({
                "filename": path.name,
                "relative_path": rel_str,
                "extension": ext,
                "size_bytes": stat["size_bytes"],
                "modified_epoch": stat["modified_epoch"],
                "survey_name": metadata_identity.get("survey_name"),
                "line_name": metadata_identity.get("line_name"),
                "volume_name": metadata_identity.get("volume_name"),
                "identity_candidates": metadata_identity.get("identity_candidates", []),
                "identity_extraction": metadata_identity.get("identity_extraction", {}),
                "inferred_line_key": inferred_line_key,
                "relationship_status": "filename_inferred",
                **classification,
            })

        elif ext in DOCUMENT_EXTENSIONS:
            pkg["documents"].append({
                "filename": path.name,
                "relative_path": rel_str,
                "extension": ext,
                "size_bytes": stat["size_bytes"],
                "modified_epoch": stat["modified_epoch"],
                "document_type": _classify_document(path.name),
                "linked_scope": "package_candidate",
            })

        else:
            pkg["other_files_count"] += 1

    packages: List[Dict[str, Any]] = []

    for pkg in package_buckets.values():
        line_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for segy in pkg["segy_files"]:
            line_groups[segy["inferred_line_key"]].append(segy)

        lines: List[Dict[str, Any]] = []
        for line_key, segy_files in sorted(line_groups.items(), key=lambda item: item[0].lower()):
            if len(segy_files) > 1:
                version_status = "multiple_processing_versions_candidate"
            else:
                version_status = "single_version_candidate"

            lines.append({
                "line_key": line_key,
                "display_name": _clean_label(line_key.replace("_", " ")),
                "line_identity_status": "filename_inferred",
                "version_status": version_status,
                "segy_count": len(segy_files),
                "segy_files": sorted(segy_files, key=lambda item: item["filename"].lower()),
            })

        pkg["line_count"] = len(lines)
        pkg["segy_count"] = len(pkg["segy_files"])
        pkg["document_count"] = len(pkg["documents"])
        pkg["lines"] = lines

        if pkg["segy_count"] == 0 and pkg["document_count"] > 0:
            pkg["package_type"] = "documents_only"
        elif pkg["segy_count"] == 1:
            pkg["package_type"] = "single_line_package_candidate"
        elif pkg["line_count"] == 1 and pkg["segy_count"] > 1:
            pkg["package_type"] = "single_line_multi_version_candidate"
        elif pkg["line_count"] > 1:
            pkg["package_type"] = "survey_package_candidate"
        else:
            pkg["package_type"] = "unknown"

        packages.append(pkg)

    packages = [
        pkg for pkg in packages
        if pkg.get("segy_count", 0) > 0 or pkg.get("document_count", 0) > 0
    ]

    packages = sorted(
        packages,
        key=lambda item: (
            item["display_name"].lower(),
            item["relative_path"].lower(),
        ),
    )

    segy_total = sum(pkg["segy_count"] for pkg in packages)
    doc_total = sum(pkg["document_count"] for pkg in packages)
    lines_total = sum(pkg["line_count"] for pkg in packages)

    return {
        "repository": {
            "repository_id": repository_id,
            "name": repo.get("name"),
            "root_path": str(root),
            "status": repo.get("status"),
            "include_subfolders": scan_subfolders,
        },
        "summary": {
            "package_count": len(packages),
            "line_group_count": lines_total,
            "segy_file_count": segy_total,
            "document_count": doc_total,
            "scanned_file_count": len(files),
        },
        "packages": packages,
        "warnings": warnings,
    }
