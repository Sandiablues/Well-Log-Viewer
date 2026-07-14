from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

_LOCK = threading.Lock()
_LOG_PATH = (
    Path(__file__).resolve().parents[2]
    / ".wlv_runtime"
    / "perf"
    / "wsi_mwd_promotion_performance.jsonl"
)

def now() -> float:
    return perf_counter()

def elapsed_ms(start: float) -> float:
    return round((perf_counter() - start) * 1000.0, 3)

def write_event(event: str, **payload: Any) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **payload,
    }
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, default=str)
    with _LOCK:
        with _LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

def log_path() -> Path:
    return _LOG_PATH
