from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Any

from app.storage.service import is_endrepo_zarr_url, resolve_endrepo_zarr_url_path, storage_service


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = BACKEND_ROOT / "data"
ZARR_ROOT = DATA_ROOT / "zarr"
VOLUMES_JSON = DATA_ROOT / "volumes.json"

NORMALIZED_FILENAME = ".normalized_metadata.json"


class LocalMetadataRepository:
    """
    Local-file metadata repository.

    This is intentionally isolated from the enrichment logic so a future
    enterprise version can replace this with a database/object-store-backed
    repository without rewriting metadata normalization or frontend APIs.
    """

    def __init__(self, zarr_root: Path = ZARR_ROOT):
        self.zarr_root = zarr_root

    def resolve_volume_path(self, volume_id: str) -> Path:
        """
        Resolve a volume id to the local artifact path used by metadata evidence.

        Supports both legacy backend-local Zarr artifacts under data/zarr and
        MSI-managed EndRepo artifacts exposed through zarr_url/storage_uri. The
        resolver stays read-only and only returns paths that already exist.
        """
        clean_id = str(volume_id or "").strip()
        if not clean_id:
            raise FileNotFoundError("Could not resolve volume path for empty volume_id")

        candidates: list[Path] = [
            self.zarr_root / f"{clean_id}.zarr",
            self.zarr_root / clean_id,
        ]

        registry_record = self.load_volume_registry_record(clean_id)
        if isinstance(registry_record, dict):
            candidates.extend(self._registry_volume_path_candidates(registry_record))

        candidates.extend(self._endrepo_volume_path_candidates(clean_id))

        for candidate in candidates:
            try:
                if candidate.exists():
                    return candidate
            except Exception:
                continue

        for root in [self.zarr_root, self._endrepo_managed_zarr_root()]:
            if root and root.exists():
                matches = list(root.rglob(f"*{clean_id}*"))
                if matches:
                    zarr_matches = [m for m in matches if m.name.endswith(".zarr") and m.is_dir()]
                    if zarr_matches:
                        return sorted(zarr_matches, key=lambda p: str(p))[0]
                    return sorted(matches, key=lambda p: str(p))[0]

        raise FileNotFoundError(f"Could not resolve volume path for volume_id={clean_id}")

    def normalized_metadata_path(self, volume_id: str) -> Path:
        volume_path = self.resolve_volume_path(volume_id)
        return volume_path / NORMALIZED_FILENAME

    def save_normalized_metadata(self, volume_id: str, normalized: dict) -> None:
        path = self.normalized_metadata_path(volume_id)
        path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")

    def get_normalized_metadata(self, volume_id: str) -> Optional[dict]:
        path = self.normalized_metadata_path(volume_id)
        return self._safe_load_json(path)

    def load_volume_registry_record(self, volume_id: str) -> Optional[dict]:
        try:
            if not VOLUMES_JSON.exists():
                return None

            data = json.loads(VOLUMES_JSON.read_text(encoding="utf-8"))

            if isinstance(data, dict):
                if volume_id in data:
                    return data.get(volume_id)

                volumes = data.get("volumes")
                if isinstance(volumes, dict):
                    return volumes.get(volume_id)

                if isinstance(volumes, list):
                    for item in volumes:
                        if isinstance(item, dict) and item.get("id") == volume_id:
                            return item

                for value in data.values():
                    if isinstance(value, dict) and value.get("id") == volume_id:
                        return value

            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("id") == volume_id:
                        return item

        except Exception:
            return None

        return None

    def _registry_volume_path_candidates(self, record: dict) -> list[Path]:
        candidates: list[Path] = []

        def add_path(value: Any) -> None:
            text = str(value or "").strip()
            if not text:
                return

            try:
                if text.startswith("/endrepo/managed/zarr/") or is_endrepo_zarr_url(text):
                    candidates.append(resolve_endrepo_zarr_url_path(text))
                    return

                if text.startswith("endrepo://"):
                    resolved = storage_service().resolve_uri(text)
                    candidates.append(Path(resolved.local_path))
                    return

                if text.startswith("/data/zarr/"):
                    candidates.append(BACKEND_ROOT / text.lstrip("/"))
                    return

                if text.startswith("file://"):
                    candidates.append(Path(text.replace("file://", "", 1)).expanduser())
                    return

                if "://" not in text:
                    candidates.append(Path(text).expanduser())
            except Exception:
                return

        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        zarr_metadata = metadata.get("zarr") if isinstance(metadata.get("zarr"), dict) else {}
        source_reference = metadata.get("source_reference") if isinstance(metadata.get("source_reference"), dict) else {}

        for value in [
            record.get("zarr_path"),
            record.get("zarr_url"),
            record.get("storage_uri"),
            metadata.get("zarr_path"),
            metadata.get("zarr_url"),
            zarr_metadata.get("zarr_path"),
            zarr_metadata.get("zarr_url"),
            source_reference.get("zarr_path"),
            source_reference.get("zarr_url"),
            source_reference.get("storage_uri"),
        ]:
            add_path(value)

        return list(dict.fromkeys(candidates))

    def _endrepo_managed_zarr_root(self) -> Optional[Path]:
        try:
            return storage_service().repository_root / "managed" / "zarr"
        except Exception:
            return None

    def _endrepo_volume_path_candidates(self, volume_id: str) -> list[Path]:
        root = self._endrepo_managed_zarr_root()
        if root is None:
            return []

        clean_id = str(volume_id or "").strip()
        name = clean_id if clean_id.endswith(".zarr") else f"{clean_id}.zarr"

        return [
            root / "3d" / name,
            root / "2d" / name,
            root / name,
        ]

    def load_metadata_evidence(self, volume_id: str) -> tuple[Path, dict]:
        volume_path = self.resolve_volume_path(volume_id)

        viewer_metadata_path = self._find_file(
            volume_path,
            [".viewer_metadata.json", "viewer_metadata.json"],
        )
        trace_header_path = self._find_file(
            volume_path,
            [".trace_header_summary.json", "trace_header_summary.json"],
        )
        binary_header_path = self._find_file(
            volume_path,
            [".segy_binary_header.json", "segy_binary_header.json"],
        )
        text_header_path = self._find_file(
            volume_path,
            [".segy_text_header.txt", "segy_text_header.txt"],
        )
        conversion_metadata_path = self._find_file(
            volume_path,
            [
                ".conversion_metadata.json",
                "conversion_metadata.json",
                ".job_metadata.json",
                "job_metadata.json",
            ],
        )

        evidence = {
            "volume_id": volume_id,
            "volume_path": str(volume_path),
            "volume_registry": self.load_volume_registry_record(volume_id),
            "viewer_metadata": self._safe_load_json(viewer_metadata_path) if viewer_metadata_path else None,
            "trace_header_summary": self._safe_load_json(trace_header_path) if trace_header_path else None,
            "binary_header": self._safe_load_json(binary_header_path) if binary_header_path else None,
            "text_header": self._safe_load_text(text_header_path) if text_header_path else None,
            "conversion_metadata": self._safe_load_json(conversion_metadata_path) if conversion_metadata_path else None,
            "evidence_paths": {
                "viewer_metadata": str(viewer_metadata_path) if viewer_metadata_path else None,
                "trace_header_summary": str(trace_header_path) if trace_header_path else None,
                "binary_header": str(binary_header_path) if binary_header_path else None,
                "text_header": str(text_header_path) if text_header_path else None,
                "conversion_metadata": str(conversion_metadata_path) if conversion_metadata_path else None,
            },
        }

        return volume_path, evidence

    def _candidate_sidecar_dirs(self, volume_path: Path) -> list[Path]:
        dirs = [volume_path]

        if volume_path.parent not in dirs:
            dirs.append(volume_path.parent)

        sidecar_dir = volume_path / "sidecars"
        if sidecar_dir.exists():
            dirs.append(sidecar_dir)

        return dirs

    def _find_file(self, volume_path: Path, names: list[str]) -> Optional[Path]:
        """
        Supports current sidecar naming styles:

        1. Inside volume folder:
           .viewer_metadata.json
           viewer_metadata.json

        2. Sibling sidecars using UUID stem:
           {uuid}.viewer_metadata.json

        3. Sibling sidecars using full zarr folder name:
           {uuid}.zarr.viewer_metadata.json
        """
        volume_name = volume_path.name
        volume_stem = volume_path.stem if volume_path.suffix == ".zarr" else volume_path.name

        expanded_names: list[str] = []

        for name in names:
            clean_name = name[1:] if name.startswith(".") else name

            expanded_names.extend(
                [
                    name,
                    clean_name,
                    f"{volume_stem}.{clean_name}",
                    f"{volume_name}.{clean_name}",
                ]
            )

        expanded_names = list(dict.fromkeys(expanded_names))

        for directory in self._candidate_sidecar_dirs(volume_path):
            for name in expanded_names:
                candidate = directory / name
                if candidate.exists():
                    return candidate

        if volume_path.exists() and volume_path.is_dir():
            for name in expanded_names:
                matches = list(volume_path.rglob(name))
                if matches:
                    return matches[0]

        return None

    def _safe_load_json(self, path: Optional[Path]) -> Optional[dict]:
        try:
            if path and path.exists() and path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return None

    def _safe_load_text(self, path: Optional[Path]) -> Optional[str]:
        try:
            if path and path.exists() and path.is_file():
                return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None
        return None


default_metadata_repository = LocalMetadataRepository()


def load_metadata_evidence(volume_id: str) -> tuple[Path, dict]:
    return default_metadata_repository.load_metadata_evidence(volume_id)


def save_normalized_metadata(volume_id: str, normalized: dict) -> None:
    default_metadata_repository.save_normalized_metadata(volume_id, normalized)


def get_normalized_metadata(volume_id: str) -> Optional[dict]:
    return default_metadata_repository.get_normalized_metadata(volume_id)


def normalized_metadata_path(volume_id: str) -> Path:
    return default_metadata_repository.normalized_metadata_path(volume_id)


def resolve_volume_path(volume_id: str) -> Path:
    return default_metadata_repository.resolve_volume_path(volume_id)
