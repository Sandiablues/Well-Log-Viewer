from __future__ import annotations

import json
from pathlib import Path
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "seismic-viewer-backend" / "data" / "volumes.json"


def main() -> None:
    payload = json.loads(REGISTRY.read_text())

    if not isinstance(payload, dict):
        raise SystemExit("Expected ID-keyed volumes.json registry.")

    headers_by_filename = {}

    for _, volume in payload.items():
        if not isinstance(volume, dict):
            continue

        filename = volume.get("filename")
        metadata = volume.get("metadata") or {}
        normalized = metadata.get("normalized") or {}
        segy = normalized.get("segy_info") or {}
        header = metadata.get("decoded_text_header") or segy.get("text_header")

        if filename and header:
            headers_by_filename[filename] = {
                "decoded_text_header": header,
                "decoded_text_header_encoding": metadata.get("decoded_text_header_encoding") or segy.get("text_header_encoding"),
                "segy_info": deepcopy(segy),
            }

    updated = 0

    for key, volume in payload.items():
        if not isinstance(volume, dict):
            continue

        filename = volume.get("filename")
        if not filename or filename not in headers_by_filename:
            continue

        metadata = volume.setdefault("metadata", {})
        source = headers_by_filename[filename]

        if not metadata.get("decoded_text_header"):
            metadata["decoded_text_header"] = source["decoded_text_header"]
            metadata["decoded_text_header_encoding"] = source["decoded_text_header_encoding"] or "unknown"

            normalized = metadata.setdefault("normalized", {})
            segy = normalized.setdefault("segy_info", {})

            for k, v in source["segy_info"].items():
                segy.setdefault(k, v)

            segy.setdefault("text_header", source["decoded_text_header"])
            segy.setdefault("text_header_encoding", source["decoded_text_header_encoding"] or "unknown")

            updated += 1
            print("Updated:", key, filename, volume.get("display_name"))

    REGISTRY.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print("Updated records:", updated)


if __name__ == "__main__":
    main()
