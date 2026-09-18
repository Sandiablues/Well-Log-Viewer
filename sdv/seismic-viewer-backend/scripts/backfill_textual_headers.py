from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "seismic-viewer-backend"
VOLUMES_PATH = BACKEND / "data" / "volumes.json"

sys.path.insert(0, str(BACKEND))

from app.services.segy_text_header import decode_segy_text_header  # noqa: E402


def _candidate_paths(volume: Dict[str, Any]) -> list[Path]:
    metadata = volume.get("metadata") or {}
    filename = volume.get("filename") or metadata.get("filename")

    raw_candidates = [
        volume.get("source_path"),
        volume.get("file_path"),
        volume.get("original_path"),
        metadata.get("source_path"),
        metadata.get("file_path"),
        metadata.get("original_path"),
        metadata.get("source_file"),
        metadata.get("source_segy"),
        metadata.get("segy_path"),
        metadata.get("upload_path"),
    ]

    candidates: list[Path] = []

    for item in raw_candidates:
        if item:
            p = Path(str(item)).expanduser()
            if not p.is_absolute():
                candidates.append(ROOT / p)
                candidates.append(BACKEND / p)
            else:
                candidates.append(p)

    if filename:
        likely_dirs = [
            BACKEND / "data" / "uploads",
            BACKEND / "data" / "segy",
            BACKEND / "data" / "test",
            BACKEND / "data",
            ROOT / "Test_Data",
        ]

        for d in likely_dirs:
            candidates.append(d / filename)

        # Last resort: bounded recursive search under backend/data and Test_Data.
        for search_root in [BACKEND / "data", ROOT / "Test_Data"]:
            if search_root.exists():
                try:
                    candidates.extend(search_root.rglob(filename))
                except Exception:
                    pass

    # Deduplicate while preserving order.
    seen = set()
    clean = []
    for p in candidates:
        key = str(p)
        if key not in seen:
            seen.add(key)
            clean.append(p)

    return clean


def _find_source_file(volume: Dict[str, Any]) -> Optional[Path]:
    for p in _candidate_paths(volume):
        if p.exists() and p.is_file() and p.stat().st_size >= 3600:
            return p
    return None


def _iter_volumes(payload: Any):
    if isinstance(payload, list):
        for i, volume in enumerate(payload):
            if isinstance(volume, dict):
                yield str(i), volume
        return

    if isinstance(payload, dict):
        if isinstance(payload.get("volumes"), list):
            for i, volume in enumerate(payload["volumes"]):
                if isinstance(volume, dict):
                    yield str(i), volume
            return

        if isinstance(payload.get("datasets"), list):
            for i, volume in enumerate(payload["datasets"]):
                if isinstance(volume, dict):
                    yield str(i), volume
            return

        for key, volume in payload.items():
            if isinstance(volume, dict):
                yield key, volume


def main() -> None:
    if not VOLUMES_PATH.exists():
        raise SystemExit(f"Missing registry: {VOLUMES_PATH}")

    original = VOLUMES_PATH.read_text()
    payload = json.loads(original)

    backup = VOLUMES_PATH.with_suffix(".json.before_text_header_backfill")
    if not backup.exists():
        backup.write_text(original)

    updated = 0
    missing = 0

    for key, volume in _iter_volumes(payload):
        source = _find_source_file(volume)

        if not source:
            missing += 1
            continue

        raw = source.read_bytes()[:3200]
        decoded, encoding, score = decode_segy_text_header(raw)

        metadata = volume.setdefault("metadata", {})
        normalized = metadata.setdefault("normalized", {})
        segy_info = normalized.setdefault("segy_info", {})

        segy_info["text_header"] = decoded
        segy_info["text_header_encoding"] = encoding
        segy_info["text_header_decode_score"] = round(score, 2)
        segy_info["text_header_source_file"] = str(source)

        # Also expose a simple direct field for UI/API fallback.
        metadata["decoded_text_header"] = decoded
        metadata["decoded_text_header_encoding"] = encoding

        updated += 1

    VOLUMES_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    print(f"Updated textual headers: {updated}")
    print(f"Missing source SEG-Y files: {missing}")
    print(f"Backup: {backup}")


if __name__ == "__main__":
    main()
