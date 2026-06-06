#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.segy_index_service import SegyIndexService


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a fast SEG-Y index package.")
    parser.add_argument("segy_path", help="Path to SEG-Y / SGY file")
    parser.add_argument("--dataset-id", default=None, help="Optional fixed dataset id")
    args = parser.parse_args()

    started = time.time()
    summary = SegyIndexService.build_index(args.segy_path, dataset_id=args.dataset_id)
    elapsed = time.time() - started

    summary["index_elapsed_seconds"] = round(elapsed, 3)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
