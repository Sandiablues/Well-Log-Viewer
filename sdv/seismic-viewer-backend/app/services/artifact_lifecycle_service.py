from __future__ import annotations

import json
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set


BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
MSI_DB = DATA_DIR / "msi" / "msi.sqlite"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _basename(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    try:
        return Path(text).name
    except Exception:
        return text


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default


def _json_loads(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return {}
    try:
        return json.loads(str(value))
    except Exception:
        return {}


def _token_values(*values: Any) -> Set[str]:
    tokens: Set[str] = set()
    for value in values:
        if isinstance(value, dict):
            tokens |= _record_tokens(value)
            continue
        if isinstance(value, (list, tuple, set)):
            for item in value:
                tokens |= _token_values(item)
            continue
        text = _clean(value)
        if not text:
            continue

        candidates = {text}
        base = _basename(text)
        if base:
            candidates.add(base)

        # MSI identifiers are composite by design, for example:
        #   msi_repr:source_segy_segy_<candidate>:zarr_<artifact>
        #   source_segy:segy_<candidate>
        # The artifact graph must resolve these back to the canonical
        # source SEG-Y candidate id without relying on frontend state.
        normalized = text.replace(":", " ").replace("|", " ").replace("/", " ")
        normalized = normalized.replace("source_segy_segy_", "segy_")
        normalized = normalized.replace("source_segy:", "")
        for part in re.split(r"[\s]+", normalized):
            clean_part = _clean(part)
            if clean_part:
                candidates.add(clean_part)
                part_base = _basename(clean_part)
                if part_base:
                    candidates.add(part_base)

        for match in re.findall(r"(?:^|[^A-Za-z0-9])((?:segy|zarr)_[A-Za-z0-9][A-Za-z0-9_-]*)", f" {text}"):
            candidates.add(match)
        for match in re.findall(r"source_segy[:_]+(segy_[A-Za-z0-9][A-Za-z0-9_-]*)", text):
            candidates.add(match)

        tokens |= {candidate for candidate in candidates if candidate}
    return {t for t in tokens if t}


def _record_tokens(record: Dict[str, Any]) -> Set[str]:
    fields = {
        "candidate_id",
        "source_candidate_id",
        "segy_file_id",
        "source_segy_file_id",
        "source_file_id",
        "line_id",
        "package_id",
        "repository_id",
        "dataset_id",
        "representation_id",
        "msi_representation_id",
        "managed_representation_id",
        "volume_id",
        "physical_volume_id",
        "legacy_volume_id",
        "filename",
        "display_name",
        "source_file_name",
        "relative_path",
        "source_path",
        "path",
        "zarr_url",
        "storage_uri",
        "artifact_id",
    }
    tokens: Set[str] = set()
    for field in fields:
        tokens |= _token_values(record.get(field))
    return tokens


def _match(tokens: Set[str], record: Dict[str, Any]) -> bool:
    if not tokens:
        return False
    rtokens = _record_tokens(record)
    if tokens & rtokens:
        return True
    basenames = {_basename(t) for t in tokens if t}
    rbasenames = {_basename(t) for t in rtokens if t}
    return bool((basenames - {""}) & (rbasenames - {""}))


def _dedupe(items: List[Dict[str, Any]], key_fields: Iterable[str]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for item in items:
        key = "|".join(_clean(item.get(k)) for k in key_fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


class ArtifactLifecycleService:
    """
    Read-only artifact ownership graph resolver.

    This service does not delete or mutate anything. It establishes a single
    backend-owned view of the artifacts that belong to a source candidate,
    MSI dataset, or MSI representation. Delete execution should be wired only
    after this graph is validated.
    """

    schema_version = "artifact.lifecycle.graph.v1"

    def graph_for_source_candidate(self, candidate_id: str) -> Dict[str, Any]:
        tokens = _token_values(candidate_id)
        source_records = self._source_records(tokens)
        tokens |= self._tokens_from_records(source_records)
        return self._build_graph("source_candidate", candidate_id, tokens, source_records)

    def graph_for_msi_dataset(self, dataset_id: str) -> Dict[str, Any]:
        tokens = _token_values(dataset_id)
        msi = self._msi_records(tokens, scope_type="msi_dataset")
        tokens |= self._tokens_from_records(msi.get("datasets", []))
        tokens |= self._tokens_from_records(msi.get("representations", []))
        tokens |= self._tokens_from_records(msi.get("viewer_loads", []))
        source_records = self._source_records(tokens)
        tokens |= self._tokens_from_records(source_records)
        return self._build_graph("msi_dataset", dataset_id, tokens, source_records, msi)

    def graph_for_msi_representation(self, representation_id: str) -> Dict[str, Any]:
        tokens = _token_values(representation_id)
        msi = self._msi_records(tokens, scope_type="msi_representation")
        tokens |= self._tokens_from_records(msi.get("datasets", []))
        tokens |= self._tokens_from_records(msi.get("representations", []))
        tokens |= self._tokens_from_records(msi.get("viewer_loads", []))
        source_records = self._source_records(tokens)
        tokens |= self._tokens_from_records(source_records)
        return self._build_graph("msi_representation", representation_id, tokens, source_records, msi)

    def validate_source_candidate(self, candidate_id: str) -> Dict[str, Any]:
        graph = self.graph_for_source_candidate(candidate_id)
        return self._validation_payload(graph)


    def delete_dry_run(self, scope_type: str, scope_id: str) -> Dict[str, Any]:
        """
        Return a deterministic, non-mutating delete plan for a resolved
        artifact graph. This performs no filesystem or database changes.
        """
        graph = self.graph_for_scope(scope_type, scope_id)
        return self._delete_dry_run_payload(graph)

    def delete_graph(self, scope_type: str, scope_id: str, confirm_delete_derived_artifacts: bool = False) -> Dict[str, Any]:
        """Execute a guarded graph delete for derived artifacts only.

        Original source SEG-Y files are never deleted. Filesystem deletion is
        restricted to paths under seismic-viewer-backend/data.
        """
        if not confirm_delete_derived_artifacts:
            raise ValueError("confirm_delete_derived_artifacts must be true for artifact graph delete execution.")

        plan = self.delete_dry_run(scope_type, scope_id)
        operations = plan.get("operations", {}) if isinstance(plan, dict) else {}

        deleted_directories: List[Dict[str, Any]] = []
        deleted_files: List[Dict[str, Any]] = []
        deleted_records: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        for item in operations.get("delete_directories") or []:
            path = self._safe_data_path(item.get("path"))
            if path is None:
                skipped.append({**item, "skip_reason": "unsafe_or_outside_data_dir"})
                continue
            if not path.exists():
                skipped.append({**item, "skip_reason": "already_missing"})
                continue
            if not path.is_dir():
                skipped.append({**item, "skip_reason": "not_a_directory"})
                continue
            try:
                shutil.rmtree(path)
                deleted_directories.append({**item, "path": str(path)})
            except Exception as exc:
                errors.append({**item, "path": str(path), "error": str(exc)})

        for item in operations.get("delete_files") or []:
            path = self._safe_data_path(item.get("path"))
            if path is None:
                skipped.append({**item, "skip_reason": "unsafe_or_outside_data_dir"})
                continue
            if not path.exists():
                skipped.append({**item, "skip_reason": "already_missing"})
                continue
            if not path.is_file():
                skipped.append({**item, "skip_reason": "not_a_file"})
                continue
            try:
                path.unlink()
                deleted_files.append({**item, "path": str(path)})
            except Exception as exc:
                errors.append({**item, "path": str(path), "error": str(exc)})

        record_result = self._delete_msi_records(operations.get("delete_records") or [])
        deleted_records.extend(record_result.get("deleted_records", []))
        skipped.extend(record_result.get("skipped_records", []))
        errors.extend(record_result.get("record_errors", []))

        post_graph = self.graph_for_scope(scope_type, scope_id)
        post_summary = post_graph.get("summary") or {}

        return {
            "schema_version": "artifact.lifecycle.delete_execution.v1",
            "ok": not errors,
            "dry_run": False,
            "root": plan.get("root"),
            "source": plan.get("source"),
            "preserved_original_source": operations.get("preserve_original_source") or [],
            "deleted_directories": deleted_directories,
            "deleted_files": deleted_files,
            "deleted_records": deleted_records,
            "skipped": skipped,
            "errors": errors,
            "summary": {
                "deleted_directory_count": len(deleted_directories),
                "deleted_file_count": len(deleted_files),
                "deleted_record_count": len(deleted_records),
                "skipped_count": len(skipped),
                "error_count": len(errors),
                "post_indexed_preview_count": post_summary.get("indexed_preview_count", 0),
                "post_index_job_count": post_summary.get("index_job_count", 0),
                "post_managed_zarr_count": post_summary.get("managed_zarr_count", 0),
                "post_msi_representation_count": post_summary.get("msi_representation_count", 0),
            },
            "post_graph_summary": post_summary,
        }

    def _safe_data_path(self, path_value: Any) -> Optional[Path]:
        text = _clean(path_value)
        if not text:
            return None
        try:
            path = Path(text).expanduser()
            if not path.is_absolute():
                path = (BACKEND_DIR / path).resolve()
            else:
                path = path.resolve()
            data_root = DATA_DIR.resolve()
            if path == data_root or data_root not in path.parents:
                return None
            return path
        except Exception:
            return None

    def _delete_msi_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        deleted: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        if not records:
            return {"deleted_records": deleted, "skipped_records": skipped, "record_errors": errors}
        if not MSI_DB.exists():
            skipped.append({"record_type": "msi", "skip_reason": "msi_db_missing"})
            return {"deleted_records": deleted, "skipped_records": skipped, "record_errors": errors}

        try:
            conn = sqlite3.connect(MSI_DB)
        except Exception as exc:
            errors.append({"record_type": "msi", "error": str(exc)})
            return {"deleted_records": deleted, "skipped_records": skipped, "record_errors": errors}

        try:
            for item in records:
                rtype = _clean(item.get("record_type"))
                dataset_id = _clean(item.get("dataset_id"))
                representation_id = _clean(item.get("representation_id"))

                if rtype == "msi_viewer_load":
                    if representation_id:
                        cur = conn.execute("DELETE FROM msi_viewer_loads WHERE representation_id = ?", (representation_id,))
                    elif dataset_id:
                        cur = conn.execute("DELETE FROM msi_viewer_loads WHERE dataset_id = ?", (dataset_id,))
                    else:
                        skipped.append({**item, "skip_reason": "missing_identity"})
                        continue
                    deleted.append({**item, "rowcount": cur.rowcount})
                    continue

                if rtype == "msi_representation":
                    if representation_id:
                        conn.execute("DELETE FROM msi_viewer_loads WHERE representation_id = ?", (representation_id,))
                        cur = conn.execute("DELETE FROM msi_representations WHERE representation_id = ?", (representation_id,))
                    elif dataset_id:
                        conn.execute("DELETE FROM msi_viewer_loads WHERE dataset_id = ?", (dataset_id,))
                        cur = conn.execute("DELETE FROM msi_representations WHERE dataset_id = ?", (dataset_id,))
                    else:
                        skipped.append({**item, "skip_reason": "missing_identity"})
                        continue
                    deleted.append({**item, "rowcount": cur.rowcount})
                    continue

                if rtype == "msi_dataset":
                    if not dataset_id:
                        skipped.append({**item, "skip_reason": "missing_identity"})
                        continue
                    conn.execute("DELETE FROM msi_viewer_loads WHERE dataset_id = ?", (dataset_id,))
                    conn.execute("DELETE FROM msi_representations WHERE dataset_id = ?", (dataset_id,))
                    cur = conn.execute("DELETE FROM msi_datasets WHERE dataset_id = ?", (dataset_id,))
                    deleted.append({**item, "rowcount": cur.rowcount})
                    continue

                skipped.append({**item, "skip_reason": "unsupported_record_type"})
            conn.commit()
        except Exception as exc:
            conn.rollback()
            errors.append({"record_type": "msi", "error": str(exc)})
        finally:
            conn.close()

        return {"deleted_records": deleted, "skipped_records": skipped, "record_errors": errors}

    def graph_for_scope(self, scope_type: str, scope_id: str) -> Dict[str, Any]:
        clean_scope = _clean(scope_type)
        if clean_scope == "source_candidate":
            return self.graph_for_source_candidate(scope_id)
        if clean_scope == "msi_dataset":
            return self.graph_for_msi_dataset(scope_id)
        if clean_scope == "msi_representation":
            return self.graph_for_msi_representation(scope_id)
        raise ValueError(f"Unsupported artifact graph scope_type: {scope_type!r}")

    def _delete_dry_run_payload(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = graph.get("artifacts", {}) if isinstance(graph, dict) else {}
        operations = {
            "preserve_original_source": [],
            "delete_directories": [],
            "delete_files": [],
            "delete_records": [],
            "warnings": [],
            "blocked": [],
        }

        for item in artifacts.get("source_segy") or []:
            operations["preserve_original_source"].append({
                "artifact_type": "source_segy",
                "artifact_id": item.get("artifact_id"),
                "path": item.get("path"),
                "reason": "Original source SEG-Y is preserved by Model 2 delete policy.",
            })

        for item in artifacts.get("indexed_preview") or []:
            path = _clean(item.get("path"))
            if path:
                operations["delete_directories"].append({
                    "artifact_type": "indexed_preview",
                    "dataset_id": item.get("dataset_id"),
                    "path": path,
                    "reason": "Source-side indexed preview is derived and should be removed on full dataset delete.",
                })

        for item in artifacts.get("optimized_cache") or []:
            path = _clean(item.get("path"))
            if path:
                operations["delete_directories"].append({
                    "artifact_type": "indexed_optimized_cache",
                    "dataset_id": item.get("dataset_id"),
                    "path": path,
                    "reason": "Optimized cache is derived from indexed preview and should be removed with the graph.",
                })

        for item in artifacts.get("index_jobs") or []:
            path = _clean(item.get("path"))
            if path:
                operations["delete_files"].append({
                    "artifact_type": "source_intake_index_job",
                    "job_id": item.get("job_id"),
                    "path": path,
                    "reason": "Index job record belongs to the source-side indexed preview lifecycle.",
                })

        for item in artifacts.get("managed_zarr") or []:
            path = _clean(item.get("path"))
            if path:
                operations["delete_directories"].append({
                    "artifact_type": "managed_zarr",
                    "dataset_id": item.get("dataset_id"),
                    "representation_id": item.get("representation_id"),
                    "path": path,
                    "reason": "Managed Zarr is the managed derived output being deleted.",
                })

        for item in artifacts.get("msi_representations") or []:
            rid = _clean(item.get("representation_id"))
            if rid:
                operations["delete_records"].append({
                    "record_type": "msi_representation",
                    "representation_id": rid,
                    "dataset_id": item.get("dataset_id"),
                    "reason": "MSI representation record belongs to the graph.",
                })

        for item in artifacts.get("msi_datasets") or []:
            did = _clean(item.get("dataset_id"))
            if did:
                operations["delete_records"].append({
                    "record_type": "msi_dataset",
                    "dataset_id": did,
                    "reason": "MSI dataset record belongs to the graph.",
                })

        for item in artifacts.get("viewer_loads") or []:
            operations["delete_records"].append({
                "record_type": "msi_viewer_load",
                "dataset_id": item.get("dataset_id"),
                "representation_id": item.get("representation_id"),
                "reason": "Viewer-load availability must be cleared with the graph.",
            })

        operations["delete_directories"] = _dedupe(operations["delete_directories"], ["artifact_type", "path"])
        operations["delete_files"] = _dedupe(operations["delete_files"], ["artifact_type", "path"])
        operations["delete_records"] = _dedupe(operations["delete_records"], ["record_type", "dataset_id", "representation_id"])

        if not operations["delete_directories"] and not operations["delete_files"] and not operations["delete_records"]:
            operations["warnings"].append({
                "code": "empty_delete_plan",
                "message": "Graph resolved, but no derived artifacts or records were found for deletion.",
            })

        return {
            "schema_version": "artifact.lifecycle.delete_dry_run.v1",
            "ok": True,
            "dry_run": True,
            "root": graph.get("root"),
            "source": graph.get("source"),
            "graph_summary": graph.get("summary"),
            "operations": operations,
            "summary": {
                "preserve_original_source_count": len(operations["preserve_original_source"]),
                "delete_directory_count": len(operations["delete_directories"]),
                "delete_file_count": len(operations["delete_files"]),
                "delete_record_count": len(operations["delete_records"]),
                "warning_count": len(operations["warnings"]),
                "blocked_count": len(operations["blocked"]),
            },
        }

    def _build_graph(
        self,
        scope_type: str,
        scope_id: str,
        tokens: Set[str],
        source_records: List[Dict[str, Any]],
        msi: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        # Expand through source records, then index records, then MSI records.
        tokens = set(tokens)
        tokens |= self._tokens_from_records(source_records)

        indexed = self._indexed_preview_records(tokens)
        tokens |= self._tokens_from_records(indexed)

        index_jobs = self._index_job_records(tokens)
        tokens |= self._tokens_from_records(index_jobs)

        if msi is None:
            msi = self._msi_records(tokens)
        else:
            # Add any MSI records discovered through source/index expansion.
            expanded_msi = self._msi_records(tokens)
            msi = {
                "datasets": _dedupe(msi.get("datasets", []) + expanded_msi.get("datasets", []), ["dataset_id"]),
                "representations": _dedupe(msi.get("representations", []) + expanded_msi.get("representations", []), ["representation_id"]),
                "viewer_loads": _dedupe(msi.get("viewer_loads", []) + expanded_msi.get("viewer_loads", []), ["representation_id", "dataset_id"]),
            }
        tokens |= self._tokens_from_records(msi.get("datasets", []))
        tokens |= self._tokens_from_records(msi.get("representations", []))

        managed_zarr = self._managed_zarr_artifacts(tokens, msi.get("representations", []))
        optimized_cache = self._optimized_cache_artifacts(indexed)

        source = self._canonical_source(source_records, tokens)

        graph = {
            "schema_version": self.schema_version,
            "root": {"scope_type": scope_type, "scope_id": scope_id},
            "source": source,
            "artifacts": {
                "source_segy": self._source_segy_artifacts(source_records),
                "indexed_preview": indexed,
                "index_jobs": index_jobs,
                "optimized_cache": optimized_cache,
                "managed_zarr": managed_zarr,
                "msi_datasets": msi.get("datasets", []),
                "msi_representations": msi.get("representations", []),
                "viewer_loads": msi.get("viewer_loads", []),
            },
            "actions": {
                "delete_full_graph": {
                    "enabled": bool(indexed or managed_zarr or msi.get("datasets") or msi.get("representations")),
                    "preserve_original_source": True,
                    "implemented": True,
                    "reason": "Graph delete execution is available through guarded backend endpoint.",
                }
            },
            "summary": {},
        }
        graph["summary"] = self._summary(graph)
        return graph

    def _source_records(self, tokens: Set[str]) -> List[Dict[str, Any]]:
        rows = _read_json(DATA_DIR / "registry" / "segy_files.json", [])
        if not isinstance(rows, list):
            rows = []
        matched = [r for r in rows if isinstance(r, dict) and _match(tokens, r)]
        return _dedupe(matched, ["segy_file_id", "candidate_id", "relative_path"])

    def _indexed_preview_records(self, tokens: Set[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        index_root = DATA_DIR / "segy_index"
        if not index_root.exists():
            return []
        for index_json in sorted(index_root.glob("*/segy_index.json")):
            payload = _read_json(index_json, {})
            if not isinstance(payload, dict):
                continue
            dataset_id = _clean(payload.get("dataset_id")) or index_json.parent.name
            enriched = {
                "artifact_type": "indexed_preview",
                "dataset_id": dataset_id,
                "path": str(index_json.parent),
                "index_json": str(index_json),
                "delete_policy": "delete_on_full_dataset_delete",
                **payload,
            }
            if _match(tokens, enriched):
                out.append(enriched)
        return _dedupe(out, ["dataset_id", "path"])

    def _index_job_records(self, tokens: Set[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        jobs_root = DATA_DIR / "source_intake_index_jobs"
        if not jobs_root.exists():
            return []
        for job_json in sorted(jobs_root.glob("*.json")):
            payload = _read_json(job_json, {})
            if not isinstance(payload, dict):
                continue
            enriched = {
                "artifact_type": "source_intake_index_job",
                "path": str(job_json),
                "delete_policy": "delete_on_full_dataset_delete",
                **payload,
            }
            result = payload.get("result")
            if isinstance(result, dict):
                enriched.update({f"result_{k}": v for k, v in result.items() if k in {"dataset_id", "candidate_id", "source_segy_file_id", "source_path", "relative_path"}})
            if _match(tokens, enriched):
                out.append(enriched)
        return _dedupe(out, ["job_id", "path"])

    def _msi_records(self, tokens: Set[str], scope_type: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        result = {"datasets": [], "representations": [], "viewer_loads": []}
        if not MSI_DB.exists():
            return result
        try:
            conn = sqlite3.connect(MSI_DB)
            conn.row_factory = sqlite3.Row
        except Exception:
            return result
        try:
            datasets = [self._row_to_dict(r) for r in conn.execute("SELECT * FROM msi_datasets").fetchall()]
            reps = [self._row_to_dict(r) for r in conn.execute("SELECT * FROM msi_representations").fetchall()]
            loads = [self._row_to_dict(r) for r in conn.execute("SELECT * FROM msi_viewer_loads").fetchall()]
        except Exception:
            conn.close()
            return result
        finally:
            try:
                conn.close()
            except Exception:
                pass

        for d in datasets:
            d["source_reference"] = _json_loads(d.get("source_reference_json"))
            d["delete_policy"] = "delete_record_on_full_dataset_delete"
        for r in reps:
            r["artifact_summary"] = _json_loads(r.get("artifact_summary_json"))
            r["metadata_summary"] = _json_loads(r.get("metadata_summary_json"))
            r["delete_policy"] = "delete_record_on_full_dataset_delete"
        for l in loads:
            l["delete_policy"] = "delete_record_on_full_dataset_delete"

        if scope_type == "msi_dataset":
            matched_datasets = [d for d in datasets if _match(tokens, d)]
            dataset_ids = {_clean(d.get("dataset_id")) for d in matched_datasets}
            matched_reps = [r for r in reps if _clean(r.get("dataset_id")) in dataset_ids or _match(tokens, r)]
        elif scope_type == "msi_representation":
            matched_reps = [r for r in reps if _match(tokens, r)]
            dataset_ids = {_clean(r.get("dataset_id")) for r in matched_reps}
            matched_datasets = [d for d in datasets if _clean(d.get("dataset_id")) in dataset_ids or _match(tokens, d)]
        else:
            matched_datasets = [d for d in datasets if _match(tokens, d)]
            matched_reps = [r for r in reps if _match(tokens, r)]
            dataset_ids = {_clean(d.get("dataset_id")) for d in matched_datasets} | {_clean(r.get("dataset_id")) for r in matched_reps}
            matched_datasets += [d for d in datasets if _clean(d.get("dataset_id")) in dataset_ids]
            matched_reps += [r for r in reps if _clean(r.get("dataset_id")) in dataset_ids]

        rep_ids = {_clean(r.get("representation_id")) for r in matched_reps}
        dataset_ids = {_clean(d.get("dataset_id")) for d in matched_datasets} | {_clean(r.get("dataset_id")) for r in matched_reps}
        matched_loads = [l for l in loads if _clean(l.get("representation_id")) in rep_ids or _clean(l.get("dataset_id")) in dataset_ids]

        result["datasets"] = _dedupe(matched_datasets, ["dataset_id"])
        result["representations"] = _dedupe(matched_reps, ["representation_id"])
        result["viewer_loads"] = _dedupe(matched_loads, ["representation_id", "dataset_id"])
        return result

    def _managed_zarr_artifacts(self, tokens: Set[str], representations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for rep in representations:
            artifact = rep.get("artifact_summary") if isinstance(rep.get("artifact_summary"), dict) else {}
            for value in [
                rep.get("zarr_url"), rep.get("storage_uri"), rep.get("artifact_id"),
                artifact.get("zarr_url"), artifact.get("storage_uri"), artifact.get("path"), artifact.get("artifact_path"),
            ]:
                text = _clean(value)
                if not text:
                    continue
                out.append({
                    "artifact_type": "managed_zarr",
                    "representation_id": rep.get("representation_id"),
                    "dataset_id": rep.get("dataset_id"),
                    "path": text,
                    "delete_policy": "delete_on_full_dataset_delete",
                    "viewer_ready": bool(rep.get("viewer_ready")),
                    "lifecycle_state": rep.get("lifecycle_state"),
                })
        return _dedupe(out, ["representation_id", "path"])

    def _optimized_cache_artifacts(self, indexed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for item in indexed:
            cache = item.get("optimized_cache") if isinstance(item.get("optimized_cache"), dict) else {}
            for value in [cache.get("path"), cache.get("zarr_url"), item.get("optimized_cache_path")]:
                text = _clean(value)
                if text:
                    out.append({
                        "artifact_type": "indexed_optimized_cache",
                        "dataset_id": item.get("dataset_id"),
                        "path": text,
                        "delete_policy": "delete_on_full_dataset_delete",
                    })
        return _dedupe(out, ["dataset_id", "path"])

    def _source_segy_artifacts(self, source_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for row in source_records:
            source_path = row.get("source_path") or row.get("path")
            if not source_path and row.get("relative_path") and row.get("repository_id"):
                source_path = row.get("relative_path")
            out.append({
                "artifact_type": "source_segy",
                "artifact_id": row.get("segy_file_id") or row.get("candidate_id"),
                "candidate_id": row.get("candidate_id") or row.get("segy_file_id"),
                "repository_id": row.get("repository_id"),
                "package_id": row.get("package_id"),
                "relative_path": row.get("relative_path"),
                "path": source_path,
                "delete_policy": "preserve_original",
            })
        return _dedupe(out, ["artifact_id", "relative_path", "path"])

    def _canonical_source(self, source_records: List[Dict[str, Any]], tokens: Set[str]) -> Dict[str, Any]:
        row = source_records[0] if source_records else {}
        return {
            "source_candidate_id": row.get("candidate_id") or row.get("segy_file_id"),
            "source_segy_file_id": row.get("segy_file_id") or row.get("source_segy_file_id"),
            "repository_id": row.get("repository_id"),
            "package_id": row.get("package_id"),
            "line_id": row.get("line_id"),
            "source_path": row.get("source_path") or row.get("path"),
            "relative_path": row.get("relative_path"),
            "filename": row.get("filename") or row.get("display_name"),
            "matched_source_record_count": len(source_records),
        }

    def _validation_payload(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = graph.get("artifacts", {})
        issues: List[Dict[str, Any]] = []
        source_count = len(artifacts.get("source_segy") or [])
        index_count = len(artifacts.get("indexed_preview") or [])
        managed_count = len(artifacts.get("managed_zarr") or [])
        msi_count = len(artifacts.get("msi_representations") or [])

        if index_count and not source_count:
            issues.append({"code": "orphaned_index_without_source_candidate", "severity": "error"})
        if managed_count and not source_count:
            issues.append({"code": "managed_output_without_source_candidate", "severity": "error"})
        if msi_count and not managed_count:
            issues.append({"code": "msi_representation_without_resolved_managed_artifact", "severity": "warning"})
        if not any([source_count, index_count, managed_count, msi_count]):
            issues.append({"code": "empty_artifact_graph", "severity": "warning"})

        return {
            "schema_version": "artifact.lifecycle.validation.v1",
            "ok": not any(i.get("severity") == "error" for i in issues),
            "root": graph.get("root"),
            "summary": graph.get("summary"),
            "issues": issues,
        }

    def _summary(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = graph.get("artifacts", {})
        return {
            "source_segy_count": len(artifacts.get("source_segy") or []),
            "indexed_preview_count": len(artifacts.get("indexed_preview") or []),
            "index_job_count": len(artifacts.get("index_jobs") or []),
            "optimized_cache_count": len(artifacts.get("optimized_cache") or []),
            "managed_zarr_count": len(artifacts.get("managed_zarr") or []),
            "msi_dataset_count": len(artifacts.get("msi_datasets") or []),
            "msi_representation_count": len(artifacts.get("msi_representations") or []),
            "viewer_load_count": len(artifacts.get("viewer_loads") or []),
        }

    def _tokens_from_records(self, records: Iterable[Dict[str, Any]]) -> Set[str]:
        tokens: Set[str] = set()
        for record in records:
            if isinstance(record, dict):
                tokens |= _record_tokens(record)
                for key in ("source_reference", "artifact_summary", "metadata_summary", "geometry_qaqc", "result"):
                    value = record.get(key)
                    if isinstance(value, dict):
                        tokens |= _record_tokens(value)
        return tokens

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {key: row[key] for key in row.keys()}


artifact_lifecycle_service = ArtifactLifecycleService()
