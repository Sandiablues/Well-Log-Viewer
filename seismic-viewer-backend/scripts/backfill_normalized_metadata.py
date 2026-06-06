from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "seismic-viewer-backend"
VOLUMES_PATH = BACKEND / "data" / "volumes.json"

sys.path.insert(0, str(BACKEND))

from app.services.metadata_normalizer import normalize_volumes_payload  # noqa: E402


def main() -> None:
    if not VOLUMES_PATH.exists():
        raise SystemExit(f"Missing volumes file: {VOLUMES_PATH}")

    original_text = VOLUMES_PATH.read_text()
    payload = json.loads(original_text)

    normalized = normalize_volumes_payload(payload)

    backup_path = VOLUMES_PATH.with_suffix(".json.before_normalized_metadata")
    if not backup_path.exists():
        backup_path.write_text(original_text)

    VOLUMES_PATH.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n")

    print(f"Updated: {VOLUMES_PATH}")
    print(f"Backup:  {backup_path}")


if __name__ == "__main__":
    main()
