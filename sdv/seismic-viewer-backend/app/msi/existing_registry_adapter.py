from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


class ExistingRegistryAdapter:
    """
    Read-only adapter over the existing source registry JSON files.

    Block 1B-B purpose:
    - inspect and translate existing source registry facts into MSI-style preview data
    - do not mutate registry files
    - do not write MSI SQLite rows
    - do not infer lifecycle from frontend state
    """

    def __init__(self, backend_dir: Path | None = None) -> None:
        self.backend_dir = backend_dir or Path(__file__).resolve().parents[2]
        self.registry_dir = self.backend_dir / "data" / "registry"

    def preview(self, sample_limit: int = 12) -> dict[str, Any]:
        repositories = self._load_list("repositories.json")
        packages = self._load_list("packages.json")
        lines = self._load_list("lines.json")
        segy_files = self._load_list("segy_files.json")

        repo_by_id = {r.get("repository_id"): r for r in repositories if isinstance(r, dict)}
        package_by_id = {p.get("package_id"): p for p in packages if isinstance(p, dict)}
        line_by_id = {l.get("line_id"): l for l in lines if isinstance(l, dict)}

        candidate_kind_counter = Counter()
        candidate_role_counter = Counter()
        conversion_status_counter = Counter()
        relationship_status_counter = Counter()
        repository_counter = Counter()
        dataset_type_counter = Counter()

        sample_datasets: list[dict[str, Any]] = []

        for item in segy_files:
            if not isinstance(item, dict):
                continue

            candidate_kind = self._clean(item.get("candidate_kind")) or "unknown"
            candidate_role = self._clean(item.get("candidate_role")) or "unknown"
            conversion_status = self._clean(item.get("conversion_status")) or "unknown"
            relationship_status = self._clean(item.get("relationship_status")) or "unknown"
            repository_id = self._clean(item.get("repository_id")) or "unknown"

            dataset_type = self._dataset_type_from_candidate_kind(candidate_kind)

            candidate_kind_counter[candidate_kind] += 1
            candidate_role_counter[candidate_role] += 1
            conversion_status_counter[conversion_status] += 1
            relationship_status_counter[relationship_status] += 1
            repository_counter[repository_id] += 1
            dataset_type_counter[dataset_type] += 1

            if len(sample_datasets) < sample_limit:
                repository = repo_by_id.get(item.get("repository_id")) or {}
                package = package_by_id.get(item.get("package_id")) or {}
                line = line_by_id.get(item.get("line_id")) or {}

                sample_datasets.append(
                    {
                        "dataset_id": f"source_segy:{item.get('segy_file_id')}",
                        "source_segy_file_id": item.get("segy_file_id"),
                        "dataset_type": dataset_type,
                        "display_name": item.get("filename") or line.get("display_name") or item.get("relative_path"),
                        "filename": item.get("filename"),
                        "relative_path": item.get("relative_path"),
                        "repository_id": item.get("repository_id"),
                        "repository_name": repository.get("name"),
                        "package_id": item.get("package_id"),
                        "package_name": package.get("display_name"),
                        "line_id": item.get("line_id"),
                        "line_name": line.get("display_name") or line.get("line_key"),
                        "candidate_kind": candidate_kind,
                        "candidate_role": candidate_role,
                        "classification_source": item.get("classification_source"),
                        "classification_confidence": item.get("classification_confidence"),
                        "classification_reasons": item.get("classification_reasons") or [],
                        "conversion_status": conversion_status,
                        "relationship_status": relationship_status,
                        "volume_id": item.get("volume_id"),
                        "size_bytes": item.get("size_bytes"),
                    }
                )

        return {
            "adapter": "existing_source_registry",
            "mode": "read_only_preview",
            "registry_dir": str(self.registry_dir),
            "source_files": {
                "repositories": len(repositories),
                "packages": len(packages),
                "lines": len(lines),
                "segy_files": len(segy_files),
            },
            "datasets": len(segy_files),
            "by_dataset_type": dict(sorted(dataset_type_counter.items())),
            "by_candidate_kind": dict(sorted(candidate_kind_counter.items())),
            "by_candidate_role": dict(sorted(candidate_role_counter.items())),
            "by_conversion_status": dict(sorted(conversion_status_counter.items())),
            "by_relationship_status": dict(sorted(relationship_status_counter.items())),
            "by_repository_id": dict(sorted(repository_counter.items())),
            "sample_limit": sample_limit,
            "sample_datasets": sample_datasets,
            "writes_performed": False,
        }


    def artifact_presence_preview(self, sample_limit: int = 20) -> dict[str, Any]:
        """
        Read-only artifact correlation preview.

        Correlates existing source registry SEG-Y records with existing artifact
        directories under data/segy_index and data/zarr.

        This does not write MSI records and does not mutate existing registries.
        """
        segy_files = self._load_list("segy_files.json")

        segy_index_dir = self.backend_dir / "data" / "segy_index"
        zarr_dir = self.backend_dir / "data" / "zarr"

        index_artifacts = self._discover_index_artifacts(segy_index_dir)
        zarr_artifacts = self._discover_zarr_artifacts(zarr_dir)

        rows: list[dict[str, Any]] = []
        representation_counter = Counter()
        viewer_ready_counter = Counter()
        artifact_state_counter = Counter()

        for item in segy_files:
            if not isinstance(item, dict):
                continue

            segy_file_id = self._clean(item.get("segy_file_id")) or ""
            candidate_kind = self._clean(item.get("candidate_kind")) or "unknown"
            dataset_type = self._dataset_type_from_candidate_kind(candidate_kind)
            conversion_status = self._clean(item.get("conversion_status")) or "unknown"

            index_matches = self._match_index_artifacts(segy_file_id, item, index_artifacts)
            zarr_matches = self._match_zarr_artifacts(segy_file_id, item, zarr_artifacts)

            inferred_representations: list[dict[str, Any]] = []

            for artifact in index_matches:
                if dataset_type == "2d_line":
                    representation_type = "indexed_segy_2d"
                    viewer_mode = "2d"
                    viewer_ready = True
                else:
                    representation_type = "unknown"
                    viewer_mode = "none"
                    viewer_ready = False

                inferred_representations.append(
                    {
                        "representation_type": representation_type,
                        "viewer_mode": viewer_mode,
                        "viewer_ready": viewer_ready,
                        "artifact_kind": "segy_index",
                        "storage_uri": artifact["storage_uri"],
                        "evidence": artifact["evidence"],
                    }
                )

            for artifact in zarr_matches:
                if dataset_type == "3d_volume":
                    representation_type = "zarr_3d"
                    viewer_mode = "3d"
                    viewer_ready = True
                elif dataset_type == "2d_line":
                    representation_type = "zarr_2d"
                    viewer_mode = "2d"
                    viewer_ready = True
                else:
                    representation_type = "unknown"
                    viewer_mode = "none"
                    viewer_ready = False

                inferred_representations.append(
                    {
                        "representation_type": representation_type,
                        "viewer_mode": viewer_mode,
                        "viewer_ready": viewer_ready,
                        "artifact_kind": "zarr",
                        "storage_uri": artifact["storage_uri"],
                        "evidence": artifact["evidence"],
                    }
                )

            if inferred_representations:
                artifact_state = "artifact_present"
            elif conversion_status == "converted":
                artifact_state = "registry_says_converted_but_no_artifact_matched"
            elif conversion_status == "error":
                artifact_state = "conversion_error"
            else:
                artifact_state = "no_artifact_matched"

            artifact_state_counter[artifact_state] += 1

            for rep in inferred_representations:
                representation_counter[rep["representation_type"]] += 1
                viewer_ready_counter["viewer_ready" if rep["viewer_ready"] else "not_viewer_ready"] += 1

            if len(rows) < sample_limit or inferred_representations or artifact_state != "no_artifact_matched":
                rows.append(
                    {
                        "dataset_id": f"source_segy:{segy_file_id}",
                        "source_segy_file_id": segy_file_id,
                        "dataset_type": dataset_type,
                        "filename": item.get("filename"),
                        "relative_path": item.get("relative_path"),
                        "candidate_kind": candidate_kind,
                        "candidate_role": item.get("candidate_role"),
                        "conversion_status": conversion_status,
                        "artifact_state": artifact_state,
                        "inferred_representations": inferred_representations,
                    }
                )

        # Keep response bounded, but always bias toward rows with artifacts/anomalies.
        priority_rows = [
            r for r in rows
            if r["inferred_representations"] or r["artifact_state"] != "no_artifact_matched"
        ]
        ordinary_rows = [
            r for r in rows
            if not r["inferred_representations"] and r["artifact_state"] == "no_artifact_matched"
        ]
        sample_rows = (priority_rows + ordinary_rows)[:sample_limit]

        return {
            "adapter": "existing_source_registry",
            "mode": "artifact_presence_preview_read_only",
            "registry_dir": str(self.registry_dir),
            "artifact_dirs": {
                "segy_index": str(segy_index_dir),
                "zarr": str(zarr_dir),
            },
            "source_counts": {
                "segy_files": len(segy_files),
                "index_artifact_dirs": len(index_artifacts),
                "zarr_artifact_dirs": len(zarr_artifacts),
            },
            "by_artifact_state": dict(sorted(artifact_state_counter.items())),
            "by_inferred_representation_type": dict(sorted(representation_counter.items())),
            "by_viewer_ready": dict(sorted(viewer_ready_counter.items())),
            "sample_limit": sample_limit,
            "sample_datasets": sample_rows,
            "writes_performed": False,
        }

    def _discover_index_artifacts(self, segy_index_dir: Path) -> dict[str, dict[str, Any]]:
        artifacts: dict[str, dict[str, Any]] = {}

        if not segy_index_dir.exists():
            return artifacts

        for path in sorted(segy_index_dir.iterdir()):
            if not path.is_dir():
                continue

            index_json = path / "segy_index.json"
            evidence = {
                "folder_name": path.name,
                "has_segy_index_json": index_json.exists(),
                "has_text_header": (path / "segy_text_header.txt").exists(),
                "has_binary_header": (path / "segy_binary_header.json").exists(),
                "has_trace_arrays": any(path.glob("trace_*.npy")),
            }

            artifact_id = path.name
            artifacts[artifact_id] = {
                "artifact_id": artifact_id,
                "path": path,
                "storage_uri": f"local://segy_index/{path.name}",
                "evidence": evidence,
            }

        return artifacts

    def _discover_zarr_artifacts(self, zarr_dir: Path) -> dict[str, dict[str, Any]]:
        artifacts: dict[str, dict[str, Any]] = {}

        if not zarr_dir.exists():
            return artifacts

        for path in sorted(zarr_dir.iterdir()):
            if not path.is_dir() or not path.name.endswith(".zarr"):
                continue

            evidence = {
                "folder_name": path.name,
                "has_zarr_json": (path / "zarr.json").exists(),
                "has_zattrs": (path / ".zattrs").exists(),
                "has_normalized_metadata": (path / ".normalized_metadata.json").exists(),
                "looks_optimized": "-optimized-" in path.name,
            }

            artifact_id = path.name[:-5] if path.name.endswith(".zarr") else path.name
            artifacts[artifact_id] = {
                "artifact_id": artifact_id,
                "path": path,
                "storage_uri": f"local://zarr/{path.name}",
                "evidence": evidence,
            }

        return artifacts

    def _match_index_artifacts(
        self,
        segy_file_id: str,
        item: dict[str, Any],
        index_artifacts: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidates = self._artifact_match_keys(segy_file_id, item)
        matches = []
        for key in candidates:
            artifact = index_artifacts.get(key)
            if artifact:
                matches.append(artifact)
        return matches

    def _match_zarr_artifacts(
        self,
        segy_file_id: str,
        item: dict[str, Any],
        zarr_artifacts: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidates = self._artifact_match_keys(segy_file_id, item)
        matches: list[dict[str, Any]] = []

        for artifact_id, artifact in zarr_artifacts.items():
            if artifact_id in candidates:
                matches.append(artifact)
                continue

            # Optimized Zarr folders are commonly named:
            # <source-or-index-id>-optimized-<hash>.zarr
            for key in candidates:
                if artifact_id.startswith(f"{key}-optimized-"):
                    matches.append(artifact)
                    break

        return matches

    @staticmethod
    def _artifact_match_keys(segy_file_id: str, item: dict[str, Any]) -> list[str]:
        keys = []

        for value in [
            segy_file_id,
            str(segy_file_id).replace("segy_", "", 1),
            item.get("volume_id"),
            item.get("line_id"),
        ]:
            if value is None:
                continue
            text = str(value).strip()
            if text and text not in keys:
                keys.append(text)

        return keys


    def artifact_metadata_correlation_inspection(self, sample_limit: int = 50) -> dict[str, Any]:
        """
        Read-only artifact metadata inspection.

        Purpose:
        - inspect index and Zarr sidecar metadata
        - extract possible correlation keys
        - identify whether artifacts can be linked to registry SEG-Y records
        - do not write MSI records
        - do not mutate source registry or artifacts
        """
        segy_files = self._load_list("segy_files.json")
        registry_lookup = self._build_registry_lookup(segy_files)

        index_dir = self.backend_dir / "data" / "segy_index"
        zarr_dir = self.backend_dir / "data" / "zarr"

        index_rows = self._inspect_index_metadata(index_dir, registry_lookup)
        zarr_rows = self._inspect_zarr_metadata(zarr_dir, registry_lookup)

        matched_index = [r for r in index_rows if r.get("matched_registry_records")]
        unmatched_index = [r for r in index_rows if not r.get("matched_registry_records")]
        matched_zarr = [r for r in zarr_rows if r.get("matched_registry_records")]
        unmatched_zarr = [r for r in zarr_rows if not r.get("matched_registry_records")]

        return {
            "adapter": "existing_source_registry",
            "mode": "artifact_metadata_correlation_inspection_read_only",
            "registry_dir": str(self.registry_dir),
            "artifact_dirs": {
                "segy_index": str(index_dir),
                "zarr": str(zarr_dir),
            },
            "source_counts": {
                "registry_segy_files": len(segy_files),
                "index_artifacts": len(index_rows),
                "zarr_artifacts": len(zarr_rows),
            },
            "correlation_counts": {
                "index_matched": len(matched_index),
                "index_unmatched": len(unmatched_index),
                "zarr_matched": len(matched_zarr),
                "zarr_unmatched": len(unmatched_zarr),
            },
            "sample_limit": sample_limit,
            "index_artifacts": index_rows[:sample_limit],
            "zarr_artifacts": zarr_rows[:sample_limit],
            "writes_performed": False,
        }

    def _build_registry_lookup(self, segy_files: list[Any]) -> dict[str, list[dict[str, Any]]]:
        lookup: dict[str, list[dict[str, Any]]] = {}

        def add(key: Any, item: dict[str, Any]) -> None:
            if key is None:
                return
            text = str(key).strip()
            if not text:
                return
            lookup.setdefault(text, []).append(item)

        for item in segy_files:
            if not isinstance(item, dict):
                continue

            segy_file_id = item.get("segy_file_id")
            filename = item.get("filename")
            relative_path = item.get("relative_path")
            line_id = item.get("line_id")
            volume_id = item.get("volume_id")

            add(segy_file_id, item)
            if isinstance(segy_file_id, str) and segy_file_id.startswith("segy_"):
                add(segy_file_id.replace("segy_", "", 1), item)

            add(filename, item)
            add(relative_path, item)
            if relative_path:
                add(Path(str(relative_path)).name, item)

            add(line_id, item)
            add(volume_id, item)

        return lookup

    def _registry_matches_for_keys(
        self,
        keys: list[Any],
        registry_lookup: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        seen: set[str] = set()
        matches: list[dict[str, Any]] = []

        for key in keys:
            if key is None:
                continue
            text = str(key).strip()
            if not text:
                continue

            for item in registry_lookup.get(text, []):
                segy_file_id = str(item.get("segy_file_id") or "")
                if not segy_file_id or segy_file_id in seen:
                    continue

                seen.add(segy_file_id)
                matches.append(
                    {
                        "segy_file_id": item.get("segy_file_id"),
                        "filename": item.get("filename"),
                        "relative_path": item.get("relative_path"),
                        "candidate_kind": item.get("candidate_kind"),
                        "candidate_role": item.get("candidate_role"),
                        "conversion_status": item.get("conversion_status"),
                        "line_id": item.get("line_id"),
                        "volume_id": item.get("volume_id"),
                    }
                )

        return matches

    def _inspect_index_metadata(
        self,
        index_dir: Path,
        registry_lookup: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        if not index_dir.exists():
            return rows

        for folder in sorted(index_dir.iterdir()):
            if not folder.is_dir():
                continue

            index_json_path = folder / "segy_index.json"
            binary_header_path = folder / "segy_binary_header.json"
            decode_path = folder / "segy_text_header_decode.json"
            text_header_path = folder / "segy_text_header.txt"

            index_json = self._load_json_file(index_json_path)
            binary_header = self._load_json_file(binary_header_path)
            decode_json = self._load_json_file(decode_path)

            possible_keys = [folder.name]

            possible_keys.extend(self._extract_leaf_values(index_json, key_hints=[
                "source", "path", "filename", "file", "segy", "dataset", "line", "volume", "id", "hash"
            ]))
            possible_keys.extend(self._extract_leaf_values(binary_header, key_hints=[
                "source", "path", "filename", "file", "segy", "dataset", "line", "volume", "id", "hash"
            ]))
            possible_keys.extend(self._extract_leaf_values(decode_json, key_hints=[
                "source", "path", "filename", "file", "segy", "dataset", "line", "volume", "id", "hash"
            ]))

            text_header_excerpt = ""
            if text_header_path.exists():
                try:
                    text_header_excerpt = text_header_path.read_text(
                        encoding="utf-8",
                        errors="ignore",
                    )[:1000]
                except Exception:
                    text_header_excerpt = ""

            matches = self._registry_matches_for_keys(possible_keys, registry_lookup)

            rows.append(
                {
                    "artifact_kind": "segy_index",
                    "folder_name": folder.name,
                    "storage_uri": f"local://segy_index/{folder.name}",
                    "sidecars": {
                        "has_segy_index_json": index_json_path.exists(),
                        "has_binary_header": binary_header_path.exists(),
                        "has_decode_json": decode_path.exists(),
                        "has_text_header": text_header_path.exists(),
                        "has_trace_arrays": any(folder.glob("trace_*.npy")),
                    },
                    "index_json_top_keys": sorted(index_json.keys()) if isinstance(index_json, dict) else [],
                    "binary_header_top_keys": sorted(binary_header.keys()) if isinstance(binary_header, dict) else [],
                    "decode_json_top_keys": sorted(decode_json.keys()) if isinstance(decode_json, dict) else [],
                    "possible_correlation_keys": self._dedupe_strings(possible_keys)[:80],
                    "matched_registry_records": matches,
                    "text_header_excerpt": text_header_excerpt,
                }
            )

        return rows

    def _inspect_zarr_metadata(
        self,
        zarr_dir: Path,
        registry_lookup: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        if not zarr_dir.exists():
            return rows

        for folder in sorted(zarr_dir.iterdir()):
            if not folder.is_dir() or not folder.name.endswith(".zarr"):
                continue

            zarr_json_path = folder / "zarr.json"
            zattrs_path = folder / ".zattrs"
            normalized_path = folder / ".normalized_metadata.json"
            viewer_metadata_path = folder / "viewer_metadata.json"

            zarr_json = self._load_json_file(zarr_json_path)
            zattrs = self._load_json_file(zattrs_path)
            normalized = self._load_json_file(normalized_path)
            viewer_metadata = self._load_json_file(viewer_metadata_path)

            artifact_id = folder.name[:-5]
            possible_keys = [
                folder.name,
                artifact_id,
            ]

            if "-optimized-" in artifact_id:
                possible_keys.append(artifact_id.split("-optimized-", 1)[0])

            for payload in [zarr_json, zattrs, normalized, viewer_metadata]:
                possible_keys.extend(self._extract_leaf_values(payload, key_hints=[
                    "source", "path", "filename", "file", "segy", "dataset", "line", "volume", "id", "hash", "survey"
                ]))

            matches = self._registry_matches_for_keys(possible_keys, registry_lookup)

            rows.append(
                {
                    "artifact_kind": "zarr",
                    "folder_name": folder.name,
                    "storage_uri": f"local://zarr/{folder.name}",
                    "sidecars": {
                        "has_zarr_json": zarr_json_path.exists(),
                        "has_zattrs": zattrs_path.exists(),
                        "has_normalized_metadata": normalized_path.exists(),
                        "has_viewer_metadata": viewer_metadata_path.exists(),
                        "looks_optimized": "-optimized-" in folder.name,
                    },
                    "zarr_json_top_keys": sorted(zarr_json.keys()) if isinstance(zarr_json, dict) else [],
                    "zattrs_top_keys": sorted(zattrs.keys()) if isinstance(zattrs, dict) else [],
                    "normalized_top_keys": sorted(normalized.keys()) if isinstance(normalized, dict) else [],
                    "viewer_metadata_top_keys": sorted(viewer_metadata.keys()) if isinstance(viewer_metadata, dict) else [],
                    "possible_correlation_keys": self._dedupe_strings(possible_keys)[:120],
                    "matched_registry_records": matches,
                    "normalized_identity_preview": self._normalized_identity_preview(normalized),
                }
            )

        return rows

    def _load_json_file(self, path: Path) -> Any:
        if not path.exists() or not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return {}

    def _extract_leaf_values(
        self,
        payload: Any,
        key_hints: list[str],
        max_values: int = 80,
    ) -> list[str]:
        values: list[str] = []

        def walk(obj: Any, path: str = "") -> None:
            if len(values) >= max_values:
                return

            if isinstance(obj, dict):
                for key, value in obj.items():
                    key_text = str(key).lower()
                    new_path = f"{path}.{key}" if path else str(key)
                    hint_match = any(hint in key_text for hint in key_hints)

                    if hint_match and isinstance(value, (str, int, float)):
                        values.append(str(value))

                    if isinstance(value, (dict, list)):
                        walk(value, new_path)
                    elif hint_match and isinstance(value, list):
                        for item in value[:10]:
                            if isinstance(item, (str, int, float)):
                                values.append(str(item))

            elif isinstance(obj, list):
                for item in obj[:50]:
                    walk(item, path)

        walk(payload)
        return values

    @staticmethod
    def _dedupe_strings(values: list[Any]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []

        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)

        return out

    @staticmethod
    def _normalized_identity_preview(normalized: Any) -> dict[str, Any]:
        if not isinstance(normalized, dict):
            return {}

        identity = normalized.get("identity")
        if isinstance(identity, dict):
            return {
                "survey_name": identity.get("survey_name"),
                "line_name": identity.get("line_name"),
                "volume_name": identity.get("volume_name"),
                "dataset_type": identity.get("dataset_type"),
                "processing_stage": identity.get("processing_stage"),
                "processing_version": identity.get("processing_version"),
            }

        return {}


    def representation_candidate_preview(self, sample_limit: int = 80) -> dict[str, Any]:
        """
        Read-only MSI representation candidate preview.

        Purpose:
        - build candidate MSI-style representations from existing registry/artifact evidence
        - do not write MSI SQLite rows
        - do not mutate source registry or artifact folders
        - do not imply current test content is definitive production MSI content
        """
        segy_files = self._load_list("segy_files.json")
        registry_by_segy_id = {
            item.get("segy_file_id"): item
            for item in segy_files
            if isinstance(item, dict) and item.get("segy_file_id")
        }

        index_dir = self.backend_dir / "data" / "segy_index"
        zarr_dir = self.backend_dir / "data" / "zarr"

        index_artifacts = self._index_artifacts_by_source_segy_id(index_dir)
        full_zarr_by_volume_id = self._full_zarr_artifacts_by_volume_id(zarr_dir)
        optimized_zarr_by_index_id = self._optimized_zarr_artifacts_by_index_id(zarr_dir)

        dataset_rows: list[dict[str, Any]] = []
        representation_type_counts = Counter()
        viewer_ready_counts = Counter()
        preferred_counts = Counter()
        dataset_candidate_state_counts = Counter()

        for segy_file_id, item in registry_by_segy_id.items():
            candidate_kind = self._clean(item.get("candidate_kind")) or "unknown"
            dataset_type = self._dataset_type_from_candidate_kind(candidate_kind)
            conversion_status = self._clean(item.get("conversion_status")) or "unknown"
            volume_id = self._clean(item.get("volume_id"))

            candidates: list[dict[str, Any]] = []

            # 1. Indexed SEG-Y artifact candidate.
            index_artifact = index_artifacts.get(segy_file_id)
            if index_artifact:
                index_id = index_artifact["index_id"]

                # Indexed 2D can be a fallback viewing representation.
                # Indexed 3D is not treated as normal full viewer-ready volume data.
                if dataset_type == "2d_line":
                    representation_type = "indexed_segy_2d"
                    viewer_mode = "2d"
                    viewer_ready = True
                    preferred_candidate = False
                    lifecycle_state = "viewer_ready"
                    role = "fallback_view"
                elif dataset_type == "3d_volume":
                    representation_type = "indexed_segy_headers"
                    viewer_mode = "none"
                    viewer_ready = False
                    preferred_candidate = False
                    lifecycle_state = "metadata_ready"
                    role = "metadata_and_cache_source"
                else:
                    representation_type = "indexed_segy_unknown"
                    viewer_mode = "none"
                    viewer_ready = False
                    preferred_candidate = False
                    lifecycle_state = "review_required"
                    role = "review_required"

                candidates.append(
                    {
                        "candidate_representation_id": f"candidate:index:{index_id}",
                        "representation_type": representation_type,
                        "viewer_mode": viewer_mode,
                        "viewer_ready": viewer_ready,
                        "preferred_candidate": preferred_candidate,
                        "lifecycle_state": lifecycle_state,
                        "role": role,
                        "storage_uri": index_artifact["storage_uri"],
                        "evidence_chain": index_artifact["evidence_chain"],
                    }
                )

                # 2. Optimized Zarr cache derived from index artifact.
                for optimized in optimized_zarr_by_index_id.get(index_id, []):
                    if dataset_type == "3d_volume":
                        representation_type = "optimized_zarr_3d_cache"
                        viewer_mode = "3d"
                        viewer_ready = True
                        lifecycle_state = "viewer_ready"
                        role = "optimized_view_cache"
                    elif dataset_type == "2d_line":
                        representation_type = "optimized_zarr_2d_cache"
                        viewer_mode = "2d"
                        viewer_ready = True
                        lifecycle_state = "viewer_ready"
                        role = "optimized_view_cache"
                    else:
                        representation_type = "optimized_zarr_unknown_cache"
                        viewer_mode = "none"
                        viewer_ready = False
                        lifecycle_state = "review_required"
                        role = "review_required"

                    candidates.append(
                        {
                            "candidate_representation_id": f"candidate:optimized_zarr:{optimized['artifact_id']}",
                            "representation_type": representation_type,
                            "viewer_mode": viewer_mode,
                            "viewer_ready": viewer_ready,
                            "preferred_candidate": False,
                            "lifecycle_state": lifecycle_state,
                            "role": role,
                            "storage_uri": optimized["storage_uri"],
                            "evidence_chain": optimized["evidence_chain"] + index_artifact["evidence_chain"],
                        }
                    )

            # 3. Full converted Zarr candidate by volume_id.
            if volume_id and volume_id in full_zarr_by_volume_id:
                zarr_artifact = full_zarr_by_volume_id[volume_id]

                if dataset_type == "3d_volume":
                    representation_type = "zarr_3d"
                    viewer_mode = "3d"
                    viewer_ready = True
                    lifecycle_state = "viewer_ready"
                    role = "full_view"
                elif dataset_type == "2d_line":
                    representation_type = "zarr_2d"
                    viewer_mode = "2d"
                    viewer_ready = True
                    lifecycle_state = "viewer_ready"
                    role = "full_view"
                else:
                    representation_type = "zarr_unknown"
                    viewer_mode = "none"
                    viewer_ready = False
                    lifecycle_state = "review_required"
                    role = "review_required"

                candidates.append(
                    {
                        "candidate_representation_id": f"candidate:zarr:{volume_id}",
                        "representation_type": representation_type,
                        "viewer_mode": viewer_mode,
                        "viewer_ready": viewer_ready,
                        "preferred_candidate": True,
                        "lifecycle_state": lifecycle_state,
                        "role": role,
                        "storage_uri": zarr_artifact["storage_uri"],
                        "evidence_chain": zarr_artifact["evidence_chain"],
                    }
                )

            # Preferred-candidate rule:
            # - full Zarr preferred over optimized cache
            # - optimized cache preferred over indexed SEG-Y fallback
            # - indexed SEG-Y 2D remains fallback only
            preferred = self._select_preferred_candidate(candidates)
            for candidate in candidates:
                candidate["preferred_candidate"] = (
                    preferred is not None
                    and candidate["candidate_representation_id"] == preferred["candidate_representation_id"]
                )

            if candidates:
                dataset_candidate_state = "has_candidates"
            elif conversion_status == "error":
                dataset_candidate_state = "conversion_error_no_candidate"
            else:
                dataset_candidate_state = "no_candidate"

            dataset_candidate_state_counts[dataset_candidate_state] += 1

            for candidate in candidates:
                representation_type_counts[candidate["representation_type"]] += 1
                viewer_ready_counts["viewer_ready" if candidate["viewer_ready"] else "not_viewer_ready"] += 1
                preferred_counts["preferred" if candidate["preferred_candidate"] else "not_preferred"] += 1

            if candidates or dataset_candidate_state != "no_candidate" or len(dataset_rows) < sample_limit:
                dataset_rows.append(
                    {
                        "dataset_id": f"source_segy:{segy_file_id}",
                        "source_segy_file_id": segy_file_id,
                        "dataset_type": dataset_type,
                        "display_name": item.get("filename") or item.get("relative_path"),
                        "filename": item.get("filename"),
                        "relative_path": item.get("relative_path"),
                        "candidate_kind": item.get("candidate_kind"),
                        "candidate_role": item.get("candidate_role"),
                        "conversion_status": conversion_status,
                        "volume_id": volume_id,
                        "candidate_state": dataset_candidate_state,
                        "candidate_representations": candidates,
                    }
                )

        priority_rows = [
            row for row in dataset_rows
            if row["candidate_representations"] or row["candidate_state"] != "no_candidate"
        ]
        ordinary_rows = [
            row for row in dataset_rows
            if not row["candidate_representations"] and row["candidate_state"] == "no_candidate"
        ]
        sample_rows = (priority_rows + ordinary_rows)[:sample_limit]

        return {
            "adapter": "existing_source_registry",
            "mode": "representation_candidate_preview_read_only",
            "source_counts": {
                "registry_segy_files": len(segy_files),
                "index_artifacts_by_source_segy_id": len(index_artifacts),
                "full_zarr_artifacts_by_volume_id": len(full_zarr_by_volume_id),
                "optimized_zarr_index_groups": len(optimized_zarr_by_index_id),
            },
            "by_dataset_candidate_state": dict(sorted(dataset_candidate_state_counts.items())),
            "by_representation_type": dict(sorted(representation_type_counts.items())),
            "by_viewer_ready": dict(sorted(viewer_ready_counts.items())),
            "by_preferred": dict(sorted(preferred_counts.items())),
            "sample_limit": sample_limit,
            "sample_datasets": sample_rows,
            "writes_performed": False,
            "test_content_notice": "Current registry/artifact content is temporary build/test content, not definitive production MSI inventory.",
        }

    def _index_artifacts_by_source_segy_id(self, index_dir: Path) -> dict[str, dict[str, Any]]:
        artifacts: dict[str, dict[str, Any]] = {}

        if not index_dir.exists():
            return artifacts

        for folder in sorted(index_dir.iterdir()):
            if not folder.is_dir():
                continue

            index_json = self._load_json_file(folder / "segy_index.json")
            if not isinstance(index_json, dict):
                continue

            source_segy_file_id = self._clean(index_json.get("source_segy_file_id"))
            if not source_segy_file_id:
                continue

            index_id = folder.name
            artifacts[source_segy_file_id] = {
                "index_id": index_id,
                "storage_uri": f"local://segy_index/{index_id}",
                "index_json": index_json,
                "evidence_chain": [
                    {
                        "evidence_type": "segy_index_json",
                        "artifact_uri": f"local://segy_index/{index_id}/segy_index.json",
                        "matched_on": "source_segy_file_id",
                        "matched_value": source_segy_file_id,
                        "confidence": "high",
                    }
                ],
            }

        return artifacts

    def _full_zarr_artifacts_by_volume_id(self, zarr_dir: Path) -> dict[str, dict[str, Any]]:
        artifacts: dict[str, dict[str, Any]] = {}

        if not zarr_dir.exists():
            return artifacts

        for folder in sorted(zarr_dir.iterdir()):
            if not folder.is_dir() or not folder.name.endswith(".zarr"):
                continue

            if "-optimized-" in folder.name:
                continue

            volume_id = folder.name[:-5]
            artifacts[volume_id] = {
                "volume_id": volume_id,
                "storage_uri": f"local://zarr/{folder.name}",
                "evidence_chain": [
                    {
                        "evidence_type": "zarr_folder_name",
                        "artifact_uri": f"local://zarr/{folder.name}",
                        "matched_on": "volume_id",
                        "matched_value": volume_id,
                        "confidence": "high",
                    }
                ],
            }

        return artifacts

    def _optimized_zarr_artifacts_by_index_id(self, zarr_dir: Path) -> dict[str, list[dict[str, Any]]]:
        artifacts: dict[str, list[dict[str, Any]]] = {}

        if not zarr_dir.exists():
            return artifacts

        for folder in sorted(zarr_dir.iterdir()):
            if not folder.is_dir() or not folder.name.endswith(".zarr"):
                continue

            artifact_id = folder.name[:-5]
            if "-optimized-" not in artifact_id:
                continue

            index_id = artifact_id.split("-optimized-", 1)[0]
            artifacts.setdefault(index_id, []).append(
                {
                    "artifact_id": artifact_id,
                    "index_id": index_id,
                    "storage_uri": f"local://zarr/{folder.name}",
                    "evidence_chain": [
                        {
                            "evidence_type": "optimized_zarr_folder_prefix",
                            "artifact_uri": f"local://zarr/{folder.name}",
                            "matched_on": "index_artifact_id_prefix",
                            "matched_value": index_id,
                            "confidence": "medium",
                        }
                    ],
                }
            )

        return artifacts

    @staticmethod
    def _select_preferred_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not candidates:
            return None

        rank_by_type = {
            "zarr_3d": 100,
            "zarr_2d": 95,
            "optimized_zarr_3d_cache": 80,
            "optimized_zarr_2d_cache": 75,
            "indexed_segy_2d": 50,
            "indexed_segy_headers": 10,
        }

        ready_candidates = [c for c in candidates if c.get("viewer_ready")]
        pool = ready_candidates or candidates

        return sorted(
            pool,
            key=lambda c: (
                rank_by_type.get(str(c.get("representation_type")), 0),
                1 if c.get("storage_uri") else 0,
            ),
            reverse=True,
        )[0]


    def test_seed_plan_preview(self, sample_limit: int = 100) -> dict[str, Any]:
        """
        Dry-run MSI seed plan.

        Purpose:
        - show exactly what would be inserted into MSI SQLite
        - do not perform writes
        - explicitly mark all rows as test/build content
        - preserve the later clean-curated reload path
        """
        candidate_preview = self.representation_candidate_preview(sample_limit=10_000)
        candidate_rows = candidate_preview.get("sample_datasets", [])

        datasets_to_seed: list[dict[str, Any]] = []
        representations_to_seed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for row in candidate_rows:
            candidate_representations = row.get("candidate_representations") or []

            if not candidate_representations:
                skipped.append(
                    {
                        "dataset_id": row.get("dataset_id"),
                        "source_segy_file_id": row.get("source_segy_file_id"),
                        "reason": row.get("candidate_state") or "no_candidate_representations",
                        "conversion_status": row.get("conversion_status"),
                        "dataset_type": row.get("dataset_type"),
                        "display_name": row.get("display_name"),
                    }
                )
                continue

            dataset_id = row.get("dataset_id")
            source_segy_file_id = row.get("source_segy_file_id")

            datasets_to_seed.append(
                {
                    "dataset_id": dataset_id,
                    "dataset_type": row.get("dataset_type") or "unknown",
                    "display_name": row.get("display_name") or row.get("filename") or source_segy_file_id,
                    "survey_name": None,
                    "line_name": None,
                    "volume_name": None,
                    "processing_stage": None,
                    "processing_version": None,
                    "registration_state": "test_seed_candidate",
                    "source_reference": {
                        "source_system": "existing_source_registry",
                        "source_segy_file_id": source_segy_file_id,
                        "filename": row.get("filename"),
                        "relative_path": row.get("relative_path"),
                        "candidate_kind": row.get("candidate_kind"),
                        "candidate_role": row.get("candidate_role"),
                        "conversion_status": row.get("conversion_status"),
                        "volume_id": row.get("volume_id"),
                        "test_content": True,
                    },
                }
            )

            for rep in candidate_representations:
                rep_id = self._candidate_representation_id_to_msi_id(
                    dataset_id=dataset_id,
                    candidate_representation_id=rep.get("candidate_representation_id"),
                )

                representations_to_seed.append(
                    {
                        "representation_id": rep_id,
                        "dataset_id": dataset_id,
                        "representation_type": rep.get("representation_type") or "unknown",
                        "viewer_mode": rep.get("viewer_mode") or "none",
                        "storage_uri": rep.get("storage_uri"),
                        "lifecycle_state": rep.get("lifecycle_state") or "not_created",
                        "viewer_ready": bool(rep.get("viewer_ready")),
                        "is_preferred": bool(rep.get("preferred_candidate")),
                        "artifact_summary": {
                            "role": rep.get("role"),
                            "evidence_chain": rep.get("evidence_chain") or [],
                            "test_content": True,
                            "source": "test_seed_plan_preview",
                        },
                    }
                )

        return {
            "adapter": "existing_source_registry",
            "mode": "test_seed_plan_preview_dry_run",
            "datasets_to_seed_count": len(datasets_to_seed),
            "representations_to_seed_count": len(representations_to_seed),
            "skipped_count": len(skipped),
            "by_dataset_type": self._count_key(datasets_to_seed, "dataset_type"),
            "by_representation_type": self._count_key(representations_to_seed, "representation_type"),
            "by_viewer_ready": {
                "viewer_ready": sum(1 for r in representations_to_seed if r.get("viewer_ready")),
                "not_viewer_ready": sum(1 for r in representations_to_seed if not r.get("viewer_ready")),
            },
            "by_preferred": {
                "preferred": sum(1 for r in representations_to_seed if r.get("is_preferred")),
                "not_preferred": sum(1 for r in representations_to_seed if not r.get("is_preferred")),
            },
            "sample_limit": sample_limit,
            "datasets_to_seed": datasets_to_seed[:sample_limit],
            "representations_to_seed": representations_to_seed[:sample_limit],
            "skipped": skipped[:sample_limit],
            "writes_performed": False,
            "test_seed_notice": (
                "Dry run only. These rows are derived from temporary build/test registry and artifact state. "
                "They must not be treated as definitive production MSI inventory. "
                "When MSI/lifecycle work is complete, loaded/managed test content should be purged and a clean curated source set reloaded."
            ),
        }

    @staticmethod
    def _candidate_representation_id_to_msi_id(
        dataset_id: Any,
        candidate_representation_id: Any,
    ) -> str:
        dataset_text = str(dataset_id or "unknown").replace(":", "_")
        candidate_text = str(candidate_representation_id or "candidate_unknown")
        candidate_text = candidate_text.replace("candidate:", "").replace(":", "_")
        return f"msi_repr:{dataset_text}:{candidate_text}"

    @staticmethod
    def _count_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
        counter = Counter()
        for row in rows:
            counter[str(row.get(key) or "unknown")] += 1
        return dict(sorted(counter.items()))


    def execute_test_seed(self) -> dict[str, Any]:
        """
        Execute constrained test-only MSI seed from the dry-run seed plan.

        Writes only MSI SQLite rows and only with test_content=true markers.
        Does not alter source registry, artifacts, or viewer load state.
        """
        from .repository import MSIRepository

        plan = self.test_seed_plan_preview(sample_limit=10_000)
        datasets = plan.get("datasets_to_seed") or []
        representations = plan.get("representations_to_seed") or []

        repo = MSIRepository()
        result = repo.upsert_test_seed_plan(datasets, representations)

        return {
            "adapter": "existing_source_registry",
            "mode": "test_seed_executed",
            "dry_run_counts": {
                "datasets_to_seed_count": plan.get("datasets_to_seed_count"),
                "representations_to_seed_count": plan.get("representations_to_seed_count"),
                "skipped_count": plan.get("skipped_count"),
            },
            **result,
            "test_seed_notice": (
                "Test seed executed. Rows are derived from temporary build/test content only. "
                "They are reversible using the purge-test-seed endpoint and must not be treated as definitive production MSI inventory."
            ),
        }

    def execute_test_seed_purge(self) -> dict[str, Any]:
        """
        Purge constrained MSI test-seed rows only.
        """
        from .repository import MSIRepository

        repo = MSIRepository()
        result = repo.purge_test_seed()

        return {
            "adapter": "existing_source_registry",
            "mode": "test_seed_purged",
            **result,
            "test_seed_notice": (
                "Only MSI rows marked as test content were purged. "
                "No source registry records, SEG-Y index folders, Zarr folders, or source files were deleted."
            ),
        }

    def _load_list(self, filename: str) -> list[Any]:
        path = self.registry_dir / filename
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    @staticmethod
    def _clean(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _dataset_type_from_candidate_kind(candidate_kind: str) -> str:
        normalized = candidate_kind.strip().lower()
        if normalized in {"2d_line", "line_candidate", "2d"}:
            return "2d_line"
        if normalized in {"3d_volume", "volume_candidate", "3d"}:
            return "3d_volume"
        return "unknown"
